"""Persist logs and outputs from successful AND failed remote verification jobs."""
import hashlib,json,os,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files=[]
for relative in ('calms_runs/remote-setup','calms_runs/remote-verification','calms_runs/code-20260923/verifier-controls'):
    files.extend(p for p in (ROOT/relative).rglob('*') if p.is_file())
with zipfile.ZipFile(ROOT/'verification-results.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(files):
        archive.write(p,p.relative_to(ROOT).as_posix())
result={'run_id':os.environ.get('GITHUB_RUN_ID'),'attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
        'commit':os.environ.get('GITHUB_SHA'),'job_status':os.environ.get('JOB_STATUS'),
        'mode':os.environ.get('MODE'),'model_api_calls':0,'files':len(files),
        'sha256':hashlib.sha256((ROOT/'verification-results.zip').read_bytes()).hexdigest()}
(ROOT/'verification-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
