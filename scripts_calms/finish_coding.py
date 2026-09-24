"""Continue an active development run through the locked held-out evaluation."""
import argparse
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true')
    parser.add_argument('--env-file',type=Path,required=True);args=parser.parse_args()
    if not args.live: raise SystemExit('Requires --live to authorize held-out API calls')
    out=ROOT/'calms_runs/code-20260923';out.mkdir(exist_ok=True)
    deadline=time.monotonic()+7200
    while not (out/'dev/complete.json').exists():
        if time.monotonic()>deadline: raise RuntimeError('Development did not complete; no test calls started')
        time.sleep(10)
    commands=[['analyze_coding.py','--stage','lock'],
              ['run_code_benchmarks.py','--backend','hosted','--split','test','--live','--max-usd','95',
               '--parallel','4','--env-file',str(args.env_file.resolve())],
              ['analyze_coding.py','--stage','test']]
    for index,command in enumerate(commands):
        with (out/f'continuation-{index}.log').open('ab') as log:
            subprocess.run([sys.executable,str(ROOT/'scripts_calms'/command[0]),*command[1:]],
                           cwd=ROOT,stdout=log,stderr=log,check=True)
    print('Coding development, held-out collection and locked analysis complete.',flush=True)

if __name__=='__main__': main()
