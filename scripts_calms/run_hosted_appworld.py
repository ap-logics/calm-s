"""Task-level AppWorld agent matrix; all execution occurs in isolated hosted Linux."""
import argparse
import hashlib
import json
import shlex
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import canonical,digest,jsonl,read_json,write_json,write_jsonl
from calms.data import unfence
from calms.providers import Client,upper_cost
from calms.live import forecasts
from hosted_runtime import HostedRuntime

DATA=ROOT/'calms_data/appworld-hosted-20260924'
OUT=ROOT/'calms_runs/appworld-agents-20260924'
INSTRUCTIONS=('You are an agent in the AppWorld synthetic app benchmark. Solve the user task using the Python REPL. '
 'Return ONLY executable Python code. Variables persist between steps. Use print to see results. '
 'Discover apps with apis.api_docs.show_app_descriptions(), APIs with '
 'apis.api_docs.show_api_descriptions(app_name="..."), and signatures with '
 'apis.api_docs.show_api_doc(app_name="...", api_name="..."). '
 'Use supervisor APIs for benchmark credentials and to mark the task complete with the answer. '
 'Never inspect evaluator internals, ground truth, files, or task solutions. You have at most 8 execution turns.\n')

class TraceClient(Client):
    def call(self,model,prompt,identity):
        self.key=digest({'model':model,'prompt':prompt,'identity':identity})
        write_json(OUT/'api-traces'/f'{self.key}.request.json',{'model':model,'prompt':prompt,'identity':identity})
        response=super().call(model,prompt,identity)
        write_json(OUT/'api-traces'/f'{self.key}.parsed-response.json',response)
        return response
    def _request(self,model,prompt,key):
        response=super()._request(model,prompt,key)
        write_json(OUT/'api-traces'/f'{self.key}.raw-response.json',response)
        return response

def bundle():
    target=DATA/'agent-runtime.zip'
    if target.exists():
        with zipfile.ZipFile(target) as z:
            for name in ('server','client','setup'):
                if z.read(name+'.py')!=(ROOT/f'scripts_calms/appworld_hosted_{name}.py').read_bytes():
                    raise RuntimeError('Frozen AppWorld bundle differs from current service source; retain both versions explicitly')
        return target
    with zipfile.ZipFile(DATA/'runtime.zip') as original,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name in original.namelist():
            if name!='bootstrap.py': z.writestr(name,original.read(name))
        for name in ('server','client','setup'):
            z.write(ROOT/f'scripts_calms/appworld_hosted_{name}.py',name+'.py')
    return target

class Session:
    def __init__(self,directory,bundle_path):
        self.directory=directory;self.sequence=0
        self.runtime=HostedRuntime(ROOT,directory)
        path=self.runtime.upload(bundle_path);dataset=self.runtime.upload(DATA/'data-0.2.0.bundle')
        command='python -m zipfile -e '+shlex.quote(path)+' /tmp/appworld && cp '+shlex.quote(dataset)+' /tmp/appworld/data-0.2.0.bundle && python /tmp/appworld/setup.py'
        self.runtime.shell(command)
        raw=self.runtime.download('/mnt/data/server-ready.json',directory/'server-ready.json')
        ready=json.loads(raw)
        if not ready['ready']: raise RuntimeError('AppWorld server setup failed; see retained error')
    def rpc(self,operation,**kwargs):
        self.sequence+=1;identity=f'rpc-{self.sequence:04d}'
        payload={'operation':operation,'request_id':identity,**kwargs}
        path=self.directory/(identity+'-request.json');write_json(path,payload)
        remote=self.runtime.upload(path)
        native=self.runtime.shell('python /tmp/appworld/client.py '+shlex.quote(remote))
        if native['outcome'].get('exit_code')!=0: raise RuntimeError('AppWorld RPC submission failed')
        raw=self.runtime.download('/mnt/data/'+identity+'-reply.json',self.directory/(identity+'-reply.json'))
        response=json.loads(raw)
        if 'error' in response: raise RuntimeError('AppWorld operation failed; full error retained')
        if response.get('state_artifact'):
            self.runtime.download(response['state_artifact'],self.directory/(identity+'-state.zip'))
        return response
    def close(self): self.runtime.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true')
    parser.add_argument('--smoke',action='store_true');parser.add_argument('--split',choices=['dev','test'],default='dev')
    parser.add_argument('--task-id')
    parser.add_argument('--session-suffix',default='',help='Explicit fresh transport attempt; original traces remain untouched')
    args=parser.parse_args()
    if not args.live: raise SystemExit('No API calls; hosted agent runs require --live')
    runtime_bundle=bundle()
    config=read_json(ROOT/'calms_configs/pilot.json')
    for w in config['workers']: w['description']='AppWorld Python-REPL agent, at most 8 code-and-observation turns, 2048 output tokens per turn.'
    known=read_json(ROOT/'calms_runs/appworld-hosted-smoke-20260924-04/smoke-result.json')
    ids=sorted([t for t in known['train_ids' if args.split=='dev' else 'dev_ids'] if t.endswith('_1')],key=digest)
    ids=ids[:8] if args.split=='dev' else ids
    protocol={'kind':'task-level AppWorld full-worker matrix','tasks':ids,'split':args.split,'workers':config['workers'],
              'forecasters':config['forecasters'],'repeats':2,'max_steps':8,'max_prompt_characters':24000,
              'official_split':'train' if args.split=='dev' else 'dev','evaluation':'official TestTracker.success',
              'limitation':'Task-level allocation of full REPL agents, not local step-success verifiers or a DAG-policy reproduction.',
              'runtime_bundle_sha256':hashlib.sha256(runtime_bundle.read_bytes()).hexdigest(),'prompt':INSTRUCTIONS}
    if args.smoke:
        session=Session(OUT/'server-controls',runtime_bundle)
        try:
            seen=[]
            for repeat in range(2):
                seen.append(session.rpc('init',task_id=ids[0],episode_id=f'control-{repeat}'))
                result=session.rpc('execute',code='print(1+1)');assert result['observation'].strip()=='2'
                evaluation=session.rpc('finish');assert evaluation['outcome']==0
            assert seen[0]==seen[1]
            write_json(OUT/'server-controls/validated.json',{'fresh_instances':2,'unsolved_controls_fail':True})
            print('Persistent AppWorld REPL, state export and negative evaluator controls passed.')
        finally: session.close()
        return
    if not (OUT/'server-controls/validated.json').exists(): raise RuntimeError('Run --smoke first')
    path=OUT/args.split/'protocol.json'
    if path.exists(): assert read_json(path)==protocol
    else: write_json(path,protocol)
    namespace=digest(protocol)
    client=TraceClient(ROOT/'calms_runs/api_ledger.sqlite',95,ROOT/'.env',live=True)
    records=[]
    try:
        if args.task_id and args.task_id not in ids: raise ValueError('Task not in frozen split')
        for task_id in ([args.task_id] if args.task_id else ids):
            target=OUT/args.split/'tasks'/(task_id+'.json')
            if target.exists(): records.append(read_json(target));continue
            taskdir=OUT/args.split/task_id
            observations=[];reports=None;forecast_records=None
            for repeat in range(2):
                completed=taskdir/f'repeat-{repeat}.json'
                if completed.exists():
                    saved=read_json(completed);observations.append(saved['outcomes'])
                    reports=saved['reports'];forecast_records=saved['forecast_records'];continue
                session=Session(taskdir/f'session-{repeat}{args.session_suffix}',runtime_bundle)
                outcomes=[]
                try:
                    for worker in config['workers']:
                        initial=session.rpc('init',task_id=task_id,episode_id=f'{args.split}-{task_id}-{worker["id"]}-{repeat}')
                        public={'task_id':task_id,'family':'AppWorld','node_id':'complete-task','instruction':INSTRUCTIONS+canonical(initial),'upstream_outputs':{}}
                        if reports is None:
                            reports,forecast_records=forecasts(client,config,public,[],[namespace,task_id])
                            write_json(taskdir/'forecasts.json',{'public':public,'reports':reports,'records':forecast_records})
                        history=[];responses=[]
                        for step in range(8):
                            context='\n'.join(history)
                            prompt=INSTRUCTIONS+'\nTASK:\n'+canonical(initial)+'\nPAST INTERACTIONS:\n'+context[-18000:]+f'\nTurn {step+1}/8. Return only Python code.'
                            assert len(prompt)<=24000
                            response=client.call(worker,prompt,[namespace,task_id,worker['id'],repeat,step])
                            responses.append(response)
                            if not response['complete']: break
                            code=unfence(response['text'])
                            output=session.rpc('execute',code=code)
                            history.append('CODE:\n'+code+'\nOBSERVATION:\n'+output['observation'][:8000])
                            if output['completed']: break
                        final=session.rpc('finish')
                        record={'worker_id':worker['id'],'outcome':final['outcome'],'cost_usd':sum(r['cost_usd'] for r in responses),
                                'complete':all(r['complete'] for r in responses),'steps':len(responses),'responses':responses,
                                'evaluation':final['evaluation']}
                        outcomes.append(record)
                        write_json(taskdir/f'{worker["id"]}-{repeat}.json',record)
                        print(json.dumps({'task':task_id,'worker':worker['id'],'repeat':repeat,'outcome':record['outcome'],
                                          'steps':len(responses),'cumulative_spend':client.total()}),flush=True)
                finally: session.close()
                observations.append(outcomes)
                write_json(completed,{'outcomes':outcomes,'reports':reports,'forecast_records':forecast_records})
            record={'task_id':task_id,'cluster_id':task_id.split('_')[0],'family':'AppWorld','split':args.split,
                    'reward':1.0,'reports':reports,'forecast_records':forecast_records,'outcomes':observations,
                    'cost_offers':[8*upper_cost(w,'x'*60000) for w in config['workers']]}
            write_json(target,record);records.append(record)
        available=[OUT/args.split/'tasks'/(t+'.json') for t in ids]
        if all(p.exists() for p in available):
            records=[read_json(p) for p in available]
            write_jsonl(OUT/args.split/'matrix.jsonl',records)
            write_json(OUT/args.split/'complete.json',{'tasks':len(records),'cumulative_spend':client.total()})
    finally: client.close()

if __name__=='__main__': main()
