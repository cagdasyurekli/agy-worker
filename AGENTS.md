# AGENTS.md — agy-worker

## Purpose

agy-worker lets a driver host (Codex or Claude Code) delegate repository exploration
and implementation to Antigravity CLI (`agy`), then verify the result itself.

- Use the `workflow.sh` facade (`run`, `status`, `verify-finalize`) with the workflow
  that matches the user's intent:
  - `explore`: read-only report;
  - `task`: bounded change;
  - `project`: repo-wide build or audit-and-fix.
- Delegate substantive work to agy. Do not refuse because the file list, architecture,
  or first test command is unknown.
- Deliver an honest `verified`, `partially_verified`, or `blocked` outcome.
- Repair failures by sending sanitized feedback to the same agy conversation within
  budget. Never fall back silently to direct driver work after a provider failure or
  an exhausted budget.

## Hard boundaries

These never relax without an explicit owner decision.

- **Worker envelopes are claims, not evidence.** Never execute an envelope's
  `commands_run` or `tests_run`. The driver reviews the actual diff and runs its own
  checks.
- **The evidence primitives stay strict.** `qa-gate.sh` and `verify-job.sh` are the
  evidence primitives; never weaken their checks to get a green result. Gate Git reads
  use the hardened invocation: no repository hooks, fsmonitor, content filters, or
  caller `GIT_*` variables.
- **Provider transmission needs exact approval.**
  - Prefer scoped mode: `--provider-scope` plus full `launch_approval_sha256`.
  - Whole-worktree mode needs `launch_approval_sha256`. Without provider scope,
    everything in the worktree is agy-readable and may reach Google/Gemini;
    `--add-dir` does not narrow that.
  - Exclude secrets, denied paths, and unrelated private content from every approved
    entry.
  - One upfront approval may cover same-scope repairs. New scope, content,
    destination, isolation, permissions, or budget needs new approval.
- **Writes stay confined.** Writes and reconciliation stay inside the disposable
  worktree; `.git` access and symlink escapes are rejected.
  - `session` isolation does not isolate provider reads.
  - `native` isolation never falls back to `session`.
  - Keep the recorded isolation mode across repairs.
- **Launch preflight fails closed.** Before each launch, fail closed when agy lacks a
  required capability, and recheck the executable binding.
- **Child environments are allowlisted.** Provider and verifier children start from an
  environment allowlist. `--provider-env` / `--verify-env` need approval per variable
  name.
- **Model and effort are caller-owned.**
- **No bypasses.** Never add or recommend `--dangerously-skip-permissions`,
  `--dangerously-bypass-approvals-and-sandbox`, or disabling a host sandbox for agy.
- **User config is off-limits.** Do not modify `~/.gemini`, `~/.codex`, or `~/.claude`
  as a code change.
- **Owner approval for outward actions.** No commit, push, PR, release, tag,
  marketplace/SkillStore submission, GitHub feedback, or tool installation without
  explicit owner approval.
- **No overstated results.** Offline tests prove the exercised mechanism, not live
  provider behavior.

## Keep it small

This is a single-maintainer tool.
- **Name the need.** Before adding a module, flag, schema, workflow, tool, or document,
  name the user need it serves, and prefer changing or deleting existing code.
- **No compatibility layers by default.** No legacy readers, deprecated aliases, or
  compatibility layers unless the owner asks; old jobs are finished or discarded with
  the release that created them.
- **No research tooling.** Research, measurement, and benchmarking tooling does not
  belong in this repository unless the owner asks for it.
- **Report the size change.** State the net size change of substantial work.

## Working in this repo

- The canonical runtime is `skills/agy-worker/runtime/`. Root scripts are thin
  wrappers. Keep mirrored files byte-identical.
- Check the branch, dirty state, and freshness against `main`. Work in a clean,
  isolated worktree and preserve a dirty checkout.
- Do not describe agy from memory. Run `./ground-truth.sh` and inspect `agy --help`
  before changing agy-facing flags or claims. agy can exit 0 with empty output; parse
  `result.structured_output`. Under agy's sandbox, worker prompts use file tools while
  the driver runs repository commands.
- `docs/REPO_MAP.md` maps each component to its owning test command. Open only the
  relevant row.

## Verification

- **Final-bytes loop.** Run the owning focused suite for what you changed, then the dev
  gate (`ruff` + `mypy`, see `CONTRIBUTING.md`), then `./scripts/ci-offline.sh` once on
  the final bytes. After that, rerun only if executable bytes, trust boundaries, or the
  test inventory change.
- **Regression tests must bite.** A bug fix or new boundary gets a regression test that
  fails on the pre-change code; confirm it.
- **Fix, don't silence.** Fix lint and type findings at their cause. A targeted
  suppression needs a reason.
- **Trust-boundary changes.** Write a short design note (options considered, residual
  risk) and get an independent review. No author is the sole acceptor of material
  work.

## Docs

- `README.md` is the first-visit page; its size limit is enforced by
  `scripts/validate-docs.py`.
- Keep one authoritative guide per topic and do not duplicate content.
- Only files listed in `docs/public-files.allowlist` live under `docs/`.
- Release history lives in git tags and releases, not in docs.
- Shipped text must stay true after release.
- Keep private evidence, drafts, and generated reports outside the repository.
- Never commit `graphify-out/` or put it in an agy prompt.
