# CALM-S implementation coverage

This file distinguishes implemented experiment machinery from evidence still to
collect. The research specification remains `AAMAS_EXPERIMENT_PLAN.txt`.

Latest extension: 31 real-matrix routing arms, 24,000 conditional audit-noise
trials and 120 development-fitted coalition affine settings have completed.
A hop-conditioned online router, equal pooling with identical audit exposure,
one-forecaster comparisons, and real-matrix exact propensity moments are now
implemented. These are exploratory and do not close all remaining requirements.
Official expanded coding data and a Docker-only EvalPlus adapter/runner are
prepared, but image execution is blocked by disabled firmware virtualization.
See `CALMS_RESUME_AFTER_RESTART.txt` for the precise status and remaining work.

## Implemented and testable offline

- Shared-total-budget checks on existing CSVs and recomputed seed summaries.
- Feedback-only simulator with honest stationary, unknown capability shift and
  task-mixture shift regimes, delayed updates and paired randomness.
- Cheapest, fixed-prior static, most-expensive monolith, epsilon-greedy empirical,
  stylized coupled optimism, equal pooling, selected pooling, audited pooling.
- Six-rate audit frontier; report-independent sampling, positive propensities,
  pessimistic audit reserves and explicit zero-audit exception.
- Exact finite-grid one-shot deviation search, allocation-side-interest sweep,
  and analytic payment variance.
- Development-fitted constant-offset report attacks evaluated on held-out real
  outcome matrices; baseline reports are not assumed to be true beliefs.
- Synthetic dependent-project portfolio allocation with exact finite optimization
  versus project-wise myopic selection.
- Equal/exponential/online convex stacking/generalized Bayesian pooling.
- Uniform/nonuniform inverse-propensity and clipped estimator bias/variance.
- Paired cluster bootstrap, input pairing checks, full-candidate Brier/log loss,
  descriptive logistic calibration and reliability bins.

## Implemented; QA collection and dependent QA workflows validated live on 23 September 2026

- OpenAI Responses and Anthropic Messages adapters; 4 workers and 3 forecasters.
- Persistent transactional spend reservations, response cache, resume and
  ambiguous-failure stops; explicit paid-run gate.
- Full-worker matrix collection with pre-outcome forecasts.
- Local MuSiQue and HumanEval-format imports; exact/JSON verifiers.
- Docker-only Python verifier (Docker is not installed on this host; untested live).
- Real on-policy task-DAG execution with actual upstream outputs and isolated
  local shadow inputs, delayed audit-only feedback and ledger settlement. Live
  MuSiQue-derived decomposed workflows have now run; Docker and AppWorld have not.
- Frozen-matrix policy replay; development-only static calibration artifacts.

## Still needed before claiming the full paper study is complete

1. Expand beyond the completed initial pilot and the new 60-development/150-test
   MuSiQue study with 24 on-policy workflow projects. The original pilot's
   source archive hash, task IDs, disjoint component splits and licence are
   recorded in `calms_data/qa-pilot/dataset_manifest.json`. Freeze a prospective
   confirmatory protocol. MuSiQue normalization and HumanEval supplied tests are limited
   adapters, not claims of official full MuSiQue or EvalPlus evaluation.
2. Obtain the original simulator if historical-number reproduction is required.
   New synthetic study code is not the missing original generating script.
3. Faithful Agora and AgentLance implementations/benchmark adaptation. No proxy
   in this harness is named as either external system.
4. AppWorld integration with genuine state snapshots, local verifiers and task
   lifecycle; optional SQL/database evaluation. Constructed JSON DAGs do not
   replace that external-validity evidence.
5. Richer learned best-response attacks and two-window collusion/ownership
   experiments. Present strategic CSVs establish only the specified analytic
   one-shot finite-report-class results; held-out attacks cover constant offsets.
6. A stronger contextual
   exploration baseline. The supplied empirical epsilon-greedy baseline is
   not a state-of-the-art routing claim. The new fixed-selection count-matched
   feedback diagnostic and cheap hop-conditioned historical predictor are
   implemented; they do not replace a strong contextual online learner.
7. Real-model shift streams, independent replications, pilot power analysis,
   hierarchical confirmatory inference, multiplicity correction and a prospective
   protocol. Synthetic results cannot substitute for these.
8. Measure verifier/tool/hosting costs if incurred, choose and justify the reward
   conversion, and tune settings on development data only. Sample configs do not
   constitute preregistration.

The first real-model QA pilot completed with 660 API calls plus 14 fixture smoke
calls, costing $2.6840 by the token ledger within the approved $50 cap. Its 18
budget/rate replay conditions, forecast diagnostics and held-out offset attacks
are complete. See `calms_runs/qa-pilot-20260923/PILOT_RESULTS.md` for findings and
limitations. The separate offline study produced 230,400 synthetic episodes;
synthetic results remain distinct from real-model evidence.

The expanded study also completed: 3,234 additional calls, total cumulative
usage-priced spend $16.0292, zero pending calls and zero shared-budget violations.
All 3,908 requests have hash-verified trace exports. Full findings, including
negative utility comparisons, are in `CALMS_EXPERIMENT_STATUS.txt`. Raw data,
source snapshots, outputs and traces are retained and archived.
