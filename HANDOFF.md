# Current handoff — 25 September 2026

Coding and task-level AppWorld are complete. See [final findings and evidence](CURRENT_EXECUTION.md). No collector is running. One uncertain $0.10 infrastructure reservation remains preserved. The following planning notes describe the earlier handoff and are superseded for completion, spending and runtime status.

# Handoff: remaining work

**Historical status at the earlier handoff:** no experiment was running then.
The original PC has disabled firmware virtualization. Another Linux/Docker host
can perform the coding stage without changing that PC. Keys must be supplied
privately, and one collaborator must own the shared remaining budget.

## 1. Coding: highest readiness

Official HumanEval+ v0.1.10 and MBPP+ v0.2.0 are retained and hash checked.
Splits are fixed: 40 development tasks per family, 80 HumanEval+ test and 120
MBPP+ test. Unselected tasks remain unused. Exact prompts do not overlap across
development/test, but public benchmark contamination and semantic overlap remain
limitations. Do not change the split after inspecting results.

Runner: `scripts_calms/run_code_benchmarks.py`. Verifier:
`docker/evalplus_check.py`. Minimal build context is in the release archive.
Source is prepared and syntax checked; runtime validation on Docker is pending.
Follow the README commands, resolve infrastructure errors before spending, and
retain image ID, installed dependency versions and positive/negative controls.
Generated and reference code must run inside the isolated container.

The runner saves immutable manifests, forecasts before worker executions,
responses, official base/expanded-test details, matrices and billing records.
It fits worker cards/cost estimates on development before the test stage.
After development, freeze policy/rate/comparator selection before test analysis.
Adapt the existing QA analysis scripts to coding matrices; do not blindly run
`analyze_expanded.py`, which targets the old QA paths. Report success, full costs,
net value at the declared reward, audit frontier, calibration and paired uncertainty.

## 2. AppWorld: implementation required

Official source revision is retained under `calms_data/external-sources/appworld`.
Implement the genuine task lifecycle, resettable shadow execution, environment
checks and consistent planner. Validate isolation and resets before paid runs.
Compare CALM-S, equal pooling, exploration and a strong fixed worker; include
myopic versus lookahead if retaining the DAG-planning claim. If local node
verification cannot be defined, use complete resettable tasks and explicitly
narrow the granularity. Existing dependent QA tasks are not AppWorld evidence.

## 3. External baselines: implementation required

Implement faithful applicable adaptations of Agora and AgentLance from their
papers. Document omitted components and scope differences. Existing coupled
score/optimism proxies must not be named as reproductions. Count calibration,
forecasting, bidding, planning and execution calls in total costs. Match tasks,
worker rosters, information access and budgets, with development-only tuning.
Primary references: https://arxiv.org/abs/2607.09600 and
https://arxiv.org/abs/2608.23867. Do not use unrelated cryptocurrency projects
with the same names. Detailed source/code availability must be verified.

## 4. Live shift streams: protocol and implementation required

Existing shift evidence is synthetic. Freeze independent real-model streams
with controlled unannounced changes to task mixture or worker conditions.
Label induced stress conditions accurately; do not imply natural capability
drift. Measure recovery, missed improvements, success, audit expense and net
value. Updates must use only past permitted observations. Cached reseed replays
are not independent live replications. Determine achievable sample sizes within
the remaining budget before collection; use pilot variance for power planning.

## 5. Multi-window strategy: implementation required

Completed attacks cover analytic one-shot grids, development-fitted offsets and
affine worker-owner coalitions. Add two-window reputation/allocation deviations
and ownership/collusion conditions if keeping repeated strategic claims. Specify
the finite attack class, information set, utility scale and transfer accounting.
Attack gains are lower bounds over that class; elicited reports are not known
private true beliefs. Retain every fit and held-out evaluation.

## 6. Final synthesis

Choose independent units appropriate to adaptive streams; preserve pairing and
development/test separation. Distinguish exploratory analyses from prospective
ones. Predefine primary/secondary outcomes and appropriate multiplicity control
for new confirmatory comparisons. Report all costs and uncertainty, including
negative results. Original simulator reproduction requires obtaining the missing
source; the new synthetic study is not its reproduction. Historical budget
violations are documented and must not be silently edited away.

## Deliverables expected from the collaborator

Return code changes, immutable protocols/configs, exact source/image versions,
task IDs/splits, all prompts/responses and failed calls, verifier details,
episode/audit traces, completed matrices, updated SQLite ledger, source snapshots,
tables/figures and a concise coverage/results report. Keep credentials excluded.
Upload a new versioned release rather than replacing the original handoff assets.
Run `python -m unittest discover -s tests_calms -v` before changing live code;
44 tests passed at handoff. Never change live source halfway through a run.

The README's $99 ceiling is cumulative, not $99 per experiment/person/machine.
If a call is uncertain, reconcile it instead of automatically retrying. If the
remaining work cannot fit the budget, preserve the partial run and report the
remaining scope; do not raise the cap without the owner's authorization.
