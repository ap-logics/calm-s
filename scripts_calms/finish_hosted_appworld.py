"""Finish the prepared task-level AppWorld study after development collection."""
import argparse
import copy
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import digest,jsonl,mean,read_json,write_csv,write_json,write_jsonl
from calms.analysis import fit_static,forecast_analysis,interval
from calms.offline import run_stream,validate_calibration

OUT=ROOT/'calms_runs/appworld-agents-20260924'
POLICIES=['cheapest','premium','static','explore','equal','selected','calms']
PROTOCOL={'scope':'Exploratory task-level AppWorld agent allocation','reward':1.0,'budget':2.5,
          'rates':[.005,.01,.02,.05,.1],'development_tasks':8,'held_out_tasks':19,
          'development_split':'official train, distinct templates, variant 1 only',
          'held_out_split':'official public dev, distinct templates, variant 1 only; NOT private test',
          'ordering':'sha256(task_id)','forecasts':'Frozen before execution; each worker runs at most 8 REPL turns',
          'inference':'One adaptive stream: policy comparisons descriptive only; worker accuracy intervals resample task templates, not decodes',
          'costs':'Model calls charged to routing; hosted verification and collection costs reported separately'}

def metrics(rows):
    return {'success':mean(r['outcome'] for r in rows),'net_value':mean(r['net_value'] for r in rows),
            'cost':mean(r['cost'] for r in rows),'audits':sum(r['audit'] is not None for r in rows),
            'budget_violations':sum(r['cost']>r['budget']+1e-9 for r in rows)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live: raise SystemExit('Requires --live for held-out model execution')
    report=OUT/'analysis'
    path=report/'prospective-protocol.json'
    if path.exists(): assert read_json(path)==PROTOCOL
    else: write_json(path,PROTOCOL)
    deadline=time.monotonic()+14400
    while not (OUT/'dev/complete.json').exists():
        if time.monotonic()>deadline: raise RuntimeError('Development incomplete; held-out collection not started')
        time.sleep(10)
    dev=sorted(jsonl(OUT/'dev/matrix.jsonl'),key=lambda r:digest(r['task_id']))
    calibration=fit_static(OUT/'dev/matrix.jsonl',report/'static.json')
    costs=[mean(rep[w]['cost_usd'] for r in dev for rep in r['outcomes']) for w in range(4)]
    for r in dev:
        r['static']=calibration['static_probabilities']['AppWorld'];r['decision_costs']=costs
    tuning=[{'rate':rate,**metrics(run_stream(dev,'calms',0,2.5,rate))} for rate in PROTOCOL['rates']]
    rate=max(tuning,key=lambda r:(r['net_value'],-r['rate']))['rate']
    lock={'rate':rate,'decision_costs':costs,'development_sha256':digest(dev),'protocol_sha256':digest(PROTOCOL)}
    if (report/'locked-selection.json').exists(): assert read_json(report/'locked-selection.json')==lock
    else: write_json(report/'locked-selection.json',lock)
    write_csv(report/'development-selection.csv',tuning)
    with (OUT/'held-out-collection.log').open('ab') as log:
        subprocess.run([sys.executable,str(ROOT/'scripts_calms/run_hosted_appworld.py'),'--live','--split','test'],
                       cwd=ROOT,stdout=log,stderr=log,check=True)
    test=sorted(jsonl(OUT/'test/matrix.jsonl'),key=lambda r:digest(r['task_id']))
    validate_calibration(test,calibration)
    for r in test:
        r['static']=calibration['static_probabilities']['AppWorld'];r['decision_costs']=costs
    episodes=[];summary=[]
    for policy in POLICIES:
        rows=run_stream(test,policy,0,2.5,rate)
        episodes+=rows;summary.append({'policy':policy,'tasks':len(test),**metrics(rows)})
    write_jsonl(report/'episodes.jsonl',episodes);write_csv(report/'descriptive-policy-results.csv',summary)
    workers=[]
    for w in range(4):
        taskmeans=[mean(rep[w]['outcome'] for rep in r['outcomes']) for r in test]
        lo,hi=interval(taskmeans)
        workers.append({'worker':test[0]['outcomes'][0][w]['worker_id'],'tasks':len(test),
                        'success':mean(taskmeans),'task_ci_low':lo,'task_ci_high':hi})
    write_csv(report/'worker-results.csv',workers)
    forecast_analysis(OUT/'test/matrix.jsonl',report/'forecast')
    write_json(report/'complete.json',{'tasks':len(test),'lock':lock,'descriptive_only':True})
    print('AppWorld task-level study completed; policy comparisons remain descriptive.',flush=True)

if __name__=='__main__': main()
