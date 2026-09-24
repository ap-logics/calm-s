import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts_calms'))
from contextual_linucb import Linear,fit,replay

class LinUCBTests(unittest.TestCase):
    def test_online_inverse_matches_closed_form(self):
        model=Linear(1,1)
        for i in range(1000): model.update([1],i%2)
        self.assertAlmostEqual(model.inverse[0][0],1/1001,places=12)
        self.assertAlmostEqual(model.predict([1],0),500/1001,places=10)

    def test_future_labels_do_not_change_earlier_choices(self):
        records=[{'task_id':f'HumanEval/{i}','cluster_id':str(i),'family':'HumanEvalPlus',
                  'cost_offers':[.01,.02,.03,.04],'decision_costs':[.01,.02,.03,.04],'reward':.25,
                  'outcomes':[[{'outcome':int(w==i%4),'cost_usd':.01*(w+1)} for w in range(4)]]}
                 for i in range(8)]
        prior=fit(records[:2],1)
        original=replay(records[2:],prior,.2,.2,0)
        changed=copy.deepcopy(records[2:])
        for result in changed[-1]['outcomes'][0]: result['outcome']=1-result['outcome']
        altered=replay(changed,prior,.2,.2,0)
        self.assertEqual([r['selected'] for r in original],[r['selected'] for r in altered])
        self.assertEqual(original[:-1],altered[:-1])

if __name__=='__main__': unittest.main()
