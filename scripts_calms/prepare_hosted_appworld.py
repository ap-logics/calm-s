"""Build an offline AppWorld runtime bundle and validate it in hosted Linux."""
import argparse
import hashlib
import json
import shlex
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import write_json
from hosted_runtime import HostedRuntime

BOOTSTRAP=r'''import json,os,pathlib,subprocess,sys,traceback,zipfile,hashlib
base=pathlib.Path(__file__).parent
os.environ['APPWORLD_ROOT']=str(base/'world')
sys.path.insert(0,str(base/'src'))
ok=False
try:
    with (base/'install.log').open('wb') as log:
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--find-links',str(base/'wheels'),
                        '-r',str(base/'requirements-linux.txt')],stdout=log,stderr=log,check=True)
    from appworld.install import install_package
    install_package()
    from appworld.common.crypto import unpack_bundle
    from appworld.common.constants import PASSWORD,SALT
    unpack_bundle(str(base/'data-0.2.0.bundle'),str(base/'world'),PASSWORD,SALT)
    from appworld import AppWorld,load_task_ids
    ids=load_task_ids('train'); assert ids
    observations=[]
    for attempt in range(2):
        with AppWorld(task_id=ids[0],experiment_name=f'calms-hosted-smoke-{attempt}') as world:
            output=world.execute('print(1 + 1)')
            assert '2' in str(output)
            evaluation=world.evaluate()
            observations.append({'task_id':ids[0],'instruction':world.task.instruction,'output':str(output),
                                 'evaluation':str(evaluation)})
    assert observations[0]['instruction']==observations[1]['instruction']
    (base/'smoke-result.json').write_text(json.dumps({'lifecycle_passed':True,'instances':observations,
                  'train_ids':ids,'dev_ids':load_task_ids('dev'),'task_success_claimed':False}))
    ok=True
except BaseException:
    (base/'error.txt').write_text(traceback.format_exc())
finally:
    with zipfile.ZipFile('/mnt/data/appworld-smoke-artifacts.partial','w',zipfile.ZIP_DEFLATED) as z:
        for pattern in ('*.log','*.txt','*result.json'):
            for p in base.glob(pattern): z.write(p,p.name)
        for p in (base/'world/experiments').rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(base).as_posix())
    pathlib.Path('/mnt/data/appworld-smoke-artifacts.partial').rename('/mnt/data/appworld-smoke-artifacts.zip')
    print(json.dumps({'lifecycle_passed':ok,'artifact_sha256':hashlib.sha256(pathlib.Path('/mnt/data/appworld-smoke-artifacts.zip').read_bytes()).hexdigest()}))
'''


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true')
    parser.add_argument('--attempt',default='01'); args=parser.parse_args()
    data=ROOT/'calms_data/appworld-hosted-20260924'; source=ROOT/'calms_data/external-sources/appworld'
    bundle=data/'runtime.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted((source/'src').rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts: z.write(p,p.relative_to(source).as_posix())
        if not (source/'src/appworld/pyproject.toml').exists(): z.write(source/'pyproject.toml','src/appworld/pyproject.toml')
        for p in sorted((data/'wheels').glob('*.whl')): z.write(p,'wheels/'+p.name)
        z.write(data/'requirements-linux.txt','requirements-linux.txt')
        z.writestr('bootstrap.py',BOOTSTRAP)
    write_json(data/'runtime-manifest.json',{'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
               'bytes':bundle.stat().st_size,'source_commit':'42b5bcf3cd334fee33f0c37c02070a9f5807add5'})
    if not args.live:
        print('Offline bundle prepared; hosted validation requires --live'); return
    out=ROOT/f'calms_runs/appworld-hosted-smoke-20260924-{args.attempt}'
    runtime=HostedRuntime(ROOT,out)
    try:
        path=runtime.upload(bundle)
        dataset=runtime.upload(data/'data-0.2.0.bundle')
        command='python -m zipfile -e '+shlex.quote(path)+' /tmp/appworld && cp '+shlex.quote(dataset)+' /tmp/appworld/data-0.2.0.bundle && python /tmp/appworld/bootstrap.py'
        result=runtime.shell(command)
        raw=runtime.download('/mnt/data/appworld-smoke-artifacts.zip',out/'artifacts.zip')
        receipt={'artifact_sha256':hashlib.sha256(raw).hexdigest(),'lifecycle_passed':False}
        with zipfile.ZipFile(out/'artifacts.zip') as z:
            for name in ('smoke-result.json','error.txt','install.log'):
                if name in z.namelist(): (out/name).write_bytes(z.read(name))
            if 'smoke-result.json' in z.namelist(): receipt['lifecycle_passed']=json.loads(z.read('smoke-result.json'))['lifecycle_passed']
        write_json(out/'receipt.json',receipt)
        if not receipt['lifecycle_passed']: raise RuntimeError('AppWorld lifecycle failed; full logs saved')
        print(json.dumps(receipt))
    finally:
        runtime.close()


if __name__=='__main__': main()
