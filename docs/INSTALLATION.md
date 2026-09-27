# Installation and compatibility

Use this guide when installing `agy-worker`, checking its local prerequisites, or
diagnosing a compatibility or host sandbox failure. The GitHub repository is the
source of truth: review the exact commit or reviewed release tag before installing.
Installation enables the local skill only. It does **not** authorize a provider call
or transmission of repository content through `agy` to Google/Gemini.

## Prerequisites

The maintained entrypoints require a POSIX-compatible environment with Bash, Python
3, git with worktree support, Codex CLI or Claude Code (experimental: pending live verification), and `agy` (Antigravity CLI) on `PATH`.
Native Windows is untested; WSL or another compatible environment may work on a
best-effort basis. Some evidence commands use fixed POSIX paths, and the optional
daily notifier is specifically a macOS LaunchAgent.

Before spending provider quota, run the offline doctor against the repository you
intend to delegate:

```bash
./doctor.sh --repo /absolute/path/to/target
./doctor.sh --repo /absolute/path/to/target --format json
```

The doctor is read-only. It checks the bundled runtime, Bash, Python, Git/worktree
support, the target repository, and the installed AGY interface through bounded local
version/help probes. It makes no provider call, account inspection, network request,
update, or repair. Version text is diagnostic only; readiness requires the capabilities
used by the worker. Doctor reports a bounded readiness category; dispatch names a
missing capability before provider launch.

`ready` does not certify authentication, provider availability, native containment,
task quality, or a future dispatch. Fix a `not-ready` prerequisite before dispatch.
An invalid invocation exits `64`; an unavailable prerequisite exits `3`.

## Choose an installation path

### Codex Git marketplace

The primary first-visit commands are in the repository README. Read the
[marketplace contract](MARKETPLACE.md) for the root-source package layout, immutable
Git-ref verification, and installed-source byte-parity boundary. The marketplace and
clone paths resolve the same canonical `skills/agy-worker/` bundle; no second runtime
is created.

After installation, start a new Codex session so the skill is rediscovered.

### Codex plugin identity migration

The new plugin and marketplace identity is `agy-worker`; the repository stays
`cagdasyurekli/codex-agy-worker`. The old installed identity will not migrate itself.
Only after the new identity is published and available, run:

```bash
codex plugin remove codex-agy-worker@codex-agy-worker
codex plugin marketplace remove codex-agy-worker
codex plugin marketplace add cagdasyurekli/codex-agy-worker
codex plugin add agy-worker@agy-worker
```

Then start a new Codex session. These commands are supported by local
`codex plugin --help` and `codex plugin marketplace --help`; they remove the old
installation/cache and its marketplace source before installing the new identity.
This unreleased candidate does not establish remote availability.

### Claude Code (experimental)

Claude Code is **experimental: pending live verification**. It uses the same skill
and runtime. To review this candidate locally, from its repository root run:

```bash
claude plugin validate .
claude plugin marketplace add .
claude plugin install agy-worker@agy-worker
```

Start a new session and invoke `/agy-worker:agy-worker`, or describe a repository
exploration/implementation task that matches the skill description. Once published,
use the GitHub marketplace commands in the README. See the official
[plugin installation](https://code.claude.com/docs/en/discover-plugins) and
[manifest validation](https://code.claude.com/docs/en/plugins-reference) references.

For a standalone skill, run `./install.sh --host claude`, or copy the complete
`skills/agy-worker/` folder to `~/.claude/skills/agy-worker`. The installer honors
`CLAUDE_SKILLS_DIR`; its default is `~/.claude/skills`. No host configuration is edited.
Do not install both forms unless you intend to expose both skill names.

### GitHub clone

Review the selected source commit, then install the canonical skill bundle:

```bash
git clone https://github.com/cagdasyurekli/codex-agy-worker.git
cd codex-agy-worker
./install.sh
```

`install.sh` defaults to the Codex skill (`--host codex`); `--host claude` selects
Claude Code. `CODEX_SKILLS_DIR` defaults to `~/.codex/skills`. It copies the canonical bundle and writes
a local pointer so checkout-only maintenance commands remain available; it does not
rewrite the public `SKILL.md` or install an additional runtime. The installer copies
current bundle files without pruning extra files already present at the destination;
an updated installation may retain tools from an older bundle.

For a released snapshot, check out the exact reviewed `vMAJOR.MINOR.PATCH` tag from
the [GitHub Releases page](https://github.com/cagdasyurekli/codex-agy-worker/releases)
before running `./install.sh`; do not substitute an unverified tag.

### Folder-only or third-party copy

`skills/agy-worker/` is the one canonical, self-contained Agent Skill. A folder-only
copy contains its Bash/Python/git core runtime and downloads no code when invoked.
Resolve the installed core runtime as documented in
[`skills/agy-worker/SKILL.md`](../skills/agy-worker/SKILL.md), then run:

```bash
"$PIPELINE/doctor.sh" --repo /absolute/path/to/target
```

The bundle may also be copied with the third-party skills CLI:

```bash
DO_NOT_TRACK=1 npx skills add cagdasyurekli/codex-agy-worker \
  --skill agy-worker --copy
```

`npx` is only an optional installer. The installed skill has no Node runtime
dependency. Review the copied files before use.

## Claude Code host permissions

If the Claude Code sandbox is enabled, approve only the filesystem/network access
needed by this job. AGY's existing session needs state writes under `~/.gemini`;
the controller also needs its exact private state, staging, and disposable-worktree
paths when they are outside cwd/tmp. Use `sandbox.filesystem.allowWrite` for narrowly
reviewed paths and `sandbox.network.allowedDomains` for observed hosts. Discover
additional paths and domains through sandbox violation reports; no fixed AGY domain
allowlist has been established by offline tests. See the official
[sandbox guide](https://code.claude.com/docs/en/sandboxing).

Never disable the sandbox for AGY or add an `excludedCommands` exemption. A Bash
permission prompt is not provider-transmission approval. The same content/SHA,
execution-mode, model, and budget approvals apply. For background dispatch, process
lifetime, and status commands, read the packaged
[Claude Code host operation](../skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#claude-code-host-operation).
Live review must establish authentication, required network destinations, state and
socket access, and interaction with optional native containment before removing the
experimental label. Offline resolver tests cannot establish those facts.

The checkout `update.sh apply` flow remains Codex-only and reinstalls the default
Codex skill. It does not migrate plugin identities or update a Claude installation;
review a new checkout and explicitly reinstall with `--host claude` for that host.

## Codex host permissions

agy starts a local language server and writes account state. New worker jobs use
the existing AGY session by default; an outer Codex sandbox can still prevent that
session from working. Run with the host permissions already approved for the task.
For CLI sessions that intentionally use `workspace-write`, the following settings
allow the language-server socket and writes under `~/.gemini`.

Add this setting to `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

Then launch an interactive Codex session with:

```bash
codex --add-dir "$HOME/.gemini"
```

For a one-off `codex exec` invocation, pass both settings explicitly:

```bash
codex exec --sandbox workspace-write --add-dir "$HOME/.gemini" \
  -c 'sandbox_workspace_write.network_access=true' "<your task>"
```

The writable directory alone is insufficient because the language-server socket bind
also needs network access. Do not use dangerous permission or approval bypass flags.

## Refused actions and report paths

The response policy is independent of the AGY version. A strictly parsed terminal
result containing `denied_actions` stops with `permission_required` (exit `6`), even
when the value is empty or malformed. Its payload is never interpreted as authority.
A separately validated candidate remains available for driver review and finalization;
same-conversation resume and continuation are blocked. A future CLI that always emits
an empty denial list will also stop conservatively.

Without a valid structured report, denial metadata creates no candidate. Invalid JSON,
framing, or schema never becomes a successful result. An exact partial-output timeout
warning must match the job's bound duration; it stops provider success while preserving
a valid candidate. A nonzero provider exit with an otherwise valid `SUCCESS` report
also remains a failure, with the candidate available for review.

Binding, cancellation, and output-limit failures retain their safety precedence.
When a valid terminal denial coincides with a hard deadline, `permission_required`
remains the stopping reason while the elapsed time and limit kind retain the deadline
facts. A deadline without denial remains `hard_deadline_exceeded`. None of these
outcomes authorizes automatic retries or changes the driver's verification duty.

File tools use absolute workspace paths. Final `files_changed` reports should use
workspace-relative paths. Scoped reconciliation also accepts canonical absolute
paths beneath that attempt's exact staged root, subject to the same observed
mutation and scope checks; paths elsewhere remain invalid.

## AGY capability requirements

Every provider launch runs a bounded local `agy --version` and `agy --help` probe,
including default/tier selection and resumed, continued, or restarted jobs. The version
is diagnostic text; no exact-version registry, model inventory, or help-SHA approval
gates launch. The controller rechecks the probed executable's identity and contents
immediately before starting that same executable. Missing, malformed, oversized, or
timed-out interface output fails closed before provider execution.

Required flags are `--add-dir`, `--conversation`, `--disable-slash-commands`, `--effort`,
`--json-schema`, `--mode`, `--model`, `--output-format`, `--print`, `--print-timeout`, and
`--sandbox`. Help must expose `plan` and `accept-edits` modes and `stream-json` output.
The whole supported surface is checked even when one job does not use every flag.
This can reject an older CLI lacking `--effort` for a model-only job.

Model and effort are forwarded as caller-selected values. AGY may reject them; help
capability checks do not certify a model catalog, authentication, backend identity,
cost, availability, or quality. No selector leaves AGY's default unchanged. See
[model and effort selection](USAGE.md#model-and-effort-selection).

Last provider-tested AGY: **1.2.11**, in a bounded session edit and same-conversation refinement; native and effective `accept-edits` semantics were not qualified. This historical observation is informational and does not gate launches or qualify later versions.

## agy interface cautions

Run `./ground-truth.sh` against the installed agy before changing agy-facing flags or
claims. Its default interface phase calls only `agy --version` and `agy --help`; use
`./ground-truth.sh --account` only when you explicitly authorize inspection of
account-owned agy state such as models, agents, plugins, and local permissions.

- Build `--print` last: its next argument is the prompt, and print mode ignores stdin.
- Exit 0 plus empty output is not success. The worker accepts a terminal result only
  through its bounded structured envelope.
- In explicit native mode, agy's sandbox shell tools run in its scratch directory rather than the target
  repository. Worker prompts use file tools; the driver owns repository commands.
- Use bounded structured evidence for provider failures. Never turn free-form error
  prose, quota text, or a retry hint into automatic retry authority.
- The terminal answer is in `result.structured_output`.
  `result.json_schema` is the echoed schema, not the answer.
- Unknown agy subcommands may print usage and exit 0; do not probe support by exit
  status alone.
- `accept-edits` does not grant shell-command permission. In headless mode, an
  unapproved command cannot prompt for consent and may stop the job, even when the
  task requested file tools only. Preserve the failure and candidate; changing the
  model or repeating the prompt does not resolve the permission boundary. The worker
  does not add global allow-rules. See [AGY headless permissions](https://antigravity.google/docs/cli/headless/).
- Prefer narrow permission allow-rules. Never use
  `--dangerously-skip-permissions` or an approval/sandbox bypass.

## Troubleshooting order

1. Confirm you reviewed the exact installed source commit or release tag.
2. Run `./doctor.sh --repo /absolute/path/to/target` and respect `not-ready`.
3. Confirm the process has the approved host permissions; for a sandboxed CLI
   session, check both settings above.
4. Run `./ground-truth.sh` before interpreting an agy interface change.
5. Resolve the named missing capability or executable-binding failure without
   changing the caller's model, effort, scope, or permissions.
6. If local prerequisites pass but a provider call fails, preserve the sanitized
   result and follow the [project workflow](PROJECT_WORKFLOW.md); do not add a shell
   retry loop.

For privacy, support, and project terms, see [PRIVACY.md](../PRIVACY.md),
[SUPPORT.md](../SUPPORT.md), and [TERMS.md](../TERMS.md).
