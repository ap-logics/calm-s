"""All network commands require an explicit --live flag and dollar ceiling."""
import argparse
import json
from pathlib import Path

from . import __version__
from .analysis import analyze, fit_static, forecast_analysis
from .attacks import attacks
from .common import ROOT, read_json, write_json
from .data import import_tasks, load_tasks, make_fixtures
from .dag import dag_simulate
from .live import collect, collection_plan, workflow
from .mechanism import POLICIES
from .offline import legacy_check, propensity, replay, simulate, strategic
from .providers import Client, validate_config


def parser():
    p = argparse.ArgumentParser(description="CALM-S experiments (not the nested AISTATS repository)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("check-legacy", help="Recompute provided result summaries and budget violations")
    s.add_argument("--source", default="results/episode_results.csv")
    s.add_argument("--output", default="calms_runs/legacy.csv")
    s.add_argument("--budget", type=float, default=2.2)
    s = sub.add_parser("fixtures", help="Create constructed JSON DAG tasks; no network")
    s.add_argument("--output", default="calms_data/constructed.jsonl")
    s.add_argument("--count", type=int, default=12)
    s = sub.add_parser("import", help="Convert local MuSiQue or HumanEval-format JSONL")
    s.add_argument("--kind", choices=("musique", "humaneval"), required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--split", choices=("dev", "test"), required=True)
    s.add_argument("--reward", type=float, default=.25)
    s = sub.add_parser("simulate", help="New feedback-only synthetic study; zero API calls")
    s.add_argument("--output", default="calms_runs/synthetic")
    s.add_argument("--seeds", type=int, default=30)
    s.add_argument("--episodes", type=int, default=80)
    s.add_argument("--shift", choices=("none", "capability", "mixture"), default="capability")
    s.add_argument("--rates", type=float, nargs="+", default=[0, .005, .01, .02, .05, .1])
    s.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    s.add_argument("--pooling", choices=("equal", "exponential", "bayesian", "stacking"), default="exponential")
    s.add_argument("--delay", type=int, default=1)
    s.add_argument("--unweighted", action="store_true")
    s = sub.add_parser("strategic", help="Exact one-shot report-grid search; zero API calls")
    s.add_argument("--output", default="calms_runs/strategic.csv")
    s = sub.add_parser("dag-simulate", help="Budgeted dependent-project allocation; zero API calls")
    s.add_argument("--output", default="calms_runs/dag")
    s.add_argument("--seeds", type=int, default=5)
    s.add_argument("--episodes", type=int, default=20)
    s.add_argument("--projects", type=int, default=4)
    s.add_argument("--nodes", type=int, default=3)
    s.add_argument("--rate", type=float, default=.05)
    s = sub.add_parser("propensity", help="HT/clipping bias-variance experiment; zero API calls")
    s.add_argument("--output", default="calms_runs/propensity.csv")
    s.add_argument("--trials", type=int, default=10000)
    s = sub.add_parser("attacks", help="Fit report deviations on dev matrix and evaluate on held-out matrix")
    s.add_argument("--dev", required=True)
    s.add_argument("--test", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--bonus", type=float, default=.5)
    s.add_argument("--side-interest", type=float, default=0)
    s = sub.add_parser("replay", help="Evaluate policies against a frozen full-worker outcome matrix")
    s.add_argument("--matrix", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--budget", type=float, default=.15)
    s.add_argument("--rate", type=float, default=.02)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--calibration", help="Development-only fit-static artifact")
    s.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    s.add_argument("--pooling", choices=("equal", "exponential", "bayesian", "stacking"), default="exponential")
    s = sub.add_parser("analyze", help="Paired cluster-bootstrap report")
    s.add_argument("--input", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--unit", choices=("seed", "cluster_id"), required=True)
    s.add_argument("--reference", default="equal")
    s.add_argument("--resamples", type=int, default=2000)
    for command in ("forecast-analysis", "fit-static"):
        s = sub.add_parser(command)
        s.add_argument("--matrix", required=True)
        s.add_argument("--output", required=True)
    s = sub.add_parser("preflight", help="Offline config/data check; does NOT read keys or contact providers")
    s.add_argument("--config", default="calms_configs/pilot.json")
    s.add_argument("--tasks", default="examples/calms_tasks.jsonl")
    s = sub.add_parser("plan", help="Offline collection call-count and cost-reservation estimate")
    s.add_argument("--config", default="calms_configs/pilot.json")
    s.add_argument("--tasks", default="examples/calms_tasks.jsonl")
    s.add_argument("--split", choices=("dev", "test"), default="test")
    s.add_argument("--repeats", type=int, default=2)
    s.add_argument("--output", default="calms_runs/collection-plan.json")
    for command in ("collect", "workflow"):
        s = sub.add_parser(command)
        s.add_argument("--config", default="calms_configs/pilot.json")
        s.add_argument("--tasks", required=True)
        s.add_argument("--split", choices=("dev", "test"), required=True)
        s.add_argument("--output", required=True)
        s.add_argument("--live", action="store_true", help="Explicitly allow paid provider requests")
        s.add_argument("--max-usd", type=float, required=True, help="Total ceiling across the persistent ledger")
        s.add_argument("--ledger", default="calms_runs/api_ledger.sqlite")
        s.add_argument("--env", default=str(ROOT / ".env"))
        s.add_argument("--docker-image", default=None)
        if command == "collect":
            s.add_argument("--repeats", type=int, default=2)
        else:
            s.add_argument("--policy", choices=tuple(p for p in POLICIES if p != "coupled"), default="calms")
            s.add_argument("--budget", type=float, default=.5)
            s.add_argument("--rate", type=float, default=.02)
            s.add_argument("--seed", type=int, default=0)
            s.add_argument("--beta", type=float, default=0)
            s.add_argument("--pooling", choices=("equal", "exponential", "bayesian", "stacking"), default="exponential")
            s.add_argument("--calibration", help="Development-only fit-static artifact")
    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    try:
        if a.command in ("collect", "workflow"):
            # Gate before config loading, .env reading, Client creation or network.
            if not a.live:
                raise ValueError("No API calls made. Paid runs require explicit --live.")
            config = validate_config(read_json(a.config))
            tasks = load_tasks(a.tasks, a.split)
            if a.command == "workflow" and a.calibration:
                calibration = read_json(a.calibration)
                if set(calibration["training_clusters"]) & {t["cluster_id"] for t in tasks}:
                    raise ValueError("Calibration overlaps evaluation tasks")
                if calibration["worker_ids"] != [w["id"] for w in config["workers"]]:
                    raise ValueError("Calibration worker order differs")
                config["static_probabilities"] = calibration["static_probabilities"]
            client = Client(a.ledger, a.max_usd, a.env, live=True)
            try:
                if a.command == "collect":
                    collect(client, config, tasks, a.output, a.repeats, a.docker_image)
                else:
                    workflow(client, config, tasks, a.output, a.policy, a.budget, a.rate,
                             a.seed, a.docker_image, a.pooling, a.beta)
            finally:
                client.close()
        elif a.command == "preflight":
            config = validate_config(read_json(a.config))
            tasks = load_tasks(a.tasks)
            print(json.dumps({"workers": len(config["workers"]), "forecasters": len(config["forecasters"]),
                  "tasks": len(tasks), "provider_access_tested": False, "keys_read": False,
                  "python_verifier_requires_docker": any(n["verifier"]["type"] == "python" for t in tasks for n in t["nodes"])}))
        elif a.command == "check-legacy":
            legacy_check(a.source, a.output, a.budget)
        elif a.command == "plan":
            plan = collection_plan(validate_config(read_json(a.config)), load_tasks(a.tasks, a.split), a.repeats)
            write_json(a.output, plan)
            print(json.dumps({k: v for k, v in plan.items() if k != "per_task"}))
        elif a.command == "fixtures":
            make_fixtures(a.output, a.count)
        elif a.command == "import":
            import_tasks(a.source, a.output, a.kind, a.split, a.reward)
        elif a.command == "simulate":
            if a.seeds < 1 or a.episodes < 2:
                raise ValueError("Need positive seeds and >=2 episodes")
            simulate(a.output, a.seeds, a.episodes, a.rates, a.shift, a.policies, a.pooling, a.delay, not a.unweighted)
        elif a.command == "strategic":
            strategic(a.output)
        elif a.command == "dag-simulate":
            dag_simulate(a.output, a.seeds, a.episodes, a.projects, a.nodes, a.rate)
        elif a.command == "propensity":
            if a.trials < 1:
                raise ValueError("trials must be positive")
            propensity(a.output, a.trials)
        elif a.command == "attacks":
            attacks(a.dev, a.test, a.output, a.bonus, a.side_interest)
        elif a.command == "replay":
            replay(a.matrix, a.output, a.budget, a.rate, a.seed, a.policies, a.pooling,
                   read_json(a.calibration) if a.calibration else None)
        elif a.command == "analyze":
            analyze(a.input, a.output, a.unit, a.reference, a.resamples)
        elif a.command == "forecast-analysis":
            forecast_analysis(a.matrix, a.output)
        elif a.command == "fit-static":
            fit_static(a.matrix, a.output)
        if getattr(a, "output", None):
            print(f"Completed {a.command}: {Path(a.output).resolve()}")
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        p.exit(2, f"CALM-S stopped: {exc}\n")
