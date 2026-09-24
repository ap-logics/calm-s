"""Offline environment setup, then start the persistent AppWorld service."""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
base=Path('/tmp/appworld')
os.environ['APPWORLD_ROOT']=str(base/'world')
os.environ['PYTHONPATH']=str(base/'src')
sys.path.insert(0,str(base/'src'))
try:
    with (base/'install.log').open('wb') as log:
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--find-links',str(base/'wheels'),
                        '-r',str(base/'requirements-linux.txt')],stdout=log,stderr=log,check=True)
    from appworld.install import install_package
    install_package()
    from appworld.common.crypto import unpack_bundle
    from appworld.common.constants import PASSWORD,SALT
    unpack_bundle(str(base/'data-0.2.0.bundle'),str(base/'world'),PASSWORD,SALT)
    with (base/'server.log').open('wb') as log:
        subprocess.Popen([sys.executable,str(base/'server.py')],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                         start_new_session=True,env=os.environ.copy())
except BaseException:
    Path('/mnt/data/server-ready.json').write_text(json.dumps({'ready':False,'error':traceback.format_exc()}))
print('SETUP SUBMITTED')
