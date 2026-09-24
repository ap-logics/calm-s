"""Deterministic random streams, atomic outputs, and immutable run manifests."""
import csv
import hashlib
import json
import math
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rng(*parts):
    return random.Random(int(digest(parts)[:16], 16))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        raise ValueError("No rows to write")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def jsonl(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")
    os.replace(tmp, path)


def code_hash():
    return digest({p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "calms").glob("*.py"))})


def manifest(directory, spec):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    spec = {"schema": 1, "code_sha256": code_hash(), **spec}
    path = directory / "manifest.json"
    if path.exists() and read_json(path) != spec:
        raise ValueError("Run manifest differs (code/config/data). Use a new output directory.")
    if not path.exists():
        write_json(path, spec)
    return spec


def load_env(path):
    """Read only the two supported keys; never interpolate or print secrets."""
    path = Path(path)
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            key = key.strip()
            if sep and key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                value = value.strip().strip("\"'")
                if value:
                    os.environ.setdefault(key, value)


def finite(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"Invalid {name}")
    return value


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0
