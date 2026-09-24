import unittest

from calms.mechanism import choose
from calms.providers import estimated_cost, upper_cost


class CostEstimateTests(unittest.TestCase):
    def test_expected_cost_changes_ranking_without_relaxing_reserve(self):
        args = ("equal", [.70, .80], [.01, .10], .20, .25, [[0, 0], [0, 0]], [.5, .5], [0])
        self.assertEqual(choose(*args), 0)
        self.assertEqual(choose(*args, decision_costs=[.001, .005]), 1)
        tight = list(args)
        tight[3] = .05
        self.assertEqual(choose(*tight, decision_costs=[.001, .005]), 0)

    def test_lookahead_preserves_total_reserve(self):
        choice = choose("calms", [.7, .99], [.02, .08], .05, 1,
                        [[0, 0], [0, 0]], [.5, .5], [0], remaining=2,
                        decision_costs=[.001, .002])
        self.assertEqual(choice, 0)

    def test_estimator_never_replaces_upper_cost(self):
        model = {"input_per_million": 2, "output_per_million": 8, "max_output_tokens": 2048,
                 "cost_estimator": {"input_tokens_per_byte": .25, "mean_output_tokens": 10}}
        before = upper_cost(model, "question")
        self.assertLess(estimated_cost(model, "question"), before)
        self.assertEqual(upper_cost(model, "question"), before)
        model["cost_estimator"]["mean_output_tokens"] = 1e9
        self.assertEqual(estimated_cost(model, "question"), before)


if __name__ == "__main__":
    unittest.main()
