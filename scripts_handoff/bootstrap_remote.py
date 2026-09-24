"""Prepare/validate a persistent Linux workspace, without loading model API keys."""
import argparse
import json
import platform
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts_handoff'))
from restore_data import restore


def run(args,log):
    with log.open('ab') as output:
        output.write(('\nCOMMAND: '+' '.join(str(a) for a in args)+'\n').encode())
        output.flush()
        subprocess.run([str(a) for a in args],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true',help='Build and validate the isolated coding image')
    parser.add_argument('--appworld',action='store_true',help='Build the isolated AppWorld runtime and smoke test it')
    args=parser.parse_args()
    if platform.system()!='Linux':
        raise SystemExit('Run this inside the Codespace/Linux host, not on the Windows controller.')
    state=ROOT/'calms_runs/remote-setup'
    state.mkdir(parents=True,exist_ok=True)
    log=state/'bootstrap.log'
    marker=state/'data-restored.json'
    if not marker.exists():
        downloads=ROOT/'downloads'
        downloads.mkdir(exist_ok=True)
        archive=downloads/'CALM-S-experiments-20260923-extension.zip'
        if not archive.exists():
            run(['gh','release','download','handoff-2026-09-24','--repo','ap-logics/calm-s',
                 '--pattern',archive.name,'--dir',downloads],log)
        restore(archive)
        marker.write_text(json.dumps({'archive':archive.name,'restored':True}))
    ledger=ROOT/'calms_runs/api_ledger.sqlite'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('pragma integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Ledger integrity failure')
        total=db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]
        pending=db.execute("select count(*) from calls where status!='done'").fetchone()[0]
    if total < 16.0291502-1e-8:
        raise RuntimeError('Unexpected fresh ledger; do not start paid work')
    run([sys.executable,'-m','unittest','discover','-s','tests_calms','-v'],log)
    summary={'platform':platform.platform(),'python':sys.version,'api_spend':total,'pending_calls':pending,
             'model_api_calls_made':0,'coding_verifier_validated':False,'appworld_runtime_validated':False}
    if args.verify:
        # Recreate context from current versioned adapter, preserving official source.
        run([sys.executable,'scripts_calms/prepare_code_runtime.py'],log)
        run(['docker','build','-t','calms-evalplus:20260923','calms_data/code-runtime'],log)
        run([sys.executable,'scripts_calms/run_code_benchmarks.py','--check-only'],log)
        summary['coding_verifier_validated']=True
        summary['coding_image_id']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','calms-evalplus:20260923'],text=True).strip()
    if args.appworld:
        run([sys.executable,'scripts_handoff/prepare_appworld_runtime.py'],log)
        run(['docker','build','-t','calms-appworld:20260924','calms_data/appworld-runtime'],log)
        run(['docker','run','--rm','--network','none','--memory','4g','--cpus','2','--pids-limit','256',
             '--cap-drop','ALL','--security-opt','no-new-privileges','calms-appworld:20260924'],log)
        summary['appworld_runtime_validated']=True
        summary['appworld_image_id']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','calms-appworld:20260924'],text=True).strip()
    (state/'status.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
