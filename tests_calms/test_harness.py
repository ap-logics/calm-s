import copy
import json
import math
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from calms.analysis import analyze, fit_static, forecast_analysis
from calms.attacks import attacks
from calms.cli import main
from calms.common import ROOT, digest, jsonl, manifest, read_json, write_jsonl
from calms.data import load_tasks, make_fixtures, public_node, validate_tasks, verify
from calms.live import collect, collection_plan, forecast_prompt, parse_forecast, workflow
from calms.mechanism import Pool, audit_design, choose, draw_audit, expected_score
from calms.offline import propensity, replay, run_stream, simulate, strategic, synthetic
from calms.providers import BudgetExceeded, Client, PendingRequest, parse_response, upper_cost, validate_config


def config():
    base = {"provider": "openai", "model": "fake-test-only", "max_output_tokens": 100,
            "input_per_million": .4, "cached_input_per_million": .1, "output_per_million": 1.6}
    return {"workers": [{**base, "id": "w0"}, {**base, "id": "w1"}],
            "forecasters": [{**base, "id": "f0"}, {**base, "id": "f1"}]}


def response(text, provider="openai"):
    if provider == "openai":
        return {"id": "fake", "model": "fake-test-only", "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": text}]}],
                "usage": {"input_tokens": 10, "output_tokens": 10}}
    return {"id": "fake", "model": "fake-test-only", "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 10, "output_tokens": 10}}


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        # Even if production code regresses, tests cannot contact either provider.
        self.block = patch("urllib.request.urlopen", side_effect=AssertionError("NETWORK FORBIDDEN IN TESTS"))
        self.block.start()

    def tearDown(self):
        self.block.stop()
        self.temp.cleanup()


class LedgerTests(TemporaryTest):
    def client(self, cap=1, transport=None):
        return Client(self.path / "ledger.sqlite", cap, self.path / "nonexistent.env",
                      transport=transport or (lambda m, p: response("answer", m["provider"])))

    def test_spend_and_cache_survive_restart(self):
        c = self.client()
        m = config()["workers"][0]
        first = c.call(m, "question", [0])
        self.assertFalse(first["cache_hit"])
        total = c.total()
        c.close()
        c = self.client(transport=lambda m, p: self.fail("Cached request was resent"))
        self.assertTrue(c.call(m, "question", [0])["cache_hit"])
        self.assertEqual(total, c.total())
        c.close()

    def test_budget_checked_before_transport(self):
        c = self.client(cap=.000001, transport=lambda m, p: self.fail("Over-budget network call"))
        with self.assertRaises(BudgetExceeded):
            c.call(config()["workers"][0], "question", [0])
        self.assertEqual(c.total(), 0)
        c.close()

    def test_timeout_keeps_reservation_and_blocks_retry(self):
        def timeout(m, p):
            raise TimeoutError("do not print server text")
        c = self.client(transport=timeout)
        with self.assertRaises(RuntimeError):
            c.call(config()["workers"][0], "question", [0])
        self.assertGreater(c.total(), 0)
        with self.assertRaises(PendingRequest):
            c.call(config()["workers"][0], "question", [0])
        c.close()

    def test_repeat_identity_makes_new_call(self):
        c = self.client()
        m = config()["workers"][0]
        c.call(m, "same", [0])
        total = c.total()
        c.call(m, "same", [1])
        self.assertAlmostEqual(c.total(), 2 * total)
        c.close()

    def test_providers_charge_usage(self):
        m = config()["workers"][0]
        for provider in ("openai", "anthropic"):
            parsed = parse_response(provider, response("ok", provider), m)
            self.assertAlmostEqual(parsed["cost_usd"], .00002)
            self.assertTrue(parsed["complete"])

    def test_cached_input_accounting(self):
        m = config()["workers"][0]
        body = response("ok")
        body["usage"]["input_tokens_details"] = {"cached_tokens": 5}
        self.assertAlmostEqual(parse_response("openai", body, m)["cost_usd"], .0000185)

    def test_missing_live_flag_never_reads_keys(self):
        with patch("calms.providers.load_env", side_effect=AssertionError("KEYS MUST NOT BE READ")):
            with self.assertRaises(SystemExit) as err:
                main(["collect", "--tasks", "missing", "--split", "test", "--output", str(self.path), "--max-usd", "1"])
            self.assertEqual(err.exception.code, 2)

    def test_preflight_never_reads_keys(self):
        with patch("calms.providers.load_env", side_effect=AssertionError("KEYS MUST NOT BE READ")):
            main(["preflight", "--config", str(ROOT / "calms_configs/pilot.json"),
                  "--tasks", str(ROOT / "examples/calms_tasks.jsonl")])


class MechanismTests(TemporaryTest):
    def test_truthful_expected_score_maximizes(self):
        for p in (.1, .3, .5, .7, .9):
            for i in range(101):
                self.assertLessEqual(expected_score(p, i / 100), expected_score(p, p) + 1e-12)

    def test_ht_unbiased_under_nonuniform_audits(self):
        pi = [.01, .02, .04, .08]
        scores = [.2, .7, .4, .9]
        self.assertAlmostEqual(sum(p * s / p for p, s in zip(pi, scores)), sum(scores))

    def test_audit_support_and_expected_cost(self):
        costs = [.01, .03, .1, .2]
        d = audit_design(costs, .02, .5, [1, 2, 4, 8])
        self.assertTrue(all(p > 0 for p in d["pi"]))
        self.assertAlmostEqual(sum(p * c for p, c in zip(d["pi"], costs)), .01)
        self.assertEqual(d["reserve"], .2)

    def test_zero_audit_has_no_support(self):
        d = audit_design([1, 2], 0, 3)
        self.assertEqual(d["pi"], [0, 0])
        self.assertIsNone(draw_audit(d, 1))

    def test_audit_draw_is_repeatable_without_reports(self):
        d = audit_design([.1] * 4, .5, 1)
        self.assertEqual([draw_audit(d, t) for t in range(30)], [draw_audit(d, t) for t in range(30)])

    def test_pool_updates_only_after_explicit_feedback(self):
        pool = Pool(2, 2)
        reports = [[.9, .9], [.1, .1]]
        self.assertEqual(pool.predict("x", reports), [.5, .5])
        pool.update("x", reports, [(0, 1, .5)])
        self.assertGreater(pool.predict("x", reports)[0], .5)

    def test_all_pooling_methods_normalized(self):
        for method in ("equal", "exponential", "stacking", "bayesian"):
            pool = Pool(2, 2, method=method)
            pool.update("x", [[0, 1], [1, 0]], [(0, 0, .001)])
            self.assertAlmostEqual(sum(pool.weights("x")), 1)
            self.assertTrue(all(math.isfinite(w) and w >= 0 for w in pool.weights("x")))

    def test_premium_does_not_fallback_to_cheaper_model(self):
        self.assertIsNone(choose("premium", [.5, .9], [.01, .1], .05, 1, [], [], [0]))

    def test_lookahead_respects_total_path_cost(self):
        self.assertIsNone(choose("calms", [.9, .99], [.1, .2], .25, 1, [], [], [0], remaining=3))

    def test_shift_forecasts_do_not_read_latent_p(self):
        records = synthetic(0, 10)
        changed = copy.deepcopy(records)
        for record in changed:
            record["true_p"] = [0, 0, 0, 0]
        a = run_stream(records, "calms", 0, .12, .1, learned=True)
        b = run_stream(changed, "calms", 0, .12, .1, learned=True)
        self.assertEqual([r["reports"] for r in a], [r["reports"] for r in b])
        self.assertEqual([r["selected"] for r in a], [r["selected"] for r in b])

    def test_current_hidden_outcomes_do_not_change_current_decision(self):
        records = synthetic(0, 2)
        changed = copy.deepcopy(records)
        for rep in changed[0]["outcomes"]:
            for w in rep:
                w["outcome"] = 1 - w["outcome"]
        a = run_stream(records, "calms", 0, .12, .1, learned=True)[0]
        b = run_stream(changed, "calms", 0, .12, .1, learned=True)[0]
        self.assertEqual(a["reports"], b["reports"])
        self.assertEqual(a["selected"], b["selected"])
        self.assertEqual(a["audit"], b["audit"])

    def test_episode_budgets_all_policies(self):
        from calms.mechanism import POLICIES
        for policy in POLICIES:
            for budget in (.001, .04, .12, 1):
                rows = run_stream(synthetic(0, 20), policy, 0, budget, .1, learned=True, beta=.00001)
                self.assertTrue(all(row["cost"] <= budget + 1e-9 for row in rows))


class DataAndRunTests(TemporaryTest):
    def test_public_prompt_excludes_labels(self):
        task = load_tasks(ROOT / "examples/calms_tasks.jsonl")[0]
        task["nodes"][0]["verifier"]["answers"] = ["SECRET_LABEL"]
        public = public_node(task, task["nodes"][0], {})
        self.assertNotIn("SECRET_LABEL", forecast_prompt(public, config(), []))
        self.assertNotIn("verifier", public)

    def test_verifiers(self):
        self.assertEqual(verify("The Norway.", {"type": "exact", "answers": ["Norway"]}), 1)
        self.assertEqual(verify('[1,2]', {"type": "json", "expected": [1, 2]}), 1)
        self.assertEqual(verify('[2,1]', {"type": "json", "expected": [1, 2]}), 0)
        with self.assertRaises(RuntimeError):
            verify("raise Exception()", {"type": "python", "tests": "assert True"})

    def test_code_early_exit_is_not_success(self):
        with patch("calms.data.shutil.which", return_value="fake-docker"), \
                patch("calms.data.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            self.assertEqual(verify("raise SystemExit(0)", {"type": "python", "tests": "assert False"}, "fake-image"), 0)

    def test_cycles_and_split_leakage_rejected(self):
        tasks = load_tasks(ROOT / "examples/calms_tasks.jsonl")
        tasks[0]["nodes"][0]["parents"] = ["answer"]
        with self.assertRaises(ValueError):
            validate_tasks(tasks)
        tasks = load_tasks(ROOT / "examples/calms_tasks.jsonl")
        tasks[1]["cluster_id"] = tasks[0]["cluster_id"]
        with self.assertRaises(ValueError):
            validate_tasks(tasks)

    def test_forecast_invalid_fallback(self):
        workers = config()["workers"]
        for text in ('{"w0":true,"w1":0.5}', '{"w0":NaN,"w1":0.5}', 'garbage', '{"w0":2,"w1":0.5}'):
            qs, valid = parse_forecast(text, workers)
            self.assertFalse(valid)
            self.assertEqual(qs, [.5, .5])

    def test_manifest_rejects_changed_settings(self):
        manifest(self.path, {"config": 1})
        manifest(self.path, {"config": 1})
        with self.assertRaises(ValueError):
            manifest(self.path, {"config": 2})

    def test_collection_resume_and_analysis_without_network(self):
        calls = []
        def fake(model, prompt):
            calls.append(prompt)
            if "Predict each worker" in prompt:
                text = '{"w0":0.9,"w1":0.8}'
            elif "Switzerland" in prompt:
                text = "Switzerland"
            else:
                text = "[1,2,5,8]"
            return response(text)
        c = Client(self.path / "ledger.sqlite", 1, self.path / "none", transport=fake)
        tasks = load_tasks(ROOT / "examples/calms_tasks.jsonl", "test")
        directory = self.path / "collect"
        rows = collect(c, config(), tasks, directory)
        self.assertEqual(len(calls), 12)  # 2 tasks * (2 forecasts + 2 workers * 2 decodes)
        collect(c, config(), tasks, directory)
        self.assertEqual(len(calls), 12)
        for r in rows:
            self.assertTrue(all(w["outcome"] == 1 for rep in r["outcomes"] for w in rep))
        forecast_analysis(directory / "matrix.jsonl", self.path / "forecasts")
        replay(directory / "matrix.jsonl", self.path / "replay", policies=("equal", "calms"))
        analyze(self.path / "replay/episodes.jsonl", self.path / "analysis", "cluster_id", resamples=100)
        self.assertTrue((self.path / "analysis/paired_contrasts.csv").exists())
        c.close()

    def test_workflow_uses_actual_upstream_outputs_and_resumes(self):
        make_fixtures(self.path / "tasks.jsonl", 2)
        tasks = load_tasks(self.path / "tasks.jsonl", "test")
        observed = []
        def fake(model, prompt):
            if "Predict each worker" in prompt:
                return response('{"w0":0.99,"w1":0.99}')
            public = json.loads(prompt.split("\n", 1)[1])
            observed.append(public)
            # Evaluator labels used ONLY inside the fake test provider, never real prompts.
            expected = next(n["verifier"]["expected"] for n in tasks[0]["nodes"] if n["id"] == public["node_id"])
            return response(json.dumps(expected))
        c = Client(self.path / "ledger.sqlite", 1, self.path / "none", transport=fake)
        rows = workflow(c, config(), tasks, self.path / "workflow", "calms", .5, .02)
        self.assertEqual(rows[0]["completed"], 1)
        self.assertTrue(any(p["upstream_outputs"] for p in observed))
        total = c.total()
        again = workflow(c, config(), tasks, self.path / "workflow", "calms", .5, .02)
        self.assertEqual(total, c.total())
        self.assertEqual(rows[0]["net_value"], again[0]["net_value"])
        c.close()

    def test_simulator_reproducible(self):
        a = simulate(self.path / "a", 2, 8, [.02], policies=("equal", "calms"))
        b = simulate(self.path / "b", 2, 8, [.02], policies=("equal", "calms"))
        self.assertEqual(a, b)
        analyze(self.path / "a/episodes.jsonl", self.path / "analysis", "seed", resamples=100)

    def test_analysis_rejects_unpaired_tasks(self):
        rows = simulate(self.path / "sim", 2, 8, [.02], policies=("equal", "calms"))
        write_jsonl(self.path / "partial.jsonl", rows[:-1])
        with self.assertRaises(ValueError):
            analyze(self.path / "partial.jsonl", self.path / "report", "seed", resamples=100)

    def test_strategic_and_propensity_exact_checks(self):
        rows = strategic(self.path / "strategic.csv")
        honest = [r for r in rows if r["mechanism"] == "separated_audit" and r["side_interest"] == 0]
        self.assertTrue(all(r["deviation_gain"] <= 1e-12 for r in honest))
        rows = propensity(self.path / "propensity.csv", trials=100)
        self.assertTrue(all(abs(r["exact_bias"]) < 1e-10 for r in rows if r["estimator"] == "ht"))
        self.assertTrue(any(abs(r["exact_bias"]) > .01 for r in rows if r["estimator"] == "unweighted"))

    def test_calibration_requires_dev_data(self):
        records = synthetic(0, 4)
        write_jsonl(self.path / "matrix.jsonl", records)
        with self.assertRaises(ValueError):
            fit_static(self.path / "matrix.jsonl", self.path / "fit.json")

    def test_offline_cost_plan_and_call_counts(self):
        tasks = load_tasks(ROOT / "examples/calms_tasks.jsonl", "test")
        plan = collection_plan(config(), tasks, 2)
        self.assertEqual(plan["worker_calls"], 8)
        self.assertEqual(plan["forecast_calls"], 4)
        self.assertEqual(plan["network_calls"], 0)
        self.assertGreater(plan["conservative_api_reservation_usd"], 0)

    def test_attacks_fit_does_not_use_test_outcomes(self):
        dev, test = synthetic(1, 4), synthetic(2, 4)
        for row in dev:
            row["split"] = "dev"
        for row in dev + test:
            for rep in row["outcomes"]:
                for i, w in enumerate(rep):
                    w["worker_id"] = f"w{i}"
        write_jsonl(self.path / "dev.jsonl", dev)
        write_jsonl(self.path / "test.jsonl", test)
        attacks(self.path / "dev.jsonl", self.path / "test.jsonl", self.path / "attack1")
        for row in test:
            for rep in row["outcomes"]:
                for w in rep:
                    w["outcome"] = 1 - w["outcome"]
        write_jsonl(self.path / "test.jsonl", test)
        attacks(self.path / "dev.jsonl", self.path / "test.jsonl", self.path / "attack2")
        self.assertEqual(read_json(self.path / "attack1/development_fits.json"),
                         read_json(self.path / "attack2/development_fits.json"))

    def test_attacks_reject_cluster_leakage(self):
        dev, test = synthetic(0, 2), synthetic(0, 2)
        for row in dev:
            row["split"] = "dev"
        write_jsonl(self.path / "dev.jsonl", dev)
        write_jsonl(self.path / "test.jsonl", test)
        with self.assertRaises(ValueError):
            attacks(self.path / "dev.jsonl", self.path / "test.jsonl", self.path / "attack")


if __name__ == "__main__":
    unittest.main()
