"""Finite portfolio allocator and dependent-project simulation.

Costs are integer units in the optimizer; declared simulator costs are exact cents.
Independent node success is a model assumption, not a claim about real LLM errors.
"""
import itertools
import math
from pathlib import Path

from .common import manifest, rng, write_json, write_jsonl
from .mechanism import Pool, audit_design, draw_audit


def portfolio(projects, costs, budget, myopic=False):
    """Multiple-choice knapsack: skip or choose one full worker path per project.

    Each project has reward and a list of worker probability vectors, one per node.
    Exact over supplied finite candidates. Returns (project-index, assignment).
    """
    if not isinstance(budget, int) or budget < 0 or any(not isinstance(c, int) or c <= 0 for c in costs):
        raise ValueError("Optimizer costs/budget must be positive integer units")
    options = []
    for project in projects:
        candidates = {}
        for assignment in itertools.product(range(len(costs)), repeat=len(project["probabilities"])):
            cost = sum(costs[w] for w in assignment)
            probability = math.prod(project["probabilities"][i][w] for i, w in enumerate(assignment))
            value = project["reward"] * probability - cost
            if cost <= budget and value > 0 and (cost not in candidates or value > candidates[cost][0]):
                candidates[cost] = (value, assignment)
        options.append(candidates)
    if myopic:
        # Project-wise immediate best option, no joint budget planning.
        selected, remaining = [], budget
        for i, opts in enumerate(options):
            allowed = [(cost, value, a) for cost, (value, a) in opts.items() if cost <= remaining]
            if allowed:
                cost, _, assignment = max(allowed, key=lambda x: x[1])
                selected.append((i, assignment))
                remaining -= cost
        return selected
    states = {0: (0, [])}
    for i, opts in enumerate(options):
        nxt = dict(states)
        for used, (total_value, selected) in states.items():
            for cost, (value, assignment) in opts.items():
                new_cost = used + cost
                if new_cost <= budget and (new_cost not in nxt or total_value + value > nxt[new_cost][0]):
                    nxt[new_cost] = (total_value + value, selected + [(i, assignment)])
        states = nxt
    return max(states.values(), key=lambda x: x[0])[1]


def dag_simulate(output, seeds=5, episodes=20, projects_count=4, nodes=3, rate=.05):
    if seeds < 1 or episodes < 2 or not 1 <= projects_count <= 8 or not 1 <= nodes <= 4:
        raise ValueError("Invalid bounded DAG study size")
    manifest(output, {"kind": "new-dependent-project-simulation", "seeds": seeds, "episodes": episodes,
                      "projects": projects_count, "nodes": nodes, "rate": rate})
    costs = [4, 7, 10, 14]
    budget = 100
    rows = []
    for seed in range(seeds):
        for policy in ("equal", "selected", "calms", "myopic"):
            pool = Pool(3, 4, method="equal" if policy == "equal" else "exponential")
            observed = [[[0, 0] for w in costs] for _ in range(3)]
            for episode in range(episodes):
                public, truths, reports, families = [], [], [], []
                for project in range(projects_count):
                    project_q, project_p, project_reports, project_families = [], [], [], []
                    for node in range(nodes):
                        family = rng(seed, episode, project, node, "type").randrange(3)
                        project_families.append(family)
                        true = [[.85, .55, .8, .94], [.4, .82, .87, .94], [.65, .7, .85, .94]][family][:]
                        if episode >= episodes // 2:
                            true[0], true[2] = .95, .35
                        project_p.append(true)
                        belief = [(a + 4 * .7) / (n + 4) for a, n in observed[family]]
                        q = [[min(.99, max(.01, p + (.06 if (w + m) % 3 == 0 else -.03)))
                              for w, p in enumerate(belief)] for m in range(3)]
                        project_reports.append(q)
                        project_q.append(pool.predict(str(family), q))
                    public.append({"reward": 80, "probabilities": project_q})
                    truths.append(project_p)
                    reports.append(project_reports)
                    families.append(project_families)
                # Every node-worker pair receives positive inclusion probability.
                flat_costs = costs * (projects_count * nodes)
                design = audit_design(flat_costs, rate if policy in ("calms", "myopic") else 0, budget)
                forecast_cost = 3
                allocation_budget = budget - forecast_cost - design["reserve"]
                selected = portfolio(public, costs, allocation_budget, myopic=policy == "myopic")
                audit = draw_audit(design, seed, episode)
                observations, execution_cost, reward, completed = [], 0, 0, 0
                for project, assignment in selected:
                    success = True
                    for node, w in enumerate(assignment):
                        y = int(rng(seed, episode, project, node, w, "production").random() < truths[project][node][w])
                        execution_cost += costs[w]
                        if policy == "selected":
                            observations.append((project, node, w, y, 1.0))
                        if not y:
                            success = False
                            break
                    if success:
                        reward += public[project]["reward"]
                        completed += 1
                audit_cost = 0
                if audit is not None:
                    project, rem = divmod(audit, nodes * len(costs))
                    node, w = divmod(rem, len(costs))
                    # Synthetic resettable local tasks: audits may inspect any node.
                    y = int(rng(seed, episode, project, node, w, "shadow").random() < truths[project][node][w])
                    audit_cost = costs[w]
                    observations.append((project, node, w, y, design["pi"][audit]))
                # Mature updates only after all project decisions and executions.
                for project, node, w, y, pi in observations:
                    family = families[project][node]
                    observed[family][w][0] += y
                    observed[family][w][1] += 1
                if policy in ("calms", "myopic"):
                    for project in range(projects_count):
                        for node in range(nodes):
                            obs = [(w, y, pi) for p, n, w, y, pi in observations if p == project and n == node]
                            pool.update(str(families[project][node]), reports[project][node], obs, importance=True)
                elif policy == "selected":
                    for project, node, w, y, pi in observations:
                        pool.update(str(families[project][node]), reports[project][node], [(w, y, pi)], importance=False)
                spend = execution_cost + audit_cost + forecast_cost
                if spend > budget:
                    raise RuntimeError("DAG budget invariant failed")
                rows.append({"seed": seed, "episode": episode, "task_id": f"s{seed}-e{episode}",
                             "cluster_id": f"s{seed}-e{episode}", "family": "synthetic-dag",
                             "policy": policy, "audit_rate": rate if policy in ("calms", "myopic") else 0,
                             "completed": completed / projects_count, "completed_projects": completed,
                             "reward": reward / 100, "cost": spend / 100, "net_value": (reward - spend) / 100,
                             "execution_cost": execution_cost / 100, "audit_cost": audit_cost / 100,
                             "forecast_cost": forecast_cost / 100, "budget": budget / 100,
                             "allocation": selected, "audit": audit, "audit_pi": design["pi"]})
    write_jsonl(Path(output) / "episodes.jsonl", rows)
    write_json(Path(output) / "complete.json", {"rows": len(rows), "api_spend": 0,
               "scope": "Synthetic resettable local node audits. Not a reproduction of the old simulator."})
    return rows
