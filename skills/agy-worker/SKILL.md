---
name: agy-worker
description: Use when Codex or Claude Code should delegate repository exploration or implementation to Google Antigravity CLI (agy), then review, verify, repair, and deliver the result.
license: MIT
compatibility: "OpenAI Codex CLI and Claude Code. Requires Bash, Python 3, git, and agy with provider network access."
metadata:
  author: cagdasyurekli
  version: "0.26.3"
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

Obtain human approval for the task, exact provider-readable content, transmission and isolation
modes, caller-selected model and budget. If the driver could do the task itself (named files, small
change, known check), say in that request that fixed agy overhead can make direct work faster, and
let the user choose; never switch on your own. One upfront approval may cover predictable
same-scope repairs and mechanical digest refresh. New scope, content exposure, destination,
isolation, permissions or budget needs fresh authority. SHA values bind the documented controller
inputs, not the entire human decision; refreshing a still-applicable binding is not another
approval request. Goal and hand-authored JSON are not ordinary-use prerequisites.

Prefer `--provider-scope FILE --approve-transmission-sha SHA256` for bounded jobs. It binds reviewed read entries, their content digest, and a write subset in a fresh owner-private mode-`0700` Gitless stage.
Whole-worktree dispatch requires `--approve-whole-worktree LAUNCH_APPROVAL_SHA256`. Every disposable-worktree entry is provider-readable and may reach Google/Gemini; `--add-dir`, prompt denylists and gate path policies do not narrow that read boundary.
Neither `workflow.sh run` nor the advanced `agy-worker.sh` initial dispatch has an implicit transmission mode or an implicit `--provider-isolation`.
The whole-worktree digest binds content, kinds, full file mode bits, symlink target hashes, the
readable manifest, provider isolation and native grant profile. The scoped digest
binds canonical read/write policy, readable path/kind manifest, selected bytes and
executable bits, isolation and grant profile; scoped mode rejects symlinks and does
not bind full POSIX permissions. The controller rechecks the approved boundary
before provider start. The human approves one `launch_approval_sha256` over canonical
`launch_authority`: those content inputs, destination and Git base, exact normalized
task and constructed prompt, fixed transport templates, workflow/edit mode, model/effort,
cycles and time budgets, scoped repair, self-verification manifest digest, provider-env
names, slash policy, additional directories and provider schema digest. Preview the
exact task and all launch options; reuse them unchanged for the approved run. Only
trailing LF bytes are removed from UTF-8 task input; spaces and CRLF are preserved.
Environment values and private verification commands are never serialized into the
approval payload. Use the private prelaunch review checklist
in [Project lifecycle and verification](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#approval-bindings-and-launch-notices), including any optional self-verification
commands, IDs and limits; keep that manifest out of the provider preview and prompt.
Retired dispatch and workflow job formats are rejected; finish or discard them with their creating release, without migration.
`--provider-isolation session|native` is caller-owned with no implicit value: the driver names the mode and its consequence in the approval request and never selects `session` on its own. `session` uses the existing AGY session with normal user filesystem/network authority plus ambient HOME, enabled user plugins, hooks and MCP servers; staging and reconciliation are not host isolation.
The controller compares a bounded observation of the verified main source checkout
against one immutable job baseline before later launches and before candidate
admission or retention. No-candidate failures and cancellations without a report
defer the post-exit comparison until the next launch; a cancelled repair defers it
until its inherited candidate is next used. A detected change blocks
the candidate; ignored untracked files and writes elsewhere on the host are outside
this check. The main-workdir helper skips this comparison, while public launch
preview still requires a linked disposable worktree. See
[Security and compatibility](references/SECURITY_AND_COMPATIBILITY.md#session-and-native-modes).
Explicit `--provider-isolation native` requires supported macOS scoped containment; it never falls back to session mode. Preserve the recorded isolation mode and grant profile across repairs.
Provider-scope approval grants neither provider execution, Git action, driver acceptance, nor publication.
Exclude secrets, denied paths and unrelated private content from every approved entry; telling the worker not to read an approved entry is not a control.

Keep raw logs and controller state outside the worktree and prompts. Each launch
requires capability preflight and immediate executable-binding recheck. Model and
effort stay caller-owned. Child environment opt-ins require approval per variable
name. Installation grants no provider or Git authority.

Read [Security and compatibility](references/SECURITY_AND_COMPATIBILITY.md) before a first
live dispatch or changing execution exposure. It owns native network/Keychain limits (native needs a one-time [dedicated agy keychain](references/TROUBLESHOOTING.md#dedicated-agy-keychain-for-native-isolation)),
verifier environments and no-follow boundaries. AGY 1.4.2 was observed starting workspace MCP commands from `.agents/`, `_agents/`, `.agent/` and `_agent/`. Preview rejects known
executable configuration under all four roots. Each launch checks actual cwd ancestry in
both modes. Prefer scoped mode excluding it, then a disposable worktree without it;
ancestors must be clear. Session mode can start enabled user-plugin MCP servers and run
global and enabled-plugin hooks in headless mode with slash commands disabled; hooks can
observe or rewrite tool calls, including shell commands. The guide details reserved paths,
native plugin/hook exclusion evidence and limits. Read the required
[launch notices](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#approval-bindings-and-launch-notices)
before initial, resume, continue or restart attempts; notices do not repeat approvals.

## Choose and run the workflow

| Intent | Workflow | Cycle budget | Driver action |
|---|---|---|---|
| Explore, understand, review or plan | `explore` | default 2, allowed 1..2 | Spot-check findings; state coverage limits. |
| Bounded feature, refactor or tests | `task` | default 2, allowed 1..2 | Review the diff; run relevant checks. |
| Project build or broad audit-and-fix | `project` | default 5, allowed 1..5 | Review changes; run build, tests and lint. |

Select only needed files and direct tests, name exact files/functions and the expected
change, size the budget to that scope, and split large changes into bounded jobs.
See [the maximum-runtime observation and cleanup test](references/TROUBLESHOOTING.md#hard_deadline_exceeded).

Use `workflow.sh run --preview`, approved `run`, read-only `status`, and `verify-finalize`; the facade does not choose a model, assurance, repair or external action.
[Project lifecycle and verification](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md) owns copyable commands, Verification v2 candidate bindings and recovery.

Quick path for the ordinary scoped `task` workflow. Keep the reviewed scope file (entries sorted by path, existing paths only; [example](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#primary-run-status-verify-finalize-path)) outside the target repository with mode `0600`, then run the whole cycle in order:

```bash
TARGET=/absolute/path/to/approved-repository
JOB_ID=job-12345
SCOPE=/absolute/private/provider-scope.json
TASK='the exact approved bounded task'
# 1. Preview: stdout has launch_approval_sha256; stderr has one "workflow-state: <path>" line.
"$PIPELINE/workflow.sh" run --preview --repo "$TARGET" --job-id "$JOB_ID" --provider-scope "$SCOPE" --provider-isolation session --task "$TASK"
STATE=/absolute/path/from/the/workflow-state/line
LAUNCH_SHA='the exact reviewed launch_approval_sha256'
# 2. Approved run: same arguments; the envelope is saved in the private state directory, never overwritten.
ENVELOPE="${STATE%/*}/envelope.json"
test ! -e "$ENVELOPE" || { echo "envelope path already exists" >&2; exit 64; }
( umask 077
  "$PIPELINE/workflow.sh" run --repo "$TARGET" --job-id "$JOB_ID" --provider-scope "$SCOPE" \
    --provider-isolation session --approve-transmission-sha "$LAUNCH_SHA" --workflow task --task "$TASK" > "$ENVELOPE"
) || exit $?
test -s "$ENVELOPE" || { echo "approved run produced no envelope" >&2; exit 1; }
# 3. Status (read-only); copy dispatch.state_sha256 for step 6.
"$PIPELINE/workflow.sh" status --repo "$TARGET" --job-id "$JOB_ID" --format json
DISPATCH_SHA='dispatch.state_sha256 from that status'
# 4. Review the candidate diff read-only in "${STATE%/*}/worktree". 5. Run checks in an isolated copy.
VERIFY_DIR=/absolute/new/private-parent/candidate
"$PIPELINE/agy-worker.sh" verification-copy --job-id "$JOB_ID" --state "$STATE" --destination "$VERIFY_DIR" --format text
( cd "$VERIFY_DIR" && PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m pytest -q )
# 6. Close: author the Verification v2 file first (guide below), then bind it.
RECEIPT="${STATE%/*}/evidence-receipt.json"
test ! -e "$RECEIPT" || { echo "receipt path already exists" >&2; exit 64; }
"$PIPELINE/workflow.sh" verify-finalize --state "$STATE" --receipt "$RECEIPT" --envelope "$ENVELOPE" \
  --approve-dispatch-sha "$DISPATCH_SHA" --verify-argv '["/usr/bin/git","diff","--check"]' \
  --verification-json "${STATE%/*}/verification-v2.json" --assurance verified
```

Author the Verification v2 file with [this guide](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#verification-v2).

Run driver-selected build/test commands and Python imports in an isolated verification copy with `PYTHONDONTWRITEBYTECODE=1`. Inspect the bound candidate's actual diff and gate binding directly. Never manually edit, delete, or chmod the bound candidate; send needed repairs to the same worker conversation. Never execute an envelope's `commands_run` or `tests_run`; bind only sanitized driver findings to the candidate.
Gate and `verify-finalize --verify-argv` verifiers run in the bound candidate: choose only commands known to be read-only there. Snapshot rejection detects changes to bound candidate state after they happen; it does not isolate the candidate. Verifiers run untrusted candidate code with the user's authority; the gate does not detect changes outside the candidate, including Git hooks and configuration. Feed separate copy test results into Verification v2.
Repair observable failures in the same conversation within budget; never silently fall back to direct-driver work after provider failure or exhausted budget.
Use initial `--allow-scoped-repair` for approved multi-turn scoped work. Without that grant, a changed scoped candidate is result/finalize-only. Preserve useful work; `restart` requires an explicit user decision.

Self-verification is optional advisory feedback, not acceptance. An unknown first
check is not a hard stop. Reuse checks only for unchanged candidate bytes and relevant
environment; the driver independently decides the final assurance.
For trust-boundary changes, use the short design note and independent review in
[Material planning governance](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#material-planning-governance).
Explicit delegation-first requires running the `delegation-policy.sh` evaluator before substantive repository work.
Controller records are local: the runtime cannot infer prior work or approval and
must never silently authorize direct-driver fallback after missing approval, a hard
stop, preflight/provider failure or exhausted budget.

Claude Code: in non-interactive `claude -p` or SDK runs, dispatch in the foreground
(up to the host's ten-minute ceiling) or keep the turn alive until it finishes;
never end the turn while a job runs. In interactive sessions, a long dispatch may
use Bash `run_in_background: true` while the main session remains active. Do not
duplicate a job or treat a Bash timeout as provider failure.
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
When `status` offers finalization for a bound candidate, `verify-finalize` records the
driver's result without a Git change and is the facade's required closure step.
