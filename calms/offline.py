"""Offline E0/E2/E3/E4/E6/E7 runners. No credentials and no network access."""
import csv
import itertools
import math
import statistics
from pathlib import Path

from .common import digest, jsonl, manifest, mean, rng, write_csv, write_json, write_jsonl
from .mechanism import POLICIES, Pool, audit_design, choose, draw_audit, expected_score


def legacy_check(source, output, budget=2.2):
    """Recompute summaries from supplied logs; not historical simulator recovery."""
    with Path(source).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = []
    for policy in sorted({r["policy"] for r in rows}):
        subset = [r for r in rows if r["policy"] == policy]
        seed_means = [mean(float(r["net_value"]) for r in subset if r["seed"] == seed)
                      for seed in sorted({r["seed"] for r in subset})]
        spend = [float(r["execution_cost"]) + float(r["audit_cost"]) for r in subset]
        accounting = [abs(float(r["net_value"]) - (float(r["reward"]) - s)) for r, s in zip(subset, spend)]
        result.append({"policy": policy, "episodes": len(subset), "seeds": len(seed_means),
                       "net_value_mean": mean(seed_means),
                       "normal_ci95_halfwidth": 1.96 * statistics.stdev(seed_means) / math.sqrt(len(seed_means)) if len(seed_means) > 1 else 0,
                       "over_total_budget": sum(v > budget + 1e-9 for v in spend),
                       "max_total_spend": max(spend), "max_accounting_residual": max(accounting)})
    write_csv(output, result)
    return result


def run_stream(records, policy, seed, budget, rate, pooling="exponential", beta=0,
               learned=False, delay=1, importance=True, distribution=None):
    if delay < 1:
        raise ValueError("Update delay must be >=1")
    workers = len(records[0]["cost_offers"])
    forecasters = len(records[0]["reports"])
    pool = Pool(forecasters, workers, method="equal" if policy == "equal" else pooling)
    counts, queued, result = {}, [], []
    priors = [0.7, 0.65, 0.8, 0.9][:workers]
    if len(priors) != workers:
        priors = [0.6] * workers
    for episode, record in enumerate(records):
        due = [item for item in queued if item[0] <= episode]
        queued = [item for item in queued if item[0] > episode]
        for _, region, reports, observations, ips in due:
            pool.update(region, reports, observations, ips)
            counts.setdefault(region, [[0, 0] for _ in range(workers)])
            for w, y, _ in observations:
                counts[region][w][0] += y
                counts[region][w][1] += 1
        region = record["family"]
        history = counts.setdefault(region, [[0, 0] for _ in range(workers)])
        if learned:
            # Only earlier permitted labels; never record['true_p'] or outcomes.
            belief = [(a + 4 * priors[w]) / (n + 4) for w, (a, n) in enumerate(history)]
            reports = [[min(0.99, max(0.01, belief[w] + (0.08 if (w + m) % 3 == 0 else -0.02)))
                        for w in range(workers)] for m in range(forecasters)]
        else:
            reports = record["reports"]
        if policy == "coupled":
            predictions = [min(0.99, reports[w % forecasters][w] + 0.15 * (w % 2)) for w in range(workers)]
        else:
            predictions = pool.predict(region, reports)
        costs = record["cost_offers"]
        audit_policy = policy in ("calms", "myopic")
        design = audit_design(costs, rate if audit_policy else 0, budget, distribution)
        fc = sum(r["cost_usd"] for r in record["forecast_records"]) if policy in ("equal", "selected", "calms", "myopic", "coupled") else 0
        pay_reserve = beta * forecasters / min(design["pi"]) if design["trigger"] else 0
        available = budget - fc - design["reserve"] - pay_reserve
        eligible = available + 1e-12 >= min(costs)
        if eligible:
            w = choose(policy, predictions, costs, available, record["reward"], history,
                       record.get("static", priors), [seed, record["task_id"]],
                       decision_costs=record.get("decision_costs"))
            aw = draw_audit(design, seed, record["task_id"])
        else:
            w, aw, fc = None, None, 0.0
        # All decisions above are made without reading evaluator-only outcomes.
        repetitions = record["outcomes"]
        rep = rng("production-repetition", seed, record["task_id"]).randrange(len(repetitions))
        arep = rng("audit-repetition", seed, record["task_id"]).randrange(len(repetitions))
        outcome = repetitions[rep][w] if w is not None else None
        audit = repetitions[arep][aw] if aw is not None else None
        y = outcome["outcome"] if outcome else 0
        ec = outcome["cost_usd"] if outcome else 0
        ac = audit["cost_usd"] if audit else 0
        if outcome and ec > costs[w] + 1e-12 or audit and ac > costs[aw] + 1e-12:
            raise ValueError("Recorded execution exceeds its predeclared cost offer")
        payment = beta * sum(1 - (q[aw] - audit["outcome"]) ** 2 for q in reports) / design["pi"][aw] if audit else 0
        observations = []
        if audit_policy:
            if audit:
                observations = [(aw, audit["outcome"], design["pi"][aw])]
            if eligible:
                queued.append((episode + delay, region, reports, observations, importance))
        elif policy in ("selected", "explore", "coupled") and outcome:
            # Selected-only objective deliberately uses selected distribution.
            queued.append((episode + delay, region, reports, [(w, y, 1)], False))
        total = ec + ac + fc + payment
        if total > budget + 1e-9:
            raise ValueError("Total episode budget exceeded")
        full_brier = mean((predictions[j] - r[j]["outcome"]) ** 2 for r in repetitions for j in range(workers))
        regret = None
        if "true_p" in record:
            oracle = max([0] + [record["reward"] * p - c for p, c in zip(record["true_p"], costs) if c <= budget])
            value = (record["reward"] * record["true_p"][w] - ec if w is not None else 0) - ac - fc - payment
            regret = oracle - value
        result.append({"seed": seed, "episode": episode, "task_id": record["task_id"],
                       "cluster_id": record["cluster_id"], "family": region, "policy": policy,
                       "audit_rate": rate if audit_policy else 0, "pooling": pooling,
                       "delay": delay, "importance": importance, "selected": w, "audit": aw,
                       "audit_pi": design["pi"], "audit_eligible": eligible,
                       "reports": reports, "predictions": predictions, "outcome": y,
                       "audit_outcome": audit["outcome"] if audit else None,
                       "execution_cost": ec, "audit_cost": ac, "forecast_cost": fc, "payment": payment,
                       "cost": total, "reward": record["reward"] * y, "net_value": record["reward"] * y - total,
                       "budget": budget, "full_brier": full_brier,
                       "selected_brier": (predictions[w] - y) ** 2 if w is not None else None,
                       "pseudo_regret": regret})
    return result


def synthetic(seed, episodes, shift="none"):
    records = []
    costs = [0.015, 0.025, 0.04, 0.07]
    for t in range(episodes):
        kind = int(rng(seed, t, "family").random() < (0.8 if shift == "mixture" and t >= episodes // 2 else 0.5))
        p = [0.45, 0.72, 0.8, 0.93] if kind else [0.78, 0.5, 0.85, 0.9]
        if shift == "capability" and t >= episodes // 2:
            p = [0.95, p[1], 0.35, p[3]]
        records.append({"task_id": f"s{seed}-t{t}", "cluster_id": f"s{seed}-t{t}",
                        "family": f"synthetic-{kind}", "reward": 0.25, "split": "test",
                        "reports": [[0.5] * 4 for _ in range(3)], "true_p": p,
                        "forecast_records": [{"cost_usd": 0.001} for _ in range(3)], "cost_offers": costs,
                        "outcomes": [[{"outcome": int(rng(seed, t, w, rep, "outcome").random() < p[w]),
                                        "cost_usd": costs[w]} for w in range(4)] for rep in range(2)]})
    return records


def simulate(output, seeds=30, episodes=80, rates=(0, .005, .01, .02, .05, .1), shift="capability",
             policies=POLICIES, pooling="exponential", delay=1, importance=True):
    manifest(output, {"kind": "new-synthetic-feedback-study", "seeds": seeds, "episodes": episodes,
                      "rates": list(rates), "shift": shift, "policies": list(policies), "pooling": pooling,
                      "delay": delay, "importance": importance})
    rows = []
    for seed in range(seeds):
        records = synthetic(seed, episodes, shift)
        for policy in policies:
            for rate in rates if policy in ("calms", "myopic") else (0,):
                rows.extend(run_stream(records, policy, seed, .12, rate, pooling=pooling,
                                       learned=True, delay=delay, importance=importance,
                                       distribution=[1, 2, 4, 8]))
    write_jsonl(Path(output) / "episodes.jsonl", rows)
    write_json(Path(output) / "complete.json", {"rows": len(rows), "api_spend": 0,
                                               "historical_reproduction": False})
    return rows


def replay(matrix, output, budget=.15, rate=.02, seed=0, policies=POLICIES, pooling="exponential", calibration=None):
    records = jsonl(matrix)
    if not records or any(r["split"] != "test" for r in records):
        raise ValueError("Replay requires nonempty held-out test records")
    if "static" in policies and calibration is None:
        raise ValueError("Static replay needs --calibration fitted on development data")
    if calibration is not None:
        validate_calibration(records, calibration)
        for record in records:
            record["static"] = calibration["static_probabilities"][record["family"]]
    manifest(output, {"kind": "frozen-forecast-replay", "matrix_sha256": digest(records), "budget": budget,
                      "rate": rate, "seed": seed, "policies": list(policies), "pooling": pooling})
    rows = []
    for policy in policies:
        rows.extend(run_stream(records, policy, seed, budget, rate, pooling=pooling))
    write_jsonl(Path(output) / "episodes.jsonl", rows)
    write_json(Path(output) / "complete.json", {"rows": len(rows), "api_spend": 0,
                                               "scope": "Frozen forecasts; no adaptive semantic forecaster claims"})
    return rows


def validate_calibration(records, calibration):
    if set(calibration["training_clusters"]) & {r["cluster_id"] for r in records}:
        raise ValueError("Development calibration leaks test clusters")
    ids = [w["worker_id"] for w in records[0]["outcomes"][0]]
    if calibration["worker_ids"] != ids:
        raise ValueError("Calibration worker roster/order differs")
    for record in records:
        probabilities = calibration["static_probabilities"].get(record["family"])
        if probabilities is None or len(probabilities) != len(ids) or any(not 0 <= p <= 1 for p in probabilities):
            raise ValueError("Calibration missing or invalid for a task family")


def strategic(output):
    """Exact best responses in one-shot finite report class; not LLM truth."""
    rows = []
    grid = [i / 100 for i in range(101)]
    for p, threshold, bonus, pi, side in itertools.product(
            [.1, .3, .5, .7, .9], [.3, .5, .7], [0, .5, 1, 2], [.01, .05, .2, 1], [0, .25, 1, 4]):
        for mechanism in ("coupled_winner", "coupled_audit", "separated_audit"):
            def payoff(q):
                selected = q >= threshold
                score = expected_score(p, q)
                if mechanism == "coupled_winner":
                    return selected * (bonus + score)
                if mechanism == "coupled_audit":
                    return score + selected * bonus
                return score + selected * side
            best = max(grid, key=payoff)
            for strategy, q in (("truthful", p), ("inflated", min(1, p + .15)),
                                ("deflated", max(0, p - .15)), ("threshold", threshold), ("best_grid", best)):
                # Horvitz-Thompson score variance: E[S^2]/pi - E[S]^2.
                s = expected_score(p, q)
                second = p * (1 - (q - 1) ** 2) ** 2 + (1 - p) * (1 - q ** 2) ** 2
                rows.append({"mechanism": mechanism, "p": p, "threshold": threshold, "bonus": bonus,
                             "audit_pi": pi, "side_interest": side, "strategy": strategy, "report": q,
                             "expected_payoff": payoff(q), "deviation_gain": payoff(q) - payoff(p),
                             "audit_score_variance": second / pi - s * s})
    write_csv(output, rows)
    return rows


def propensity(output, trials=10000):
    # Fixed full-information score; randomness is audit selection only.
    q, y = [.2, .4, .7, .9], [0, 1, 0, 1]
    score = [1 - (a - b) ** 2 for a, b in zip(q, y)]
    truth = sum(score)
    rows = []
    for distribution in ([1, 1, 1, 1], [1, 2, 4, 8]):
        for trigger in (.01, .05, .2, 1):
            probs = [trigger * v / sum(distribution) for v in distribution]
            samples = {"ht": [], "unweighted": [], "clip10": [], "clip50": [], "clip100": []}
            for trial in range(trials):
                r = rng("propensity", distribution, trigger, trial)
                w = r.choices(range(4), weights=distribution)[0] if r.random() < trigger else None
                for name, values in samples.items():
                    weight = (1 / probs[w]) if w is not None else 0
                    if name == "unweighted":
                        weight = 4 / trigger if w is not None else 0
                    elif name.startswith("clip"):
                        weight = min(weight, int(name[4:]))
                    values.append(weight * score[w] if w is not None else 0)
            for name, values in samples.items():
                weights = [1 / p for p in probs]
                if name == "unweighted":
                    weights = [4 / trigger] * 4
                if name.startswith("clip"):
                    weights = [min(w, int(name[4:])) for w in weights]
                exact = sum(p * w * s for p, w, s in zip(probs, weights, score))
                variance = sum(p * (w * s) ** 2 for p, w, s in zip(probs, weights, score)) - exact ** 2
                rows.append({"sampling": "uniform" if len(set(distribution)) == 1 else "nonuniform",
                             "trigger": trigger, "estimator": name, "target": truth,
                             "exact_bias": exact - truth, "exact_variance": variance,
                             "monte_carlo_bias": mean(values) - truth,
                             "rmse": math.sqrt(mean((v - truth) ** 2 for v in values)), "trials": trials})
    write_csv(output, rows)
    return rows
