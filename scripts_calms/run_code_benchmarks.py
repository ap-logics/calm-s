"""Resumable coding collection with official EvalPlus in isolated runtimes.

Run --check-only after building the image. Paid collection requires --live.
Hosted Linux controls were validated on 2026-09-24.
"""
import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from calms.common import code_hash, digest, jsonl, manifest, mean, read_json, write_json, write_jsonl
from calms.providers import Client, estimated_cost, upper_cost, validate_config
from calms.live import forecasts, worker_prompt
from calms.data import unfence

DATA = ROOT/'calms_data/code-20260923'
OUT = ROOT/'calms_runs/code-20260923'


class TraceClient(Client):
    def call(self, model, prompt, identity):
        self.active_key = digest({'model':model,'prompt':prompt,'identity':identity})
        write_json(OUT/'api-traces'/f'{self.active_key}.request.json',
                   {'model':model,'prompt':prompt,'identity':identity,'request_sha256':self.active_key})
        result = super().call(model,prompt,identity)
        write_json(OUT/'api-traces'/f'{self.active_key}.parsed-response.json',result)
        return result

    def _request(self, model, prompt, key):
        body = Client._request(model,prompt,key)
        write_json(OUT/'api-traces'/f'{self.active_key}.raw-response.json',body)
        return body


def check(image, problem, solutions, directory):
    directory.mkdir(parents=True,exist_ok=True)
    dataset = 'humaneval' if problem['task_id'].startswith('HumanEval/') else 'mbpp'
    payload = {'dataset':dataset,'problem':problem,'solutions':solutions}
    write_json(directory/'input.json',payload)
    name = 'calms-evalplus-'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='calms-evalplus-') as temp:
        Path(temp,'input.json').write_text(json.dumps(payload),encoding='utf-8')
        command = ['docker','run','--rm','--name',name,'--network','none','--read-only',
            '--memory','2g','--cpus','2','--pids-limit','128','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--user','65534:65534',
            '--tmpfs','/tmp:rw,size=256m','--shm-size','128m',
            '--mount',f'type=bind,source={temp},target=/input,readonly',image,'/input/input.json']
        try:
            with (directory/'stdout.txt').open('wb') as stdout, (directory/'stderr.txt').open('wb') as stderr:
                completed = subprocess.run(command,stdout=stdout,stderr=stderr,timeout=1200)
            if completed.returncode:
                raise RuntimeError('EvalPlus container failed; retained outputs require inspection. No outcome imputed.')
            lines = (directory/'stdout.txt').read_text(encoding='utf-8').splitlines()
            result = json.loads(lines[-1])
            assert result['task_id'] == problem['task_id'] and len(result['results']) == len(solutions)
            write_json(directory/'result.json',result)
            return result['results']
        finally:
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)


def public(problem, family):
    return {'task_id':problem['task_id'],'family':family,'node_id':'code',
        'instruction':'Return a complete Python solution, including the function definition and required imports.\n'+problem['prompt'],
        'upstream_outputs':{}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split',choices=['dev','test'],default='dev')
    parser.add_argument('--image',default='calms-evalplus:20260923')
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--max-usd',type=float,default=95)
    parser.add_argument('--backend',choices=['docker','actions','hosted'],default='docker')
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--parallel',type=int,default=4)
    args = parser.parse_args()
    if args.backend=='hosted' and not args.live:
        raise SystemExit('Hosted verification itself costs money; requires --live even with --check-only.')
    if args.backend=='docker' and not shutil.which('docker'):
        raise SystemExit('Docker unavailable; no keys read and no paid calls made.')
    if not 0 < args.max_usd <= 95:
        raise SystemExit('Cumulative API cap must be at most $95; $5 is reserved for remote compute.')
    if not 1<=args.parallel<=4:
        raise SystemExit('Parallel independent tasks must be between one and four.')
    if not args.check_only and not args.live:
        raise SystemExit('Paid collection requires --live; no keys read.')
    remote=None
    if args.backend=='actions':
        sys.path.insert(0,str(ROOT/'scripts_handoff'))
        from remote_verifier import RemoteVerifier
        remote=RemoteVerifier(OUT/'remote-batches')
        image='github-actions@'+remote.revision
    elif args.backend=='hosted':
        from hosted_verifier import HostedVerifier
        remote=HostedVerifier(ROOT/'calms_runs/hosted-evalplus-controls-20260924',root=ROOT,
                              env_file=args.env_file,max_usd=args.max_usd)
        image='openai-hosted-linux@'+remote.revision
    else:
        image = subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',args.image],text=True).strip()
    # Known correct and wrong solutions must pass/fail for BOTH benchmark families.
    problems,controls = [],[]
    for family in ('HumanEvalPlus','MbppPlus'):
        dev = jsonl(DATA/f'{family}-dev-private.jsonl')
        problem = dev[0]
        solutions=[problem['prompt']+problem['canonical_solution'],'raise RuntimeError("negative control")']
        controls.append({'problem':problem,'solutions':solutions})
        result = None if remote else check(image,problem,solutions,OUT/'verifier-controls'/family)
        if result is not None and [r['outcome'] for r in result] != [1,0]:
            raise SystemExit('Verifier controls failed; no paid calls made.')
        problems += [(family,p) for p in jsonl(DATA/f'{family}-{args.split}-private.jsonl')]
    if remote:
        control_results=remote.verify(controls)
        if any([r['outcome'] for r in result]!=[1,0] for result in control_results):
            raise SystemExit('Remote verifier controls failed; no paid calls made.')
    if args.check_only:
        print('Both official benchmark verifier controls passed. Hosted checks, if requested, are budgeted API calls.')
        return
    if args.split == 'test':
        config = read_json(OUT/'development-fitted-config.json')
    else:
        config = read_json(ROOT/'calms_configs/pilot.json')
        for worker in config['workers']:
            worker['description'] = 'Python coding worker; no measured coding accuracy supplied yet.'
    validate_config(config)
    directory = OUT/args.split
    current_spec = {'schema':1,'code_sha256':code_hash(),'kind':'official-evalplus-full-matrix','config':config,'image_id':image,
        'tasks_sha256':digest(problems),'repeats':2,'split':args.split,
        'runner_sha256':digest(Path(__file__).read_text()),
        'dataset_manifest':read_json(DATA/'dataset-manifest.json')}
    if (directory/'manifest.json').exists():
        spec=read_json(directory/'manifest.json')
        # Transport-only repairs may reuse paid responses. Preserve their original
        # request namespace; reject changes to models, prompts' core, data or repeats.
        for key in current_spec:
            if key not in ('image_id','runner_sha256') and current_spec[key]!=spec[key]:
                raise ValueError('Collection protocol changed: '+key)
        write_json(directory/'transport-revisions'/f'{digest(current_spec)}.json',
                   {'original_manifest_sha256':digest(spec),'current_execution':current_spec,
                    'reason':'Hosted artifact completion polling; worker/forecaster requests unchanged'})
    else:
        spec=manifest(directory,current_spec)
    namespace = digest(spec)
    client = TraceClient(ROOT/'calms_runs/api_ledger.sqlite',args.max_usd,args.env_file,live=True)
    records = []
    def collect_one(pair):
        family,problem=pair
        task_id=problem['task_id']
        task=public(problem,family)
        own=TraceClient(ROOT/'calms_runs/api_ledger.sqlite',args.max_usd,args.env_file,live=True)
        try:
            reports,forecast_records=forecasts(own,config,task,[],[namespace,task_id])
            write_json(directory/'forecasts'/f'{digest(task_id)}.json',{'reports':reports,'records':forecast_records,'public':task})
            responses=[]
            for repeat in range(2):
                for worker in config['workers']:
                    response=own.call(worker,worker_prompt(task),[namespace,task_id,'worker',worker['id'],repeat])
                    responses.append({**response,'worker_id':worker['id']})
            write_json(directory/'unverified'/f'{digest(task_id)}.json',responses)
            print(json.dumps({'collected':task_id,'cumulative_spend':own.total()}),flush=True)
            return family,problem,task,reports,forecast_records,responses
        finally:
            own.close()
    try:
        missing=[]
        for family,problem in problems:
            task_id = problem['task_id']
            target = directory/'tasks'/f'{digest(task_id)}.json'
            if target.exists():
                records.append(read_json(target))
                continue
            missing.append((family,problem))
        for offset in range(0,len(missing),20):
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                collected=list(pool.map(collect_one,missing[offset:offset+20]))
            batch=[{'problem':item[1],'solutions':[unfence(r['text']) if r['complete'] else 'raise RuntimeError("incomplete")' for r in item[5]]} for item in collected]
            verified=remote.verify(batch) if remote else [check(image,item['problem'],item['solutions'],directory/'verification'/digest(item['problem']['task_id'])) for item in batch]
            for item,checks in zip(collected,verified):
                family,problem,task,reports,forecast_records,responses=item
                task_id=problem['task_id']
                outcomes=[{**response,'outcome':result['outcome']} for response,result in zip(responses,checks)]
                record={'task_id':task_id,'cluster_id':task_id,'family':family,'split':args.split,'reward':.25,
                    'reports':reports,'forecast_records':forecast_records,'outcomes':[outcomes[:4],outcomes[4:]],
                    'cost_offers':[upper_cost(w,worker_prompt(task)) for w in config['workers']],
                    'decision_costs':[estimated_cost(w,worker_prompt(task)) for w in config['workers']]}
                write_json(directory/'tasks'/f'{digest(task_id)}.json',record)
                records.append(record)
            write_json(directory/'progress.json',{'tasks':len(records),'target':len(problems),'cumulative_spend':client.total()})
        by_id={r['task_id']:r for r in records}
        records=[by_id[p['task_id']] for _,p in problems]
        write_jsonl(directory/'matrix.jsonl',records)
        if args.split == 'dev':
            fitted = copy.deepcopy(config)
            for j,worker in enumerate(fitted['workers']):
                observations = [rep[j] for r in records for rep in r['outcomes']]
                worker['description'] = f"Coding development accuracy: {mean(o['outcome'] for o in observations):.3f} across 80 tasks with two decodes each."
                ratios = []
                for (family,p),r in zip(problems,records):
                    size = len(worker_prompt(public(p,family)).encode())
                    ratios += [rep[j]['input_tokens']/size for rep in r['outcomes']]
                worker['cost_estimator'] = {'input_tokens_per_byte':mean(ratios),
                    'mean_output_tokens':mean(o['output_tokens'] for o in observations)}
            write_json(OUT/'development-fitted-config.json',fitted)
        write_json(directory/'complete.json',{'tasks':len(records),'cumulative_spend':client.total()})
    finally:
        client.close()


if __name__ == '__main__':
    main()
