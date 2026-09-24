import itertools
import math
import tempfile
import unittest
from pathlib import Path

from calms.dag import dag_simulate, portfolio


class DagTests(unittest.TestCase):
    def test_optimizer_matches_bruteforce(self):
        projects = [{"reward": 20, "probabilities": [[.6, .9], [.7, .95]]},
                    {"reward": 15, "probabilities": [[.8, .9], [.85, .9]]}]
        costs, budget = [2, 4], 10
        paths = [None] + list(itertools.product(range(2), repeat=2))
        brute = 0
        for assignments in itertools.product(paths, repeat=2):
            spend = sum(sum(costs[w] for w in path) for path in assignments if path is not None)
            if spend <= budget:
                value = sum(projects[i]["reward"] * math.prod(projects[i]["probabilities"][j][w] for j, w in enumerate(path))
                            for i, path in enumerate(assignments) if path is not None) - spend
                brute = max(brute, value)
        selected = portfolio(projects, costs, budget)
        actual = sum(projects[i]["reward"] * math.prod(projects[i]["probabilities"][j][w] for j, w in enumerate(path))
                     - sum(costs[w] for w in path) for i, path in selected)
        self.assertAlmostEqual(actual, brute)

    def test_skip_unprofitable_projects(self):
        self.assertEqual(portfolio([{"reward": 1, "probabilities": [[.9], [.9]]}], [2], 10), [])

    def test_dag_shared_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = dag_simulate(Path(tmp), seeds=2, episodes=4, projects_count=2, nodes=2)
            self.assertEqual(len(rows), 32)
            self.assertTrue(all(r["cost"] <= r["budget"] for r in rows))
            self.assertTrue(any(r["allocation"] for r in rows))


if __name__ == "__main__":
    unittest.main()
