"""Export scientific figures from retained CSVs; no provider access."""
import csv
import importlib.metadata
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".calms_plot_dependencies"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "calms_runs/plot-config"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = ROOT / "calms_runs/expanded-20260923"
ANALYSIS = OUT / "analysis"
FIGURES = OUT / "figures"


def rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.savefig(FIGURES / f"{name}.png", dpi=200, bbox_inches="tight")
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def main():
    if not (ANALYSIS / "complete.json").exists():
        raise SystemExit("Run the complete offline analysis first")
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "savefig.facecolor": "white"})
    primary = rows(ANALYSIS / "primary/report/summary.csv")
    chosen = [r for r in primary if r["arm"].split("|")[0] in ("cheapest", "premium", "static", "explore", "equal", "selected", "calms")]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for i, r in enumerate(chosen):
        name, center = r["arm"].split("|")[0], float(r["net_value"])
        low, high = float(r["ci95_low"]), float(r["ci95_high"])
        ax.errorbar(center, i, xerr=[[center-low], [high-center]], fmt="o", capsize=4,
                    color="#b13f2c" if name == "calms" else "#23687a", markersize=6)
    ax.set_yticks(range(len(chosen)), [r["arm"].split("|")[0] for r in chosen])
    ax.invert_yaxis()
    ax.set_xlabel("Mean net value (USD equivalent; reward = $0.25)")
    ax.set_title("Fresh QA evaluation: 150 questions in 10 disjoint streams", loc="left", pad=16)
    ax.grid(axis="x", alpha=.2)
    fig.text(.12, .01, "95% percentile intervals over stream means; use paired contrasts for comparisons.", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    save(fig, "qa-primary")

    frontier = rows(ANALYSIS / "budget-audit-frontier.csv")
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for budget, color in ((.10, "#467ba8"), (.20, "#b13f2c"), (.40, "#308569")):
        group = sorted((r for r in frontier if float(r["budget"]) == budget and r["policy"] == "calms"), key=lambda r: float(r["rate"]))
        ax.plot([100*float(r["rate"]) for r in group], [float(r["net_value"]) for r in group],
                "o-", label=f"CALM-S; budget ${budget:.2f}", color=color)
    for policy, style, color in (("premium", "--", "#444444"), ("equal", ":", "#23687a")):
        baseline = next(r for r in frontier if float(r["budget"]) == .20 and r["policy"] == policy)
        ax.axhline(float(baseline["net_value"]), linestyle=style, color=color, label=f"{policy}; budget $0.20")
    ax.set(xlabel="Nominal audit rate (% of episode budget using reserved costs)",
           ylabel="Mean net value (USD equivalent)")
    ax.set_title("Audit-cost frontier: every prespecified rate retained", loc="left", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=.2)
    fig.tight_layout()
    save(fig, "audit-frontier")

    forecast = rows(ANALYSIS / "forecast-with-cheap-baselines.csv")
    labels = {"historical": "Historical", "contextual_historical": "Hop-conditioned historical",
              "equal_pool": "Equal LLM pool", "forecaster_0": "GPT-4.1 mini forecast",
              "forecaster_1": "Haiku forecast", "forecaster_2": "GPT-4.1 forecast"}
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    for i, r in enumerate(forecast):
        center, low, high = float(r["brier"]), float(r["task_ci_low"]), float(r["task_ci_high"])
        ax.errorbar(center, i, xerr=[[center-low], [high-center]], fmt="o", capsize=4,
                    color="#308569" if "historical" in r["predictor"] else "#23687a")
    ax.set_yticks(range(len(forecast)), [labels[r["predictor"]] for r in forecast])
    ax.invert_yaxis()
    ax.set_xlabel("Full-candidate Brier loss (lower is better)")
    ax.set_title("Forecast quality against cheap development-fitted predictors", loc="left", pad=16)
    ax.grid(axis="x", alpha=.2)
    fig.text(.12, .01, "95% task-bootstrap intervals; worker outcomes and decodes are averaged within each task.", fontsize=9)
    fig.tight_layout(rect=(0, .05, 1, 1))
    save(fig, "forecast-quality")
    versions = sorted(f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions(path=[str(ROOT / '.calms_plot_dependencies')]))
    (FIGURES / "requirements.txt").write_text("\n".join(versions) + "\n")
    (FIGURES / "environment.json").write_text(json.dumps({"python": sys.version, "matplotlib": matplotlib.__version__}, indent=2))
    print(FIGURES)


if __name__ == "__main__":
    main()
