# Completed hosted studies — 25 September 2026

Coding and task-level AppWorld collection and analysis are complete. The full paper study remains incomplete: the original simulator and faithful Agora/AgentLance reproductions remain unresolved.

## Results

Coding: 80 development and 200 held-out tasks, four workers and two decodes each. Development locked audit rate 0.005 and static comparator. Ten disjoint replay streams support the paired analysis. CALM-S success was 85%, mean cost $0.004548555 and net value 0.207951445; static success was 85.5%, cost $0.001484816 and net value 0.212265184. CALM-S minus static net value was -0.004313739 (97.5% interval [-0.010356046, 0.001819332]). No demonstrated advantage. Zero budget violations.

AppWorld: 8 development and 19 held-out public-development task templates, four workers, two fresh executions each, at most eight REPL turns. This is task-level allocation, not step-local DAG verification or private-test evaluation. CALM-S solved 0/19 replay tasks, static/premium 5/19. Their mean net values were -0.010427653 and 0.199392316 respectively. CALM-S realized zero audits at the locked 0.005 rate. The single adaptive stream supports descriptive comparisons only. Across both worker decodes, anthropic_large succeeded 11/38 times; the other three workers succeeded 0/38 each. These results do not establish market superiority or truthfulness.

## Evidence and spending

Final evidence: https://github.com/ap-logics/calm-s/releases/tag/hosted-evidence-20260925t034101z

Archive: CALM-S-hosted-increment-20260925T034101Z.zip, 165,544,695 bytes, 44,671 files.
SHA-256: 2df5d3ecb36e073c231c0a33f2e794d4d943e18a55e35c4da5ee917e0d67edf6
GitHub asset digest and size match the local receipt. Credential scan passed.

Combine this final increment with CALM-S-experiments-20260923-extension.zip from handoff-2026-09-24. The older interim hosted increment is unnecessary. Use a clean checkout and the restore scripts; retain the ledger. For a spending handoff, merge the final snapshot with restore_hosted_increment.py --take-over-ledger only after ensuring there is no other spending owner. No additional paid collection is needed for these two completed studies.

Ledger: 11,318 settled rows totaling $44.7205364, plus one unresolved $0.10 infrastructure reservation. Conservative committed total $44.8205364 against the shared $95 ceiling. Rows include infrastructure and research calls; this is ledger accounting, not a reconciled provider invoice.

The pending reservation belongs to session-0-recovery-2/shell-113 for task 37a8675_1: hosted Responses returned HTTP 500 with uncertain execution/billing. The container was confirmed deleted. Recovery used a fresh isolated world and cached worker responses. The reservation remains intact; do not blindly retry or refund it. Available failed-attempt traces and pre-recovery summaries are retained; unavailable state from deleted failed containers cannot be recovered. Completed executions retain state exports. API keys remain local.

Both collectors and the evidence publisher exited successfully. The controlling PC no longer needs to remain on for these runs. Source and report updates after the immutable evidence snapshot are in the repository.
