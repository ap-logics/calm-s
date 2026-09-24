"""Freeze the second CALM-S study without API access or evaluation outcomes."""
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import digest, jsonl, mean, read_json, write_json, write_jsonl
from calms.data import public_node, validate_tasks
from calms.live import collection_plan, worker_prompt

DATA = ROOT / "calms_data/expanded-20260923"


def components(row):
    return {str(q["id"]) for q in row["question_decomposition"]}


def select(rows, used, group, per_hop):
    chosen = []
    ordered = sorted(rows, key=lambda r: digest([2026092302, group, r["id"]]))
    for hops in (4, 3, 2):
        target = per_hop[hops] if isinstance(per_hop, dict) else per_hop
        batch = []
        for row in ordered:
            if len(row["question_decomposition"]) == hops and not components(row) & used:
                batch.append(row)
                used.update(components(row))
                if len(batch) == target:
                    break
        if len(batch) != target:
            raise ValueError(f"Insufficient disjoint {group} {hops}-hop questions")
        chosen.extend(batch)
    return sorted(chosen, key=lambda r: digest(["stream-order", group, r["id"]]))


def context(row):
    return "\n\n".join(p["title"] + "\n" + p["paragraph_text"] for p in row["paragraphs"])


def qa_task(row, split):
    return {"id": row["id"], "cluster_id": row["id"], "family": "musique", "split": split,
            "reward": .25, "nodes": [{"id": "answer", "parents": [],
            "prompt": context(row) + "\nQuestion: " + row["question"] +
                      "\nReturn only the short answer, without explanation.",
            "verifier": {"type": "exact", "answers": [row["answer"], *row.get("answer_aliases", [])]}}]}


def workflow_task(row, split):
    nodes = []
    for i, sub in enumerate(row["question_decomposition"], 1):
        refs = sorted({int(s) for s in re.findall(r"#(\d+)", sub["question"])})
        if any(r >= i or r < 1 for r in refs):
            raise ValueError("Invalid decomposition reference")
        answers = [sub["answer"]]
        if i == len(row["question_decomposition"]):
            answers += [row["answer"], *row.get("answer_aliases", [])]
        nodes.append({"id": f"h{i}", "parents": [f"h{r}" for r in refs],
            "prompt": context(row) + "\nQuestion: " + sub["question"] +
            "\nReplace each #k reference with the actual upstream answer named hk. "
            "The notation 'X >> relation' asks for that relation of X. "
            "Return only the short answer, without explanation.",
            "verifier": {"type": "exact", "answers": list(dict.fromkeys(answers))}})
    return {"id": "dag-" + row["id"], "cluster_id": row["id"], "family": "musique-decomposed",
            "split": split, "reward": .25, "nodes": nodes}


def fit_config(config, records, tasks, label):
    """Aggregate only permitted development outcomes; never test outcomes."""
    if any(r["split"] != "dev" for r in records):
        raise ValueError("Capability and cost fitting requires development-only records")
    by_id = {t["id"]: t for t in tasks}
    result = copy.deepcopy(config)
    for w, worker in enumerate(result["workers"]):
        ratios, outputs, outcomes = [], [], []
        for r in records:
            task = by_id[r["task_id"]]
            size = len(worker_prompt(public_node(task, task["nodes"][0], {})).encode("utf-8"))
            for rep in r["outcomes"]:
                outcome = rep[w]
                ratios.append((outcome["input_tokens"] + outcome["cached_tokens"]) / size
                              if worker["provider"] == "anthropic" else outcome["input_tokens"] / size)
                outputs.append(outcome["output_tokens"])
                outcomes.append(outcome["outcome"])
        worker["cost_estimator"] = {"input_tokens_per_byte": mean(ratios), "mean_output_tokens": mean(outputs)}
        worker["description"] = (f"{label}: {sum(outcomes)} correct of {len(outcomes)} decodes on "
            f"{len(records)} development opportunities. This is a noisy historical rate, not this task's answer. "
            "Use task difficulty as well; success requires an exact short answer and no explanation.")
    result["purpose"] = "Expanded CALM-S study; development-fitted cards and cost estimates"
    result["development_fit"] = {"matrix_sha256": digest(records), "training_clusters": sorted({r["cluster_id"] for r in records}),
                                "utility_costs_only": True, "budget_reserves_unchanged": True}
    return result


def main():
    if (DATA / "protocol.json").exists():
        print("Expanded protocol already frozen", DATA)
        return
    old_sources = jsonl(ROOT / "calms_data/qa-pilot/dev-source.jsonl") + jsonl(ROOT / "calms_data/qa-pilot/test-source.jsonl")
    used = set().union(*(components(r) for r in old_sources))
    raw = ROOT / "calms_data/raw/musique_v1.0.zip"
    with zipfile.ZipFile(raw) as z:
        def source(split):
            names = [n for n in z.namelist() if n.endswith(f"musique_ans_v1.0_{split}.jsonl") and not n.startswith("__MACOSX/")]
            if len(names) != 1:
                raise ValueError("Ambiguous data source")
            return [json.loads(line) for line in z.read(names[0]).decode().splitlines() if line.strip()]
        train, test = source("train"), source("dev")
    groups = {}
    for group, source_rows, per_hop in (("dev", train, 20), ("workflow-dev", train, 4),
                                      ("workflow-test", test, {2: 12, 3: 9, 4: 3}),
                                      ("test", test, {2: 90, 3: 50, 4: 10})):
        groups[group] = select(source_rows, used, group, per_hop)
    config = fit_config(read_json(ROOT / "calms_configs/pilot.json"),
                        jsonl(ROOT / "calms_runs/qa-pilot-20260923/dev/matrix.jsonl"),
                        jsonl(ROOT / "calms_data/qa-pilot/dev.jsonl"), "Whole multi-hop QA pilot")
    write_json(DATA / "config.json", config)
    plans = {}
    for group, rows in groups.items():
        split = "dev" if group.endswith("dev") else "test"
        write_jsonl(DATA / f"{group}-source.jsonl", rows)
        tasks = [workflow_task(r, split) if group.startswith("workflow") else qa_task(r, split) for r in rows]
        write_jsonl(DATA / f"{group}.jsonl", validate_tasks(tasks))
        if not group.startswith("workflow"):
            plans[group] = collection_plan(config, tasks, 2)
            write_json(DATA / f"{group}-cost-plan.json", plans[group])
    # Node-calibration tasks use known upstream answers ONLY on development data.
    # Final on-policy workflow evaluation always consumes actual worker outputs.
    flattened = []
    for row in groups["workflow-dev"]:
        task = workflow_task(row, "dev")
        for i, node in enumerate(task["nodes"]):
            public = {p: row["question_decomposition"][int(p[1:])-1]["answer"] for p in node["parents"]}
            flattened.append({"id": task["id"] + "-" + node["id"], "cluster_id": row["id"],
                "family": task["family"], "split": "dev", "reward": .25, "nodes": [{**node, "parents": [],
                    "prompt": node["prompt"] + "\nSupplied earlier answers: " + json.dumps(public)}]})
    write_jsonl(DATA / "workflow-node-dev.jsonl", validate_tasks(flattened))
    plans["workflow-node-dev"] = collection_plan(config, flattened, 2)
    write_json(DATA / "workflow-node-dev-cost-plan.json", plans["workflow-node-dev"])
    write_json(DATA / "protocol.json", {
        "frozen_before_new_calls": True, "date": "2026-09-23", "total_api_cap_usd": 100,
        "previous_spend_included": True, "seed": 2026092302,
        "source_archive_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "source": "https://github.com/StonyBrookNLP/musique", "license": "CC-BY-4.0",
        "all_groups_and_previous_pilot_component_disjoint": True,
        "task_ids": {g: [r["id"] for r in rows] for g, rows in groups.items()},
        "hop_counts": {g: {str(h): sum(len(r["question_decomposition"]) == h for r in rows) for h in (2, 3, 4)} for g, rows in groups.items()},
        "hop_allocation_note": "Unequal test allocation fixed before calls due to scarcity of disjoint 4-hop components; report hop strata separately.",
        "data_hashes": {p.name: digest(jsonl(p)) for p in DATA.glob("*.jsonl")},
        "collection_calls": sum(p["worker_calls"] + p["forecast_calls"] for p in plans.values()),
        "collection_upper_reservation_usd": sum(p["conservative_api_reservation_usd"] for p in plans.values()),
        "expected_collection_cost_usd": "Approximately $11-$18 based on first pilot; not a guarantee",
        "qa": {"dev": 60, "test": 150, "worker_decodes": 2, "forecasters": 3,
               "test_streams": 10, "tasks_per_stream": 15, "rates": [0, .005, .01, .02, .05, .1],
               "budgets": [.10, .20, .40], "primary_budget": .20,
               "rate_selection": "maximize mean dev CALM-S net value over strictly positive rates; ties choose lower",
               "comparator_selection": "best dev of cheapest, premium, static, explore, equal, selected",
               "reward": .25, "reward_sensitivity": [.05, .10, .25, .50, 1.0],
               "primary_inference": "paired bootstrap of 10 disjoint stream means, not cached replicate seeds",
               "cost_ablation": "same frozen outcomes with utility cost estimate versus original conservative offer"},
        "workflow": {"dev_projects": 12, "dev_nodes": len(flattened), "test_projects": 24,
                     "streams": 3, "tasks_per_stream": 8, "budget": .60, "rate": .02,
                     "policies": ["static", "explore", "equal", "selected", "calms"],
                     "real_upstream_outputs": True, "fail_fast": True,
                     "scope": "MuSiQue decomposition-derived QA workflow, not AppWorld; descriptive n=3 streams"},
        "limitations": ["Public benchmark may have model contamination", "Normalized exact answer matching, not official full MuSiQue metrics",
                        "No real scoring transfers", "Forecasts frozen in QA replay; recomputed on-policy for workflow",
                        "Prospective expanded study after inspecting first pilot; not an externally registered study",
                        "Conservative feasibility reserves retained; budget settings are engineering choices, not matched realized spend"]})
    print(json.dumps({"prepared": str(DATA), "tasks": {g: len(r) for g, r in groups.items()},
                      "collection_calls": sum(p["worker_calls"] + p["forecast_calls"] for p in plans.values()),
                      "conservative_collection_usd": sum(p["conservative_api_reservation_usd"] for p in plans.values())}))


if __name__ == "__main__":
    main()
