---
name: agy-worker
description: Use when Codex or Claude Code should delegate repository exploration or implementation to Google Antigravity CLI (agy), then review, verify, repair, and deliver the result.
license: MIT
compatibility: "OpenAI Codex CLI; Claude Code experimental: pending live verification. Requires Bash, Python 3, git, and agy with provider network access."
metadata:
  author: cagdasyurekli
  version: "0.22.0"
---

# Delegate repository work and verify the result

Delegate substantive exploration or implementation to `agy`, then inspect its diff
and run driver-owned checks. Unknown files, architecture or a first test command do
not prevent useful exploration; worker envelopes are not evidence.

`SKILL_ROOT` contains this file. In Claude Code it is `${CLAUDE_SKILL_DIR}`,
substituted in instructions rather than exported by Bash. Resolve the package:

```bash
PIPELINE="$(bash "$SKILL_ROOT/scripts/resolve-pipeline.sh")" || exit $?
```

Use `"$PIPELINE/doctor.sh" --repo /absolute/path/to/target` for offline readiness;
`ready` proves neither authentication nor task success. See the [Package README](README.md).

## Authorize provider work

Obtain human approval for the task, exact provider-readable content, transmission and
isolation modes, caller-selected model and budget. One upfront approval may cover
predictable same-scope repairs and mechanical digest refresh. New scope, content
exposure, destination, isolation, permissions or budget needs fresh authority.
SHA values bind that decision; refreshing a still-applicable binding is not another
approval request. Goal and hand-authored JSON are not ordinary-use prerequisites.

Prefer `--provider-scope FILE --approve-transmission-sha SHA256` for bounded jobs. It binds reviewed read entries, their content digest, and a write subset in a fresh owner-private mode-`0700` Gitless stage.
Whole-worktree dispatch requires `--approve-whole-worktree LAUNCH_APPROVAL_SHA256`. Every disposable-worktree entry is provider-readable and may reach Google/Gemini; `--add-dir`, prompt denylists and gate path policies do not narrow that read boundary.
Neither `workflow.sh run` nor the advanced `agy-worker.sh` initial dispatch has an implicit transmission mode.
Approvals bind content, kinds, permissions, symlink targets and execution mode; the controller rechecks this binding before provider start.
Retired dispatch and workflow job formats are rejected; finish or discard them with their creating release, without migration.
Default `--provider-isolation session` uses the existing AGY session. AGY has normal user filesystem/network authority; staging and reconciliation are not host isolation.
Explicit `--provider-isolation native` requires supported macOS scoped containment; it never falls back to session mode. Preserve the recorded isolation mode and grant profile across repairs.
Provider-scope approval grants neither provider execution, Git action, driver acceptance, nor publication.
Exclude secrets, denied paths and unrelated private content from every approved entry; telling the worker not to read an approved entry is not a control.

Keep raw logs and controller state outside the worktree and prompts. Each launch
requires capability preflight and immediate executable-binding recheck. Model and
effort stay caller-owned; recommendations are advisory. Child environment opt-ins
require approval per variable name. Installation grants no provider or Git authority.

Read [Security and compatibility](references/SECURITY_AND_COMPATIBILITY.md) before a
first live dispatch or changing execution exposure. It owns native network/Keychain
limits, verifier environments and no-follow boundaries. Read the required
[launch notices](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#approval-bindings-and-launch-notices)
before initial, resume, continue or restart attempts; notices do not repeat approvals.

## Choose and run the workflow

| Intent | Workflow | Cycle budget | Driver action |
|---|---|---|---|
| Explore, understand, review or plan | `explore` | default 2, allowed 1..2 | Spot-check findings; state coverage limits. |
| Bounded feature, refactor or tests | `task` | default 2, allowed 1..2 | Review the diff; run relevant checks. |
| Project build or broad audit-and-fix | `project` | default 5, allowed 1..5 | Review changes; run build, tests and lint. |

Use `workflow.sh run --preview`, approved `run`, read-only `status`, and
`verify-finalize`. The facade does not choose a model, assurance, repair or external
action. [Project lifecycle and verification](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md)
owns copyable commands, Verification v2 candidate bindings and recovery.

Run driver-selected build/test commands and Python imports in an isolated
verification copy with `PYTHONDONTWRITEBYTECODE=1`. Inspect the bound candidate's
actual diff and gate binding directly. Never manually edit, delete, or chmod the
bound candidate; send needed
repairs to the same worker conversation. Never execute an envelope's
`commands_run` or `tests_run`; bind only sanitized driver findings to the candidate.
Gate and `verify-finalize --verify-argv` verifiers run in the bound candidate: choose
only commands known to be read-only there. Snapshot rejection detects a mutation
after it happens; it does not isolate the candidate. Feed separate copy test results
into Verification v2.
Repair observable failures in the same conversation within budget; never silently
fall back to direct-driver work after provider failure or exhausted budget.
Use initial `--allow-scoped-repair` for approved multi-turn scoped work. Without that
grant, a changed scoped candidate is result/finalize-only. Preserve useful work;
`restart` requires an explicit user decision.

Self-verification is optional advisory feedback, not acceptance. An unknown first
check is not a hard stop. Reuse checks only for unchanged candidate bytes and relevant
environment; the driver independently decides the final assurance.
For trust-boundary changes, use the short design note and independent review in
[Material planning governance](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#material-planning-governance).
Explicit delegation-first requires running the `delegation-policy.sh` evaluator before substantive repository work.
Controller records are local: the runtime cannot infer prior work or approval and
must never silently authorize direct-driver fallback after missing approval, a hard
stop, preflight/provider failure or exhausted budget.

Claude Code: keep the main session active and use Bash `run_in_background: true`
for an approved long dispatch. Do not duplicate a job or treat a Bash timeout as provider failure.
Bash permission approval is separate from transmission approval. Read
[Claude Code host operation](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#claude-code-host-operation).

## Hard stops and delivery

Stop for missing exact approval; secrets or denied/unrelated private content in
approved inputs; writes escaping the worktree, entering `.git` or traversing symlink
boundaries; or unapproved Git, publication, installation, account or external actions.
Never use dangerous permission/approval-bypass flags or disable the host sandbox for AGY.
Do not modify user configuration as a code change. Never weaken the evidence gate.

Before changing AGY-facing flags or claims, run `"$PIPELINE/ground-truth.sh"` and
inspect current help. Its default version/help phase is local; `--account` is separate.
Read `result.structured_output`, not echoed schema or empty display text.

Deliver `verified`, `partially_verified`, `rejected` or `blocked` with the checks
actually run and remaining gaps. Offline checks do not prove live provider behavior,
completeness, release state or general correctness. Use
[Troubleshooting](references/TROUBLESHOOTING.md) for the failing boundary.
