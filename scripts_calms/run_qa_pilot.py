"""Run the prepared CALM-S QA pilot under one cumulative provider ledger cap."""
import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-usd", type=float, required=True)
    parser.add_argument("--output", default="calms_runs/qa-pilot-20260923")
    args = parser.parse_args()
    if not args.live:
        parser.error("Paid pilot requires --live. Nothing was sent.")
    output = (ROOT / args.output).resolve()
    data = ROOT / "calms_data/qa-pilot"
    dataset = read_json(data / "dataset_manifest.json")
    output.mkdir(parents=True, exist_ok=True)
    progress = output / "progress.json"
    stages = []
    def run(name, *command):
        write_json(progress, {"active_stage": name, "completed_stages": stages, "cap_usd": args.max_usd})
        print("Starting", name, flush=True)
        subprocess.run([sys.executable, "-m", "calms", *map(str, command)], cwd=ROOT, check=True)
        stages.append(name)
    for split in ("dev", "test"):
        run("collect-" + split, "collect", "--config", ROOT / "calms_configs/pilot.json", "--tasks", data / (split + ".jsonl"),
            "--split", split, "--repeats", 2, "--output", output / split, "--max-usd", args.max_usd, "--live")
    dev, test = output / "dev/matrix.jsonl", output / "test/matrix.jsonl"
    run("fit-static", "fit-static", "--matrix", dev, "--output", output / "static.json")
    run("forecast-analysis", "forecast-analysis", "--matrix", test, "--output", output / "forecast-report")
    run("held-out-attacks", "attacks", "--dev", dev, "--test", test, "--output", output / "attacks")
    # Pilot diagnostic only: fixed USD-equivalent reward and predeclared budgets.
    for budget in (.15, .30, .60):
        for rate in (0, .005, .01, .02, .05, .1):
            target = output / f"replay-b{budget:g}-r{rate:g}"
            run(target.name, "replay", "--matrix", test, "--calibration", output / "static.json", "--budget", budget,
                "--rate", rate, "--output", target)
            run(target.name + "-analysis", "analyze", "--input", target / "episodes.jsonl", "--unit", "cluster_id",
                "--output", target / "report")
    ledger = ROOT / "calms_runs/api_ledger.sqlite"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as c:
        accounting = [{"status": s, "calls": n, "cost_or_reservation_usd": total}
                      for s, n, total in c.execute("SELECT status,COUNT(*),SUM(cost) FROM calls GROUP BY status")]
    write_json(progress, {"active_stage": None, "completed_stages": stages, "cap_usd": args.max_usd,
                          "status": "complete", "accounting": accounting,
                          "scope": "Exploratory MuSiQue QA pilot; frozen-forecast replay, not the full paper study"})
    print(json.dumps({"status": "complete", "output": str(output), "accounting": accounting}), flush=True)


if __name__ == "__main__":
    main()
