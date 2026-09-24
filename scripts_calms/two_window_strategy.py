"""Exact finite-class two-window deviation search with known synthetic beliefs.

The first report affects audit-trained pooling weights in the second window.
The second report may depend on the observed first-window audit state. This is
a bounded best-response diagnostic, not a theorem about arbitrary LLM strategies.
"""
import argparse
import itertools
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import digest,manifest,write_csv,write_json,write_jsonl
from calms.mechanism import Pool,expected_score

GRID=[i/40 for i in range(41)]


def action(weight,q,p,competitor):
    prediction=[weight*q+(1-weight)*competitor,p[1]]
    utilities=[.25*prediction[w]-[.01,.02][w] for w in range(2)]
    chosen=max(range(2),key=lambda w:utilities[w])
    return chosen if utilities[chosen]>0 else None


def utility(weight,q,p,competitor,side,mechanism):
    chosen=action(weight,q,p,competitor)
    score=(expected_score(p[0],q)+expected_score(p[1],p[1]))/2
    if mechanism=='coupled_winner':
        score=score if chosen==0 else 0
    return score+side*(chosen==0)


def states(q,p,competitor,trigger,method):
    result=[]
    for worker,outcome in itertools.product(range(2),(0,1)):
        probability=trigger/2*(p[worker] if outcome else 1-p[worker])
        pool=Pool(2,2,method=method)
        pool.update('context',[[q,p[1]],[competitor,p[1]]],[(worker,outcome,trigger/2)],True)
        result.append({'probability':probability,'worker':worker,'outcome':outcome,
                       'next_weight':pool.weights('context')[0]})
    result.append({'probability':1-trigger,'worker':None,'outcome':None,'next_weight':.5})
    assert abs(sum(s['probability'] for s in result)-1)<1e-12
    return result


def evaluate(q,p,competitor,trigger,method,side,mechanism,adaptive):
    value=utility(.5,q,p,competitor,side,mechanism)
    branches=[]
    for state in states(q,p,competitor,trigger,method):
        weight=state['next_weight']
        q2=max(GRID,key=lambda x:(utility(weight,x,p,competitor,side,mechanism),-abs(x-p[0]))) if adaptive else p[0]
        value+=state['probability']*utility(weight,q2,p,competitor,side,mechanism)
        branches.append({**state,'second_report':q2,'second_selected':action(weight,q2,p,competitor)})
    return value,branches


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'calms_runs/two-window-20260924')
    args=parser.parse_args()
    manifest(args.output,{'kind':'exact-synthetic-two-window-finite-best-response','grid':GRID,
        'script':digest(Path(__file__).read_text()),'api_calls':0,
        'scope':'Two forecasters, two workers; one scalar report deviates. Independent Bernoulli outcomes with known stationary beliefs. Selection bonus is in score units, not dollars.'})
    summaries,traces=[],[]
    for p,competitor,trigger,method,side,mechanism in itertools.product(
        ([.4,.6],[.65,.7],[.8,.6]),(.2,.8),(.02,.2,1.),('equal','exponential','bayesian'),
        (0,.25,1.,4.),('separated_audit','coupled_winner')):
        baseline,_=evaluate(p[0],p,competitor,trigger,method,side,mechanism,False)
        candidates=[]
        for q in GRID:
            value,branches=evaluate(q,p,competitor,trigger,method,side,mechanism,True)
            candidates.append((value,q,branches))
        best,q,branches=max(candidates,key=lambda row:(row[0],-abs(row[1]-p[0])))
        row={'p0':p[0],'p1':p[1],'competitor':competitor,'trigger':trigger,'pooling':method,
             'side_interest':side,'mechanism':mechanism,'baseline':baseline,'best_payoff':best,
             'deviation_gain':best-baseline,'first_report':q}
        if mechanism=='separated_audit' and side==0:
            assert abs(best-baseline)<1e-12, 'Proper scoring without ownership must favor truth'
        assert best+1e-12>=baseline
        summaries.append(row)
        traces.append({**row,'best_second_window_policy':branches,
                       'candidate_payoffs':[{'q':x[1],'payoff':x[0]} for x in candidates]})
    write_csv(args.output/'summary.csv',summaries)
    write_jsonl(args.output/'strategy-traces.jsonl',traces)
    write_json(args.output/'complete.json',{'settings':len(summaries),'api_spend':0,
        'max_side_free_separated_gain':max(r['deviation_gain'] for r in summaries if r['mechanism']=='separated_audit' and r['side_interest']==0),
        'limitations':'Finite scalar unilateral class with known synthetic beliefs. Not a full-game equilibrium, actual LLM collusion, or a cash-transfer experiment.'})
    print(args.output)


if __name__=='__main__':
    main()
