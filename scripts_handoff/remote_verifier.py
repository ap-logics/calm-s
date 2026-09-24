"""Windows controller for isolated GitHub Actions verification. No model keys sent."""
import hashlib
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

REPO='ap-logics/calm-s'


class RemoteVerifier:
    def __init__(self,output):
        self.output=Path(output)
        # Account-specific credential stays in memory; never printed or written.
        token=subprocess.check_output(['gh','auth','token','--hostname','github.com','--user','ap-logics'],text=True).strip()
        self.env={**os.environ,'GH_TOKEN':token}
        if self.gh(['api','user','--jq','.login']).strip()!='ap-logics':
            raise RuntimeError('Remote verification must use ap-logics')
        self.revision=self.gh(['api',f'repos/{REPO}/commits/main','--jq','.sha']).strip()

    def gh(self,args,check=True):
        result=subprocess.run(['gh',*args],env=self.env,text=True,capture_output=True,timeout=180)
        if check and result.returncode:
            raise RuntimeError('GitHub verifier operation failed: '+result.stderr[:1000])
        return result.stdout if check else result

    def verify(self,tasks):
        raw=json.dumps({'schema':1,'tasks':tasks},sort_keys=True,separators=(',',':')).encode()
        checksum=hashlib.sha256(raw).hexdigest()
        tag=f'calms-code-batch-{self.revision[:10]}-{checksum[:20]}'
        directory=self.output/tag
        directory.mkdir(parents=True,exist_ok=True)
        payload=directory/'batch.json'
        payload.write_bytes(raw)
        existing=self.gh(['release','view',tag,'--repo',REPO,'--json','assets'],check=False)
        if existing.returncode:
            if 'not found' not in existing.stderr.lower() and '404' not in existing.stderr:
                raise RuntimeError('Cannot inspect prior verification release; refusing ambiguous resubmission')
            self.gh(['release','create',tag,str(payload),'--repo',REPO,'--target',self.revision,
                     '--title',tag,'--notes','Data-only isolated coding verification batch. No model API credentials. Retain inputs and outputs.'])
        runs=json.loads(self.gh(['run','list','--repo',REPO,'--workflow','remote-verifier.yml',
                                '--limit','100','--json','databaseId,displayTitle,status,conclusion,url']))
        matched=[r for r in runs if r['displayTitle']==f'CALM-S code-batch {tag}']
        assets=json.loads(self.gh(['release','view',tag,'--repo',REPO,'--json','assets']))['assets']
        if not any(a['name']=='verification-receipt.json' for a in assets) and not matched:
            self.gh(['workflow','run','remote-verifier.yml','--repo',REPO,'--ref','main',
                     '-f','mode=code-batch','-f',f'batch_tag={tag}'])
        deadline=time.monotonic()+7200
        last=None
        while time.monotonic()<deadline:
            assets=json.loads(self.gh(['release','view',tag,'--repo',REPO,'--json','assets']))['assets']
            if any(a['name']=='verification-receipt.json' for a in assets):
                break
            runs=json.loads(self.gh(['run','list','--repo',REPO,'--workflow','remote-verifier.yml',
                                    '--limit','100','--json','databaseId,displayTitle,status,conclusion,url']))
            matched=[r for r in runs if r['displayTitle']==f'CALM-S code-batch {tag}']
            if matched:
                state=matched[0]
                if state['status']!=last:
                    print(json.dumps({'remote_batch':tag,**state}),flush=True)
                    last=state['status']
                if state['status']=='completed' and state['conclusion']!='success':
                    raise RuntimeError(f"Remote verifier failed: {state['url']}; local API outputs remain cached")
            time.sleep(15)
        else:
            raise TimeoutError('Remote verification is still pending; inputs and local model calls are retained')
        for name in ('verification-results.zip','verification-receipt.json'):
            if not (directory/name).exists():
                self.gh(['release','download',tag,'--repo',REPO,'--pattern',name,'--dir',str(directory)])
        receipt=json.loads((directory/'verification-receipt.json').read_text())
        archive=directory/'verification-results.zip'
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=receipt['sha256']:
            raise RuntimeError('Remote result checksum failed')
        if receipt['job_status']!='success' or receipt['commit']!=self.revision:
            raise RuntimeError('Remote verifier did not succeed at the expected source revision')
        with zipfile.ZipFile(archive) as z:
            result=json.loads(z.read('calms_runs/remote-verification/results.json'))
        if result['batch_sha256']!=checksum:
            raise RuntimeError('Remote results belong to a different batch')
        assert [r['task_id'] for r in result['results']]==[t['problem']['task_id'] for t in tasks]
        for task,item in zip(tasks,result['results']):
            assert len(task['solutions'])==len(item['results'])
            for check in item['results']:
                assert check['outcome']==int(all(check[x]['status']=='pass' for x in ('base','plus')))
        return [r['results'] for r in result['results']]
