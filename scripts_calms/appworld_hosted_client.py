"""Submit one local RPC to the persistent hosted AppWorld process."""
import json
import sys
from pathlib import Path
request=json.loads(Path(sys.argv[1]).read_text())
target=Path('/tmp/appworld/inbox')/(request['request_id']+'.json')
reply=Path('/mnt/data')/(request['request_id']+'-reply.json')
if not target.with_suffix('.consumed').exists() and not reply.exists():
    target.with_suffix('.partial').write_text(json.dumps(request))
    target.with_suffix('.partial').rename(target)
print('SUBMITTED '+request['request_id'])
