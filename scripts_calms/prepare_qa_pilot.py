"""Download authors' public MuSiQue data and freeze a small disjoint pilot.

No provider API access. A pilot subset, not an official leaderboard evaluation.
"""
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import digest, read_json, rng, write_json, write_jsonl
from calms.data import import_tasks, load_tasks
from calms.live import collection_plan

URL = "https://drive.google.com/uc?export=download&id=1tGdADlNjWFaHLeZZGShh2IRcpO6Lv24h"


class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action, self.fields = None, {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.action = attrs.get("action")
        if tag == "input" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")


def download(path):
    if path.exists() and zipfile.is_zipfile(path):
        return
    with urllib.request.urlopen(URL, timeout=45) as response:
        head = response.read(4096)
        if head.startswith(b"PK"):
            content = head + response.read()
        else:
            form = Form()
            form.feed((head + response.read()).decode("utf-8"))
            if urllib.parse.urlparse(form.action or "").hostname != "drive.usercontent.google.com":
                raise RuntimeError("Unexpected public download confirmation form")
            request_url = form.action + "?" + urllib.parse.urlencode(form.fields)
            with urllib.request.urlopen(request_url, timeout=60) as response2:
                content = response2.read()
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise RuntimeError("Authors' download did not return the dataset archive")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def source_ids(row):
    return {str(q["id"]) for q in row.get("question_decomposition", [])}


def sample(rows, forbidden, split):
    rows = sorted(rows, key=lambda r: digest([20260923, split, r["id"]]))
    selected = []
    used = set(forbidden)
    # Ten problems of each hop length, selected independently of outcomes.
    for hops in (2, 3, 4):
        count = 0
        for row in rows:
            if len(row.get("question_decomposition", [])) != hops or source_ids(row) & used:
                continue
            # Keep complete context; no silent clipping or context-length selection.
            selected.append(row)
            used |= source_ids(row)
            count += 1
            if count == 10:
                break
        if count != 10:
            raise RuntimeError("Not enough disjoint questions at a requested hop length")
    return selected, used


def main():
    raw = ROOT / "calms_data/raw/musique_v1.0.zip"
    output = ROOT / "calms_data/qa-pilot"
    if (output / "dataset_manifest.json").exists():
        print("Pilot dataset is already frozen at", output)
        return
    download(raw)
    with zipfile.ZipFile(raw) as z:
        def rows(split):
            matches = [n for n in z.namelist() if n.endswith("musique_ans_v1.0_" + split + ".jsonl") and not n.startswith("__MACOSX/")]
            if len(matches) != 1:
                raise RuntimeError("Dataset member missing or ambiguous")
            return [json.loads(line) for line in z.read(matches[0]).decode("utf-8").splitlines() if line.strip()]
        dev, used = sample(rows("train"), set(), "dev")
        test, _ = sample(rows("dev"), used, "test")
    config = read_json(ROOT / "calms_configs/pilot.json")
    plans = {}
    for split, selected in (("dev", dev), ("test", test)):
        source = output / f"{split}-source.jsonl"
        target = output / f"{split}.jsonl"
        write_jsonl(source, selected)
        import_tasks(source, target, "musique", split, .25)
        plans[split] = collection_plan(config, load_tasks(target, split), 2)
        write_json(output / f"{split}-cost-plan.json", plans[split])
    write_json(output / "dataset_manifest.json", {
        "purpose": "CALM-S exploratory QA pilot; not confirmatory or official leaderboard",
        "source": URL, "authors_repository": "https://github.com/StonyBrookNLP/musique",
        "license": "CC-BY-4.0", "archive_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "selection_seed": 20260923, "dev_source_split": "MuSiQue-Ans train",
        "test_source_split": "MuSiQue-Ans dev", "per_split": 30, "hop_counts": {"2": 10, "3": 10, "4": 10},
        "source_singlehop_ids_disjoint": True, "test_task_ids": [r["id"] for r in test],
        "dev_task_ids": [r["id"] for r in dev], "reward_usd_equivalent": .25,
        "verifier": "Harness normalized exact answer match with dataset aliases; not official full metric",
        "decodes_per_worker": 2, "worker_calls": 480, "forecast_calls": 180,
        "conservative_api_reservation_usd": sum(p["conservative_api_reservation_usd"] for p in plans.values())})
    print(json.dumps({"prepared": str(output), "dev_tasks": 30, "test_tasks": 30,
                      "calls": 660, "conservative_reservation_usd": sum(p["conservative_api_reservation_usd"] for p in plans.values())}))


if __name__ == "__main__":
    main()
