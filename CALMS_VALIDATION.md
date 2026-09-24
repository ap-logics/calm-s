# Offline validation — 22 September 2026

This validation is exclusively for CALM-S. It did not use the real `.env`,
contact either model provider, or run a real benchmark.

- `python -m unittest discover -s tests_calms -v`: **38 tests passed**.
- `python -m calms plan --output calms_runs/validation-plan.json`: completed
  without reading keys. The two independent fixture tasks require 16 worker
  calls and 6 forecast calls if later authorized; the conservative configured
  reservation estimate is $0.3381464. This is not a measured API bill.
- `python scripts_calms/offline_suite.py --seeds 3 --episodes 12 --output
  calms_runs/validated-final`: completed. Outputs include legacy accounting,
  analytic strategy search, propensity-estimator checks, stationary/drift
  simulations, pooling/delay/importance ablations and dependent-project routing.
- Provider integrations were exercised using fake responses with network access
  explicitly blocked in the tests. Resume reused cached responses without calls.
- The finite portfolio optimizer matched independent exhaustive enumeration on
  a small problem. Decision tests checked that hidden current outcomes and
  latent probabilities cannot affect current reports or selections.
- Docker execution was not exercised: Docker is not installed on this host.
  Generated Python is never evaluated directly on the host. Its verifier has a
  completion-marker check so an early successful process exit is not enough.

The synthetic grid has only three independent seeds and twelve episodes per
condition. These outputs validate the machinery; they are not confirmatory
results and must not replace the paper's table without a new declared protocol.

Remaining scientific and integration work is listed in `CALMS_COVERAGE.md`.
Usage and paid-run guards are documented in `README_CALMS.md`.
