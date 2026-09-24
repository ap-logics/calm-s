"""Explicit provider model-access check. No generations and no key disclosure."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import load_env, read_json, write_json
import os


def main():
    load_env(ROOT / ".env")
    config = read_json(ROOT / "calms_configs/pilot.json")
    results = {}
    for provider, keyname, url in (
        ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1/models"),
        ("anthropic", "ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/models?limit=100"),
    ):
        requested = sorted({m["model"] for role in ("workers", "forecasters") for m in config[role] if m["provider"] == provider})
        key = os.environ.get(keyname)
        if not key:
            results[provider] = {"status": "key_missing"}
            continue
        headers = {"Authorization": "Bearer " + key} if provider == "openai" else {"x-api-key": key, "anthropic-version": "2023-06-01"}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                body = json.load(response)
            models = {m["id"] for m in body["data"]}
            results[provider] = {"status": "authenticated", "requested_models": {m: m in models for m in requested},
                                 "more_pages": body.get("has_more", False)}
        except urllib.error.HTTPError as exc:
            results[provider] = {"status": "http_error", "http_status": exc.code}
        except (OSError, ValueError, KeyError):
            results[provider] = {"status": "connection_or_response_error"}
    write_json(ROOT / "calms_runs/provider_access.json", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
