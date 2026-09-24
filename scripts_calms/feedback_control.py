"""Fixed-selection, count-matched feedback diagnostic; not deployment utility."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import mean, rng
from calms.mechanism import Pool, audit_design, choose, draw_audit


def feedback_control(records, budget, rate, stream_length=15):
    result = []
    for stream, offset in enumerate(range(0, len(records), stream_length)):
        pools = {"random_candidate": Pool(3, 4), "selected_candidate": Pool(3, 4)}
        labels = {name: 0 for name in pools}
        for step, r in enumerate(records[offset:offset+stream_length]):
            reports, costs = r["reports"], r["cost_offers"]
            design = audit_design(costs, rate, budget)
            fc = sum(f["cost_usd"] for f in r["forecast_records"])
            available = budget - fc - design["reserve"]
            fixed_prediction = [mean(q[w] for q in reports) for w in range(4)]
            selected = choose("equal", fixed_prediction, costs, available, r["reward"], [[0, 0]]*4,
                              r["static"], [stream, r["task_id"]], decision_costs=r.get("decision_costs"))
            aw = draw_audit(design, stream, r["task_id"]) if selected is not None else None
            rep = rng("matched-feedback", stream, r["task_id"]).randrange(len(r["outcomes"]))
            for name, pool in pools.items():
                predicted = pool.predict(r["family"], reports)
                result.append({"stream": stream, "step": step, "task_id": r["task_id"], "arm": name,
                    "labels_before": labels[name],
                    "full_brier_before": mean((predicted[w]-out[w]["outcome"])**2 for out in r["outcomes"] for w in range(4)),
                    "label_revealed": int(aw is not None), "fixed_selected": selected,
                    "note": "count-matched diagnostic with fixed equal-pool selection; no principal utility claim"})
                observations = []
                if aw is not None:
                    w = aw if name == "random_candidate" else selected
                    pi = design["pi"][w] if name == "random_candidate" else design["trigger"]
                    observations = [(w, r["outcomes"][rep][w]["outcome"], pi)]
                    labels[name] += 1
                pool.update(r["family"], reports, observations, True)
        assert len(set(labels.values())) == 1
    return result
