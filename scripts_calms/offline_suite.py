"""Run the implemented CALM-S offline study grid. Never imports providers/keys."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--episodes", type=int, default=12)
    p.add_argument("--output", default="calms_runs/offline-suite")
    a = p.parse_args()
    output = Path(a.output).resolve()

    def run(*args):
        subprocess.run([sys.executable, "-m", "calms", *map(str, args)], cwd=ROOT, check=True)

    run("check-legacy", "--source", ROOT / "results/episode_results.csv", "--output", output / "legacy.csv")
    run("strategic", "--output", output / "strategic.csv")
    run("propensity", "--trials", 1000, "--output", output / "propensity.csv")
    for shift in ("none", "capability", "mixture"):
        target = output / shift
        run("simulate", "--seeds", a.seeds, "--episodes", a.episodes, "--shift", shift, "--output", target)
        run("analyze", "--input", target / "episodes.jsonl", "--output", target / "report", "--unit", "seed")
    for pooling in ("equal", "bayesian", "stacking"):
        target = output / ("pooling-" + pooling)
        run("simulate", "--seeds", a.seeds, "--episodes", a.episodes, "--pooling", pooling,
            "--policies", "equal", "calms", "--output", target)
    for label, options in (("delay3", ["--delay", 3]), ("unweighted", ["--unweighted"])):
        run("simulate", "--seeds", a.seeds, "--episodes", a.episodes, "--policies", "equal", "calms",
            "--output", output / label, *options)
    target = output / "dag"
    run("dag-simulate", "--seeds", a.seeds, "--episodes", a.episodes, "--output", target)
    run("analyze", "--input", target / "episodes.jsonl", "--output", target / "report", "--unit", "seed")
    print("Offline CALM-S suite complete. No keys read; no provider requests made.")


if __name__ == "__main__":
    main()
