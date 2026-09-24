"""Remote-only batch execution. No provider keys or model API calls."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts_calms'))
from run_code_benchmarks import check

payload=json.loads(Path(sys.argv[1]).read_text())
assert payload['schema']==1 and 1<=len(payload['tasks'])<=20
out=ROOT/'calms_runs/remote-verification'
out.mkdir(parents=True,exist_ok=True)
results=[]
for item in payload['tasks']:
    identifier=hashlib.sha256(item['problem']['task_id'].encode()).hexdigest()
    assert 1<=len(item['solutions'])<=8
    verified=check('calms-evalplus:20260923',item['problem'],item['solutions'],out/identifier)
    results.append({'task_id':item['problem']['task_id'],'results':verified})
(out/'results.json').write_text(json.dumps({'schema':1,'batch_sha256':hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),'results':results},indent=2))
print(json.dumps({'tasks_verified':len(results),'model_api_calls':0}))
