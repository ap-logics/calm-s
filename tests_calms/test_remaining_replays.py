import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts_calms'))
from remaining_replays import contextual, priors
from calms.offline import synthetic, run_stream


class ReplayCausalityTests(unittest.TestCase):
    def records(self):
        records = synthetic(7, 20, 'none')
        for i, r in enumerate(records):
            r['task_id'] = f'2hop-test-{i}'
            r['decision_costs'] = r['cost_offers']
        return records

    def test_current_and_future_labels_cannot_change_current_action(self):
        records = self.records()
        baseline = contextual(records, {}, .1, .02)
        for cut in (0, 4, 14, 15):
            changed = copy.deepcopy(records)
            for r in changed[cut:]:
                for rep in r['outcomes']:
                    for result in rep:
                        result['outcome'] = 1-result['outcome']
            attacked = contextual(changed, {}, .1, .02)
            for before, after in zip(baseline[:cut+1], attacked[:cut+1]):
                self.assertEqual(before['predictions'], after['predictions'])
                self.assertEqual(before['selected'], after['selected'])
                self.assertEqual(before['audit'], after['audit'])

    def test_repeated_decodes_count_as_one_development_task(self):
        records = self.records()[:1]
        records[0]['outcomes'][0][0]['outcome'] = 0
        records[0]['outcomes'][1][0]['outcome'] = 1
        self.assertEqual(priors(records)['2'][0], [1.5, 1.5])

    def test_equal_and_weighted_use_identical_audit_exposure(self):
        records = self.records()
        equal = run_stream(records, 'calms', 0, .2, .1, pooling='equal', distribution=[1,2,4,8])
        weighted = run_stream(records, 'calms', 0, .2, .1, pooling='exponential', distribution=[1,2,4,8])
        self.assertEqual([(r['audit'],r['audit_cost'],r['audit_pi']) for r in equal],
                         [(r['audit'],r['audit_cost'],r['audit_pi']) for r in weighted])


if __name__ == '__main__':
    unittest.main()
