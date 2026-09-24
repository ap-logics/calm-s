"""Bounded concurrent CALM-S collection; one persistent cumulative spend ledger."""
import argparse
import concurrent.futures as cf
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts_calms"))
from calms.analysis import fit_static
from calms.common import code_hash, digest, jsonl, read_json, write_json, write_jsonl
from calms.data import load_tasks
from calms.live import collect, workflow
from calms.providers import Client, validate_config
from prepare_expanded import DATA, fit_config

OUT = ROOT / "calms_runs/expanded-20260923"
LEDGER = ROOT / "calms_runs/api_ledger.sqlite"


def accounting():
    with sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return [{"status": s, "calls": n, "cost_or_reservation_usd": c}
                for s, n, c in db.execute("SELECT status,COUNT(*),SUM(cost) FROM calls GROUP BY status")]


def bounded(jobs, function, concurrency, update):
    """Keep only concurrency jobs in flight; stop scheduling after any failure."""
    remaining = iter(jobs)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = {}
        for _ in range(concurrency):
            job = next(remaining, None)
            if job is not None:
                pending[pool.submit(function, job)] = job
        while pending:
            done, _ = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            # Check every completed future before launching more work.
            for future in done:
                if future.exception():
                    for other in pending:
                        other.cancel()
                    raise future.exception()
            for future in done:
                job = pending.pop(future)
                results[job[0]] = future.result()
                update(len(results), len(jobs))
            for _ in done:
                job = next(remaining, None)
                if job is not None:
                    pending[pool.submit(function, job)] = job
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-usd", type=float, required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if not args.live or not 0 < args.max_usd <= 100 or not 1 <= args.concurrency <= 4:
        parser.error("Requires --live, 0 < cumulative --max-usd <= 100, and concurrency 1..4")
    protocol = read_json(DATA / "protocol.json")
    for name, expected in protocol["data_hashes"].items():
        if digest(jsonl(DATA / name)) != expected:
            raise ValueError("Frozen data hash changed")
    config = validate_config(read_json(DATA / "config.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    stages = []
    initial_code = code_hash()

    def progress(stage, done, total, status="running"):
        result = {"status": status, "stage": stage, "completed": done, "total": total,
                  "completed_stages": stages, "cumulative_cap_usd": args.max_usd,
                  "elapsed_seconds_this_invocation": time.time() - started, "accounting": accounting()}
        write_json(OUT / "progress.json", result)
        print(json.dumps(result), flush=True)

    def client():
        if code_hash() != initial_code:
            raise RuntimeError("Core code changed during live run; stopped")
        return Client(LEDGER, args.max_usd, ROOT / ".env", live=True)

    try:
        for stage in ("dev", "workflow-node-dev", "test"):
            tasks = load_tasks(DATA / f"{stage}.jsonl")
            target = OUT / stage
            jobs = [(t["id"], t) for t in tasks]
            def one(job):
                _, task = job
                c = client()
                try:
                    return collect(c, config, [task], target / "shards" / digest(task["id"]), 2)[0]
                finally:
                    c.close()
            progress(stage, 0, len(tasks))
            results = bounded(jobs, one, args.concurrency, lambda n, total: progress(stage, n, total))
            write_jsonl(target / "matrix.jsonl", [results[t["id"]] for t in tasks])
            write_json(target / "manifest.json", {"kind": "independent-task-shards", "code_sha256": initial_code,
                       "tasks_sha256": digest(tasks), "config": config, "repeats": 2})
            stages.append(stage)
        # Fit only development node outcomes; test workflow outcomes are still unseen.
        node_records = jsonl(OUT / "workflow-node-dev/matrix.jsonl")
        wf_config = fit_config(config, node_records, load_tasks(DATA / "workflow-node-dev.jsonl"),
                               "Single-hop decomposition node with supplied correct upstream development answers")
        calibration = fit_static(OUT / "workflow-node-dev/matrix.jsonl", OUT / "workflow-static.json")
        wf_config["static_probabilities"] = calibration["static_probabilities"]
        write_json(OUT / "workflow-config.json", wf_config)
        tasks = load_tasks(DATA / "workflow-test.jsonl")
        jobs = [(f"{policy}-stream{s}", (policy, s, tasks[s*8:(s+1)*8]))
                for policy in protocol["workflow"]["policies"] for s in range(3)]
        def one_workflow(job):
            name, (policy, seed, stream) = job
            c = client()
            try:
                return workflow(c, wf_config, stream, OUT / "workflow" / name, policy, .60, .02, seed=seed)
            finally:
                c.close()
        progress("workflow", 0, len(jobs))
        results = bounded(jobs, one_workflow, args.concurrency, lambda n, total: progress("workflow", n, total))
        write_jsonl(OUT / "workflow/episodes.jsonl", [r for name, _ in jobs for r in results[name]])
        stages.append("workflow")
        progress("live-collection-complete", len(stages), len(stages), "complete")
    except Exception as exc:
        progress("stopped", 0, 0, "stopped")
        print("Stopped safely:", type(exc).__name__, str(exc), flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
