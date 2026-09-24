"""Trusted lifecycle smoke test only; no LLM, API keys, or solved-task claims."""
import json
from appworld import AppWorld, load_task_ids

ids=load_task_ids('train')
assert ids, 'Training tasks unavailable'
task_id=ids[0]
observations=[]
for attempt in range(2):
    with AppWorld(task_id=task_id,experiment_name=f'calms-lifecycle-smoke-{attempt}') as world:
        result=world.execute('print(1 + 1)')
        assert '2' in str(result)
        observations.append({'task_id':task_id,'instruction':world.task.instruction,'output':str(result)})
assert observations[0]['instruction']==observations[1]['instruction']
print(json.dumps({'appworld_lifecycle_smoke':True,'instances':observations,
                  'model_api_calls':0,'task_success_claimed':False}))
