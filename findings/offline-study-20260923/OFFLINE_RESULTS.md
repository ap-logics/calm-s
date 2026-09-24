# CALM-S offline study run

Completed: 30 independent seeds x 80 episodes per simulated arm.

Nine study outputs contain 230,400 episode records with zero shared-budget violations. No provider API calls were used. These are new simulations, not reproductions of the original paper table.

## Illustrative 2% audit condition versus equal pooling

| Regime | Equal-pool mean value | CALM-S mean value | Difference |
|---|---:|---:|---:|
| none | 0.16554 | 0.15215 | -0.01339 |
| capability | 0.10346 | 0.14039 | +0.03694 |
| mixture | 0.16377 | 0.14535 | -0.01842 |

This fixed illustrative slice is not a selected best audit rate. All six rates and all baseline arms remain in each report directory. A comparison with equal pooling alone does not establish superiority over the strongest comparator.

Included: stationary/capability/mixture shifts; equal/exponential/Bayesian/stacking pooling; delayed/uncorrected updates; dependent-project allocation; one-shot strategic search; propensity bias/variance.

The forecasters in these simulations learn from permitted past feedback; this does not establish real LLM adaptation or external benchmark performance. Do not combine these synthetic units with real QA tasks for confidence intervals.
