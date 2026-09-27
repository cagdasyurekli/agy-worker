# Troubleshooting

Start from the first failing boundary. Do not turn a local preflight, provider,
lifecycle, or verification failure into an automatic retry, a changed model, or a
weaker check. Preserve the current candidate and state until the cause is classified.

For the normal command sequence, read
[Project lifecycle and verification](PROJECT_LIFECYCLE_AND_VERIFICATION.md). For
provider, environment, and verifier limits, read
[Security and compatibility](SECURITY_AND_COMPATIBILITY.md).

## The runtime does not resolve

**Symptom:** `resolve-pipeline.sh` reports that the pipeline or complete bundle is
missing.

**Action:** Reinstall or recopy the whole `skills/agy-worker/` package, including
`runtime/`, `scripts/`, `references/`, and `agents/`. Do not point the resolver at a
partial runtime or edit `.pipeline-root` by hand. A standalone marker must be an
absolute path to a complete installation.

## Doctor reports `not-ready`

Fix the named local prerequisite or missing AGY capability, then rerun the read-only
doctor. Version drift does not require activation or help-SHA approval. A `ready`
result does not test authentication, provider availability, native containment, or
task quality.

## Transmission preview fails

The preview requires a real canonical branch-backed linked Git worktree. Common
causes are an ordinary directory copy, a detached or unregistered worktree, a root
`.git` layout that does not match the contract, an outward/broken symlink, a special
node, path drift between scans, or a configured enumeration limit.

Create or repair the disposable worktree using Git, remove unapproved content, and
rerun the provider-free preview. Do not bypass the preview or interpret a preview
failure as provider rejection. If using a narrow provider-scope policy, recompute and
review its unified transmission SHA after any content or policy change.

The scope policy itself must be a current-user, regular, unlinked `0600` file at its
resolved path. Recreate it if it is group/world-readable, read-only, a symlink,
hardlinked, replaced, or changed during the bound read; do not weaken the policy-file
boundary to recover a preview.

## Preflight fails before provider launch

Tell the user that the task was not sent to AGY. Keep the caller's model, effort,
permissions, authentication, scope, and task unchanged while classifying the local
failure. A model change cannot repair a permission, missing executable, invalid
worktree, approval, environment, quota, or human-decision blocker.

Every provider launch checks the required AGY capabilities and immediately rechecks
the same executable. A missing flag, malformed help or changed binary stops before
the task starts. The version is diagnostic only; no compatibility-disposition or
help-SHA approval can bypass a failed probe. Preserve the caller's selection and
resolve the named prerequisite before starting new work.
For a lifecycle attempt, status keeps `selection_preflight_failed` (exit `26`);
inspect the existing private `stderr_path` for the missing capability names. That
diagnostic contains fixed flag names, not raw help output. Initial CLI preflight
reports the missing names directly.

## agy exits zero but ordinary output is empty

This can be valid CLI behavior. Parse `result.structured_output`; do not treat the
echoed schema or empty display text as the worker result. If the structured report is
missing or invalid, preserve the sanitized failure and do not invent an envelope.
A command-permission denial can also produce empty output in headless mode;
`accept-edits` grants no shell permission. Keep the selected model and authority
unchanged, retain the actual controller failure, and do not silently retry or widen
permissions. A file-tool-only prompt does not guarantee the worker avoids commands.

## Authentication, quota, timeout, or provider failure

Classify only from reviewed, bounded evidence. Do not infer account health, billing,
model acceptance, or provider availability from local controller state.

There is no version-specific quota countdown or automatic retry. A strict terminal
`denied_actions` field, including an empty or malformed value, stops provider reuse.
A valid candidate remains reviewable; a missing report does not become a candidate.
An exact duration-bound partial-timeout signal or nonzero provider exit also prevents
successful completion. Follow the recorded reason and available actions.

For a candidate-free failure, consult `available_actions`. A mechanically eligible
`resume` keeps the exact stored conversation; a fresh `restart` requires explicit user
direction. Both require the current state SHA and a new provider notice.

## A provider error or cancellation still has a candidate

A structurally valid `ERROR` candidate is reviewable. Retrieve `result`, inspect the
diff, create Verification v2 from driver-owned evidence, then choose an eligible
same-conversation `continue` or `finalize`. Do not use `resume`.

A structurally valid `CANCELED` or `CANCELLED` candidate is preserved for review and
finalization, or an explicitly directed fresh restart. It is never resumed or
continued. Local cancellation proves local process closure only; report remote
cancellation as unverified unless independently established.

## Scoped native launch is unavailable

Explicit `--provider-isolation native` requires supported macOS scoped containment.
New jobs use the existing AGY session by default. A general
`doctor` readiness result does not qualify that native launch or authentication.
If launch reports `status_unavailable`, inspect the host and bound executable/profile
before changing the task. Do not retry a provider call or silently switch execution
or transmission modes: that changes the exposure approved by the user. Keep the
candidate and identify the failed prerequisite in the handoff.

## State approval is stale

Mutating lifecycle commands require the current `state_sha256`; `wait` uses
`--after-state-sha`. Read `status` again, understand what changed, rebuild any
candidate-bound evidence, and use the newly reported approval only if the intended
action remains available. Never copy a stale digest forward blindly.

Refreshing this mechanical state binding does not by itself require another human
approval. Reuse the approved job scope when the action remains covered; request new
authority only when its scope, transmission, destination, or budget materially changes.

For facade finalization of a bound dispatch, use `dispatch.state_sha256` as
`--approve-dispatch-sha`. It is distinct from a convenient current facade state hash.
The former facade `--approve-state-sha` alias is rejected; advanced dispatcher and
job lifecycle commands still use their own `--approve-state-sha` flag.

## Unsupported job schema or removed flag

This agy-worker release accepts only current dispatch and workflow job
formats. Finish or discard an older job using the release that created it; the last
documented release with legacy-schema support is v0.22.0. Preserve its artifacts;
do not rewrite a schema number to bypass rejection. Current dispatch records use
state V15 and command V13, and selection records use V4. Earlier formats reject,
including ordinary jobs that used no removed feature. Use the actual creating release.
There is no in-place migration.
`--boost`, `--approve-boost-risk-sha`, and `--persona` were removed after v0.22.0;
start new work through the ordinary workflow with task instructions in the prompt.
Use current explicit transmission approvals instead of facade `--approve-preview-sha`
and `--legacy-preview-approval`; use `--approve-dispatch-sha` for facade finalization.
See [controller state and actions](PROJECT_LIFECYCLE_AND_VERIFICATION.md#controller-state-and-actions).

## Candidate drift or verification-copy failure

Tracked, untracked, deleted, and ignored paths participate in candidate binding. A
cache file, bytecode file, generated artifact, or manual cleanup can invalidate the
snapshot. Do not delete or regenerate files to force equality. Stop writes to the
candidate, inspect it read-only, and create a new isolated verification copy.

The copy fails closed for source drift, an existing or non-private destination,
outward/broken/Git-administration symlinks, or an invalid destination boundary. A
failed copy is not usable evidence. A non-`0700` immediate-parent diagnostic is emitted
only when its bounded inspection is small enough; otherwise the failure stays an invalid
destination boundary. Preserve the original candidate and report the unresolved failure.

## The gate rejects scope or verifier input

- A declared-path mismatch means Git found changes outside the envelope declaration.
- `--only` rejects every changed path outside its repeatable policy; `--allow` only
  permits known undeclared artifacts and does not override `--only`.
- A no-op with `--expect-edits` is a rejection, not a verified result.
- Non-empty worker `commands_run` or `tests_run` fields are untrusted claims and cause
  rejection; choose commands independently.
- `--verify-argv` must be a canonical JSON array and cannot smuggle an implicit shell.
- A verifier that mutates the candidate invalidates the exercised state.

Fix a real candidate defect through a bounded same-conversation repair when budget
remains. Fix a driver invocation error locally. Never weaken the gate simply to make
it green.

## A verifier needs environment or network access

The default verifier baseline excludes `HOME`. Add an ordinary variable only by exact
name with `--verify-env NAME`. Credential-like names, including `HOME`, require
`--verify-credential-env NAME` and the credential-access acknowledgement. Explicit
shell verification separately requires network and credential-access
acknowledgements.

Acknowledgements do not provide a value or network isolation and do not authorize an
external write. Candidate code can import unreviewed code, so expose no credential
merely to reproduce an ambient shell setup. Prefer a narrower offline verifier.

## The repair budget ends with failed or missing checks

Keep the useful candidate and report `partially_verified` with the exact failed,
missing, or unavailable checks and unresolved gaps. Do not erase the candidate,
silently start a new conversation, or call it verified. A fresh restart is a separate
explicit user decision.
