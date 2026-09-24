"""Retain new hosted runs as an incremental, secret-scanned handoff archive."""
import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import load_env,write_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wait-for-completion',action='store_true')
    parser.add_argument('--publish',action='store_true');parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    args=parser.parse_args()
    complete=[ROOT/'calms_runs'/name/'analysis/complete.json' for name in ['code-20260923','appworld-agents-20260924']]
    if args.wait_for_completion:
        deadline=time.monotonic()+86400
        while not all(p.exists() for p in complete):
            if time.monotonic()>deadline: raise RuntimeError('Studies incomplete after 24h; refusing final-completion archive')
            time.sleep(20)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'calms_runs/hosted-handoff'/stamp;out.mkdir(parents=True)
    ledger=out/'api_ledger_snapshot.sqlite'
    with sqlite3.connect(ROOT/'calms_runs/api_ledger.sqlite') as source,sqlite3.connect(ledger) as target:
        source.backup(target)
        accounting=list(target.execute('select status,count(*),sum(cost) from calls group by status'))
    load_env(args.env_file)
    secrets=[os.environ[k].encode() for k in ['OPENAI_API_KEY','ANTHROPIC_API_KEY'] if os.environ.get(k)]
    files=[]
    for directory in (ROOT/'calms_runs').iterdir():
        if directory.is_dir() and (directory.name.startswith(('hosted-','appworld-hosted-','two-window-'))
                                  or directory.name in ('code-20260923','appworld-agents-20260924')):
            if directory.name=='hosted-handoff': continue
            files += [p for p in directory.rglob('*') if p.is_file() and p.suffix!='.tmp']
    files += [p for p in (ROOT/'calms_runs/expanded-20260923/analysis/linucb').rglob('*') if p.is_file()]
    data=ROOT/'calms_data/appworld-hosted-20260924'
    # Wheels are already retained byte-for-byte inside runtime.zip and agent-runtime.zip.
    files += [p for p in data.iterdir() if p.is_file()]
    for directory in ('scripts_calms','scripts_handoff','tests_calms'):
        files += [p for p in (ROOT/directory).rglob('*.py') if '__pycache__' not in p.parts]
    files += [ROOT/'README.md',ROOT/'REMOTE_EXECUTION.md',ledger]
    archive=out/f'CALM-S-hosted-increment-{stamp}.zip'
    hashes=[];deferred=[]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(set(files)):
            raw=p.read_bytes()
            if any(secret in raw for secret in secrets): raise RuntimeError('Credential scan rejected artifact')
            if p.suffix=='.json':
                try: json.loads(raw)
                except (ValueError,UnicodeDecodeError):
                    deferred.append(str(p.relative_to(ROOT)));continue
            relative=p.relative_to(ROOT).as_posix()
            z.writestr(relative,raw)
            hashes.append({'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        status={'files':hashes,'accounting':accounting,'snapshot_utc':stamp,
                'new_studies_complete':all(p.exists() for p in complete),'in_progress_files_deferred':deferred,
                'base_archive':'CALM-S-experiments-20260923-extension.zip from handoff-2026-09-24',
                'scope':'Incremental new hosted evidence; combine with original cumulative archive. Raw wheels can be extracted from calms_data/appworld-hosted-20260924/runtime.zip.',
                'limitations':'Original simulator and full external market reproductions remain unresolved. See failed infrastructure attempt summaries for any unavailable internal logs.'}
        z.writestr('ARCHIVE_MANIFEST.json',json.dumps(status,indent=2))
    receipt={'archive':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
             'files':len(hashes),'accounting':accounting,'new_studies_complete':status['new_studies_complete'],
             'credential_scan':'passed','base_archive':status['base_archive']}
    write_json(out/'receipt.json',receipt)
    if args.publish:
        token=subprocess.check_output(['gh','auth','token','--hostname','github.com','--user','ap-logics'],text=True).strip()
        environment={**os.environ,'GH_TOKEN':token}
        assert subprocess.check_output(['gh','api','user','--jq','.login'],env=environment,text=True).strip()=='ap-logics'
        note=out/'release-notes.md'
        note.write_text('Incremental CALM-S hosted execution evidence. Combine with the September 23 extension archive. '+
                        ('Coding and task-level AppWorld analyses are complete.' if status['new_studies_complete'] else
                         'This is an in-progress snapshot; experiment collection continues. Do not claim the study is complete.')+
                        '\n\nThe ZIP includes checksums, a consistent ledger snapshot, raw new API traces, runtime sources, '+
                        'state exports, failures and available reports. No credentials.\n',encoding='utf-8')
        tag='hosted-evidence-'+stamp.lower()
        subprocess.run(['gh','release','create',tag,str(archive),str(out/'receipt.json'),'--repo','ap-logics/calm-s',
                        '--title','CALM-S hosted evidence '+stamp,'--notes-file',str(note)],env=environment,check=True)
    print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
