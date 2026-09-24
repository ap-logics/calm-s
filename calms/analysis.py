"""Paired cluster inference and full-candidate forecasting diagnostics."""
import math
from collections import defaultdict
from pathlib import Path

from .common import jsonl, mean, rng, write_csv, write_json


def interval(values, resamples=2000, seed=0):
    values = list(values)
    if len(values) < 2:
        return None, None
    r = rng("bootstrap", seed)
    draws = sorted(mean(r.choices(values, k=len(values))) for _ in range(resamples))
    return draws[int(.025 * (resamples - 1))], draws[int(.975 * (resamples - 1))]


def arm(row):
    return f"{row['policy']}|r={row.get('audit_rate', 0):g}|pool={row.get('pooling', 'default')}"


def analyze(path, output, unit="seed", reference="equal", resamples=2000):
    rows = jsonl(path)
    if unit not in ("seed", "cluster_id") or resamples < 100:
        raise ValueError("Invalid bootstrap configuration")
    groups = defaultdict(list)
    for row in rows:
        groups[arm(row)].append(row)
    estimates, cluster_values = [], {}
    for name, subset in sorted(groups.items()):
        clustered = defaultdict(list)
        for row in subset:
            clustered[str(row[unit])].append(row["net_value"])
        units = {key: mean(v) for key, v in clustered.items()}
        cluster_values[name] = units
        low, high = interval(units.values(), resamples)
        estimates.append({"arm": name, "rows": len(subset), "independent_units": len(units),
                          "net_value": mean(units.values()), "ci95_low": low, "ci95_high": high,
                          "mean_cost": mean(r["cost"] for r in subset),
                          "success_rate": mean(r.get("outcome", r.get("completed", 0)) for r in subset),
                          "budget_violations": sum(r["cost"] > r["budget"] + 1e-9 for r in subset)})
    reference_names = [k for k in groups if k.split("|")[0] == reference]
    if len(reference_names) != 1:
        raise ValueError("Analysis requires exactly one reference arm")
    base = cluster_values[reference_names[0]]
    contrasts = []
    for name, values in cluster_values.items():
        if name == reference_names[0]:
            continue
        if set(base) != set(values):
            raise ValueError("Incomplete paired run: cluster IDs differ")
        # Require the SAME opportunity multiset in each arm, not just same seeds.
        base_tasks = sorted((str(r[unit]), r["task_id"]) for r in groups[reference_names[0]])
        tasks = sorted((str(r[unit]), r["task_id"]) for r in groups[name])
        if base_tasks != tasks:
            raise ValueError("Incomplete paired run: task coverage differs")
        differences = [values[k] - base[k] for k in sorted(base)]
        low, high = interval(differences, resamples)
        contrasts.append({"arm": name, "reference": reference_names[0], "paired_units": len(differences),
                          "difference": mean(differences), "ci95_low": low, "ci95_high": high})
    write_csv(Path(output) / "summary.csv", estimates)
    if contrasts:
        write_csv(Path(output) / "paired_contrasts.csv", contrasts)
    write_json(Path(output) / "analysis.json", {"unit": unit, "resamples": resamples,
               "note": "Percentile paired cluster bootstrap; no equivalence claim; one-unit CI is unavailable. "
                       "Use seed for independent synthetic streams. Reused cached tasks are not new independent seeds. "
                       "Use task clusters for frozen-matrix replay. Adaptive real streams need independent stream replication."})
    return estimates


def calibration(pairs):
    """Logistic calibration intercept/slope, damped Newton; null if unidentifiable."""
    if len(pairs) < 10 or len({y for _, y in pairs}) < 2 or len({p for p, _ in pairs}) < 2:
        return None, None
    a, b = 0.0, 1.0
    for _ in range(100):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for q, y in pairs:
            q = max(1e-6, min(1 - 1e-6, q))
            x = math.log(q / (1 - q))
            z = max(-30, min(30, a + b * x))
            p = 1 / (1 + math.exp(-z))
            w = p * (1 - p)
            g0 += y - p
            g1 += (y - p) * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if det < 1e-10:
            return None, None
        da, db = (g0 * h11 - g1 * h01) / det, (g1 * h00 - g0 * h01) / det
        scale = max(1, abs(da), abs(db))
        a, b = a + da / scale, b + db / scale
        if max(abs(a), abs(b)) > 30:
            return None, None
        if max(abs(da), abs(db)) < 1e-6:
            return a, b
    return None, None


def forecast_analysis(matrix, output):
    records = jsonl(matrix)
    pairs = defaultdict(list)
    for r in records:
        vectors = {f"forecaster-{m}": q for m, q in enumerate(r["reports"])}
        vectors["equal_pool"] = [mean(q[w] for q in r["reports"]) for w in range(len(r["cost_offers"]))]
        for name, qs in vectors.items():
            for repetitions in r["outcomes"]:
                for w, q in enumerate(qs):
                    pairs[(r["family"], name)].append((q, repetitions[w]["outcome"]))
    rows, bins = [], []
    for (family, name), values in sorted(pairs.items()):
        a, b = calibration(values)
        rows.append({"family": family, "predictor": name, "observations_not_independent_tasks": len(values),
                     "brier": mean((p - y) ** 2 for p, y in values),
                     "log_loss": mean(-math.log(max(1e-9, p if y else 1 - p)) for p, y in values),
                     "calibration_intercept": a, "calibration_slope": b})
        for bin_index in range(10):
            group = [(p, y) for p, y in values if min(9, int(p * 10)) == bin_index]
            bins.append({"family": family, "predictor": name, "bin": bin_index, "count": len(group),
                         "mean_probability": mean(p for p, y in group) if group else None,
                         "observed_success": mean(y for p, y in group) if group else None})
    write_csv(Path(output) / "forecast_scores.csv", rows)
    write_csv(Path(output) / "reliability_bins.csv", bins)
    return rows


def fit_static(matrix, output):
    records = jsonl(matrix)
    if not records or any(r["split"] != "dev" for r in records):
        raise ValueError("Static calibration must use development data only")
    buckets = defaultdict(list)
    for record in records:
        buckets[record["family"]].append(record)
    estimates = {}
    for family, data in buckets.items():
        estimates[family] = [mean(mean(rep[w]["outcome"] for rep in record["outcomes"]) for record in data)
                            for w in range(len(data[0]["cost_offers"]))]
    artifact = {"static_probabilities": estimates, "training_clusters": sorted({r["cluster_id"] for r in records}),
                "worker_ids": [w["worker_id"] for w in records[0]["outcomes"][0]]}
    write_json(output, artifact)
    return artifact
