"""Task schema, local benchmark imports and deterministic non-LLM verifiers."""
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .common import canonical, finite, jsonl, rng, write_jsonl


def unfence(text):
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip()


def normalized(text):
    text = re.sub(r"[^\w\s]", "", str(text).lower())
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", text).split())


def validate_tasks(tasks):
    ids = set()
    clusters = {}
    for task in tasks:
        if task["id"] in ids:
            raise ValueError("Duplicate task ID")
        ids.add(task["id"])
        if task["split"] not in ("dev", "test"):
            raise ValueError("split must be dev or test")
        key = task["cluster_id"]
        if key in clusters and clusters[key] != task["split"]:
            raise ValueError("Source cluster crosses dev/test split")
        clusters[key] = task["split"]
        finite(task["reward"], "reward")
        if not task.get("family") or not task.get("nodes"):
            raise ValueError("Task needs family and nodes")
        seen = set()
        for node in task["nodes"]:
            if node["id"] in seen or any(parent not in seen for parent in node.get("parents", [])):
                raise ValueError("Nodes must be unique and topologically ordered")
            seen.add(node["id"])
            if node["verifier"]["type"] not in ("exact", "json", "python"):
                raise ValueError("Unsupported verifier")
            if not node.get("prompt"):
                raise ValueError("Missing prompt")
    if not tasks:
        raise ValueError("Empty task dataset")
    return tasks


def load_tasks(path, split=None):
    tasks = validate_tasks(jsonl(path))
    selected = [t for t in tasks if split is None or t["split"] == split]
    if not selected:
        raise ValueError("No tasks in requested split")
    return selected


def public_node(task, node, outputs):
    # Allowlist; never serialize an entire task into an API prompt.
    return {"task_id": task["id"], "family": task["family"], "node_id": node["id"],
            "instruction": node["prompt"],
            "upstream_outputs": {p: outputs[p] for p in node.get("parents", [])}}


def verify(text, spec, docker_image=None):
    text = unfence(text)
    if spec["type"] == "exact":
        return int(normalized(text) in [normalized(x) for x in spec["answers"]])
    if spec["type"] == "json":
        try:
            return int(json.loads(text) == spec["expected"])
        except (ValueError, TypeError):
            return 0
    if not docker_image or not shutil.which("docker"):
        raise RuntimeError("Python verification needs Docker and --docker-image; never executes generated code on host")
    name = "calms-" + uuid.uuid4().hex
    marker = "CALMS_VERIFIED_" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="calms-code-") as directory:
        path = Path(directory) / "submission.py"
        path.write_text(text + "\n" + spec["tests"] + "\nprint(" + repr(marker) + ")\n", encoding="utf-8")
        command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
                   "--memory", "256m", "--cpus", "1", "--pids-limit", "64", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--user", "65534:65534", "--tmpfs", "/tmp:rw,size=16m",
                   "--mount", f"type=bind,source={directory},target=/work,readonly",
                   docker_image, "python", "-I", "-B", "/work/submission.py"]
        try:
            with tempfile.TemporaryFile() as captured:
                proc = subprocess.run(command, stdout=captured, stderr=subprocess.DEVNULL, timeout=20)
                if proc.returncode in (125, 126, 127):
                    raise RuntimeError("Docker verifier infrastructure failed; outcome not recorded")
                length = captured.tell()
                if length > 65536:
                    return 0
                captured.seek(0)
                # A generated early exit(0) must not bypass all appended tests.
                return int(proc.returncode == 0 and captured.read().rstrip().endswith(marker.encode()))
        except subprocess.TimeoutExpired:
            return 0
        finally:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)


def require_verifier(tasks, docker_image):
    if not any(n["verifier"]["type"] == "python" for t in tasks for n in t["nodes"]):
        return
    if not docker_image or not shutil.which("docker"):
        raise ValueError("Code tasks require a local Docker verifier image before any paid calls")
    p = subprocess.run(["docker", "image", "inspect", docker_image], capture_output=True, timeout=20)
    if p.returncode:
        raise ValueError("Docker image is not available locally. Build it before a paid run.")
    if verify("x = 1", {"type": "python", "tests": "assert x == 1"}, docker_image) != 1:
        raise ValueError("Docker verification smoke test failed")


def make_fixtures(path, count=12):
    """Constructed dependent JSON tasks, explicitly NOT an external benchmark."""
    tasks = []
    for i in range(count):
        values = rng("fixture", i).sample(range(1, 100), 12)
        kept = sorted(v for v in values if v % 3 != 0)
        doubled = [v * 2 for v in kept]
        tasks.append({"id": f"constructed-{i}", "cluster_id": f"constructed-{i}",
                      "family": "constructed-json-workflow", "split": "dev" if i % 4 == 0 else "test",
                      "reward": 0.25, "nodes": [
            {"id": "filter", "parents": [], "prompt": "Return only a JSON array: remove multiples of 3 and sort ascending: " + str(values),
             "verifier": {"type": "json", "expected": kept}},
            {"id": "double", "parents": ["filter"], "prompt": "Read the upstream array. Return only a JSON array with every value doubled.",
             "verifier": {"type": "json", "expected": doubled}},
            {"id": "aggregate", "parents": ["double"], "prompt": 'Read the upstream array. Return only JSON {"sum": sum of values, "count": number of values}.',
             "verifier": {"type": "json", "expected": {"sum": sum(doubled), "count": len(doubled)}}}]})
    write_jsonl(path, validate_tasks(tasks))


def import_tasks(source, output, kind, split, reward):
    rows = jsonl(source)
    tasks = []
    for row in rows:
        if kind == "musique":
            tid = str(row["id"])
            context = "\n".join(p["paragraph_text"] for p in row["paragraphs"])
            node = {"id": "answer", "parents": [], "prompt": context + "\nQuestion: " + row["question"] +
                    "\nReturn only the short answer, without explanation.",
                    "verifier": {"type": "exact", "answers": [row["answer"], *row.get("answer_aliases", [])]}}
        else:
            # Exported HumanEval-format records with explicit executable tests.
            # This does NOT silently claim EvalPlus expanded tests from base tests.
            tid = str(row["task_id"])
            node = {"id": "code", "parents": [], "prompt": "Return the complete Python solution, including the function definition.\n" + row["prompt"],
                    "verifier": {"type": "python", "tests": row["test"] + f"\ncheck({row['entry_point']})"}}
        tasks.append({"id": tid, "cluster_id": tid, "family": kind, "split": split,
                      "reward": reward, "nodes": [node]})
    write_jsonl(output, validate_tasks(tasks))
