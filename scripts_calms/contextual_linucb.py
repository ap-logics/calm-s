"""Cost-aware disjoint LinUCB adaptation with development-only tuning.

Algorithm reference: Li et al. (2010), https://arxiv.org/abs/1003.0146.
This is an implementation of the linear-bandit rule, not a RouteLLM reproduction.
"""
import argparse
import copy
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import digest,jsonl,mean,rng,write_csv,write_json,write_jsonl

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def mv(a,x): return [dot(row,x) for row in a]

class Linear:
    def __init__(self,d,regularization):
        self.inverse=[[float(i==j)/regularization for j in range(d)] for i in range(d)]
        self.b=[0.0]*d
    def update(self,x,y):
        v=mv(self.inverse,x);denominator=1+dot(x,v)
        self.inverse=[[a-v[i]*v[j]/denominator for j,a in enumerate(row)] for i,row in enumerate(self.inverse)]
        self.b=[b+y*z for b,z in zip(self.b,x)]
    def predict(self,x,alpha):
        variance=max(0,dot(x,mv(self.inverse,x)))
        return min(1,max(0,dot(x,mv(self.inverse,self.b))+alpha*math.sqrt(variance)))

def features(record):
    # All features are observable before worker execution. The cost offer is
    # a deterministic prompt-length reserve, never a realized token charge.
    hop=record['task_id'][0] if record['family']=='musique' else ''
    return [1,float(hop=='2'),float(hop=='3'),float(hop=='4'),
            float(record['family']=='HumanEvalPlus'),float(record['family']=='MbppPlus'),
            math.log1p(record['cost_offers'][0]*100)]

def fit(records,regularization):
    models=[Linear(7,regularization) for _ in range(4)]
    for record in records:
        x=features(record)
        for w in range(4):
            # One fractional target per task; two decodes are not two independent contexts.
            models[w].update(x,mean(rep[w]['outcome'] for rep in record['outcomes']))
    return models

def replay(records,prior,alpha,budget,seed):
    models=copy.deepcopy(prior);rows=[]
    for episode,record in enumerate(records):
        x=features(record); predictions=[m.predict(x,alpha) for m in models]
        costs=record.get('decision_costs',record['cost_offers'])
        feasible=[w for w in range(4) if record['cost_offers'][w]<=budget]
        selected=max(feasible,key=lambda w:(record['reward']*predictions[w]-costs[w],-w)) if feasible else None
        if selected is not None and record['reward']*predictions[selected]-costs[selected]<0: selected=None
        # Outcomes are first accessed after selecting an action.
        repetition=rng('production-repetition',seed,record['task_id']).randrange(len(record['outcomes']))
        outcome=record['outcomes'][repetition][selected] if selected is not None else None
        y=outcome['outcome'] if outcome else 0;cost=outcome['cost_usd'] if outcome else 0
        assert cost<=budget+1e-9
        rows.append({'policy':'linucb','seed':seed,'episode':episode,'task_id':record['task_id'],
                     'cluster_id':record['cluster_id'],'selected':selected,'outcome':y,'cost':cost,
                     'budget':budget,'forecast_cost':0,'audit_cost':0,'audit':None,'audit_rate':0,
                     'net_value':record['reward']*y-cost,'predictions':predictions})
        if selected is not None: models[selected].update(x,y)
    return rows

def run(directory,length):
    dev=jsonl(directory/'dev/matrix.jsonl');test=jsonl(directory/'test/matrix.jsonl')
    assert not {r['cluster_id'] for r in dev}&{r['cluster_id'] for r in test}
    ordered=sorted(dev,key=lambda r:digest(r['task_id']))
    training=ordered[::2];validation=ordered[1::2]
    tuning=[]
    for ridge in (1,10):
        for alpha in (0,.05,.2,.5,1):
            rows=replay(validation,fit(training,ridge),alpha,.2,0)
            tuning.append({'ridge':ridge,'alpha':alpha,'net_value':mean(r['net_value'] for r in rows)})
    selected=max(tuning,key=lambda r:(r['net_value'],-r['alpha'],-r['ridge']))
    output=directory/'analysis/linucb'
    write_csv(output/'development-tuning.csv',tuning)
    write_json(output/'selection.json',{'selected':selected,'fit_task_ids':[r['task_id'] for r in training],
              'validation_task_ids':[r['task_id'] for r in validation],'dev_sha256':digest(dev),
              'features':'Intercept, public QA hop count, coding benchmark family, log deterministic prompt-cost reserve',
              'feedback':'Only the chosen worker label after each action; no paid forecasting calls or audit labels',
              'status':'Exploratory secondary baseline; primary comparisons remain unchanged'})
    prior=fit(dev,selected['ridge'])
    ordered=sorted(test,key=lambda r:digest(r['task_id'])) if directory.name=='code-20260923' else test
    rows=[]
    for seed,start in enumerate(range(0,len(ordered),length)):
        rows+=replay(ordered[start:start+length],prior,selected['alpha'],.2,seed)
    write_jsonl(output/'episodes.jsonl',rows)
    write_json(output/'summary.json',{'tasks':len(test),'net_value':mean(r['net_value'] for r in rows),
                                    'success':mean(r['outcome'] for r in rows),'cost':mean(r['cost'] for r in rows)})
    print(directory.name,selected,mean(r['outcome'] for r in rows))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--study',choices=['qa','coding'],required=True);args=parser.parse_args()
    run(ROOT/'calms_runs'/('expanded-20260923' if args.study=='qa' else 'code-20260923'),15 if args.study=='qa' else 20)
