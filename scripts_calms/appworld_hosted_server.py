"""Trusted single-process AppWorld REPL service, runs only inside hosted Linux."""
import json
import os
import time
import traceback
import zipfile
from pathlib import Path
from appworld import AppWorld

BASE=Path('/tmp/appworld')
INBOX=BASE/'inbox';INBOX.mkdir(exist_ok=True)
world=None
Path('/mnt/data/server-ready.json').write_text(json.dumps({'ready':True}))
while True:
    pending=sorted(INBOX.glob('*.json'))
    if not pending:
        time.sleep(.1);continue
    for path in pending:
        request=json.loads(path.read_text()); path.rename(path.with_suffix('.consumed'))
        result={}
        try:
            op=request['operation']
            if op=='init':
                if world: world.close()
                world=AppWorld(task_id=request['task_id'],experiment_name=request['episode_id'])
                supervisor=world.task.supervisor
                result={'instruction':world.task.instruction,'supervisor':{k:getattr(supervisor,k) for k in
                        ['first_name','last_name','email','phone_number']}}
                world.save_state('initial')
            elif op=='execute':
                result={'observation':str(world.execute(request['code'])),'completed':world.task_completed()}
                world.save_logs()
            elif op=='finish':
                world.save()
                evaluation=world.evaluate()
                result={'outcome':int(evaluation.success),'evaluation':evaluation.to_dict()}
                world.close();world=None
                artifact=Path('/mnt/data')/(request['request_id']+'-state.zip')
                with zipfile.ZipFile(artifact.with_suffix('.partial'),'w',zipfile.ZIP_DEFLATED) as z:
                    for p in (BASE/'world/experiments').rglob('*'):
                        if p.is_file(): z.write(p,p.relative_to(BASE/'world').as_posix())
                    for name in ('install.log','server.log'):
                        if (BASE/name).exists(): z.write(BASE/name,name)
                artifact.with_suffix('.partial').rename(artifact)
                result['state_artifact']=str(artifact)
            elif op=='stop':
                if world: world.close()
                result={'stopped':True}
            else: raise ValueError('Unknown operation')
        except BaseException:
            result={'error':traceback.format_exc()}
        output=Path('/mnt/data')/(request['request_id']+'-reply.json')
        output.with_suffix('.partial').write_text(json.dumps(result))
        output.with_suffix('.partial').rename(output)
        if request['operation']=='stop': raise SystemExit(0)
