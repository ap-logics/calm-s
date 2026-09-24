# CALM-S first real-model QA pilot

Completed under the user-approved US$50 cumulative cap.

- 30 development and 30 held-out MuSiQue QA problems; 480 worker calls and 180 forecast calls.
- Pilot token-cost ledger: **$2.6793**. Total including the separate connectivity smoke test: **$2.6840**.
- Outstanding uncertain/in-flight reservations: $0.0000.
- Costs use provider token usage and configured USD prices; taxes/hosting are excluded and provider billing is authoritative.
- This is an exploratory QA pilot, not the full confirmatory AAMAS experiment suite.

## Held-out worker results

| Worker | Accuracy over 60 decodes | Mean cost/call |
|---|---:|---:|
| openai_small | 35.0% | $0.00102 |
| anthropic_small | 40.0% | $0.00311 |
| openai_large | 38.3% | $0.00357 |
| anthropic_large | 63.3% | $0.00993 |

Invalid forecasts: 0/180. Incomplete worker outputs: 3/480.

## Routing diagnostic at the predeclared $0.30 budget and 2% audit rate

Reward is a declared $0.25 equivalent per correct answer. This arbitrary conversion needs sensitivity analysis.
The pilot runs budgets $0.15/$0.30/$0.60 and rates 0/0.5/1/2/5/10%; this is the middle-budget illustrative slice.

| Policy | Mean net value | Success rate | Mean spend |
|---|---:|---:|---:|
| calms | 0.07957 | 36.7% | $0.01210 |
| cheapest | 0.09065 | 36.7% | $0.00102 |
| coupled | 0.11011 | 50.0% | $0.01489 |
| equal | 0.08038 | 36.7% | $0.01128 |
| explore | 0.10533 | 43.3% | $0.00300 |
| myopic | 0.07957 | 36.7% | $0.01210 |
| premium | 0.14850 | 63.3% | $0.00984 |
| selected | 0.08038 | 36.7% | $0.01128 |
| static | 0.14850 | 63.3% | $0.00984 |

## Limits on interpretation

- Only 30 distinct held-out problems. Repeated decodes are not independent tasks.
- The adapter supplies paragraph text without titles and scores normalized exact answers with aliases; this is not the full official MuSiQue evaluation.
- Forecasts are frozen for replay; only the router/pool updates. This is not evidence of semantic forecasting adaptation.
- Task-level bootstrap intervals in replay CSVs are diagnostic. Pool updates couple tasks over time, so they must not be used as confirmatory adaptive-stream significance tests.
- Transfers are disabled in replay. Proper-scoring incentive evidence comes separately from the strategic experiments.
- Code-generation benchmarks, AppWorld and faithful Agora/AgentLance comparisons have not run.
- The parallel offline suite has 230,400 synthetic episode records and zero shared-budget violations. Those are synthetic results, not real-agent benchmark outcomes.

## Files

- `dev/matrix.jsonl`, `test/matrix.jsonl`: full worker outcomes, forecasts, usage and latency.
- `forecast-report/`: Brier/log scores and calibration bins.
- `attacks/`: development-fitted offsets evaluated on held-out outcomes.
- `replay-*/report/`: all 18 fixed budget/rate conditions and paired diagnostic summaries.
- `progress.json`: completed stage list and accounting.
- `../../calms_data/qa-pilot/dataset_manifest.json`: source, hashes, task IDs and split protocol.

Dataset: [MuSiQue authors' repository](https://github.com/StonyBrookNLP/musique), CC BY 4.0.
