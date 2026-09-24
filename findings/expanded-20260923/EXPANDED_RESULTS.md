# CALM-S expanded real-model study

Total recorded API cost including the first pilot: **$16.0292**, within the $99 execution cap.

## Scope

- 60 new QA development problems and 150 fresh QA test problems, four workers with two decodes and three forecasters per problem.
- 12 additional development projects provide 36 node-calibration tasks; 24 different projects are executed on-policy under five routing policies.
- All sets exclude shared single-hop component IDs, including both splits of the original pilot.
- Full context now includes paragraph titles. Development-only empirical worker cards are supplied to forecasters.
- Routing uses development-estimated costs for utility; conservative cost reserves still enforce affordability and API caps.
- Collection invalid forecasts: 0; incomplete worker responses: 6. Shared-budget violations: 0.

## Locked QA comparison

Development selected audit rate **0.5%** and comparator **premium**. Primary episode budget is $0.20; reward is a declared $0.25 equivalent.
QA adaptive replay uses ten disjoint streams of 15 tasks. Intervals resample stream means. They do not turn repeated decodes into independent tasks.

| Policy | Success | Mean net value | Mean spend |
|---|---:|---:|---:|
| calms | 66.0% | 0.14405 | $0.02095 |
| cheapest | 36.7% | 0.09065 | $0.00102 |
| coupled | 62.0% | 0.13582 | $0.01918 |
| equal | 66.0% | 0.14411 | $0.02089 |
| explore | 50.7% | 0.12163 | $0.00504 |
| myopic | 66.0% | 0.14405 | $0.02095 |
| premium | 66.0% | 0.15510 | $0.00990 |
| selected | 66.0% | 0.14411 | $0.02089 |
| static | 66.0% | 0.15510 | $0.00990 |

The coupled condition is a stylized optimism wrapper, not a faithful external market baseline.

## Dependent QA workflows

Each worker sees the actual earlier worker answers. Failed nodes terminate the project. Reference answers remain local to the verifier.
This is a MuSiQue decomposition-derived workflow, not AppWorld. Only three independent streams are available: treat this table as descriptive.

| Policy | Complete projects | Mean net value | Mean spend |
|---|---:|---:|---:|
| calms | 29.2% | 0.04318 | $0.02973 |
| equal | 33.3% | 0.05650 | $0.02684 |
| explore | 20.8% | 0.04619 | $0.00589 |
| selected | 29.2% | 0.04599 | $0.02693 |
| static | 37.5% | 0.08163 | $0.01212 |

## Reading the result

Use the primary paired contrasts and equal-pool comparison, including their uncertainty. Do not select the best held-out rate as a headline.
The audit contribution is the comparison with equal/selected pooling and exploration; a gain over a cheap worker alone does not establish it.
All tested budgets, rates, reward conversions, original-cost-objective ablations, and hop strata are retained, including unfavorable results.

## Remaining limitations

- Exact answer matching with aliases is a limited semantic verifier, not the official full MuSiQue metric. Public-data model contamination is possible.
- The fresh QA set has 90 two-hop, 50 three-hop and 10 four-hop problems because disjoint four-hop components were scarce. Report the hop-stratified table alongside pooled results.
- Whole-question QA forecasts are frozen in replay. Workflow forecasts are recomputed using each policy's permitted history; node priors use correct-upstream development calibration.
- No real financial transfers were made; proper-scoring incentive evidence remains a separate analytic/strategic study.
- Coding/EvalPlus, AppWorld and faithful Agora/AgentLance comparisons remain outstanding. This is not the entire AAMAS evidence package.
- Recorded costs are usage-priced estimates, excluding taxes/hosting. Provider billing is authoritative.

## Outputs

- `analysis/primary/report/paired_contrasts.csv`: locked primary comparison.
- `analysis/equal-reference/`: comparison against equal pooling.
- `analysis/contextual/report/`: cheap hop-conditioned historical baseline.
- `analysis/budget-audit-frontier.csv`, `reward-sensitivity.csv`, `cost-objective-ablation.csv`, `hop-strata.csv`.
- `analysis/forecast-with-cheap-baselines.csv`, `analysis/attacks/`, `analysis/workflow/`.
- `../../calms_data/expanded-20260923/protocol.json`: frozen protocol, task IDs and source hashes.
