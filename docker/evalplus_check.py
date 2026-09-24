"""Container-only adapter to the retained official EvalPlus checking functions."""
import copy
import json
import sys
from pathlib import Path

from evalplus.eval import PASS, untrusted_check
from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS
from evalplus.gen.util import trusted_exec
from evalplus.data.mbpp import mbpp_deserialize_inputs


def main():
    payload = json.loads(Path(sys.argv[1]).read_text())
    problem = payload['problem']
    dataset = payload['dataset']
    if dataset == 'mbpp':
        for name in ('base_input','plus_input'):
            problem[name] = mbpp_deserialize_inputs(problem['task_id'],problem[name])
    reference = problem['prompt']+problem['canonical_solution']
    truth = {}
    for name in ('base','plus'):
        truth[name] = trusted_exec(reference, copy.deepcopy(problem[name+'_input']), problem['entry_point'],
            record_time=True, output_not_none=dataset == 'mbpp' and problem['entry_point'] in MBPP_OUTPUT_NOT_NONE_TASKS)
    results = []
    for solution in payload['solutions']:
        record = {}
        for name in ('base','plus'):
            expected, times = truth[name]
            status, details = untrusted_check(dataset, solution, copy.deepcopy(problem[name+'_input']),
                problem['entry_point'], copy.deepcopy(expected), problem['atol'], times, fast_check=False)
            record[name] = {'status':status,'details':[bool(v) for v in details]}
        record['outcome'] = int(all(record[name]['status'] == PASS for name in ('base','plus')))
        results.append(record)
    print(json.dumps({'task_id':problem['task_id'],'results':results}))


if __name__ == '__main__':
    main()
