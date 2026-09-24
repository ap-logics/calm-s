"""Validate and restore a hosted increment. Never read keys or make API calls."""
import argparse
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--take-over-ledger',action='store_true',help='Use only after stopping paid execution on the original machine')
    args=parser.parse_args();receipt=json.loads(args.receipt.read_text())
    assert hashlib.sha256(args.archive.read_bytes()).hexdigest()==receipt['sha256'],'Archive checksum mismatch'
    snapshots=[];restored=0
    with zipfile.ZipFile(args.archive) as z:
        manifest=json.loads(z.read('ARCHIVE_MANIFEST.json'))
        for item in manifest['files']:
            relative=PurePosixPath(item['path'])
            assert not relative.is_absolute() and '..' not in relative.parts
            raw=z.read(item['path']);assert hashlib.sha256(raw).hexdigest()==item['sha256']
            if relative.parts[0] not in ('calms_data','calms_runs'): continue
            target=ROOT.joinpath(*relative.parts)
            assert target.resolve().is_relative_to(ROOT.resolve())
            if target.exists() and target.read_bytes()!=raw:
                raise RuntimeError('Different existing artifact: '+str(relative)+'; restore into a clean checkout instead')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);restored+=1
            if target.name=='api_ledger_snapshot.sqlite': snapshots.append(target)
    if args.take_over_ledger:
        assert len(snapshots)==1,'Expected exactly one new ledger snapshot'
        destination=ROOT/'calms_runs/api_ledger.sqlite'
        with sqlite3.connect(snapshots[0]) as source,sqlite3.connect(destination) as target:
            target.execute('CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY,status TEXT,cost REAL,reservation REAL,response TEXT)')
            target.execute('BEGIN IMMEDIATE')
            for row in source.execute('SELECT * FROM calls'):
                old=target.execute('SELECT * FROM calls WHERE key=?',(row[0],)).fetchone()
                if old is not None and old!=row:
                    if old[1]!='pending' or row[1]!='done': raise RuntimeError('Conflicting ledger row; manual reconciliation required')
                    target.execute('UPDATE calls SET status=?,cost=?,reservation=?,response=? WHERE key=?',(*row[1:],row[0]))
                elif old is None: target.execute('INSERT INTO calls VALUES (?,?,?,?,?)',row)
            target.commit()
            pending=target.execute("SELECT count(*) FROM calls WHERE status='pending'").fetchone()[0]
            print('Ledger merged without resetting spend. Pending reservations requiring inspection:',pending)
    print('Verified and restored',restored,'data/run files. No API calls made.')

if __name__=='__main__':main()
