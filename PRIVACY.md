# Privacy disclosure

This document describes the data behavior of the open-source
`codex-agy-worker` project and its packaged Agent Skill. It is a project policy,
not a claim about every version or configuration of the third-party tools it calls.

## What the project itself does

The repository does not operate a hosted service, collect analytics, or send
telemetry on its own. Model-tier recommendations, Evidence Receipt v1 creation and
validation, and all offline test suites run locally without a network or provider.
Installing the skill copies its public workflow files and a local pointer to
the checkout; it does not contact a network service or change agy or Codex
configuration.

## When data can leave the machine

When a user explicitly dispatches a job, `agy-worker.sh` passes the task prompt to the
locally installed Antigravity CLI (`agy`), an external tool backed by Google/Gemini
services. Prefer `--provider-scope` for bounded jobs. Whole-worktree dispatch remains
an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception; when selected, treat
the entire disposable `--workdir` as worker-readable and potentially transmissible to
that service, even when the task names only a few paths. Prompt denylist instructions,
`qa-gate --only`, `--allow`, and `--add-dir` do not narrow that read boundary.

Optional `--provider-scope FILE --approve-transmission-sha SHA256` binds exact reviewed
read entries, their selected-content digest, and a write subset, then copies only
selected entries into a fresh owner-private mode-`0700` Gitless provider cwd. The
controller still locally enumerates and validates the complete worktree path/kind
surface and scope entries before staging. New jobs default to
`--provider-isolation session`, using the caller's existing AGY session and normal
HOME. AGY retains normal user filesystem and network authority: selection and
reconciliation do not enforce a host read/write boundary. Disclose this mode in the
initial approval alongside the task and selected content; the job cannot silently
switch modes later.

Explicit `--provider-isolation native` requires supported macOS scoped containment
with private HOME/TMP and never falls back to session mode. In native mode, the bound agy image receives non-local TCP
443, DNS through the local resolver socket, local TCP listener permissions, and
reviewed Keychain service access; this is not a recipient allowlist. On macOS,
the listener rule also permits wildcard binds, so the agy image can expose a
listener to the local network. Outbound connections to local TCP services remain denied.
The bound agy image can inspect metadata and existence of its executable's exact
parent directory for Core Foundation SSL initialization. This adds no directory
listing or sibling-file access and does not transfer to a different executed image.
The same image can read metadata for ancestors of its private HOME so SQLite can
resolve conversation database paths. This grants no ancestor listing or file data;
other executable images and self-verification receive no such exception.
Native preparation expresses the approved staged read/write scope in a generated
private AGY settings file. It copies no user settings and grants no commands,
URLs, MCP tools, or ambient paths; the native filesystem boundary remains in force.

The exact `/usr/bin/security` helper shares the reviewed Keychain service access
and can read the bound default Keychain file. This file rule grants no provider,
other-executable, directory, write, or additional network access. Before native
launch, the driver reads only the default Keychain locator and file identity, then
creates a minimal locator preference in the private provider HOME; it does not copy
owner preferences or credentials. The existing service permission cannot be limited
to one token or operation; disclose broader same-user Keychain read/change/delete
authority and the helper's exact file access in the initial approval package.
The stage is writable, while reconciliation enforces its approved write subset.
Process-group cleanup and trusted-local-owner limits are described in
[Security and compatibility](skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md).
Scope approval alone grants no provider execution, Git action, acceptance, or publication.

Before the initial provider attempt, approve the exact scope transmission digest or
whole-worktree manifest. Later resume, continue, and restart actions preserve that
mode and require the exact current controller-state approval. Codex binds those
state values; they do not require another human prompt while the approved task,
transmission, permissions, and budget still cover the action. Credentials, secrets,
private keys, regulated or
user-denied data, and unrelated private files must be absent from the entire default
worktree transmission or every entry selected for scoped staging. Telling the worker
not to read approved content is not a privacy control.

The project does not automatically submit GitHub issues, push code, merge branches,
or publish releases. Those are separate actions with separate approval boundaries.

The public conformance kit itself uses only checked-in synthetic content in private
disposable local repositories and invokes no agy, provider, or network client. Its
`--gate` argument is executable code selected by the user and runs with that user's
normal privileges; the kit does not sandbox it or prevent a hostile implementation
from reading files or using the network. Review a supplied gate before running it.
The supplied gate and loaded code, local owner and same-UID processes, and OS
administrators are trusted for cleanup pathname stability. Cleanup is descriptor-
relative while exact parent/root identities remain unchanged; drift produces a
sanitized failure and may leave a private residual. The runner never scans for or
chases a moved directory and makes no same-user tamper-resistance claim. The kit
discards bounded gate output and reports no fixture paths or captured bytes.

## Local artifacts and retention

Each job can create local private artifacts under `logs/<job>/`, including the task,
full prompt, agy stream, stderr, staged oversized prompt, and extracted envelope.
Temporary worktrees and envelopes may also exist outside the repository. Review and
sanitize any information before sharing it through the routes in [SUPPORT.md](SUPPORT.md).

When explicitly requested, `verify-job.sh` creates one local receipt at a new path the
user chose in an owner-private directory outside the audited repository. It records
the immutable base; SHA-256 hashes of the exact envelope snapshot, ordered path
policy, verifier commands, and candidate states; bounded gate outcome labels; and,
when supplied, the validated caller model/tier selection and canonical pre-dispatch
advisory (including its rationale, controlled evidence, and relative cost statement).
It does not store source or diff content, repository paths, prompts, worker prose,
raw logs, verifier commands or output, credentials, provider telemetry, or pricing.
Receipts are mode `0600`, unsigned, not self-authenticating, and never uploaded by
this command. The internal gate evidence descriptor is closed before any verifier
shell or interpreter starts. The wrapper removes executable shell/Python startup
controls only from the evidence-mode gate and verifier environment; it does not read
or modify the caller's configuration. Handled HUP, INT, and TERM interruptions remove
wrapper-owned snapshot, handoff, temporary, and partial receipt files. The user
controls durable receipt retention just like other local artifacts.

`evidence-report.sh` reads one explicitly named receipt and, when supplied, only the
explicitly named binding artifacts. It performs no dispatch, routing, gate, git, or
network action. Standard output is the default; an explicit new report file is mode
`0600` and never overwrites. Text, canonical JSON, Markdown, and GitHub Step Summary
formats contain only bounded verdict/outcome labels, hashes, deterministic verifier
labels, binding-presence flags, and fixed integrity and human-review statements. The
reporter never discovers or writes `GITHUB_STEP_SUMMARY`; a workflow must redirect
its stdout explicitly. It excludes source, diffs, prompts, worker prose, raw
commands or output, logs, credentials, and absolute repository paths. The report is
still unsigned and cannot authenticate a rewritten receipt.

When explicitly requested with `--timing-report <PATH>`, `scripts/ci-offline.sh`
publishes one mode-`0600`, no-overwrite timing report to an owner-private mode-`0700`
directory. It first requires a clean tracked/untracked worktree, then binds only the
exact current HEAD commit SHA, deterministic canonical stage inventory digest, gate
outcome, and observational monotonic wall-clock
durations per suite. It strictly excludes file paths, commands, environment values,
logs, credentials, provider/account data, timestamps, host identity, and cost claims.

CI shard execution (`scripts/ci_sharding.py` and `scripts/ci-offline.sh --shard`) publishes
one mode-`0600`, no-overwrite shard receipt to a mode-`0700` local directory. It binds
only the schema version (currently v2), kind (`agy-worker-ci-shard-receipt`), exact lowercase Git HEAD commit SHA,
deterministic canonical stage inventory digest, shard ID, expected stage IDs, observed stage IDs,
per-stage monotonic durations, outcome, and fixed unsigned integrity statement. It strictly excludes repository paths, commands,
environment values, logs, credentials, provider/account data, timestamps, host identity, and cost claims.
GitHub Actions uploads these deliberately privacy-safe receipts as one-day workflow artifacts;
uploaded copies inherit repository Actions access rather than local filesystem ownership.
The aggregate `test` check verifies all four receipts within the same workflow run and fails closed
on missing, malformed, duplicate, version-stale, or mismatched evidence. Standalone validation retains
read-only compatibility with the smaller historical v1 receipt and its stage-identity digest.

`job.sh` stores one explicitly named mode-`0600` lifecycle state file in an
owner-private external directory. It contains canonical absolute repository,
worktree, Git-common-directory, and receipt paths; filesystem identities; the exact
branch, immutable base, and job ID; state-history, receipt, and candidate SHA-256
bindings; gate exit/verdict; and cleanup progress. `status` emits only bounded state,
match, and hash facts. `preserve-instructions` prints local Git commands and paths
only when explicitly requested; it executes none. The lifecycle performs no network,
provider, dispatch, commit, or publication action. Rejected-only cleanup removes the
exact registered disposable worktree and unchanged branch ref after fresh explicit
hash approvals, but deliberately retains the cleaned private state tombstone. Partial
or ambiguous states are retained for manual recovery rather than automatically
deleted.

Gate-owned Git reads also ignore caller Git variables and system/global config,
disable fsmonitor/hooks and external diff/textconv, and reject effective repository
clean/process/required content-filter definitions before comparison or snapshots.
Filter rejection diagnostics omit configured commands and values.

Lifecycle-owned Git execution ignores system/global and caller Git configuration,
uses a private empty hooks directory, and disables prompts, pagers, fsmonitor,
external diff, protocols, and recursive submodules. Before worktree creation it
rejects local included hook/helper/filter configuration and any effective base-tree
or repository-info content-filter attribute. It therefore does not grant repository
hooks or filters execution authority during lifecycle initialization. Fatal or
ambiguous ref evidence is never treated as absence and retains the truthful recovery
state.

The project does not delete these artifacts automatically. The person running the
tool controls retention and should review and remove unneeded artifacts according to
their own policy. Do not commit or paste raw logs into public reports.

The optional local update notifier stores a canonical status, result fingerprint,
source-manifest hashes, and resumable install/uninstall state under the account's
owner-private Application Support directory. It does not store raw compatibility
output, repository content, credentials, prompts, provider data, or personal paths in
notifications. The notifier itself has no independent network or mutating Git
authority; its hash-bound child invokes the existing read-only `update.sh check
--watch`, which performs fixed bounded HTTPS requests and local Git inspection with
global/system configuration disabled. It never applies an update or invokes agy,
Codex work, or a provider. Uninstall preserves replacement or ambiguous recovery
state rather than deleting it. A displayed macOS notification cannot be retracted.

The explicit-account models capture runner is a separate, never-automatic action.
Its checked-in tests use only disposable synthetic account roots and make no agy,
provider, or network call. Every production invocation requires separate user
authorization for the exact canonical owner-`0700` account HOME/profile and one
snapshot-backed `agy models` call. The external CLI may read account contents or use
credentials under its own behavior. It may also write or mutate normal HOME state and
create caches. The runner does not enumerate those contents and cannot detect,
prevent, or revert HOME changes; account residuals may remain even when capture
rejects. The account HOME, local owner and same-UID processes, reviewed source and
interpreter, and OS administrators are trusted.

After group closure, capture-owned TMP/XDG/cwd must be unchanged and empty. The fixed
1.1.12 JSON capture bridge has one narrower reviewed exception: it may hash and
compare-delete the exact owner-private bounded language-server schema cache leaf in
its own TMP, fsync, and then prove scratch is empty. Every other cache shape rejects
and remains a private residual. On a
bounded exit-zero observation the runner retains otherwise uninterpreted raw
stdout/stderr, exact profile and runner bytes, bounded summary, and capture record in
a new owner-private directory; files are mode `0600` and raw bytes are never printed.
The sanitized console JSON contains only the artifact root, capture SHA-256, and
`captured` status. The final marker is `models.capture.sha256`, not an accepted
binding. Output semantics such as authentication, license, permission, quota,
rate-limit, interactive, or inventory content are decided only by later offline
reconciliation. Nonzero, overflow, timeout, identity/scratch drift, or publication
failure publishes no final marker. The runner never logs in, prompts, retries, falls
back, dispatches a task, selects or routes a model, changes metadata, or uploads the
artifacts. The user controls retention and must not commit the private profile or raw
evidence.

`scripts/models_capture_profile.py` is the separate, process-inert preparation
step for that action. It accepts only explicit stdin paths, does not inspect
HOME contents or ambient configuration, and validates no-follow external source,
snapshot, and version evidence before atomically creating one owner-private canonical
profile. It never invokes agy, a provider, a network client, a shell, or a Git
command; preparing a profile does not authorize a capture.

`scripts/models_capture_1_1_22_classifier.py` is the separate sidecar maintenance
tool for diagnosing sanitized 1.1.22 models capture failure evidence. It requires an
explicit owner-private (`0700`) directory path, never scans for evidence, and enforces
strict fail-closed checks on permissions, topology, and artifact hashes. Its output is
a mode-`0600` canonical JSON record containing only the classified category, origin,
hashes, and enforced limitations. It excludes all raw stderr/stdout text, error prose,
absolute filesystem paths, and account identifiers, and grants no activation, retry,
or routing authority.

`scripts/models_capture_1_1_22_reprofile.py` is a separate, process-inert reprofile
preparation adapter that accepts an already-validated prior 1.1.22 capture profile
and produces a new profile reflecting exactly one permitted change:
`account_home_identity.nlink`. It opens the explicitly supplied account HOME only for
no-follow descriptor metadata; it never enumerates or reads HOME contents. Its output
is a mode-`0600` canonical profile in a distinct owner-private output root. It has no
subprocess, network, Git, retry, capture, inventory acceptance, routing, or activation
authority. Recovery validation is bounded to the explicitly supplied recovery root's
fixed artifact and scratch allowlists; it does not expand into HOME discovery.
Reprofiling does not authorize a capture or renew any prior one-call authorization.

## Support and changes

Questions about this disclosure can be opened through the route in
[SUPPORT.md](SUPPORT.md) without including private content. Material changes to the
project's data flow should update this document before a public release.
