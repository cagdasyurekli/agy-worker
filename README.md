<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/logo-dark.svg">
  <img src="docs/assets/brand/logo-light.svg" alt="" width="132" height="132">
</picture>

# codex-agy-worker

**An Agent Skill for bounded Antigravity CLI delegation with independent
Git-scope checks and driver-owned verification.**

[![Offline test workflow](https://github.com/cagdasyurekli/codex-agy-worker/actions/workflows/test.yml/badge.svg)](https://github.com/cagdasyurekli/codex-agy-worker/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

Use **Codex CLI or Claude Code** to delegate repository exploration, features, and project-scale
coding to **Antigravity CLI (`agy`)**. Claude Code host operation was live-tested on synthetic tasks;
in headless `claude -p` or SDK runs, keep the turn alive until dispatch finishes.
The driver reviews the diff, runs checks, and decides whether the result is verified,
partial, or blocked. The worker report is never acceptance evidence.

## Quick start

Requires a POSIX-compatible environment with Bash, Python 3, git, a driver host, and
`agy` on `PATH`. Native Windows is untested; WSL may work on a best-effort basis.

### Codex

Confirm the reviewed marketplace source contains the `agy-worker` manifests before installing:

```bash
codex plugin marketplace add cagdasyurekli/codex-agy-worker
codex plugin add agy-worker@agy-worker
```

Existing users: follow the [identity migration](docs/INSTALLATION.md#codex-plugin-identity-migration).

### Claude Code

For a reviewed source containing the Claude manifests, use:

```text
/plugin marketplace add cagdasyurekli/codex-agy-worker
/plugin install agy-worker@agy-worker
```

The plugin skill is `/agy-worker:agy-worker`. For checkout-based testing, use the
[local installation instructions](docs/INSTALLATION.md#claude-code).

### GitHub fallback

Review and install directly from GitHub (the repository name is unchanged):

```bash
git clone https://github.com/cagdasyurekli/codex-agy-worker.git
cd codex-agy-worker
./install.sh
# Claude Code:
./install.sh --host claude
```

Choose one host installation, then start a new session. Both use the canonical
`skills/agy-worker/` bundle and the same runtime. Review the selected source commit.
Installation does not authorize a provider dispatch or repository transmission.

### Try the evidence boundary offline

```bash
./proof-demo.sh
```

The starter proof uses private synthetic repositories without a provider or network. It demonstrates
fixed gate cases; it is not a security certification or proof of general correctness.

### First real task

Before an agy-backed request, approve one exact transmission and execution mode.
Prefer `--provider-scope` for bounded jobs: it binds reviewed read entries, their content digest, and a
write subset, then stages those entries in an owner-private Gitless directory.
Whole-worktree dispatch remains an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception
and may expose every disposable-worktree file through `agy` to Google/Gemini.
`--add-dir`, prompt restrictions, and `qa-gate --only` do not narrow provider reads.
New jobs use the existing AGY session by default, with normal user filesystem/network access;
selected staging is not host isolation. `--provider-isolation native` optionally adds macOS containment. Scope approval
grants no provider execution, Git action, acceptance, or publication. Read [PRIVACY.md](PRIVACY.md).

Inspect a content-bound preview before approval; this starts no provider or network:

```bash
./agy-worker.sh transmission-preview --workdir "$WT" --provider-scope "$SCOPE" --format json
```

Review its exact `transmission_sha256` with the scope policy. See [usage](docs/USAGE.md)
for the registered-worktree requirement and whole-worktree preview.

In a new driver session, ask:

> Use the agy-worker skill to add error-path tests for the parser modules under
> `/absolute/path/to/project/src/`. Allow changes only under `tests/`, verify with
> `python3 -m pytest -q tests/test_parser.py`, and preserve accepted work on a branch.

The driver creates an isolated worktree, obtains any missing exact approval, reviews
the candidate diff, and runs its own checks. Unknown architecture does not block delegation.

[Learn how to verify an agent candidate without trusting its report](docs/VERIFYING_AGENT_OUTPUT.md).

## The evidence pipeline

`workflow.sh run`, `status`, and `verify-finalize` coordinate a disposable worktree,
provider approval, candidate inspection, and driver-owned verification. The facade
requires an explicit transmission choice and never infers acceptance from a worker report.

1. Review the content-bound preview and authorize the exact provider exposure.
2. Let AGY explore or implement in the approved scope.
3. Inspect the actual Git diff and run checks chosen by the driver.
4. Request a bounded repair in the same conversation, or preserve and finalize the
   candidate as verified, partially verified, rejected, or blocked.

`qa-gate.sh` checks Git-derived changed paths against declared scope and runs the
specified verifiers. `verify-job.sh` can publish a private unsigned evidence receipt.
Neither a successful envelope nor a green gate commits, merges, or publishes work.
See [Project workflow](docs/PROJECT_WORKFLOW.md) for copyable commands, approval
bindings, isolated verification copies, repair and recovery.

## What it is for

- **Explore:** repository understanding, review and planning with spot-checked findings.
- **Task:** a bounded feature, refactor or test change with driver-owned checks.
- **Project:** broader implementation or audit-and-fix work with bounded repair cycles.

An unknown file list, architecture or first test command does not prevent useful
exploration. Optional self-verification is advisory; final acceptance stays with the
host driver. Goal is opt-in.

This is not autonomous publication, a security certification, an exhaustive audit,
or a replacement for reviewing untrusted code. Bash, Python and Git are sufficient;
there is no Node runtime, MCP daemon or shared controller service.

## Documentation

| Task | Guide |
|---|---|
| Install, migrate an existing installation, or diagnose readiness | [Installation and compatibility](docs/INSTALLATION.md) |
| Choose workflows, scope, models and options | [Usage](docs/USAGE.md) |
| Verify, repair, finalize or recover a candidate | [Project workflow](docs/PROJECT_WORKFLOW.md) |
| Run CI, check updates or maintain the notifier | [Operations](docs/OPERATIONS.md) |
| Understand the evidence boundary | [Verification tutorial](docs/VERIFYING_AGENT_OUTPUT.md) |
| Use the portable package | [Skill package](skills/agy-worker/README.md) |
| Review marketplace packaging | [Marketplace](docs/MARKETPLACE.md) |
| Find implementation owners and checks | [Repository map](docs/REPO_MAP.md) |
| Read fixture-conformance limits | [Conformance](docs/CONFORMANCE.md) |
| See product direction | [Roadmap](docs/ROADMAP.md) |

## Limits and trust

- `session` mode retains normal user host access. Selected-content staging limits
  what is staged and reconciled; it is not host isolation.
- Explicit native mode requires supported macOS scoped containment and has documented
  network/Keychain exposure. It never falls back to session. See
  [execution boundaries](skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md#execution-boundaries).
- Each launch checks required AGY capabilities and the executable binding. Version
  text is diagnostic; readiness does not prove authentication, model availability,
  effective provider semantics or task quality.
- Model and effort remain caller-owned. Provider failures do not authorize silent
  model changes, new conversations or direct-driver fallback.
- Verifiers may execute untrusted candidate code. Review commands and their exposure;
  keep raw worker logs, credentials and controller state outside provider-readable content.
- Offline fixtures prove only their exercised mechanisms. A green gate establishes
  evidence for the bound candidate and commands, not general correctness or security.

Release state, a local checkout, an installed bundle and an external catalog listing
are separate facts. The [installation guide](docs/INSTALLATION.md) owns provider
qualification and host compatibility details.

## Contributing and support

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the focused and full checks,
[SUPPORT.md](SUPPORT.md) for sanitized reports, and [SECURITY.md](SECURITY.md) for
private vulnerability reporting. Data handling is described in [PRIVACY.md](PRIVACY.md).

## License

[MIT](LICENSE). See [TERMS.md](TERMS.md) for scope and disclaimers.
