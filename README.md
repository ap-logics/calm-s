# CALM-S — CALM-S experiment handoff

Research code, findings and retained evidence for **CALM-S: Audited Forecast
Settlement for Budgeted LLM-Agent Orchestration**. Owner: **ap-logics**.
Handoff date: 24 September 2026. **The full study is not complete.**

## Start here

- [Handoff and remaining experiments](HANDOFF.md)
- [Findings index](findings/README.md)
- [Detailed research plan](AAMAS_EXPERIMENT_PLAN.txt)
- [Implementation coverage and limitations](CALMS_COVERAGE.md)
- [Full retained archives](https://github.com/ap-logics/calm-s/releases/tag/handoff-2026-09-24)

The repository contains runnable source, tests, original manuscript/results,
and browsable reports/tables/figures. Release assets contain **all retained
experiment data, task splits, model outputs, traces, ledger snapshot and source
snapshots**. A Git clone alone does not download those large artifacts.
The newer extension ZIP is the complete cumulative archive; the earlier ZIP
and original code ZIP preserve historical versions. [SHA-256 hashes](release-assets.json).

## Findings to preserve

| Study | Result |
|---|---|
| Expanded QA, 150 test tasks | CALM-S 66% success; premium/static 66% |
| Mean QA cost | CALM-S $0.0209533; premium/static $0.0099049 |
| Mean QA net value, declared $0.25 success reward | CALM-S $0.1440467; premium/static $0.1550951 |
| Dependent QA workflows, 24 projects per policy | CALM-S 7/24; static 9/24; descriptive, only three streams |
| Extra contextual router | 65.3% success, $0.0096245 mean cost, no extra audits |
| Paid collection | 3,908 completed calls; $16.0291502 usage-priced spend; no pending calls |

These results **do not support a broad net-value advantage** in the tested QA
setting. Retain unfavorable comparisons, incomplete outputs and all denominators.
The extra 31 routing arms and 24,000 audit-noise trials are exploratory replays,
not new independent model executions. Coalition report attacks are stylized,
not observed LLM collusion. [Detailed results](findings/README.md).

## Set up on another machine

Use Python 3.12 for continuity. No GPU is required. Linux with Docker is needed
for the prepared coding verifier; AppWorld integration is still unfinished.

```sh
git clone https://github.com/ap-logics/calm-s.git
cd calm-s
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests_calms -v
gh release download handoff-2026-09-24 --repo ap-logics/calm-s --pattern 'CALM-S-experiments-20260923-extension.zip' --dir downloads
python scripts_handoff/restore_data.py downloads/CALM-S-experiments-20260923-extension.zip
```

Private-repository access is required. Alternatively download the ZIP from the
release page and pass its path to the restore script. Restoration verifies its
SHA-256, validates archived file hashes, restores data/runs and recovers the
existing SQLite ledger. It refuses to overwrite differing local artifacts.
It never reads keys or calls model APIs. Do not extract the archive over updated
source: the restore script deliberately restores only data and run artifacts.

Copy `.env.example` to `.env` and supply keys privately **only when ready for
paid collection**. No keys are included in this repository or release assets.
Continue the existing ledger; the cumulative cap is **$99**, leaving **$82.9708498**
at handoff. Coordinate a single spending owner: copies of the ledger on different
machines cannot enforce a combined cap. Do not run paid work concurrently from
separate clones. Return the updated ledger and traces with completed work.

## Run the prepared next stage

After restoration, with Docker running:

```sh
docker build -t calms-evalplus:20260923 calms_data/code-runtime
python scripts_calms/run_code_benchmarks.py --check-only
python scripts_calms/run_code_benchmarks.py --split dev --live --max-usd 99
python scripts_calms/run_code_benchmarks.py --split test --live --max-usd 99
```

**Docker execution is not yet validated.** Both positive and negative controls
must pass before spending. The runner enforces this. Development must finish
before test starts. A full run entails 80 development + 200 test coding tasks,
four workers, two responses each and three forecasters: up to 3,080 API calls.
The budget ceiling can stop a partial run safely. Do not reset the ledger to
force completion. The coding analysis and remaining experiment integrations
still require work; see [HANDOFF.md](HANDOFF.md).

## Provenance and interpretation

Historical traces retain model text, parsed usage, latency, IDs and reconstructed
hash-verified requests. Original raw HTTP envelopes were not recorded. The new
coding runner additionally saves raw response JSON. Third-party benchmark and
source licenses remain applicable; this handoff grants no new license to them.
The old manuscript is an input artifact, not a validated account of every result.
The missing historical simulator cannot be claimed reproduced. There is no
guarantee of AAMAS acceptance, and unfinished experiments must not be reported as
completed. Nothing in this repository automatically schedules paid experiments.
