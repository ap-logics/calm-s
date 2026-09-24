"""Offline EvalPlus bundles verified in OpenAI hosted Linux; never execute locally."""
import ast
import hashlib
import json
import os
import shlex
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from calms.common import canonical, digest, load_env, write_json


class HostedVerifier:
    def __init__(self, output, root=ROOT, env_file=None, max_usd=95):
        self.root = Path(root)
        self.output = Path(output)
        self.env_file = env_file or self.root / '.env'
        self.max_usd = min(max_usd, 95)
        self.source = self.root / 'calms_data/external-sources/evalplus'
        self.adapter = self.root / 'docker/evalplus_check.py'
        self.revision = digest({'controller': Path(__file__).read_text(),
                                'adapter': self.adapter.read_text(),
                                'source': {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted((self.source/'evalplus').rglob('*.py'))}})

    def verify(self, tasks):
        identity = digest({'backend':'hosted-evalplus-v1','revision':self.revision,'tasks':tasks})
        directory = self.output / identity
        directory.mkdir(parents=True, exist_ok=True)
        result_path = directory / 'validated-result.json'
        if result_path.exists():
            return json.loads(result_path.read_text())['results']
        # Transport repairs must not force re-execution of already validated
        # results. Reuse only an identical batch with byte-identical official
        # verifier sources and adapter in the retained bundle.
        for prior in self.output.glob('*/validated-result.json'):
            batch=prior.parent/'batch.json'; prior_bundle=prior.parent/'bundle.zip'
            if not batch.exists() or not prior_bundle.exists(): continue
            if json.loads(batch.read_text()).get('tasks')!=tasks: continue
            with zipfile.ZipFile(prior_bundle) as old:
                source_match=all(old.read(p.relative_to(self.source).as_posix())==p.read_bytes()
                                 for p in (self.source/'evalplus').rglob('*.py'))
            if source_match:
                # The adapter is checked below after reproducing its AST helper.
                candidate_prior=prior
                break
        else:
            candidate_prior=None
        if not 1 <= len(tasks) <= 20:
            raise ValueError('One to twenty tasks per isolated batch')
        write_json(directory/'batch.json', {'tasks':tasks})
        # Extract the unchanged official helper without importing online dataset loaders.
        source = (self.source/'evalplus/data/mbpp.py').read_text()
        helper = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='mbpp_deserialize_inputs')
        adapter = self.adapter.read_text().replace('from evalplus.data.mbpp import mbpp_deserialize_inputs',
                                                    ast.get_source_segment(source, helper))
        if candidate_prior:
            with zipfile.ZipFile(candidate_prior.parent/'bundle.zip') as old:
                if old.read('check.py').decode()==adapter:
                    result=json.loads(candidate_prior.read_text())
                    write_json(result_path,{**result,'reused_from':str(candidate_prior),'source_and_adapter_identical':True})
                    return result['results']
        launcher = '''import hashlib,json,pathlib,subprocess,sys,zipfile,platform,traceback
base=pathlib.Path(__file__).parent
tasks=json.loads((base/'batch.json').read_text())['tasks']
results=[]
try:
    for i,task in enumerate(tasks):
        task['dataset']='humaneval' if task['problem']['task_id'].startswith('HumanEval/') else 'mbpp'
        inp=base/f'input-{i}.json'; inp.write_text(json.dumps(task))
        try:
            run=subprocess.run([sys.executable,str(base/'check.py'),str(inp)],capture_output=True,timeout=1200)
        except subprocess.TimeoutExpired as e:
            (base/f'stdout-{i}.txt').write_bytes(e.stdout or b'')
            (base/f'stderr-{i}.txt').write_bytes(e.stderr or b'')
            raise
        (base/f'stdout-{i}.txt').write_bytes(run.stdout)
        (base/f'stderr-{i}.txt').write_bytes(run.stderr)
        if run.returncode: raise RuntimeError(f'checker failed for task {i}')
        result=json.loads(run.stdout.decode().splitlines()[-1])
        assert result['task_id']==task['problem']['task_id']
        assert len(result['results'])==len(task['solutions'])
        results.append(result)
    (base/'result.json').write_text(json.dumps({'results':results,'python':sys.version,'platform':platform.platform()}))
except BaseException:
    (base/'error.txt').write_text(traceback.format_exc())
with zipfile.ZipFile('/mnt/data/calms-artifacts.partial','w',zipfile.ZIP_DEFLATED) as z:
    for p in base.glob('*.json'): z.write(p,p.name)
    for p in base.glob('*.txt'): z.write(p,p.name)
pathlib.Path('/mnt/data/calms-artifacts.partial').rename('/mnt/data/calms-artifacts.zip')
print('CALMS_ARTIFACT_SHA256='+hashlib.sha256(pathlib.Path('/mnt/data/calms-artifacts.zip').read_bytes()).hexdigest())
'''
        bundle = directory/'bundle.zip'
        with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted((self.source/'evalplus').rglob('*.py')):
                z.write(p,p.relative_to(self.source).as_posix())
            z.writestr('check.py',adapter)
            z.writestr('launch.py',launcher)
            z.write(directory/'batch.json','batch.json')
        db = sqlite3.connect(self.root/'calms_runs/api_ledger.sqlite',timeout=30)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('select 1 from calls where key=?',(identity,)).fetchone():
            db.rollback()
            raise RuntimeError('Existing hosted attempt requires inspection; refusing ambiguous paid retry')
        if db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]+.5 > self.max_usd:
            db.rollback()
            raise RuntimeError('Cumulative spending cap reached')
        db.execute("insert into calls values (?,'pending',.5,.5,NULL)",(identity,))
        db.commit()
        load_env(self.env_file)
        container = None
        def request(name, method, path, payload=None, upload=None, binary=False):
            headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']}
            if upload:
                boundary='calms'+uuid.uuid4().hex
                data=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="bundle.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()
                      +upload.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
                headers['Content-Type']='multipart/form-data; boundary='+boundary
            else:
                data=canonical(payload).encode() if payload is not None else None
                headers['Content-Type']='application/json'
            write_json(directory/f'{name}.request.json',{'method':method,'path':path,'body':payload,
                       'upload_sha256':hashlib.sha256(upload.read_bytes()).hexdigest() if upload else None})
            req=urllib.request.Request('https://api.openai.com/v1/'+path,data=data,headers=headers,method=method)
            try:
                with urllib.request.urlopen(req,timeout=1800) as response: raw=response.read()
            except urllib.error.HTTPError as error:
                (directory/f'{name}.error.json').write_bytes(error.read())
                raise RuntimeError(f'Hosted API HTTP {error.code}; details retained') from None
            (directory/f'{name}.response.{"bin" if binary else "json"}').write_bytes(raw)
            return raw if binary else json.loads(raw)
        try:
            container=request('container','POST','containers',{'name':'calms-evalplus','memory_limit':'4g',
                         'expires_after':{'anchor':'last_active_at','minutes':20}})
            prefix='containers/'+container['id']
            uploaded=request('upload','POST',prefix+'/files',upload=bundle)
            command='python -m zipfile -e '+shlex.quote(uploaded['path'])+' /mnt/data/calms && python /mnt/data/calms/launch.py'
            response=request('shell','POST','responses',{'model':'gpt-6-sol','store':False,
                'reasoning':{'effort':'low'},'max_output_tokens':2048,'tool_choice':'required',
                'tools':[{'type':'shell','environment':{'type':'container_reference','container_id':container['id']}}],
                'input':'Run exactly this one command once, with timeout_ms 1200000. Do not inspect or change files, do not retry failures, and do not generate answers. Stop after tool output.\n'+command})
            usage=response['usage']; cached=usage.get('input_tokens_details',{}).get('cached_tokens',0)
            cost=.12+((usage['input_tokens']-cached)*2+cached*.2+usage['output_tokens']*10)/1e6
            receipt={'cost_usd':cost,'infrastructure':True,'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],
                     'response_id':response['id'],'container_fee_conservative':.12}
            db.execute("update calls set status='done',cost=?,response=? where key=?",(cost,canonical(receipt),identity)); db.commit()
            calls=[item for item in response.get('output',[]) if item['type']=='shell_call']
            if len(calls)!=1 or calls[0]['action']['commands']!=[command]:
                raise RuntimeError('Hosted controller did not execute the exact authorized command')
            outputs=[o for item in response['output'] if item['type']=='shell_call_output' for o in item['output']]
            if len(outputs)!=1 or outputs[0]['outcome'].get('exit_code')!=0:
                raise RuntimeError('Native shell checker failed; no outcomes imputed')
            lines=outputs[0]['stdout'].splitlines()
            expected=next((x.split('=',1)[1] for x in lines if x.startswith('CALMS_ARTIFACT_SHA256=')),None)
            artifact=None
            for poll in range(180):
                if poll and poll % 6 == 0:
                    poll_key=digest({'hosted_batch':identity,'completion_poll':poll})
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]+.05>self.max_usd:
                        db.rollback(); raise RuntimeError('Completion polling budget exhausted')
                    db.execute("insert into calls values (?,'pending',.05,.05,NULL)",(poll_key,)); db.commit()
                    ping_command='python -c "from pathlib import Path; print(\'READY\' if Path(\'/mnt/data/calms-artifacts.zip\').exists() else \'WAIT\')"'
                    ping=request(f'completion-{poll}','POST','responses',{'model':'gpt-6-sol','store':False,
                        'reasoning':{'effort':'low'},'max_output_tokens':512,'tool_choice':'required',
                        'tools':[{'type':'shell','environment':{'type':'container_reference','container_id':container['id']}}],
                        'input':'Run exactly this single read-only command once and stop:\n'+ping_command})
                    pu=ping['usage']; pc=pu.get('input_tokens_details',{}).get('cached_tokens',0)
                    poll_cost=((pu['input_tokens']-pc)*2+pc*.2+pu['output_tokens']*10)/1e6
                    db.execute("update calls set status='done',cost=?,response=? where key=?",
                               (poll_cost,canonical({'cost_usd':poll_cost,'infrastructure':True,'response_id':ping['id']}),poll_key)); db.commit()
                    actual=[i for i in ping['output'] if i['type']=='shell_call']
                    if len(actual)!=1 or actual[0]['action']['commands']!=[ping_command]:
                        raise RuntimeError('Unexpected completion poll command')
                listing=request(f'files-{poll}','GET',prefix+'/files?limit=100')
                files=listing['data']
                page=0
                while listing.get('has_more'):
                    page+=1
                    listing=request(f'files-{poll}-page{page}','GET',prefix+'/files?limit=100&after='+listing['last_id'])
                    files+=listing['data']
                artifact=next((f for f in files if f['path']=='/mnt/data/calms-artifacts.zip'),None)
                if artifact: break
                time.sleep(5)
            if not artifact: raise RuntimeError('No completed artifact after 15 minutes; no outcomes imputed')
            raw=request('artifacts','GET',prefix+'/files/'+artifact['id']+'/content',binary=True)
            if expected and hashlib.sha256(raw).hexdigest()!=expected: raise RuntimeError('Artifact hash mismatch')
            write_json(directory/'download-receipt.json',{'sha256':hashlib.sha256(raw).hexdigest(),
                       'completion_evidence':'Atomic artifact rename after all checker subprocesses returned'})
            import io
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                result=json.loads(z.read('result.json'))
                for n in z.namelist():
                    if Path(n).name!=n: raise RuntimeError('Unsafe artifact member')
                    (directory/n).write_bytes(z.read(n))
            validated=[]
            if len(result['results'])!=len(tasks): raise RuntimeError('Task count mismatch')
            for t,r in zip(tasks,result['results']):
                assert t['problem']['task_id']==r['task_id'] and len(t['solutions'])==len(r['results'])
                validated.append(r['results'])
            write_json(result_path,{'identity':identity,'results':validated,'receipt':receipt})
            return validated
        finally:
            if container:
                try: request('cleanup','DELETE','containers/'+container['id'])
                except Exception as e: write_json(directory/'cleanup-error.json',{'type':type(e).__name__})
            db.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true'); args=parser.parse_args()
    if not args.live: raise SystemExit('Paid hosted verification requires --live')
    tasks=[]
    for family in ('HumanEvalPlus','MbppPlus'):
        p=json.loads((ROOT/f'calms_data/code-20260923/{family}-dev-private.jsonl').read_text().splitlines()[0])
        tasks.append({'problem':p,'solutions':[p['prompt']+p['canonical_solution'],'raise RuntimeError("negative control")']})
    results=HostedVerifier(ROOT/'calms_runs/hosted-evalplus-controls-20260924').verify(tasks)
    assert all([r['outcome'] for r in row]==[1,0] for row in results), results
    print('Hosted official EvalPlus positive/negative controls passed for both families.')
