# CALM-S experiment harness

This is the code for **CALM-S: Audited Forecast Settlement for Budgeted LLM-Agent
Orchestration**. Work from this directory, not the nested `aamas/` repository.
That repository belongs to a different AISTATS paper and is not a dependency.

**Expanded real-model study completed on 23 September 2026.** Total recorded API
spend is $16.0292 across 3,908 calls, including the first pilot. The fresh QA test
has 150 problems; 24 dependent QA projects were also run under five policies.
CALM-S matched the premium baseline's 66% QA success at roughly twice its cost.
See [status and findings](CALMS_EXPERIMENT_STATUS.txt),
[expanded results](calms_runs/expanded-20260923/EXPANDED_RESULTS.md), and
[data retention](CALMS_DATA_RETENTION.txt). This does not complete the full paper study.

**The first paid CALM-S QA pilot completed on 23 September 2026:** 60 real
MuSiQue problems, 660 API calls, and $2.6840 total usage-priced cost including
14 separate smoke calls, within the approved $50 cap. See
[pilot results](calms_runs/qa-pilot-20260923/PILOT_RESULTS.md).
Tests use fake provider responses and block outbound requests. Offline commands do not read
`.env`. Paid commands refuse to run without `--live` and `--max-usd`.

## Reproduce the expanded study

The frozen dataset, configuration and protocol are under
`calms_data/expanded-20260923/`. `scripts_calms/run_expanded.py --live --max-usd 99`
runs paid collection and workflows using the existing cumulative ledger.
**Do not rerun paid collection just to inspect results.** Offline analysis is
`python scripts_calms/analyze_expanded.py`; trace export is
`python scripts_calms/preserve_experiments.py`. The live launch used Python
3.12.10; its environment is recorded with the run. Plotting dependencies and
Python version are recorded under the figures directory.

The expanded controller uses development-fitted cost estimates in expected
utility while retaining pessimistic cost offers for feasibility and reservations.
The original objective is retained as an offline ablation. Original-pilot source
is preserved in `CALM-S-code.zip`; do not attempt to resume old manifests with
changed core code. Full data and trace retention is required for this project.

## Start here: offline only

Python 3.11+ is sufficient. The harness has no third-party Python dependencies.
From the project root, in PowerShell or a terminal:

```powershell
python -m unittest discover -s tests_calms -v
python -m calms preflight
python -m calms plan
python scripts_calms/offline_suite.py --seeds 3 --episodes 12
```

The last command runs a small complete offline grid: legacy accounting checks,
exact strategic deviations, audit estimator checks, three feedback-learning
regimes, six audit rates, pooling/delay/weighting ablations, and a dependent-project
allocation study. This is smoke-scale evidence, not the final sample size.

For the planned synthetic replication count:

```powershell
python scripts_calms/offline_suite.py --seeds 30 --episodes 80 --output calms_runs/offline-full
```

Results go under `calms_runs/` (ignored by Git). Every simulation saves its code
hash and settings. A changed implementation or configuration requires a new run
directory. New simulated results are **not** presented as reproductions of the
old paper table; the original generating code was not supplied.

## What exists

| Plan | Runnable code | Scope |
|---|---|---|
| E0 | `check-legacy` | Recomputes CSV statistics/accounting; original simulator recovery remains external |
| E1 | `collect`, `forecast-analysis`, `fit-static` | Pre-outcome full-worker collection, calibration diagnostics, development-only static fit |
| E2 | `replay`, `workflow`, audit-rate simulation grid | Frozen independent-task replay and on-policy task DAG execution; common spending rules |
| E3 | `strategic`, `attacks` | Exact known-belief search and development-fitted deviations on held-out model outcomes; not a repeated-game proof |
| E4 | `simulate --shift ...` | Feedback-only adaptation, unknown capability/mixture shifts, delayed updates; synthetic study |
| E5 | `dag-simulate`, `workflow` | Exact finite synthetic portfolio allocation and constructed dependent JSON workflows |
| E6 | `--pooling`, `--unweighted`, `--delay`, `--policy` | Equal, exponential, generalized Bayesian and online convex stacking; selected-only versus audits; myopic comparison |
| E7 | `propensity` | Uniform/nonuniform HT and clipping, exact bias/variance plus Monte Carlo |

See [CALMS_COVERAGE.md](CALMS_COVERAGE.md) for remaining paper-level work. In
particular, this is not a faithful Agora/AgentLance reproduction, AppWorld adapter,
or a completed confirmatory study. The distinction is deliberate: fixture and
synthetic success cannot be reported as real benchmark success.

## Agent roster

`calms_configs/pilot.json` defines four workers and three forecasters using only
OpenAI and Anthropic. It uses GPT-4.1 mini, Haiku 4.5, GPT-4.1 and Sonnet 5 as
workers, and three separate forecasting contexts. IDs, output limits, prices,
and roles are editable. These are starting configurations, not a claim that
these models are the best scientific roster. Both accounts and all configured
models were successfully used in the first QA pilot.

The Python controller does selection, audit sampling, budget accounting and
settlement. Verifiers are code, not LLM judges. No GPU cluster is required for
API-backed calls; local Python and, for generated-code evaluation, Docker run on
the experiment machine.

## Data

`examples/calms_tasks.jsonl` contains three tiny fixtures, not benchmark data.
Generate dependent fixtures with:

```powershell
python -m calms fixtures --count 12 --output calms_data/constructed.jsonl
```

Import a locally obtained MuSiQue JSONL file or HumanEval-format JSONL file:

```powershell
python -m calms import --kind musique --source PATH_TO_LOCAL_JSONL --split dev --output calms_data/qa-dev.jsonl
python -m calms import --kind humaneval --source PATH_TO_LOCAL_JSONL --split test --output calms_data/code-test.jsonl
```

Split by original problem before import. The harness rejects a source cluster
appearing in both splits within one dataset. A fitted calibration artifact also
rejects overlapping evaluation clusters. Separate unrelated imports still need
a reviewed split manifest. The MuSiQue adapter uses normalized exact answer
matching with aliases and fixed supplied evidence, not an official full metric
implementation. HumanEval import uses the supplied `test` field; it does not
magically add EvalPlus expanded tests. Bring the correct tests explicitly and
record their version before making a stronger benchmark claim.

Task schema: one JSON object per line with `id`, `cluster_id`, `family`, `split`,
`reward` (USD equivalent), and topologically ordered `nodes`. Every node has
`id`, `parents`, `prompt`, and `verifier`. Supported verifiers:

- `{"type":"exact","answers":["accepted answer"]}`
- `{"type":"json","expected":{"key":"value"}}`
- `{"type":"python","tests":"def check(...): ...\ncheck(solution)"}`

Only allowlisted public fields go to models. Verifier answers/tests stay local.
Actual upstream output, not the reference output, is passed to downstream nodes.
The constructed workflow stops when a node fails its verifier and earns the
project reward only when all nodes pass. Shadow execution receives the same
pre-node input and its output never enters the production workflow.

For code tasks, install Docker and build the verifier image yourself:

```powershell
docker build -f docker/calms-verifier.Dockerfile -t calms-verifier:local .
```

Generated code never executes in the host Python process. Containers have no
network, read-only filesystem, unprivileged user, bounded CPU/memory/PIDs and a
wall-time limit. A missing/broken verifier stops the run. Container isolation
does not make public benchmark tests impossible to game; review suspicious code
and retain outputs. Pin the image digest for a final study.

## Real-model commands -- require an approved spending cap

The project-root `.env` supplies `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. The
program never prints their contents. Nothing here installs credentials in the
unrelated repository.

Full-matrix collection runs all workers twice per independent task. All three
forecasts happen before any worker execution:

```powershell
python -m calms collect --tasks examples/calms_tasks.jsonl --split test --repeats 2 --output calms_runs/api-fixture --max-usd 1 --live
```

That example is a small **paid fixture test**, not the real pilot. Add
`--docker-image calms-verifier:local` for code tasks. Dataset choice, model limits,
and a spending cap must be fixed before a real pilot.

Once a genuine development matrix and test matrix have been collected:

```powershell
python -m calms fit-static --matrix calms_runs/dev/matrix.jsonl --output calms_runs/static.json
python -m calms forecast-analysis --matrix calms_runs/test/matrix.jsonl --output calms_runs/forecast-report
python -m calms attacks --dev calms_runs/dev/matrix.jsonl --test calms_runs/test/matrix.jsonl --output calms_runs/attacks
python -m calms replay --matrix calms_runs/test/matrix.jsonl --calibration calms_runs/static.json --budget 0.15 --rate 0.02 --output calms_runs/replay
python -m calms analyze --input calms_runs/replay/episodes.jsonl --unit cluster_id --output calms_runs/replay-report
```

Replay is offline. It reuses **frozen** forecasts and worker outcomes and updates
only the pool/router. It does not pretend that one cached forecast sequence is
valid for different adaptive forecasting histories. Do not treat replay seeds
over the same cached tasks as independent task samples.

`attacks` is also offline. It tunes unilateral constant probability offsets on
development outcomes and evaluates the chosen offsets on held-out outcomes.
The elicited baseline reports are not observed true beliefs, so a positive
separated-score gain may be calibration correction, not a theorem violation.
It evaluates expected audit-score exposure, not realized sparse payments.

The on-policy workflow runner recomputes forecasts from its own permitted history:

```powershell
python -m calms workflow --tasks calms_data/constructed.jsonl --split test --policy calms --budget 0.50 --rate 0.02 --output calms_runs/workflow-calms --max-usd 5 --live
```

This is also paid. Other implemented policies include `equal`, `selected`,
`cheapest`, `premium`, `static`, `explore`, and `myopic`. A real static policy
requires `--calibration`. Do not call `premium` the strongest model without
development evidence: this configuration selects the most expensive worker and
abstains if it cannot afford that worker. Live coupled self-report is not
implemented; the offline condition is explicitly stylized.

## Budgets, cache and failure behavior

There are two different budgets:

1. `--max-usd`: research API-spend ceiling across all calls in the shared SQLite
   ledger (`calms_runs/api_ledger.sqlite`). It includes full-matrix measurement
   calls. The ceiling is cumulative for that ledger, not reset on each command.
2. `--budget`: a policy's total USD-equivalent episode budget, covering its worker
   calls, forecasts, shadow audits and any simulated score transfer.

Before each API call, a transaction reserves a conservative text-token cost.
Inputs are limited to 60,000 UTF-8 bytes, output token limits are explicit, and
normal input pricing conservatively bounds cached input. This depends on the
configured provider rates being correct. Actual returned usage reconciles the
reservation; an overrun stops the run. Taxes, hosting, currency conversion and
unimplemented paid tools are outside this ledger. Provider billing is authoritative.

Request identities include run code/config/data hashes, task, role, model and
decode index. Completed calls are cached. A resumed policy is still charged its
original per-call cost in scientific accounting, even when research reruns are
free. Forecast/worker outputs and usage are retained locally; secrets are not.

Timeouts and ambiguous errors stop immediately, keep their full reservation,
and are not automatically retried. Inspect provider billing and the ledger
before reconciling them. Do not delete the ledger to bypass a spending limit.
Run one process per output directory. Different runs can share the ledger; its
transactions protect the overall reservation total.

Audits are drawn independently of current reports, across ALL eligible workers,
including the production worker. An audit of that worker is a separate shadow
execution. Selection cannot inspect the audit draw. `--rate` sets expected audit
spending as a fraction of the declared episode budget; maximum audit execution
cost is reserved beforehand to avoid report-dependent exclusions. This reserve
can reduce production spending even on unaudited episodes; measure this cost.
Zero rate is an ablation with zero support, not an incentive guarantee.

`--beta` optionally enables theoretical quadratic-score transfers in the workflow
ledger. Default beta=0 means transfers are disabled: do not claim implemented
monetary truthfulness from that run. Transfers are simulated accounting, never
actual payments to a provider. Positive beta reserves the maximum possible
inverse-propensity payment; very sparse audits may make this impractical.

## Analysis and scientific scope

`analyze` reports paired percentile cluster-bootstrap intervals. Use independent
seed/stream means for synthetic adaptive studies and original-task clusters for
frozen replay. One independent unit produces no confidence interval. Incomplete
paired task coverage is rejected. The generic analyzer is not sufficient for a
single adaptively coupled real stream; collect independent streams and specify
the appropriate hierarchical analysis before a confirmatory claim.

The live planner uses bounded lookahead with a homogeneous future-node success
approximation. It is not an exact stochastic DAG solver. `dag-simulate` separately
uses an exact multiple-choice knapsack over full synthetic worker paths, under
independent node-success assumptions. AppWorld's state cloning and verification
are not implemented by either of these constructed environments.

Forecast-only exponential weights, online convex stacking and generalized Bayes
have different update rules; none is advertised as universally best. The
synthetic forecasters learn only from permitted past labels, never current latent
probabilities. Full-candidate errors and true-probability regret are calculated
by evaluator code only after decisions. Real runs have no true-probability oracle.

## API references checked during implementation

- [OpenAI Responses creation](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [GPT-4.1 mini snapshots and prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [GPT-4.1 snapshots and prices](https://developers.openai.com/api/docs/models/gpt-4.1)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create)
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)

Model availability was verified for the September 2026 pilot; account throughput
limits were not characterized. Recheck prices and snapshot IDs when freezing a
new study.
