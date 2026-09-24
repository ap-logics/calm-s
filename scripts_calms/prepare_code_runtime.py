"""Create a minimal Docker build context containing no keys, model traces or tasks."""
import hashlib
import shutil
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from calms.common import write_json

target = ROOT/'calms_data/code-runtime'
source = ROOT/'calms_data/external-sources/evalplus'
shutil.copytree(source/'evalplus',target/'evalplus/evalplus',dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(source/'LICENSE',target/'evalplus/LICENSE')
shutil.copy2(ROOT/'docker/evalplus_check.py',target/'evalplus_check.py')
shutil.copy2(ROOT/'docker/calms-evalplus.Dockerfile',target/'Dockerfile')
write_json(target/'context-manifest.json',{'files':{
    p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in target.rglob('*') if p.is_file() and p.name != 'context-manifest.json'},
    'status':'Prepared; image build and positive/negative verifier controls pending Docker availability.'})
print(target)
