"""Development-locked coding replay; explicit frozen-forecast interpretation."""
import argparse
import copy
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.analysis import analyze, fit_static, forecast_analysis
from calms.common import digest,jsonl,mean,read_json,rng,write_csv,write_json,write_jsonl
from calms.mechanism import POLICIES
from calms.offline import run_stream,validate_calibration

OUT=ROOT/'calms_runs/code-20260923'
REPORT=OUT/'analysis'
PROTOCOL={'schema':1,'primary_budget':.2,'reward':.25,'stream_length':20,
          'rates':[0,.005,.01,.02,.05,.1],'budgets':[.05,.1,.2,.5],
          'ordering':'sha256(task_id), pooled families','audit_selection':'best positive rate by development net value; lower rate breaks ties',
          'comparators':'best non-CALMS development arm and equal pooling',
          'intervals':'paired disjoint-stream percentile bootstrap, 5000 resamples; 97.5% intervals for two primary contrasts (Bonferroni)',
          'interpretation':'Frozen pre-outcome forecasts; adaptive replay of recorded worker decodes, not live policy-dependent forecasts. No actual transfers.',
          'hosting':'Infrastructure collection cost reported separately; routing utility includes model forecasts, chosen worker and audit. Reward is a declared conversion, not measured business value.'}

def streams(records,policy,rate,budget=.2):
    records=sorted(records,key=lambda r:digest(r['task_id']))
    rows=[]
    for seed,offset in enumerate(range(0,len(records),20)):
        rows+=run_stream(records[offset:offset+20],policy,seed,budget,rate)
    return rows

def summaries(rows):
    return {'net_value':mean(r['net_value'] for r in rows),'success':mean(r['outcome'] for r in rows),
            'cost':mean(r['cost'] for r in rows),'audits':sum(r['audit'] is not None for r in rows)}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',choices=['protocol','lock','test'],required=True)
    args=parser.parse_args()
    path=REPORT/'prospective-protocol.json'
    if path.exists(): assert read_json(path)==PROTOCOL
    else: write_json(path,PROTOCOL)
    if args.stage=='protocol': print('Coding analysis protocol frozen before held-out collection'); return
    dev=jsonl(OUT/'dev/matrix.jsonl'); assert len(dev)==80
    calibration=fit_static(OUT/'dev/matrix.jsonl',REPORT/'static.json')
    for r in dev: r['static']=calibration['static_probabilities'][r['family']]
    tuning=[]
    for policy in POLICIES:
        if policy in ('coupled','myopic'): continue
        for rate in PROTOCOL['rates'] if policy=='calms' else [0]:
            tuning.append({'policy':policy,'rate':rate,**summaries(streams(dev,policy,rate))})
    rate=max((r for r in tuning if r['policy']=='calms' and r['rate']>0),key=lambda r:(r['net_value'],-r['rate']))['rate']
    comparator=max((r for r in tuning if r['policy']!='calms'),key=lambda r:r['net_value'])['policy']
    lock={'rate':rate,'comparator':comparator,'development_sha256':digest(dev),'protocol_sha256':digest(PROTOCOL)}
    if (REPORT/'locked-selection.json').exists(): assert read_json(REPORT/'locked-selection.json')==lock
    else: write_json(REPORT/'locked-selection.json',lock)
    write_csv(REPORT/'development-selection.csv',tuning)
    if args.stage=='lock': print(lock); return
    test=jsonl(OUT/'test/matrix.jsonl'); assert len(test)==200
    validate_calibration(test,calibration)
    for r in test: r['static']=calibration['static_probabilities'][r['family']]
    rows=[]
    for policy in POLICIES: rows+=streams(test,policy,rate)
    write_jsonl(REPORT/'primary/episodes.jsonl',rows)
    summary=analyze(REPORT/'primary/episodes.jsonl',REPORT/'primary/report','seed',comparator,5000)
    analyze(REPORT/'primary/episodes.jsonl',REPORT/'equal-reference','seed','equal',5000)
    contrasts=[]
    for reference in dict.fromkeys([comparator,'equal']):
        differences=[]
        for seed in range(10):
            a=[r['net_value'] for r in rows if r['policy']=='calms' and r['seed']==seed]
            b=[r['net_value'] for r in rows if r['policy']==reference and r['seed']==seed]
            assert len(a)==len(b)==20
            differences.append(mean(a)-mean(b))
        random=rng('coding-primary-bootstrap',reference)
        draws=sorted(mean(random.choices(differences,k=10)) for _ in range(5000))
        contrasts.append({'policy':'calms','reference':reference,'difference':mean(differences),
                          'ci97_5_low':draws[int(.0125*4999)],'ci97_5_high':draws[int(.9875*4999)],'streams':10})
    write_csv(REPORT/'primary-adjusted-contrasts.csv',contrasts)
    frontier=[]
    for budget in PROTOCOL['budgets']:
        for policy in ('cheapest','premium','static','explore','equal','selected','calms'):
            for ar in PROTOCOL['rates'] if policy=='calms' else [0]:
                frontier.append({'budget':budget,'policy':policy,'rate':ar,**summaries(streams(test,policy,ar,budget))})
    write_csv(REPORT/'budget-audit-frontier.csv',frontier)
    workers=[]
    for family in ['all','HumanEvalPlus','MbppPlus']:
        subset=test if family=='all' else [r for r in test if r['family']==family]
        for w in range(4):
            observations=[rep[w] for r in subset for rep in r['outcomes']]
            workers.append({'family':family,'worker':observations[0]['worker_id'],'tasks':len(subset),
                            'accuracy':mean(v['outcome'] for v in observations),'cost':mean(v['cost_usd'] for v in observations),
                            'incomplete':sum(not v['complete'] for v in observations)})
    write_csv(REPORT/'worker-results.csv',workers)
    forecast_analysis(OUT/'test/matrix.jsonl',REPORT/'forecast')
    write_json(REPORT/'complete.json',{'lock':lock,'tasks':200,'paired_streams':10,'summary':summary})
    print(contrasts)

if __name__=='__main__': main()
