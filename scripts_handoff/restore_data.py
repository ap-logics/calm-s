"""Verify the release archive and restore retained artifacts without paid calls."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def restore(archive, destination=ROOT):
    archive=Path(archive)
    destination=Path(destination).resolve()
    assets=json.loads((ROOT/'release-assets.json').read_text())['assets']
    expected=next(a for a in assets if a['name']=='CALM-S-experiments-20260923-extension.zip')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected['sha256']:
        raise ValueError('Archive checksum differs from the versioned handoff')
    with zipfile.ZipFile(archive) as z:
        files=json.loads(z.read('ARCHIVE_MANIFEST.json'))['files']
        selected=[]
        for record in files:
            relative=PurePosixPath(record['path'])
            if relative.is_absolute() or '..' in relative.parts or any(':' in p or '\\' in p for p in relative.parts):
                raise ValueError('Unsafe archive path')
            content=z.read(record['path'])
            if hashlib.sha256(content).hexdigest()!=record['sha256']:
                raise ValueError('Archived artifact hash mismatch')
            if relative.parts[0] not in ('calms_data','calms_runs'):
                continue
            target=destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('Destination escapes workspace')
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=record['sha256']:
                raise ValueError(f'Refusing to overwrite a changed artifact: {relative}')
            selected.append((record['path'],target))
        for name,target in selected:
            if not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as source,target.open('xb') as output:
                    shutil.copyfileobj(source,output)
    ledger=destination/'calms_runs/api_ledger.sqlite'
    snapshot=destination/'calms_runs/retained-traces/api_ledger_snapshot.sqlite'
    if not ledger.exists():
        with sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True) as source:
            with sqlite3.connect(ledger) as output:
                source.backup(output)
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        states=db.execute('select status,count(*),sum(cost) from calls group by status').fetchall()
        total=db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]
    if total+1e-8 < 16.0291502:
        raise ValueError('Existing ledger is below the handoff spending total; reconcile before paid work')
    print(json.dumps({'restored_files':len(selected),'ledger':states,'cumulative_cap_usd':99,
        'remaining_usd':max(0,99-total),'api_calls_made':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('--destination',type=Path,default=ROOT,help='Optional clean workspace for restore verification')
    args=parser.parse_args()
    restore(args.archive,args.destination)
