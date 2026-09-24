"""Export verified per-call traces and archive all CALM-S artifacts, never keys."""
import argparse
import hashlib
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import canonical, code_hash, digest, jsonl, read_json, write_json
from calms.data import public_node
from calms.live import forecast_prompt, worker_prompt

TRACE = ROOT / "calms_runs/retained-traces"
LEDGER = ROOT / "calms_runs/api_ledger.sqlite"


def export_traces():
    TRACE.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True) as db:
        ledger = {k: {"status": s, "cost_or_reservation_usd": c, "upper_reservation_usd": b,
                      "parsed_response": json.loads(r) if r else None}
                  for k, s, c, b, r in db.execute("SELECT key,status,cost,reservation,response FROM calls")}
    seen = set()

    def emit(model, prompt, identity, provenance):
        key = digest({"model": model, "prompt": prompt, "identity": identity})
        if key not in ledger:
            raise ValueError("Reconstructed request does not match a ledger entry")
        body = ({"model": model["model"], "input": prompt, "max_output_tokens": model["max_output_tokens"], "store": False}
                if model["provider"] == "openai" else
                {"model": model["model"], "messages": [{"role": "user", "content": prompt}], "max_tokens": model["max_output_tokens"]})
        trace = {"request_sha256": key, "provider": model["provider"], "model_config": model,
                 "request_body": body, "request_identity": identity,
                 "provenance": provenance, **ledger[key],
                 "scope": "Exact request body reconstructed and hash-verified; stored parsed response with original text/usage, not a raw HTTP envelope. Authentication headers excluded."}
        path = TRACE / "calls" / f"{key}.json"
        if path.exists() and read_json(path) != trace:
            # A previously pending call can settle; retain both snapshots.
            old = read_json(path)
            write_json(TRACE / "prior-call-states" / f"{key}-{digest(old)}.json", old)
        write_json(path, trace)
        seen.add(key)

    # Full-matrix runs, including the original fixture smoke and QA pilot.
    for path in sorted((ROOT / "calms_runs").rglob("manifest.json")):
        manifest = read_json(path)
        if manifest.get("kind") != "full-matrix":
            continue
        directory, config = path.parent, manifest["config"]
        namespace = digest(manifest)
        provenance = {"manifest": str(path.relative_to(ROOT)), "manifest_sha256": namespace,
                      "code_sha256": manifest["code_sha256"]}
        for fp in (directory / "forecasts").glob("*.json"):
            item = read_json(fp)
            public = item["public"]
            task_id = public["task_id"]
            for model in config["forecasters"]:
                emit(model, forecast_prompt(public, config, []), [namespace, task_id, "forecast", model["id"]], provenance)
            for repeat in range(manifest["repeats"]):
                for worker in config["workers"]:
                    identity = [namespace, task_id, "worker", worker["id"], repeat]
                    key = digest({"model": worker, "prompt": worker_prompt(public), "identity": identity})
                    if key in ledger:
                        emit(worker, worker_prompt(public), identity, provenance)
    # On-policy workflows: reconstruct history only from permitted revealed labels.
    data_path = ROOT / "calms_data/expanded-20260923/workflow-test.jsonl"
    if data_path.exists():
        task_map = {t["id"]: t for t in jsonl(data_path)}
        for path in sorted((ROOT / "calms_runs/expanded-20260923/workflow").glob("*/manifest.json")):
            manifest = read_json(path)
            output, config, policy = path.parent, manifest["config"], manifest["policy"]
            namespace, history = digest(manifest), {}
            source = output / "episodes.jsonl"
            if not source.exists():
                continue
            for row in jsonl(source):
                task, outputs, observed = task_map[row["task_id"]], {}, []
                region = task["family"]
                history.setdefault(region, [])
                for event in row["events"]:
                    if event.get("status") == "insufficient_reserved_budget":
                        continue
                    node = next(n for n in task["nodes"] if n["id"] == event["node_id"])
                    public = public_node(task, node, outputs)
                    assert digest(public) == event["public_state_sha256"]
                    identity = [namespace, task["id"], node["id"]]
                    provenance = {"manifest": str(path.relative_to(ROOT)), "manifest_sha256": namespace,
                                  "code_sha256": manifest["code_sha256"], "policy": policy}
                    if event["forecast_records"]:
                        for model in config["forecasters"]:
                            emit(model, forecast_prompt(public, config, history[region]),
                                 [*identity, "forecast", model["id"]], provenance)
                    w, aw = event["selected"], event["audit"]
                    if w is not None:
                        emit(config["workers"][w], worker_prompt(public), [*identity, "production", w], provenance)
                        outputs[node["id"]] = event["worker_result"]["text"]
                        if policy == "selected":
                            observed.append({"worker": config["workers"][w]["id"], "outcome": event["outcome"], "task_id": task["id"]})
                    if aw is not None:
                        emit(config["workers"][aw], worker_prompt(public), [*identity, "shadow", aw], provenance)
                        observed.append({"worker": config["workers"][aw]["id"], "outcome": event["audit_outcome"], "task_id": task["id"]})
                history[region].extend(observed)
    unmatched = {key: value for key, value in ledger.items() if key not in seen}
    write_json(TRACE / "unmatched-ledger-records.json", unmatched)
    # SQLite backup API gives a consistent snapshot, even if a reader is active.
    with sqlite3.connect(LEDGER.resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(TRACE / "api_ledger_snapshot.sqlite") as target:
            source.backup(target)
    write_json(TRACE / "trace-index.json", {"ledger_calls": len(ledger), "exact_requests_exported": len(seen),
        "unmatched_records_retained": len(unmatched), "raw_http_envelopes_available": False,
        "retention": "No artifact cleanup; keys and authentication headers are excluded."})
    return len(ledger), len(seen)


def archive(archive_name="CALM-S-experiments-20260923.zip"):
    paths = []
    for name in ("calms", "scripts_calms", "tests_calms", "calms_configs", "calms_data", "calms_runs", "docker", "results", "paper"):
        base = ROOT / name
        paths += [p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".tmp"]
    paths += [p for p in ROOT.iterdir() if p.is_file() and
              (p.name.startswith("CALMS_") or p.name in ("README_CALMS.md", "AAMAS_EXPERIMENT_PLAN.txt", "pyproject.toml", ".env.example", ".gitignore", ".dockerignore", "CALM-S.code-workspace", "CALM-S-code.zip"))]
    # Do not include the active SQLite file; the consistent backup is retained.
    paths = sorted(set(p for p in paths if p != LEDGER and p.name not in (".env", "api_ledger.sqlite-wal", "api_ledger.sqlite-shm")))
    keys = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                value = value.strip().strip("\"'")
                if value:
                    keys.append(value.encode())
    hashes = []
    if Path(archive_name).name != archive_name or not archive_name.endswith(".zip"):
        raise ValueError("Archive name must be a local .zip filename")
    destination = ROOT / archive_name
    if destination.exists():
        raise ValueError("Archive already exists; preserve it and choose a new filename")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in paths:
            content = p.read_bytes()
            if any(secret in content for secret in keys):
                raise ValueError("Credential scan rejected an artifact; archive must not be distributed")
            relative = p.relative_to(ROOT).as_posix()
            hashes.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            z.writestr(relative, content)
        z.writestr("ARCHIVE_MANIFEST.json", json.dumps({"files": hashes,
            "scope": "All CALM-S generated data and source artifacts; no unrelated aamas repository or credentials.",
            "response_scope": "Original model text, parsed usage/latency/IDs, exact hash-verified reconstructed requests. Raw HTTP envelopes were not recorded.",
            "code_sha256": code_hash()}, indent=2))
    receipt = ROOT / ("CALMS_ARCHIVE_RECEIPT.json" if archive_name == "CALM-S-experiments-20260923.zip"
                      else archive_name.removesuffix(".zip") + "-receipt.json")
    write_json(receipt, {"archive": destination.name, "files": len(hashes),
               "bytes": destination.stat().st_size, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
               "credential_scan": "passed", "original_artifacts_retained": True})
    return str(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--archive-name", default="CALM-S-experiments-20260923.zip")
    args = parser.parse_args()
    if read_json(ROOT / "calms_runs/expanded-20260923/progress.json")["status"] != "complete":
        raise SystemExit("Wait for the live run to complete before final trace export.")
    ledger, traced = export_traces()
    print(json.dumps({"ledger_calls": ledger, "verified_traces": traced, "archive": archive(args.archive_name) if args.archive else None}))


if __name__ == "__main__":
    main()
