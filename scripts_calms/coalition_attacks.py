"""Development-fitted coalition affine deviations; conditional frozen-matrix study.

These are stylized worker-owner reports, not a faithful external market baseline.
They do not establish a multi-window equilibrium or identify private true beliefs.
"""
import itertools
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from calms.common import digest,jsonl,manifest,mean,write_csv,write_json,write_jsonl

BASE = ROOT/'calms_runs/expanded-20260923'
OUT = ROOT/'calms_runs/coalition-attacks-20260923'


def payoff(record,owners,slope,offset,mechanism,side):
    reports = [record['reports'][w % len(record['reports'])][w] for w in range(4)]
    for w in owners:
        reports[w] = min(1,max(0,slope*reports[w]+offset))
    utilities = [record['reward']*reports[w]-record['decision_costs'][w] for w in range(4)]
    chosen = max(range(4),key=lambda w:utilities[w])
    if utilities[chosen] <= 0:
        chosen = None
    selected = int(chosen in owners)
    scores = {w:mean(1-(reports[w]-rep[w]['outcome'])**2 for rep in record['outcomes']) for w in owners}
    score = mean(scores.values())
    # Score units are normalized coalition-average scores, not dollar transfers.
    if mechanism == 'coupled_winner':
        value = (scores[chosen]+.5+side) if selected else 0
    elif mechanism == 'coupled_audit':
        value = score+(.5+side)*selected
    else:
        value = score+side*selected
    principal = mean(record['reward']*rep[chosen]['outcome']-rep[chosen]['cost_usd'] for rep in record['outcomes']) if chosen is not None else 0
    return value,principal,selected


def main():
    dev,test = jsonl(BASE/'dev/matrix.jsonl'),jsonl(BASE/'test/matrix.jsonl')
    assert not {r['cluster_id'] for r in dev}&{r['cluster_id'] for r in test}
    candidates = list(itertools.product((0,.5,1,1.5,2),(-.4,-.3,-.2,-.1,0,.1,.2,.3,.4)))
    manifest(OUT,{'kind':'exploratory-coalition-affine-deviations','dev':digest(dev),'test':digest(test),
        'candidate_transforms':candidates,'script':digest(Path(__file__).read_text()),
        'scope':'Expected score exposure; worker-owner coalition fractions; one-shot fitted affine class. No true-belief or repeated-game claim.'})
    fits,rows,summaries = [],[],[]
    for size in (1,2):
        for owners in itertools.combinations(range(4),size):
            for mechanism,side in itertools.product(('coupled_winner','coupled_audit','separated_audit'),(0,.25,1,4)):
                slope,offset = max(candidates,key=lambda ab:(
                    mean(payoff(r,owners,*ab,mechanism,side)[0] for r in dev),-abs(ab[0]-1)-abs(ab[1])))
                identity = dict(owners=list(owners),fraction=size/4,mechanism=mechanism,side=side,slope=slope,offset=offset)
                fits.append(identity)
                gains,losses = [],[]
                for r in test:
                    baseline = payoff(r,owners,1,0,mechanism,side)
                    attack = payoff(r,owners,slope,offset,mechanism,side)
                    gains.append(attack[0]-baseline[0])
                    losses.append(attack[1]-baseline[1])
                    rows.append(dict(**identity,task_id=r['task_id'],baseline_payoff=baseline[0],attack_payoff=attack[0],
                        deviation_gain=gains[-1],principal_value_change=losses[-1],selection_change=attack[2]-baseline[2]))
                summaries.append(dict(**identity,heldout_gain=mean(gains),principal_value_change=mean(losses)))
    write_json(OUT/'development-fits.json',fits)
    write_jsonl(OUT/'heldout-traces.jsonl',rows)
    write_csv(OUT/'summary.csv',summaries)
    write_json(OUT/'complete.json',{'fits':len(fits),'heldout_comparisons':len(rows),'api_spend':0,
        'zero_manipulators':'Identity baseline included in every paired comparison.',
        'limitations':'Coalitions control diagonal worker-owner reports. Not actual LLM collusion or two-window reputation attacks. Gains relative to elicited reports may be calibration corrections.'})
    print(OUT)


if __name__ == '__main__':
    main()
