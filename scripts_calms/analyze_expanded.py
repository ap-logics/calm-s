"""Offline, protocol-locked analyses of the second real-model CALM-S study."""
import copy
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts_calms"))
from feedback_control import feedback_control
from calms.analysis import analyze, fit_static, forecast_analysis, interval
from calms.attacks import attacks
from calms.common import digest, jsonl, mean, read_json, write_csv, write_json, write_jsonl
from calms.mechanism import POLICIES
from calms.offline import run_stream, validate_calibration

DATA = ROOT / "calms_data/expanded-20260923"
OUT = ROOT / "calms_runs/expanded-20260923"
REPORT = OUT / "analysis"


def streams(records, policy, budget, rate, length=15):
    result = []
    for seed, offset in enumerate(range(0, len(records), length)):
        result.extend(run_stream(records[offset:offset+length], policy, seed, budget, rate))
    return result


def mean_rows(rows):
    return {"net_value": mean(r["net_value"] for r in rows), "success": mean(r["outcome"] for r in rows),
            "cost": mean(r["cost"] for r in rows), "forecast_cost": mean(r["forecast_cost"] for r in rows),
            "audit_cost": mean(r["audit_cost"] for r in rows), "audits": sum(r["audit"] is not None for r in rows),
            "abstentions": sum(r["selected"] is None for r in rows),
            "budget_violations": sum(r["cost"] > r["budget"] + 1e-9 for r in rows)}


def main():
    if read_json(OUT / "progress.json")["status"] != "complete":
        raise SystemExit("All live stages must complete before final analysis.")
    protocol = read_json(DATA / "protocol.json")
    qa = protocol["qa"]
    dev = jsonl(OUT / "dev/matrix.jsonl")
    test = jsonl(OUT / "test/matrix.jsonl")
    calibration = fit_static(OUT / "dev/matrix.jsonl", REPORT / "static.json")
    validate_calibration(test, calibration)
    for record in dev + test:
        record["static"] = calibration["static_probabilities"][record["family"]]
    # Development choices are saved before any held-out comparison is computed.
    tuning = []
    for policy in [p for p in POLICIES if p not in ("coupled", "myopic")]:
        for rate in qa["rates"] if policy == "calms" else [0]:
            rows = streams(dev, policy, qa["primary_budget"], rate)
            tuning.append({"policy": policy, "rate": rate, **mean_rows(rows)})
    positive = [r for r in tuning if r["policy"] == "calms" and r["rate"] > 0]
    rate = max(positive, key=lambda r: (r["net_value"], -r["rate"]))["rate"]
    comparator = max((r for r in tuning if r["policy"] != "calms"), key=lambda r: r["net_value"])["policy"]
    write_csv(REPORT / "development-selection.csv", tuning)
    locked = {"audit_rate": rate, "comparator": comparator,
        "source": "development only", "dev_matrix_sha256": digest(dev), "primary_budget": qa["primary_budget"]}
    lock_path = REPORT / "locked-selection.json"
    if lock_path.exists():
        assert read_json(lock_path) == locked, "Development selection changed after lock"
    else:
        write_json(lock_path, locked)
    rows = []
    for policy in POLICIES:
        rows.extend(streams(test, policy, qa["primary_budget"], rate))
    write_jsonl(REPORT / "primary/episodes.jsonl", rows)
    summary = analyze(REPORT / "primary/episodes.jsonl", REPORT / "primary/report", "seed", comparator)
    analyze(REPORT / "primary/episodes.jsonl", REPORT / "equal-reference", "seed", "equal")
    frontier, all_rows = [], []
    for budget in qa["budgets"]:
        for policy in ("cheapest", "premium", "static", "explore", "equal", "selected", "calms"):
            for audit_rate in qa["rates"] if policy == "calms" else [0]:
                values = streams(test, policy, budget, audit_rate)
                all_rows.extend(values)
                frontier.append({"budget": budget, "policy": policy, "rate": audit_rate, **mean_rows(values)})
    write_csv(REPORT / "budget-audit-frontier.csv", frontier)
    write_jsonl(REPORT / "budget-audit-frontier.jsonl", all_rows)
    sensitivity = []
    for reward in qa["reward_sensitivity"]:
        altered = copy.deepcopy(test)
        for record in altered:
            record["reward"] = reward
        for policy in ("static", "explore", "equal", "selected", "calms"):
            values = streams(altered, policy, qa["primary_budget"], rate)
            sensitivity.append({"reward": reward, "policy": policy, **mean_rows(values)})
    write_csv(REPORT / "reward-sensitivity.csv", sensitivity)
    cost_ablation = []
    for mode in ("development-estimate", "original-reserve-objective"):
        altered = copy.deepcopy(test)
        if mode == "original-reserve-objective":
            for record in altered:
                record.pop("decision_costs", None)
        for policy in ("static", "equal", "selected", "calms"):
            cost_ablation.append({"cost_objective": mode, "policy": policy,
                **mean_rows(streams(altered, policy, qa["primary_budget"], rate))})
    write_csv(REPORT / "cost-objective-ablation.csv", cost_ablation)
    forecast_analysis(OUT / "test/matrix.jsonl", REPORT / "forecast")
    attacks(OUT / "dev/matrix.jsonl", OUT / "test/matrix.jsonl", REPORT / "attacks")
    # Cheap contextual baseline: hop count is known from the problem template;
    # probabilities are fitted on dev only. No test labels influence routing.
    by_hop = defaultdict(list)
    for r in dev:
        by_hop[r["task_id"][0]].append(r)
    priors = {h: [mean(rep[w]["outcome"] for r in subset for rep in r["outcomes"]) for w in range(4)]
              for h, subset in by_hop.items()}
    contextual = copy.deepcopy(test)
    for r in contextual:
        r["static"] = priors[r["task_id"][0]]
    contextual_rows = streams(contextual, "static", qa["primary_budget"], 0)
    for row in contextual_rows:
        row["policy"] = "contextual_static"
    write_jsonl(REPORT / "contextual/episodes.jsonl", contextual_rows +
                [r for r in rows if r["policy"] in ("calms", "equal")])
    analyze(REPORT / "contextual/episodes.jsonl", REPORT / "contextual/report", "seed", "contextual_static")
    worker_rows, forecast_rows, strata = [], [], []
    for w, worker in enumerate(test[0]["outcomes"][0]):
        values = [rep[w] for r in test for rep in r["outcomes"]]
        worker_rows.append({"worker": worker["worker_id"], "decodes": len(values),
                           "accuracy": mean(v["outcome"] for v in values), "mean_cost": mean(v["cost_usd"] for v in values),
                           "incomplete": sum(not v["complete"] for v in values)})
    write_csv(REPORT / "worker-results.csv", worker_rows)
    for name in ("historical", "contextual_historical", "equal_pool", "forecaster_0", "forecaster_1", "forecaster_2"):
        errors = []
        for record in test:
            if name == "historical":
                qs = record["static"]
            elif name == "contextual_historical":
                qs = priors[record["task_id"][0]]
            elif name == "equal_pool":
                qs = [mean(q[w] for q in record["reports"]) for w in range(4)]
            else:
                qs = record["reports"][int(name[-1])]
            errors.append(mean((qs[w] - rep[w]["outcome"])**2 for rep in record["outcomes"] for w in range(4)))
        low, high = interval(errors)
        forecast_rows.append({"predictor": name, "brier": mean(errors), "task_ci_low": low, "task_ci_high": high,
                              "independent_tasks": len(errors), "forecast_cost_included_in_routing": True})
    write_csv(REPORT / "forecast-with-cheap-baselines.csv", forecast_rows)
    for hop in ("2", "3", "4"):
        for policy in ("static", "equal", "selected", "calms"):
            subset = [r for r in rows if r["policy"] == policy and r["task_id"].startswith(hop)]
            strata.append({"hops": hop, "policy": policy, "tasks": len(subset), **mean_rows(subset)})
    write_csv(REPORT / "hop-strata.csv", strata)
    for feedback_rate in sorted({rate, .1}):
        feedback = feedback_control(test, qa["primary_budget"], feedback_rate)
        write_csv(REPORT / f"feedback-count-matched-r{feedback_rate:g}.csv", feedback)
    wf = jsonl(OUT / "workflow/episodes.jsonl")
    wf_summary = analyze(OUT / "workflow/episodes.jsonl", REPORT / "workflow", "seed", "static")
    # Three workflow streams are too few for a confirmatory bootstrap claim.
    write_json(REPORT / "workflow/interpretation.json", {"descriptive_only": True, "streams": 3,
        "note": "Do not use these n=3 bootstrap intervals as confirmatory evidence. 24 distinct benchmark-derived workflows."})
    with sqlite3.connect((ROOT / "calms_runs/api_ledger.sqlite").resolve().as_uri() + "?mode=ro", uri=True) as c:
        accounting = list(c.execute("SELECT status,COUNT(*),SUM(cost) FROM calls GROUP BY status"))
    spend = sum(c for s, n, c in accounting if s == "done")
    records = dev + test + jsonl(OUT / "workflow-node-dev/matrix.jsonl")
    invalid = sum(not f["valid_forecast"] for r in records for f in r["forecast_records"])
    incomplete = sum(not w["complete"] for r in records for rep in r["outcomes"] for w in rep)
    violations = sum(r["cost"] > r["budget"] + 1e-9 for r in all_rows + wf)
    assert not violations
    lines = ["# CALM-S expanded real-model study", "",
        f"Total recorded API cost including the first pilot: **${spend:.4f}**, within the $99 execution cap.", "",
        "## Scope", "", "- 60 new QA development problems and 150 fresh QA test problems, four workers with two decodes and three forecasters per problem.",
        "- 12 additional development projects provide 36 node-calibration tasks; 24 different projects are executed on-policy under five routing policies.",
        "- All sets exclude shared single-hop component IDs, including both splits of the original pilot.",
        "- Full context now includes paragraph titles. Development-only empirical worker cards are supplied to forecasters.",
        "- Routing uses development-estimated costs for utility; conservative cost reserves still enforce affordability and API caps.",
        f"- Collection invalid forecasts: {invalid}; incomplete worker responses: {incomplete}. Shared-budget violations: {violations}.", "",
        "## Locked QA comparison", "",
        f"Development selected audit rate **{rate:.1%}** and comparator **{comparator}**. Primary episode budget is $0.20; reward is a declared $0.25 equivalent.",
        "QA adaptive replay uses ten disjoint streams of 15 tasks. Intervals resample stream means. They do not turn repeated decodes into independent tasks.", "",
        "| Policy | Success | Mean net value | Mean spend |", "|---|---:|---:|---:|"]
    for r in summary:
        lines.append(f"| {r['arm'].split('|')[0]} | {r['success_rate']:.1%} | {r['net_value']:.5f} | ${r['mean_cost']:.5f} |")
    lines += ["", "The coupled condition is a stylized optimism wrapper, not a faithful external market baseline.", "",
        "## Dependent QA workflows", "",
        "Each worker sees the actual earlier worker answers. Failed nodes terminate the project. Reference answers remain local to the verifier.",
        "This is a MuSiQue decomposition-derived workflow, not AppWorld. Only three independent streams are available: treat this table as descriptive.", "",
        "| Policy | Complete projects | Mean net value | Mean spend |", "|---|---:|---:|---:|"]
    for r in wf_summary:
        lines.append(f"| {r['arm'].split('|')[0]} | {r['success_rate']:.1%} | {r['net_value']:.5f} | ${r['mean_cost']:.5f} |")
    lines += ["", "## Reading the result", "",
        "Use the primary paired contrasts and equal-pool comparison, including their uncertainty. Do not select the best held-out rate as a headline.",
        "The audit contribution is the comparison with equal/selected pooling and exploration; a gain over a cheap worker alone does not establish it.",
        "All tested budgets, rates, reward conversions, original-cost-objective ablations, and hop strata are retained, including unfavorable results.", "",
        "## Remaining limitations", "",
        "- Exact answer matching with aliases is a limited semantic verifier, not the official full MuSiQue metric. Public-data model contamination is possible.",
        "- The fresh QA set has 90 two-hop, 50 three-hop and 10 four-hop problems because disjoint four-hop components were scarce. Report the hop-stratified table alongside pooled results.",
        "- Whole-question QA forecasts are frozen in replay. Workflow forecasts are recomputed using each policy's permitted history; node priors use correct-upstream development calibration.",
        "- No real financial transfers were made; proper-scoring incentive evidence remains a separate analytic/strategic study.",
        "- Coding/EvalPlus, AppWorld and faithful Agora/AgentLance comparisons remain outstanding. This is not the entire AAMAS evidence package.",
        "- Recorded costs are usage-priced estimates, excluding taxes/hosting. Provider billing is authoritative.", "",
        "## Outputs", "", "- `analysis/primary/report/paired_contrasts.csv`: locked primary comparison.",
        "- `analysis/equal-reference/`: comparison against equal pooling.",
        "- `analysis/contextual/report/`: cheap hop-conditioned historical baseline.",
        "- `analysis/budget-audit-frontier.csv`, `reward-sensitivity.csv`, `cost-objective-ablation.csv`, `hop-strata.csv`.",
        "- `analysis/forecast-with-cheap-baselines.csv`, `analysis/attacks/`, `analysis/workflow/`.",
        "- `../../calms_data/expanded-20260923/protocol.json`: frozen protocol, task IDs and source hashes.", ""]
    (OUT / "EXPANDED_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(REPORT / "complete.json", {"protocol_sha256": digest(protocol), "accounting": accounting,
        "invalid_collection_forecasts": invalid, "incomplete_collection_workers": incomplete,
        "budget_violations": violations, "primary_rate": rate, "primary_comparator": comparator})
    print(json.dumps({"report": str(OUT / "EXPANDED_RESULTS.md"), "cumulative_spend_usd": spend}))


if __name__ == "__main__":
    main()
