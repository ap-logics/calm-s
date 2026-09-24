"""Write a concise report only after all predeclared pilot stages finish."""
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import jsonl, mean, read_json


def main():
    output = ROOT / "calms_runs/qa-pilot-20260923"
    progress = read_json(output / "progress.json")
    if progress.get("status") != "complete":
        raise SystemExit("Pilot is not complete; no final report written.")
    dev, held = jsonl(output / "dev/matrix.jsonl"), jsonl(output / "test/matrix.jsonl")
    records = dev + held
    ledger = ROOT / "calms_runs/api_ledger.sqlite"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as c:
        states = list(c.execute("SELECT status,COUNT(*),SUM(cost) FROM calls GROUP BY status"))
    measured = sum(cost for status, _, cost in states if status == "done")
    reserved = sum(cost for status, _, cost in states if status != "done")
    pilot_cost = sum(sum(f["cost_usd"] for f in r["forecast_records"]) +
                     sum(w["cost_usd"] for rep in r["outcomes"] for w in rep) for r in records)
    text = ["# CALM-S first real-model QA pilot", "", "Completed under the user-approved US$50 cumulative cap.", "",
            f"- 30 development and 30 held-out MuSiQue QA problems; 480 worker calls and 180 forecast calls.",
            f"- Pilot token-cost ledger: **${pilot_cost:.4f}**. Total including the separate connectivity smoke test: **${measured:.4f}**.",
            f"- Outstanding uncertain/in-flight reservations: ${reserved:.4f}.",
            "- Costs use provider token usage and configured USD prices; taxes/hosting are excluded and provider billing is authoritative.",
            "- This is an exploratory QA pilot, not the full confirmatory AAMAS experiment suite.", "",
            "## Held-out worker results", "", "| Worker | Accuracy over 60 decodes | Mean cost/call |", "|---|---:|---:|"]
    for w, worker in enumerate(held[0]["outcomes"][0]):
        values = [rep[w] for r in held for rep in r["outcomes"]]
        text.append(f"| {worker['worker_id']} | {mean(v['outcome'] for v in values):.1%} | ${mean(v['cost_usd'] for v in values):.5f} |")
    invalid = sum(not f["valid_forecast"] for r in records for f in r["forecast_records"])
    incomplete = sum(not w["complete"] for r in records for rep in r["outcomes"] for w in rep)
    text += ["", f"Invalid forecasts: {invalid}/180. Incomplete worker outputs: {incomplete}/480.", "",
             "## Routing diagnostic at the predeclared $0.30 budget and 2% audit rate", "",
             "Reward is a declared $0.25 equivalent per correct answer. This arbitrary conversion needs sensitivity analysis.",
             "The pilot runs budgets $0.15/$0.30/$0.60 and rates 0/0.5/1/2/5/10%; this is the middle-budget illustrative slice.", "",
             "| Policy | Mean net value | Success rate | Mean spend |", "|---|---:|---:|---:|"]
    with (output / "replay-b0.3-r0.02/report/summary.csv").open() as f:
        for row in csv.DictReader(f):
            text.append(f"| {row['arm'].split('|')[0]} | {float(row['net_value']):.5f} | {float(row['success_rate']):.1%} | ${float(row['mean_cost']):.5f} |")
    text += ["", "## Limits on interpretation", "",
             "- Only 30 distinct held-out problems. Repeated decodes are not independent tasks.",
             "- The adapter supplies paragraph text without titles and scores normalized exact answers with aliases; this is not the full official MuSiQue evaluation.",
             "- Forecasts are frozen for replay; only the router/pool updates. This is not evidence of semantic forecasting adaptation.",
             "- Task-level bootstrap intervals in replay CSVs are diagnostic. Pool updates couple tasks over time, so they must not be used as confirmatory adaptive-stream significance tests.",
             "- Transfers are disabled in replay. Proper-scoring incentive evidence comes separately from the strategic experiments.",
             "- Code-generation benchmarks, AppWorld and faithful Agora/AgentLance comparisons have not run.",
             "- The parallel offline suite has 230,400 synthetic episode records and zero shared-budget violations. Those are synthetic results, not real-agent benchmark outcomes.", "",
             "## Files", "", "- `dev/matrix.jsonl`, `test/matrix.jsonl`: full worker outcomes, forecasts, usage and latency.",
             "- `forecast-report/`: Brier/log scores and calibration bins.",
             "- `attacks/`: development-fitted offsets evaluated on held-out outcomes.",
             "- `replay-*/report/`: all 18 fixed budget/rate conditions and paired diagnostic summaries.",
             "- `progress.json`: completed stage list and accounting.",
             "- `../../calms_data/qa-pilot/dataset_manifest.json`: source, hashes, task IDs and split protocol.", "",
             "Dataset: [MuSiQue authors' repository](https://github.com/StonyBrookNLP/musique), CC BY 4.0.", ""]
    report = output / "PILOT_RESULTS.md"
    report.write_text("\n".join(text), encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
