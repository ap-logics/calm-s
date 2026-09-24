"""Direct provider APIs with a transactional spend ledger and request cache.

No automatic retry of ambiguous requests: a timeout may already be billable.
Unknown calls keep their full reservation and require manual reconciliation.
"""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from .common import canonical, digest, finite, load_env


class BudgetExceeded(RuntimeError):
    pass


class PendingRequest(RuntimeError):
    pass


def validate_config(config):
    for role in ("workers", "forecasters"):
        if not config.get(role):
            raise ValueError(f"Missing {role}")
        ids = [m["id"] for m in config[role]]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate {role} IDs")
        for m in config[role]:
            if m["provider"] not in ("openai", "anthropic"):
                raise ValueError("Only OpenAI and Anthropic are supported")
            if not m.get("model"):
                raise ValueError("Missing model ID")
            for rate in ("input_per_million", "output_per_million", "cached_input_per_million"):
                finite(m[rate], rate)
            if m["cached_input_per_million"] > m["input_per_million"]:
                raise ValueError("Cached input rate must not exceed reserved normal input rate")
            if not isinstance(m["max_output_tokens"], int) or not 1 <= m["max_output_tokens"] <= 8192:
                raise ValueError("max_output_tokens must be 1..8192")
    return config


def upper_cost(model, prompt):
    # Text-only, no hidden tool schemas. UTF-8 byte count + ample framing reserve.
    # Enforce short contexts so tiered long-context pricing is never entered.
    size = len(prompt.encode("utf-8"))
    if size > 60000:
        raise ValueError("Prompt exceeds the 60,000-byte harness limit")
    return ((size + 4096) * model["input_per_million"] +
            model["max_output_tokens"] * model["output_per_million"]) / 1e6


def estimated_cost(model, prompt):
    """Development-fitted utility estimate; NEVER used as a spending reserve."""
    estimate = model.get("cost_estimator")
    reserve = upper_cost(model, prompt)
    if estimate is None:
        return reserve
    ratio = finite(estimate["input_tokens_per_byte"], "input token estimate", 1e-9)
    output = finite(estimate["mean_output_tokens"], "output token estimate")
    tokens = len(prompt.encode("utf-8")) * ratio
    return min(reserve, (tokens * model["input_per_million"] +
                         output * model["output_per_million"]) / 1e6)


def parse_response(provider, body, model):
    usage = body["usage"]
    it = usage["input_tokens"]
    ot = usage["output_tokens"]
    if provider == "openai":
        cached = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
        text = "".join(c.get("text", "") for item in body.get("output", [])
                       for c in item.get("content", []) if c.get("type") == "output_text")
        complete = body.get("status") == "completed"
        cost = ((it - cached) * model["input_per_million"] + cached * model["cached_input_per_million"]
                + ot * model["output_per_million"]) / 1e6
    else:
        cached = usage.get("cache_read_input_tokens", 0)
        created = usage.get("cache_creation_input_tokens", 0)
        if created:
            raise ValueError("Unexpected cache creation; explicit caching is disabled")
        text = "".join(c["text"] for c in body.get("content", []) if c.get("type") == "text")
        complete = body.get("stop_reason") == "end_turn"
        cost = (it * model["input_per_million"] + cached * model["cached_input_per_million"]
                + ot * model["output_per_million"]) / 1e6
    finite(cost, "provider cost")
    return {"text": text, "complete": complete, "input_tokens": it, "output_tokens": ot,
            "cached_tokens": cached, "cost_usd": cost, "response_id": body.get("id"),
            "returned_model": body.get("model")}


class Client:
    def __init__(self, ledger, max_usd, env_path, live=False, transport=None):
        if not live and transport is None:
            raise ValueError("Paid requests require --live")
        finite(max_usd, "max_usd", 0.000001)
        load_env(env_path)
        self.max_usd, self.transport = max_usd, transport
        Path(ledger).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(ledger, timeout=30)
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, status TEXT, "
                        "cost REAL, reservation REAL, response TEXT)")
        self.db.commit()

    def close(self):
        self.db.close()

    def total(self):
        return self.db.execute("SELECT COALESCE(SUM(cost),0) FROM calls").fetchone()[0]

    def call(self, model, prompt, identity):
        request_key = digest({"model": model, "prompt": prompt, "identity": identity})
        reservation = upper_cost(model, prompt)
        key_name = "OPENAI_API_KEY" if model["provider"] == "openai" else "ANTHROPIC_API_KEY"
        if self.transport is None and not os.environ.get(key_name):
            raise ValueError(f"Missing {key_name}")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT status,response FROM calls WHERE key=?", (request_key,)).fetchone()
            if old:
                if old[0] != "done":
                    raise PendingRequest("A prior request has uncertain billing. Inspect ledger; automatic retry disabled.")
                self.db.commit()
                return {**json.loads(old[1]), "cache_hit": True}
            if self.total() + reservation > self.max_usd + 1e-12:
                raise BudgetExceeded("API spend ceiling would be exceeded; completed calls are resumable")
            self.db.execute("INSERT INTO calls VALUES (?, 'pending', ?, ?, NULL)",
                            (request_key, reservation, reservation))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        started = time.monotonic()
        try:
            if self.transport:
                body = self.transport(model, prompt)
            else:
                body = self._request(model, prompt, os.environ[key_name])
            result = parse_response(model["provider"], body, model)
            result.update(latency_seconds=time.monotonic() - started, request_sha256=request_key)
            self.db.execute("UPDATE calls SET status='done',cost=?,response=? WHERE key=?",
                            (result["cost_usd"], canonical(result), request_key))
            self.db.commit()
            if result["cost_usd"] > reservation + 1e-12:
                raise BudgetExceeded("Actual price exceeded reservation. Reconcile model pricing before continuing.")
            return {**result, "cache_hit": False}
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
            # No headers, key fragments, response bodies or server error text in logs.
            raise RuntimeError(f"Provider request failed ({type(exc).__name__}); reservation retained") from None

    @staticmethod
    def _request(model, prompt, key):
        if model["provider"] == "openai":
            url = "https://api.openai.com/v1/responses"
            payload = {"model": model["model"], "input": prompt,
                       "max_output_tokens": model["max_output_tokens"], "store": False}
            headers = {"Authorization": "Bearer " + key}
        else:
            url = "https://api.anthropic.com/v1/messages"
            payload = {"model": model["model"], "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": model["max_output_tokens"]}
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=canonical(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
