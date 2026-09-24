# Run from Windows without local virtualization

## Validated hosted route — 24 September 2026

GitHub Codespaces returned an exhausted allowance/budget error. GitHub Actions
run 36032228785 could not start because the account is billing-locked. Neither
failure requires changing the repository account: keep `ap-logics/calm-s`.

The OpenAI hosted shell works with the existing authorized OpenAI key. Both
EvalPlus benchmark families passed canonical-solution and deliberately wrong
solution controls. AppWorld's official environment opened twice from fresh state,
executed trusted REPL commands, and ran its evaluator successfully. This is
runtime validation, not a claim that the AppWorld experiment matrix is complete.

Keys stay in the ignored local `.env`; only code/data are uploaded to containers.
Paid operations reserve costs transactionally in `calms_runs/api_ledger.sqlite`.
The current combined API/infrastructure ceiling is $95, leaving a $5 buffer
under the user's $100 total ceiling. Container fees are conservative estimates;
provider billing remains authoritative. Do not create a fresh ledger to resume.

```powershell
python scripts_calms/run_code_benchmarks.py --backend hosted --split dev --live --max-usd 95
python scripts_calms/analyze_coding.py --stage lock
python scripts_calms/run_code_benchmarks.py --backend hosted --split test --live --max-usd 95
python scripts_calms/analyze_coding.py --stage test
```

For a development run already active, `finish_coding.py --live --env-file .env`
waits for its completion, freezes development choices, runs held-out collection,
and analyses it. Start only one continuation process. Every worker response is
cached; transport repairs reuse the original request namespace and are recorded
separately. Results are accepted only from the official checker artifact, never
from the infrastructure model's prose.

Hosted containers default to no outbound network. AppWorld dependencies and its
official public dataset are uploaded as separate files below the service's 50MB
limit. Its working tree lives under `/tmp`, while only final artifacts are
exported from `/mnt/data`, avoiding the 1,000-exported-file limit. Long-running
commands require explicit completion checks before artifact retrieval.

The AppWorld worker adapter is task-level allocation of complete REPL agents,
with two independently reset executions per worker and official task-success
evaluation. It must not be described as step-level DAG auditing. The public
AppWorld development split is held out from our training subset; it is not the
benchmark's private official test split.

## Alternative Codespaces route (currently blocked for this account)

The `.devcontainer` configuration creates a persistent Linux/Docker workspace in
GitHub Codespaces. The Windows PC only controls it; no local Docker or WSL is needed.
The repository stays private under `ap-logics/calm-s`.

## Create or reconnect

Use the **ap-logics** login. GitHub CLI needs the `codespace` OAuth scope:

```powershell
gh auth switch --hostname github.com --user ap-logics
gh auth refresh --hostname github.com --scopes codespace
gh codespace create --repo ap-logics/calm-s --branch main --display-name CALM-S-experiments --machine basicLinux32gb --idle-timeout 10m --retention-period 720h
```

The machine identifier must be confirmed against available machines before use.
Alternatively use GitHub's **Code → Codespaces → Create codespace** and select
the smallest available two-core machine. Bootstrap restores the verified release
and existing ledger and runs offline tests. It makes no model API calls.

Connect using the returned Codespace name:

```powershell
gh codespace ssh --codespace NAME
```

Inside `/workspaces/calm-s`, validate both environments:

```sh
python scripts_handoff/bootstrap_remote.py --verify --appworld
```

Check `calms_runs/remote-setup/status.json` and `bootstrap.log`. Setup is not
validated until these commands succeed. AppWorld smoke validation is only a
runtime/lifecycle check, not the unfinished CALM-S AppWorld experiment integration.

## Secrets and paid work

Keep API keys in the ignored `.env` file or scoped Codespaces secrets. Never
commit them or include them in a runtime build context. The default setup does
not transfer keys or launch paid experiments. Preserve the existing ledger and
the cumulative $99 API limit; only one machine may own paid execution at a time.
Do not start experiments from both the original PC and the Codespace.

After validated setup, use the README's sequential development/test commands.
The existing manifest/cache resumes completed API work. An uncertain request
must be reconciled before retrying. Keep all outcomes, failures and raw traces.

## Persistence and costs

Codespaces storage persists while stopped, but it is not a permanent archive.
Export and upload versioned run checkpoints before deleting the Codespace and
before its retention period ends. Never delete it as a cleanup shortcut.
Use `gh codespace stop --codespace NAME` when idle. An idle timeout is set to ten
minutes to limit compute consumption; stopped storage can still be billed.
GitHub's included quota/budget determines whether charges apply; model API costs
remain separate. Do not increase GitHub spending limits automatically.

## Remaining research work

Remote execution removes the host limitation. It does not complete AppWorld's
CALM-S integration, faithful external baselines, live shift streams or multi-window
attacks. Their status and deliverables remain in HANDOFF.md. Never label runtime
smoke tests as finished research experiments.
