"""Development-fitted report deviations on real frozen outcome matrices.

An elicited probability is a baseline report, not an observed true LLM belief.
Positive separated-score gain can reflect correcting that baseline's calibration.
"""
from pathlib import Path

from .common import digest, jsonl, manifest, mean, write_csv, write_json


def report_payoff(record, worker, offset, mechanism, bonus, side):
    count = len(record["cost_offers"])
    reports = [record["reports"][w % len(record["reports"])][w] for w in range(count)]
    q = min(1, max(0, reports[worker] + offset))
    reports[worker] = q
    chosen = max(range(count), key=lambda w: record["reward"] * reports[w] - record["cost_offers"][w])
    if record["reward"] * reports[chosen] - record["cost_offers"][chosen] <= 0:
        chosen = None
    selected = int(chosen == worker)
    score = mean(1 - (q - repeat[worker]["outcome"]) ** 2 for repeat in record["outcomes"])
    if mechanism == "coupled_winner":
        payoff = selected * (bonus + score)
    elif mechanism == "coupled_audit":
        payoff = score + selected * bonus
    else:
        payoff = score + selected * side
    principal = mean(record["reward"] * rep[chosen]["outcome"] - rep[chosen]["cost_usd"]
                     for rep in record["outcomes"]) if chosen is not None else 0
    return payoff, selected, principal


def attacks(development, test, output, bonus=.5, side=0):
    dev, held = jsonl(development), jsonl(test)
    if not dev or not held or any(r["split"] != "dev" for r in dev) or any(r["split"] != "test" for r in held):
        raise ValueError("Attacks need nonempty development and test matrices with correct splits")
    if {r["cluster_id"] for r in dev} & {r["cluster_id"] for r in held}:
        raise ValueError("Attack tuning leaks held-out tasks")
    ids = [w["worker_id"] for w in dev[0]["outcomes"][0]]
    if any([w["worker_id"] for w in r["outcomes"][0]] != ids for r in dev + held):
        raise ValueError("Worker rosters differ across matrices")
    manifest(output, {"kind": "held-out-baseline-report-deviations", "development_sha256": digest(dev),
                      "test_sha256": digest(held), "bonus": bonus, "side_interest": side})
    rows, fits = [], []
    for mechanism in ("coupled_winner", "coupled_audit", "separated_audit"):
        for w, worker_id in enumerate(ids):
            candidates = [i / 100 for i in range(-50, 51, 5)]
            # Tie-break toward no change; no test labels used to select the attack.
            delta = max(candidates, key=lambda d: (mean(report_payoff(r, w, d, mechanism, bonus, side)[0] for r in dev), -abs(d)))
            fits.append({"mechanism": mechanism, "worker_id": worker_id, "offset": delta})
            for record in held:
                base = report_payoff(record, w, 0, mechanism, bonus, side)
                attacked = report_payoff(record, w, delta, mechanism, bonus, side)
                rows.append({"mechanism": mechanism, "worker_id": worker_id, "task_id": record["task_id"],
                             "cluster_id": record["cluster_id"], "family": record["family"], "offset": delta,
                             "baseline_payoff": base[0], "deviation_payoff": attacked[0],
                             "deviation_gain": attacked[0] - base[0], "selection_change": attacked[1] - base[1],
                             "principal_value_change": attacked[2] - base[2]})
    write_csv(Path(output) / "held_out_deviations.csv", rows)
    write_json(Path(output) / "development_fits.json", {"fits": fits, "scope":
               "Unilateral constant-offset attack class. Expected audit-score exposure; not realized sparse payments. "
               "Baseline reports are not known true beliefs. No repeated-game/collusion claim."})
    return rows
