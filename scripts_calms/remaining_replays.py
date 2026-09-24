"""Exploratory E2/E6/E7 extensions on retained real-model matrices; no API calls."""
import copy
import hashlib
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import jsonl, mean, rng, write_csv, write_json, write_jsonl, manifest, digest
from calms.offline import run_stream
from calms.mechanism import audit_design, draw_audit
from calms.analysis import interval

OUT = ROOT / 'calms_runs/remaining-replays-20260923'
BASE = ROOT / 'calms_runs/expanded-20260923'


def hop(r):
    return r['task_id'].split('hop')[0]


def priors(dev):
    groups = defaultdict(lambda: [[1., 1.] for _ in range(4)])
    for r in dev:
        for w in range(4):
            # Two decodes share a task: count their mean as one task observation.
            y = mean(rep[w]['outcome'] for rep in r['outcomes'])
            groups[hop(r)][w][0] += y
            groups[hop(r)][w][1] += 1-y
    return dict(groups)


def contextual(records, initial, epsilon, audit_rate=0):
    rows = []
    for stream, offset in enumerate(range(0, len(records), 15)):
        state = copy.deepcopy(initial)
        for episode, r in enumerate(records[offset:offset+15]):
            counts = state.setdefault(hop(r), [[1., 1.] for _ in range(4)])
            predictions = [a/(a+b) for a,b in counts]
            costs = r['cost_offers']
            design = audit_design(costs, audit_rate, .2)
            feasible = [w for w in range(4) if costs[w] <= .2-design['reserve']]
            random = rng('contextual', stream, r['task_id'])
            w = (random.choice(feasible) if random.random() < epsilon else
                 max(feasible, key=lambda j: .25*predictions[j]-r['decision_costs'][j])) if feasible else None
            aw = draw_audit(design, stream, r['task_id']) if w is not None else None
            rep = rng('production-repetition', stream, r['task_id']).randrange(2)
            arep = rng('audit-repetition', stream, r['task_id']).randrange(2)
            production = r['outcomes'][rep][w] if w is not None else None
            audit = r['outcomes'][arep][aw] if aw is not None else None
            y = production['outcome'] if production else 0
            cost = (production['cost_usd'] if production else 0)+(audit['cost_usd'] if audit else 0)
            rows.append(dict(seed=stream, episode=episode, task_id=r['task_id'], selected=w, audit=aw,
                predictions=predictions, outcome=y, cost=cost, net_value=.25*y-cost,
                budget=.2, forecast_cost=0, audit_cost=audit['cost_usd'] if audit else 0,
                full_brier=mean((predictions[j]-rep[j]['outcome'])**2 for rep in r['outcomes'] for j in range(4))))
            # Updates occur only after action selection; no unrevealed outcomes enter state.
            observations = [(w,y)] if w is not None else []
            if audit:
                observations.append((aw,audit['outcome']))
            for j,label in observations:
                counts[j][0] += label
                counts[j][1] += 1-label
    return rows


def summarize(name, rows):
    streams = defaultdict(list)
    for row in rows:
        streams[row['seed']].append(row['net_value'])
    lo, hi = interval([mean(v) for v in streams.values()])
    return dict(arm=name, tasks=len(rows), streams=len(streams), success=mean(r['outcome'] for r in rows),
        cost=mean(r['cost'] for r in rows), net_value=mean(r['net_value'] for r in rows),
        ci95_low=lo, ci95_high=hi, full_brier=mean(r['full_brier'] for r in rows),
        audits=sum(r['audit'] is not None for r in rows),
        budget_violations=sum(r['cost'] > r['budget']+1e-9 for r in rows))


def ablations(dev, test):
    summaries, traces = [], []
    tuning = []
    # Leave-one-stream-out development predictions avoid fitting on the tuning outcome.
    for epsilon in (0, .05, .1, .2, .4):
        rows = []
        for offset in range(0, len(dev), 15):
            rows += contextual(dev[offset:offset+15], priors(dev[:offset]+dev[offset+15:]), epsilon)
        tuning.append(dict(epsilon=epsilon, net_value=mean(r['net_value'] for r in rows)))
    epsilon = max(tuning, key=lambda x: (x['net_value'], -x['epsilon']))['epsilon']
    write_json(OUT/'contextual-development-selection.json', dict(tuning=tuning, epsilon=epsilon,
        scope='Exploratory extension after prior test results were seen; tuning uses development only.'))
    for rate in (0, .005, .02, .1):
        name = f'contextual-epsilon={epsilon}-audit={rate}'
        rows = contextual(test, priors(dev), epsilon, rate)
        summaries.append(summarize(name, rows))
        traces += [dict(arm=name, **r) for r in rows]
    variants = [('equal-same-audits','equal',True,1,None),
                ('exponential','exponential',True,1,None), ('bayesian','bayesian',True,1,None),
                ('stacking','stacking',True,1,None), ('no-ips','exponential',False,1,None),
                ('delay3','exponential',True,3,None)]
    variants += [(f'one-forecaster-{m}','exponential',True,1,m) for m in range(3)]
    for rate in (.005, .02, .1):
        for name, pooling, importance, delay, forecaster in variants:
            records = copy.deepcopy(test)
            if forecaster is not None:
                for r in records:
                    r['reports'] = [r['reports'][forecaster]]
                    r['forecast_records'] = [r['forecast_records'][forecaster]]
            rows = []
            for seed, offset in enumerate(range(0,len(records),15)):
                rows += run_stream(records[offset:offset+15], 'calms', seed, .2, rate,
                    pooling=pooling, importance=importance, delay=delay, distribution=[1,2,4,8])
            label = f'{name}-audit={rate}'
            summaries.append(summarize(label, rows))
            traces += [dict(arm=label, **r) for r in rows]
    write_csv(OUT/'routing-summary.csv', summaries)
    write_jsonl(OUT/'routing-traces.jsonl', traces)
    assert not any(r['budget_violations'] for r in summaries)
    return summaries


def propensity(test, trials=1000):
    """Exact conditional moments plus audit-only Monte Carlo; repetitions averaged."""
    summaries, simulations = [], []
    for distribution in ([1,1,1,1], [1,2,4,8]):
        for rate in (.005,.02,.1):
            designs = [audit_design(r['cost_offers'],rate,.2,distribution) for r in test]
            scores = [[[mean(1-(q[w]-rep[w]['outcome'])**2 for rep in r['outcomes'])
                        for w in range(4)] for q in r['reports']] for r in test]
            truth = [mean(mean(s[m]) for s in scores) for m in range(3)]
            draws = []
            for trial in range(trials):
                random = rng('propensity', distribution,rate,trial)
                draws.append([random.choices(range(5), weights=[1-d['trigger'],*d['pi']])[0]-1 for d in designs])
            for clip in (None,10,50,100):
                multipliers = [[min(1/pi,clip) if clip else 1/pi for pi in d['pi']] for d in designs]
                exact_mean, exact_variance = [], []
                for m in range(3):
                    means = [sum(d['pi'][w]*v[w]*s[m][w]/4 for w in range(4)) for d,v,s in zip(designs,multipliers,scores)]
                    second = [sum(d['pi'][w]*(v[w]*s[m][w]/4)**2 for w in range(4)) for d,v,s in zip(designs,multipliers,scores)]
                    exact_mean.append(mean(means))
                    exact_variance.append(sum(b-a*a for a,b in zip(means,second))/len(test)**2)
                estimates = []
                ess_values = []
                ranking = []
                for trial, selections in enumerate(draws):
                    estimate = [sum(multipliers[t][w]*scores[t][m][w]/4 for t,w in enumerate(selections) if w>=0)/len(test) for m in range(3)]
                    weights = [multipliers[t][w] for t,w in enumerate(selections) if w>=0]
                    ess = sum(weights)**2/sum(v*v for v in weights) if weights else 0
                    estimates.append(estimate)
                    ess_values.append(ess)
                    ranking.append(max(range(3),key=lambda m: estimate[m]) == max(range(3),key=lambda m:truth[m]))
                    simulations.append(dict(distribution=distribution,rate=rate,clip=clip,trial=trial,
                        estimates=estimate,truth=truth,ess=ess,audit_workers=selections))
                for m in range(3):
                    samples = sorted(e[m] for e in estimates)
                    summaries.append(dict(distribution=str(distribution),rate=rate,clip=clip,forecaster=m,
                        target=truth[m], exact_bias=exact_mean[m]-truth[m], exact_variance=exact_variance[m],
                        exact_rmse=math.sqrt(exact_variance[m]+(exact_mean[m]-truth[m])**2),
                        mc_bias=mean(samples)-truth[m], mc_rmse=math.sqrt(mean((v-truth[m])**2 for v in samples)),
                        p50=samples[trials//2],p95=samples[int(trials*.95)],p99=samples[int(trials*.99)],
                        mean_ess=mean(ess_values), max_weight=max(max(v) for v in multipliers),
                        top_forecaster_recovery=mean(ranking)))
                    if clip is None:
                        assert abs(exact_mean[m]-truth[m]) < 1e-12
    write_csv(OUT/'propensity-summary.csv', summaries)
    write_jsonl(OUT/'propensity-monte-carlo.jsonl', simulations)
    return summaries


def main():
    dev, test = jsonl(BASE/'dev/matrix.jsonl'), jsonl(BASE/'test/matrix.jsonl')
    assert not {r['cluster_id'] for r in dev} & {r['cluster_id'] for r in test}
    manifest(OUT,dict(kind='exploratory-retained-real-matrix-extensions',dev=digest(dev),test=digest(test),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Frozen reports/outcomes. Monte Carlo measures conditional audit noise, not new independent tasks.',
        api_calls=0))
    routing = ablations(dev,test)
    propensity(test)
    write_json(OUT/'complete.json',dict(routing_arms=len(routing),routing_rows=sum(r['tasks'] for r in routing),
        propensity_trials=24000,api_spend=0,budget_violations=0))
    print(OUT)


if __name__ == '__main__':
    main()
