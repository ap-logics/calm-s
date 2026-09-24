# Active hosted experiments — 24 September 2026

GitHub billing does not block the current route. Hosted Linux controls passed
for both EvalPlus benchmark families and for the official AppWorld environment,
persistent REPL, fresh resets, negative evaluation controls and state exports.

Coding development has completed: 80 tasks, four workers, two decodes per worker,
three pre-outcome forecasters. The 200 held-out tasks are collecting with the
development choices locked. `finish_coding.py` continues through analysis.

AppWorld development is running: eight training-template tasks, four workers,
two fresh agent executions each, at most eight REPL turns per execution.
`finish_hosted_appworld.py` waits for development, locks settings, collects
19 distinct public-development templates as our held-out set, then analyses them.
This task-level extension is exploratory, not a private-test result or a
step-level DAG-auditing reproduction. Its single adaptive stream does not support
confirmatory policy confidence intervals. Worker failures are retained.

Both processes share the same transactional ledger and $95 combined spending
ceiling, with $5 left below the user's $100 limit. The controlling PC must stay
awake and online. API keys are local; generated benchmark code runs remotely.
Do not start a second machine with an independent copy of the ledger while these
processes are active.

An explicitly in-progress snapshot is available at:
https://github.com/ap-logics/calm-s/releases/tag/hosted-evidence-20260924t174315z

It contains 5,801 files in a 116 MB incremental archive. Combine it with the
previous 331 MB cumulative extension archive. Original datasets and wheels are
retained; wheel bytes are embedded in the uploaded runtime ZIPs to avoid another
duplicate copy in the incremental archive. Its ledger snapshot is $19.6274088;
this is historical snapshot spending, not the final bill.

A separate `snapshot_hosted_runs.py --wait-for-completion --publish` process
waits for both new analysis completion files, then publishes their full new
evidence automatically. A stopped/failed study cannot trigger a final archive.
No result should be called complete without its `analysis/complete.json`.

Resume and diagnostics:

- Coding: `calms_runs/code-20260923/continuation-*.log`, per-split progress,
  manifests, transport revisions, matrices and exact/raw API traces.
- AppWorld: `calms_runs/appworld-agents-20260924/`, including each RPC, model
  request/response, official evaluation and ZIP of database states and tool logs.
- Infrastructure controls and failures: `calms_runs/hosted-*` and
  `calms_runs/appworld-hosted-*`. One early infrastructure smoke exceeded the
  service export-file limit; its unavailable internal logs are explicitly noted
  in `failure-summary.json`. Subsequent fixed controls passed.
- A cached request with a pending reservation must be reconciled, not blindly
  retried. Hosted sessions that expired require deliberate restart from retained
  evidence. Never reset the cumulative spending ledger.

The original simulator is still unavailable. Agora's public repository is a
framework preview that excludes the paper's calibrators and reproducibility
configuration. Neither it nor AgentLance has been faithfully reproduced here.
These are research-scope limitations, not remaining virtualization problems.

The new cost-aware disjoint LinUCB baseline uses development-only tuning and
only earlier selected-worker labels. It is an exploratory secondary comparison,
not a RouteLLM reproduction. Numerical and future-label-isolation tests pass;
the repository now has 46 passing unit tests.
