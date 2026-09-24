"""Causal pooling updates, report-independent audits, and bounded DAG planning."""
import itertools
import math

from .common import mean, rng


POLICIES = ("cheapest", "premium", "static", "explore", "coupled", "equal", "selected", "calms", "myopic")


def expected_score(p, q):
    return 1 - (p * (1 - q) ** 2 + (1 - p) * q ** 2)


def audit_design(costs, rate, reference_budget, distribution=None):
    """At most one audit per window. pi_w = trigger * conditional_worker_prob.

    Reserve the maximum audit cost BEFORE any reports. The Bernoulli trigger is
    chosen to meet an expected cost target, not a hard per-window fraction.
    """
    if not 0 <= rate <= 1 or reference_budget <= 0 or not costs or min(costs) <= 0:
        raise ValueError("Invalid audit design")
    weights = distribution or [1] * len(costs)
    if len(weights) != len(costs) or min(weights) <= 0:
        raise ValueError("Every candidate must have positive audit support")
    probs = [v / sum(weights) for v in weights]
    trigger = min(1, rate * reference_budget / sum(p * c for p, c in zip(probs, costs)))
    return {"pi": [trigger * p for p in probs], "reserve": max(costs) if trigger else 0,
            "trigger": trigger, "distribution": probs}


def draw_audit(design, *seed):
    r = rng("audit", *seed)
    if r.random() >= design["trigger"]:
        return None
    return r.choices(range(len(design["pi"])), weights=design["distribution"])[0]


class Pool:
    def __init__(self, count, workers, eta=4, method="exponential"):
        if method not in ("equal", "exponential", "bayesian", "stacking"):
            raise ValueError("Unknown pooling method")
        self.count, self.workers, self.eta, self.method = count, workers, eta, method
        self.loss, self.exposure, self.stack = {}, {}, {}

    def weights(self, region):
        if self.method == "equal":
            return [1 / self.count] * self.count
        if self.method == "stacking":
            return self.stack.get(region, [1 / self.count] * self.count)
        loss = self.loss.get(region, [0] * self.count)
        if self.method == "exponential":
            loss = [v / max(self.exposure.get(region, 0), 1) for v in loss]
        # Bayesian is generalized Bayes on observed log likelihood, documented.
        eta = 1 if self.method == "bayesian" else self.eta
        floor = min(loss)
        values = [math.exp(-min(700, eta * (v - floor))) for v in loss]
        return [v / sum(values) for v in values]

    def predict(self, region, reports):
        weights = self.weights(region)
        return [sum(weights[m] * reports[m][w] for m in range(self.count)) for w in range(self.workers)]

    def update(self, region, reports, observations, importance=True, clip=None):
        # observations = (worker index, binary outcome, inclusion probability).
        losses = self.loss.setdefault(region, [0.0] * self.count)
        weights = self.weights(region)
        gradient = [0.0] * self.count
        for worker, outcome, pi in observations:
            if not 0 < pi <= 1:
                raise ValueError("Observed label requires positive propensity")
            multiplier = 1 / pi if importance else 1
            if clip is not None:
                multiplier = min(multiplier, clip)
            pooled = sum(weights[m] * reports[m][worker] for m in range(self.count))
            for m in range(self.count):
                q = reports[m][worker]
                if self.method == "bayesian":
                    safe = min(1 - 1e-9, max(1e-9, q))
                    loss = -math.log(safe if outcome else 1 - safe)
                else:
                    loss = (q - outcome) ** 2
                losses[m] += multiplier * loss / self.workers
                gradient[m] += multiplier * 2 * (pooled - outcome) * q / self.workers
        self.exposure[region] = self.exposure.get(region, 0) + 1
        if self.method == "stacking" and observations:
            # Online convex stacking by exponentiated-gradient update.
            logs = [math.log(max(1e-100, w)) - 0.05 * g for w, g in zip(weights, gradient)]
            mx = max(logs)
            values = [math.exp(max(-700, v - mx)) for v in logs]
            self.stack[region] = [v / sum(values) for v in values]


def choose(policy, predictions, costs, budget, reward, history, static, seed, remaining=1, decision_costs=None):
    utility_costs = costs if decision_costs is None else decision_costs
    if len(utility_costs) != len(costs) or any(not math.isfinite(c) or c < 0 for c in utility_costs):
        raise ValueError("Invalid decision costs")
    feasible = [w for w, c in enumerate(costs) if c <= budget + 1e-12]
    if not feasible:
        return None
    if policy == "cheapest":
        return min(feasible, key=lambda w: utility_costs[w])
    if policy == "premium":
        premium = max(range(len(costs)), key=lambda w: costs[w])
        return premium if premium in feasible else None
    p = list(predictions)
    if policy == "static":
        p = list(static)
    if policy == "explore":
        p = [(a + 1) / (n + 2) for a, n in history]
        if rng("exploration", *seed).random() < 0.1:
            return rng("exploration-worker", *seed).choice(feasible)
    if policy == "myopic" or remaining == 1:
        w = max(feasible, key=lambda w: reward * p[w] - utility_costs[w])
        return w if reward * p[w] - utility_costs[w] > 0 else None
    # Exact bounded lookahead under homogeneous remaining-node probabilities.
    # It is a heuristic model of future nodes, NOT a true DAG-value oracle.
    horizon = min(remaining, 5)
    best_value, selected = 0.0, None
    for assignment in itertools.product(feasible, repeat=horizon):
        cost = sum(costs[w] for w in assignment)
        if cost > budget + 1e-12:
            continue
        value = reward * math.prod(p[w] for w in assignment) - sum(utility_costs[w] for w in assignment)
        if value > best_value:
            best_value, selected = value, assignment[0]
    return selected
