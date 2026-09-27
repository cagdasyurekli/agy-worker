# Architectural lessons

These are durable prevention rules for `codex-agy-worker`. This file is not a
release log, task diary, or list of completed work.

## The acceptance gate must not trust repository Git configuration

Scope reads and before/after candidate snapshots must share hardened Git execution.
Scrub caller Git variables, disable helper execution and index shortcuts, and reject
effective content-filter definitions before content-sensitive reads. A stale index
with a lying fsmonitor can conceal undeclared changes; a clean filter can rewrite
comparison bytes. Test direct and receipt paths without refreshing the index between
fixture setup and the gate. Match path policy by segments so a wildcard cannot
silently authorize deeper directories.

## Reap an exited leader before binding its surviving process group

A terminated child may remain a zombie in Darwin process-group enumeration while
its detailed process identity is unavailable. Reap an already-exited Popen child
before binding remaining group members. Preserve UID, session, group, start-time,
and PID-reuse checks for live members; missing zombie metadata must not become a
blanket permission to ignore an unbound live process. Cover both exited leaders
and live leaders with surviving children.

## A worker report is never evidence

The worker is outside the trust boundary. Its envelope is useful for routing and
scope comparison, but every claim must be re-derived by the driver.

- Validate the complete envelope shape before reading it.
- Compare every declared path and change kind with Git reality.
- Never execute `commands_run` or `tests_run`; they are untrusted text. Only
  driver-authored verifier specs may execute. Prefer canonical `--verify-argv` arrays
  so argument bytes never cross an implicit shell; shell verification needs explicit
  network and credential acknowledgements, and diagnostics identify only label/mode.
- Provider-facing envelopes may omit only those report-only arrays; canonicalization
  restores them empty before validating the complete contract. A canonical summary is
  bounded to 8,192 characters. Omission is ergonomics, not permission for a worker
  command or test claim to execute.
- Require an accepting gate and human diff review before integrating a candidate.
  Preserving a rejected or routed candidate for forensic review is distinct from
  accepting or integrating it. A confident summary or high confidence score changes
  nothing.

## Git scope must be immutable and complete

Capture the full commit ID before dispatch. Mutable names such as `HEAD` or branch
names let the comparison point move and invalidate the audit.

Constrain edit jobs with driver-owned `--only` policies, check declared-versus-
actual paths and change kinds, and include ignored as well as ordinary untracked
files. An allowlisted artifact remains auditable and must not satisfy
`--expect-edits`. Snapshot the complete Git-visible candidate before and after
verification so a passing verifier cannot rewrite it. Use a branch-backed disposable
worktree so rejected changes are isolated and accepted changes are not destroyed by
cleanup.

Resolve-undo metadata in the Git index (`REUC`) leaves the worktree state outside
semantic snapshot guarantees. When observed immediately before provider launch, the
controller fails closed with the bounded reason `resolve_undo_present`, exit code 20,
and `failure_stage=binding_failure` without launching a provider process, exposing
paths/OIDs/counts, or mutating the index. The controller never clears index metadata;
explicit recovery via `git update-index --clear-resolve-undo` is owner-managed for
a disposable worktree.

## Progress renews only an idle lease

Progress is evidence that a locally supervised stream is still moving, not evidence
of success or permission to run indefinitely. Renew an idle lease only for bounded,
schema-valid lifecycle events; malformed, oversized, or unrecognized bytes must not
count as a heartbeat. Keep idle timeout, per-attempt hard deadline, and caller-owned
absolute maximum separate. A fresh heartbeat may justify an explicit bounded deadline
extension, but never an automatic fresh provider attempt or an unbounded extension.
Sanitize elapsed time, progress age/count, attempt origin, and terminal reason; do
not publish progress content, prompts, raw errors, or conversation identifiers.

Timeout recovery is a new authority decision. Only a candidate-free failed state may
be eligible for exact-conversation resume; make any new conversation an explicit,
labelled restart. Local status and cancellation describe the controller and its process
group only. They do not prove a provider's remote status or cancellation.

Pre-gate dispatch failure is not a rejected receipt. Keep it in a separate terminal
lifecycle state and permit cleanup only after binding the exact closed controller,
immutable lifecycle worktree/base, current state and candidate approvals, and an
empty or explicitly discarded candidate. Never force a receiptless residual through
the receipt-based cleanup authority.

## Mode flags can be prompt transformations

An upstream mode label may be implemented by transforming the prompt rather than by
enforcing a filesystem permission. Do not disable the mechanism that applies that
mode in the same invocation. For plan dispatches, stage untrusted/full prompt content
privately and pass only a fixed driver prompt when slash expansion is required for the
upstream transformation. Still describe the mode honestly: disposable worktrees and
post-run no-change gates, not the label itself, provide the enforceable read-only
boundary.

## Quality evidence must guide work, not prevent useful work

A schema-valid envelope, unchanged diff, and steady progress prove transport and
bounded execution; they do not prove exhaustive semantic coverage. State that limit
plainly, spot-check broad reports, and have Codex run the repository's meaningful
checks. Do not turn the absence of an exhaustive proof into a generic dispatch ban:
an exploration can be useful, and a project candidate can be valuable even when some
checks remain unresolved.

Treat assurance as graduated. For explicit workflows, `verified` requires Verification
v2; `explore` needs complete coverage, zero unresolved gaps, zero failed checks, and
zero missing checks, while `task`/`project` need at least one passed check, zero
failed/missing checks, and completed driver diff review. `partially_verified` preserves a useful candidate with exact unresolved
checks. `blocked` is for a genuine authorization, repository-boundary, or execution
obstacle. A failed check should normally create a bounded same-conversation repair
request, not an automatic fresh retry, deletion, or refusal.

Candidate availability and provider success are different facts. A terminal provider
`ERROR` candidate goes to `result`, driver Verification v2, then `continue` or
`finalize`; a `CANCELED` candidate is preserved for `result` and finalization or an
explicit fresh restart, never resume/continue. Preserve means retain for review and
driver disposition, not accept or integrate; neither branch is automatic.
Worktree reconciliation must be ordered around controller-owned quiescence: capture
the baseline before provider launch, capture the terminal candidate after the provider
group is reaped, and recompute the exact queued SHA+entry baseline before every
provider `Popen`, `continue`, and `finalize`. Compare two bounded no-follow directory
topology manifests (names, kinds, directory metadata, and empty directories) without
re-reading regular-file content already covered by the primary observation; bind the
Git, index, root, and selected-Git target facts. Drift or unavailable evidence fails
closed.
This is not a filesystem snapshot, FSEvents watcher, hostile same-user tamper defense,
clean-worktree/review/acceptance proof, or semantic recommendation. The local owner,
same-UID processes, and OS administrators remain the TCB, and mutation after an
entry's final read is the explicit portable residual. Text status must remain sanitized
driver-owned output; JSON may expose bounded lifecycle facts but not worker prose,
prompts, paths, raw logs, or conversation IDs.

Use v9 phases literally: an active initial, resume, or restart attempt is
`dispatching`; a pre-candidate failure is `attempt-failed`; a recognized candidate is
`awaiting-verification`; an active continuation is `repairing`; and an actual failed
continuation attempt is `repair-failed`. Controller terminal phases are `completed` or
`blocked`; exact Codex driver decisions/dispositions are `verified`,
`partially_verified`, `rejected`, or `blocked`.

Lifecycle disposition needs a current candidate binding. Verification v2 binds the
candidate SHA and records checks, coverage, evidence/gap counts, and diff-review
completion. Read old verification only for compatibility; never use it to `continue`
or `finalize`. Exact-conversation `resume` and visibly fresh `restart` both require
the current state SHA, and neither is automatic.

Candidate snapshots bind ignored artifacts as well as tracked and untracked content.
If a provider leaves stale bytecode and a normal driver import rewrites it, removing or
regenerating cache files cannot prove the original candidate returned. Preserve that
candidate and run writable checks in `verification-copy`: it binds the current
result/schema/root/worktree before and after a private, no-follow copy that excludes
`.git`. Every contained link is rebased to an equivalent relative target in that copy,
while broken/outward/Git-admin links are rejected. The copy is only a physical verifier workspace; it neither reconciles
drift nor records provider success, acceptance, or a driver disposition. Git-dependent
inspection remains read-only against the original candidate.

That check is bounded to an owner-controlled quiescent interval. It fails closed on
ordinary source or destination-parent drift and never reports a failed copy as usable,
but it is not same-UID tamper resistance: a local actor can still substitute a regular
file with an outward link only for the read and restore it before rebinding. Keep that
exact residual rather than turning a portable local verifier into a full hostile-process
filesystem snapshot.

Two bounded remedies were compared. An isolated verification copy keeps the candidate
strict, is portable with Python's standard library, and costs one bounded local copy;
it was selected. Ignored-drift reconciliation or a second controller digest would cost
less I/O but needs a narrow allowlist and a second authority rule that could normalize
unknown provider or driver artifacts into a candidate. That residual is unacceptable:
the controller continues to reject every source drift and owns only deterministic
binding facts, while Codex still owns the choice and interpretation of checks.

Direct selection preserves the exact caller model and effort. Every launch uses a
bounded capability probe and immediate executable-binding recheck. Version text is
diagnostic only; help proves neither model availability nor account entitlement.
A failed preflight must stop before provider execution without silently changing the
choice. Driver review and candidate-bound verification remain independent.

The following historical migration contract was retired by the unreleased
[current-only job format change](PROJECT_WORKFLOW.md#retired-job-formats-and-flags):
V1 remained historical and read-only. A V3/V4 current result could
make its first lifecycle transition only with the current state SHA plus the exact
`migration_binding_sha256` exposed by `status`; both were rebound under the transition
lock. V3/V4 `last_success_*`-only evidence remained read-only. Persisted V5/V6 state
retained its exact legacy digest; V7 retained its exact semantic-v1 digest; and V8
retained its explicit semantic-v1 algorithm. An approved V5/V6 transition first
proved that legacy digest, then atomically recorded a fresh semantic-v1 V9 baseline
and candidate; V7/V8 reused their exact proved semantic observation. New V9 state
also persisted a stable no-follow root/Git-administration boundary identity, separate
from mutable candidate content.

Security controls protect irreversible boundaries; they are not the product goal.
Keep provider-transmission approval, worktree containment, credential exclusion,
dangerous-bypass rejection, and explicit publication authority. Do not require an
exact file list or a prewritten acceptance command merely to start useful
Codex-guided work.

Test policy text against natural requests such as “build this project”, “discover the
files”, “review this repository”, and “repair the failed tests”. A policy that only
passes narrow happy-path wording can silently make the product unusable even while its
security tests remain green.

## Updates are explicit and trust official sources

`update.sh check` is read-only. `update.sh apply` is an explicit human-authorized
operation; never run it in the background or as part of a worker job. The fixed
project release origin must not be environment-overridable. A verified different
commit is an update observation, not proof of version ordering; unavailable or
malformed evidence remains inconclusive.

A literal GitHub URL passed to `git ls-remote` is not a fixed-source guarantee: Git
still honors repository and global `url.*.insteadOf`, proxy, credential, and transport
configuration. Read-only project release evidence therefore uses an exact
`api.github.com` REST repository/path allowlist, a proxyless redirect-rejecting strict
JSON client, and no Git network command. Keep the explicit apply-time fetch limitation
visible; observation hardening does not silently harden mutation.

A stable release tag should bind through the compact exact Git ref document, not a
full commit document whose inert file and parent metadata can exceed an otherwise
sound evidence bound. Keep release-document and ref/source-document byte ceilings
separate, test both the observed large-release accept path and overflow rejection,
and still compare the API revision with the separately fetched Git tag before apply.

Bounding a parent command is insufficient when stdout/stderr pipes or descendants can
outlive it. Capture both streams incrementally, cap them independently, impose a hard
deadline, create a fresh process group, and kill/reap that group on timeout, overflow,
or HUP/INT/TERM. Return only parsed canonical fields; never surface raw child output
as compatibility evidence or diagnostics.

## Capabilities and response semantics are separate

A local help probe establishes only the required interface. Keep provider response
handling strict and version-independent: denial presence blocks automatic continuation,
malformed framing is never salvaged, and a valid candidate remains available for
independent driver verification. A version string cannot establish task success.

## Diagnostics observe; they do not repair

A readiness command is safest when its success claim is narrower than the job it
precedes. Check only bounded offline prerequisites and semantic command output; do
not turn an exit code, usage page, or executable name into proof of compatibility.
Keep paths and raw command output out of reports, because even a diagnostic can leak
repository names, credentials, or personal configuration.

Never make a doctor scan home configuration, probe invented authentication commands,
call a provider, access the network, run an updater, or repair a failure. Report
missing capabilities or malformed prerequisites as not ready. Green proves only the tested offline conditions, not
authentication, provider availability, sandbox permission, task quality, or a future
dispatch. Portable diagnostics reuse the runtime capability probe and fail closed when
their bundle is incomplete. Treat temp placement and
signal propagation as part of the trust boundary: ignore caller temp paths, keep
captures private and bounded, and terminate the exact active process group. A
non-symlink file is not contained when one of its parent directories is a symlink;
canonicalize the root and require package-owned parents to be real directories.

A disposable candidate worktree isolates files, not execution. Candidate validation
runs release-owned scripts with the invoking user's privileges. Exact tag/ref and
fast-forward checks prove transport consistency, not that candidate code is harmless.
Keep the expected-origin boundary, protect the release account and tag process, and
do not describe candidate execution as a sandbox.

## Private evidence must be private when created

Prompts, model streams, stderr, and extracted envelopes can contain repository data.
Set an owner-only process mask before creating dispatcher-owned log directories or
files; fixing permissions after a write leaves an avoidable disclosure window. A
custom log root belongs to the caller, so contain each new job under its own private
directory instead of rewriting that root. Before the first job write, require the
final existing root itself to be a current-user-owned real directory without
group/other write bits, then use its physical path. Create a missing root under the
private mask. This is a bounded final-component invariant, not proof that every
ancestor is safe or that all filesystem TOCTOU races are eliminated. Create the job
directory atomically and fail closed when its path already names a directory, file,
or symlink; reusing an attacker-prepared path defeats creation-time permissions.

Do not let log hardening alter candidate-file behavior. Restore the caller's mask
only inside the untrusted worker child while keeping the shell-owned redirections
private. An oversized staged prompt may need its proven read-only access modes during
agy execution, but it must stay below a non-traversable job parent and return to
owner-only modes immediately afterward. Restore those modes from the normal child
return path and an EXIT trap; HUP, INT, and TERM handlers must restore first and then
re-raise the same signal so cleanup does not turn termination into success.

A private parent directory does not determine the modes of files a child creates.
Set an owner-private umask at the child execution boundary without changing the
caller mask, and keep post-child validators strict: accept an expected cache leaf
only when its exact owner-only mode and descriptor identity still match.

Treat a direct-selection version probe as a process-group boundary too. Read its
stdout incrementally under byte and wall-clock limits, close the whole group on
oversize, timeout, HUP, INT, or TERM, and do so before reading the task or publishing
selection provenance. Signal cleanup must preserve the conventional `128 + signal`
status instead of relabelling interruption as unavailable evidence.

## Model routing is explicit

The caller selects the tier or direct model/effort input. Built-in retries preserve
that choice; gate failures do not silently increase cost or effort. Recommendations
remain visible, advisory, and separate from dispatch and gate acceptance. Forward
model and effort as separate literal arguments without constructing a compound slug
or inventing an effort catalog. AGY rejection is visible, with no fallback.
Preserve presence as data: unset differs from explicit empty, CLI and matching
environment sources conflict even when equal, and repeated components never mean
“last wins.” Bind the exact choice in private selection and receipt records.

Only an independently observed, bounded quality or verification gap can justify
recommending a higher named tier. Permission, authentication, scope-policy, contract,
untrusted-claim, and human-required failures need correction at their own boundary,
not more model spend. Do not infer ordering for agy's `default` choice or a custom
model label, and do not invent a tier above the highest named tier. Reject ambiguous
or cross-stage evidence rather than guessing.

## A rejected worker can prove the gate works

The real Playbook-Gemini exercise exposed the distinction between worker success and
gate success: focused tests passed on a corrective attempt, but `git diff --check`
still failed, so the candidate was correctly rejected. Passing tests do not override
scope or diff hygiene. Report such an outcome as successful enforcement by the gate,
not as a successful worker delivery, and never weaken independent checks to obtain a
green result.

## A starter proof is not an acceptance claim

A useful offline proof must exercise the maintained gate, not a reimplementation of
its decision logic. Give the passing and rejecting cases independent repositories,
require their exact exit contracts, and include a negative control showing that a
copied permissive gate cannot make the overall proof pass. Keep canonical fixtures
strict so silent edits cannot turn a teaching example into a different claim.

Buffer success output until every case and cleanup step succeeds. Describe the
result as evidence for the fixed synthetic cases only: a gate pass is still not a
human diff review, accepted candidate, correctness result, security certification,
benchmark, or production validation.

## Public conformance is fixture compatibility, not certification

A compatibility claim needs executable, versioned fixtures rather than prose. Bind
the manifest and every repository/envelope source by digest, require exact exits, and
include negative cases for the tempting trust-boundary regressions: worker claims,
ignored files, mutable bases, missing or mutating verification, and human-required
outcomes. A permissive reference gate must fail the kit.

Do not turn a public fixture suite into a security badge. A supplied gate is code run
with the caller's privileges, and a finite public suite can be special-cased. Bound
ordinary execution and output, keep results nonleaking, state that detached hostile
code is outside process-group containment, and limit the claim to the reviewed
fixture version. Receipt, report, lifecycle, dispatch, and provider compatibility
need their own contracts; passing direct gate fixtures proves none of them.

Cleanup must name its TCB honestly. The supplied gate and loaded code, local owner
and same-UID processes, and OS administrators can mutate pathnames. Hold no-follow,
close-on-exec parent/root descriptors; bind exact identities; delete nested content
with bounded descriptor-relative operations; and unlink symlinks without traversing
their targets. Final pathname removal still trusts that TCB. On any identity drift,
stop without scanning for or chasing the moved inode and report a sanitized residual;
do not claim same-user tamper resistance or guaranteed cleanup under hostile code.

## Receipts bind observations; they do not create authority

A useful receipt records the gate's own bounded structured handoff rather than
parsing prose or reimplementing acceptance in an outer wrapper. Snapshot the exact
envelope bytes the gate validates, retain the resolved immutable base and the gate's
internal initial/final candidate-state digests, and cross-check the gate process exit
against one unique handoff. Missing, duplicate, malformed, mismatched, interrupted,
or unknown evidence is an internal protocol failure—not a result to reconstruct.

Keep private data out by hashing ordered policy and verifier commands and assigning
deterministic labels. An optional selection or pre-dispatch advisory must pass its
own canonical policy and agree when both are supplied; it still cannot participate
in acceptance or change the selected model. Never bind a later post-gate advisory by
rewriting a one-pass receipt.

CI formatting is another presentation boundary, not an integration authority. Build
canonical JSON from the validated bounded report fields instead of serializing the
receipt again. Keep Markdown dynamic values on a narrow atom grammar and reject final
payloads that can start workflow commands or inject links/HTML. A Step Summary mode
should write stdout like every other format; shell redirection to
`GITHUB_STEP_SUMMARY` must remain explicit in trusted workflow code so the renderer
cannot discover CI environment paths, comment, upload, or acquire GitHub credentials.

Durability and non-overwrite are separate properties. Write and validate a same-dir
mode-`0600` temporary, `fsync` it, publish with an atomic hard link that refuses an
existing target, `fsync` the parent, remove the temporary, and `fsync` the parent
again. On validation, link, or durability failure, remove every publisher-owned
partial and never delete or overwrite a raced caller/attacker target. Revalidate the
private parent immediately before linking.

A pre-opened evidence descriptor is authority, not ordinary inherited process state.
Validate it in the gate parent, then close it before every verifier child and
descendant executes; otherwise a verifier can forge or corrupt the supposedly
gate-owned handoff. Signal ownership must span the full receipt transaction, not just
the gate wait: track private files and the pinned published inode before the atomic
link, terminate and reap the active process group, and remove only wrapper-owned
artifacts on HUP, INT, or TERM.

Closing a sensitive descriptor in a newly started helper is already too late:
Python `sitecustomize` or a shell `BASH_ENV` hook can execute before that helper's
first statement. Bind evidence mode to the receipt wrapper, sanitize executable
startup controls before launching the gate, run gate-owned Python with isolated/no-site
startup, and close the numeric validated FD with a Bash builtin in the already-running
gate process before starting the verifier shell. Do not preserve the ambient verifier
environment: start from the closed baseline and forward only explicitly approved names
to the verifier child, never stripped startup controls or the internal capability.

Schema validation detects malformed and internally inconsistent content, not an
authorized rewrite. An unsigned JSON document can be changed and rehashed by anyone
who can replace it. State that limitation in the document itself; require a separately
trusted envelope or candidate digest when later tampering matters. Receipt existence
does not replace `qa-gate.sh`, human diff review, signing, authenticity, correctness,
or security evidence.

Rendering is a view, not a new evidence authority. Validate the complete receipt and
every explicitly supplied binding before producing a byte of text, then render only
fixed labels, hashes, and bounded presence flags. Do not import raw paths, commands,
prompts, logs, or worker prose into a “friendly” report. Keep receipt-only selection
and recommendation-record validation side-effect-free: canonical recommendation
generation belongs only to the explicit pre-gate publication input, never to later
validation or rendering. A format change cannot improve `rejected` or `routed`, and
`gate-passed` still needs human diff review.

## Distribution must preserve the trust boundary

A public skill cannot depend on a developer's absolute checkout path or assume that
an installer copied the surrounding repository. Keep the core runtime once, inside
the canonical Agent Skills bundle, and make repository-root commands compatibility
wrappers. A complete plugin may resolve those wrappers and an explicit standalone
install may use a local checkout marker, but a skill-folder-only copy must fall back
to its bundled runtime without fetching code. Test every accepted layout, reject
incomplete bundles and invalid markers, and preserve the root CLI's observable
defaults. Do not duplicate the runtime across packages or introduce a daemon merely
to make installation look uniform.

Skill installation is not consent to transmit a repository. Before dispatch, treat
the entire disposable worktree as worker-readable and potentially transmissible
through agy to Google/Gemini when whole-worktree mode is selected. Scoped approval is
valid only for the exact reviewed read/write policy and selected-content digest.
Prompt denylist and gate path policies govern task writes and candidate acceptance,
not read isolation. Keep secrets, denied paths, unrelated private files, and local
logs out of every provider attempt, and make privacy, support, and usage terms public
alongside the GitHub distribution.

Disclosure alone is weaker than admission control. The ordinary facade should require
the caller to bind either the current whole-worktree manifest or the selected-content
scope and transmission digest; a deprecated broad-mode spelling may remain readable
only behind an explicit migration acknowledgement, never as a silent default.

Catalog metadata is a public product claim. Keep the skill frontmatter explicit about
the supported host, runtime prerequisites, license, and release version; a provider
model slug is not host compatibility. Put the fuller execution-boundary explanation in
a focused skill reference, and do not add empty assets or unsupported integrations to
raise a directory score.

Claude metadata was previously removed because an untested catalog surface implied
host support. Reintroducing it requires one runtime, positive and negative layout
tests, portable driver instructions, and an explicit experimental label until live
installation, background dispatch, and sandbox checks pass. Offline package tests
do not replace that host evidence.

An inherited shell environment is also a trust boundary. Provider processes and local
interface probes start from a small operational baseline; driver-owned verification
uses a stricter baseline without `HOME`. Additional variables require exact-name opt-in,
and only their names—not values—belong in frozen command or receipt policy. Verifier-only values must
cross the outer gate through a private descriptor and enter only the `env -i` verifier
child; ambient preservation would let schema or Git controls influence gate work.
Credential-like verifier names require a separate flag and acknowledgement; an
acknowledgement never supplies the value. This reduces accidental secret exposure but
does not isolate `PATH`, filesystem, network, or same-user processes. A trusted test
command can still import unreviewed candidate code.

A provider-readable path preview is useful only if it branches before prompt, model,
provider, logging, state, stdin, and network work. Build it from two complete bounded
no-follow scans, expose only relative path/kind entries, and keep the root `.git`
control marker out of the public manifest. A path digest is review evidence, not
transmission approval and not a future-launch binding.

Keep distribution surfaces no broader than the maintained product. A Codex package
manifest and an explicitly approved repo marketplace descriptor can validate one local
root package without creating a listing. Bind the marketplace entry name to the plugin
manifest and require source `.`: a `plugins/` copy, second skill, second runtime,
escaping path, or symlinked source turns a simple discovery surface into an unreviewed
second distribution. Installed-skill bytes must still match the canonical source.
Neither descriptor installs, publishes, or enables an external catalog; those remain
owner actions. Do not retain Claude catalogs after choosing a GitHub-first, Codex-only
product. GitHub Pages enablement and search-console ownership are external state changes with
their own approval and verification. Use accurate natural-language landing copy, a
canonical URL, and a sitemap that the owner explicitly submits through Search Console;
do not trade the project's evidence boundary for keyword stuffing or unsupported
product claims. Do not place `robots.txt` under a GitHub Pages project subpath and call
it crawler control: robots rules are host-root metadata owned by the site owner,
outside this repository's publication slice.

Treat Python syntax compilation as a package-boundary write. `-B` does not suppress
bytecode emitted by an explicit `py_compile` invocation, so CI and contributor checks
must set `sys.pycache_prefix` to a private external temporary directory inside an
isolated interpreter (`-I` ignores `PYTHONPYCACHEPREFIX`). A cache inside the public
skill is a distribution leak, not harmless ignored state; keep the positive
external-cache path and a plain-compile negative control paired offline.

## Public discovery claims need the same evidence discipline

The landing page and README are part of the trust boundary because users choose
whether to install before reading the implementation. Lead with the bounded mechanism:
Codex delegates to agy, then the driver independently checks Git scope and runs its own
verification commands. Do not turn those checks into claims that the project proves
general correctness, security, or official endorsement.

Keep GitHub repository files separate from GitHub repository settings. A checked-in
Pages source, sitemap, policy, or preview recommendation does not prove that Pages,
About metadata, topics, homepage, private reporting, search indexing, or a social
preview is enabled. Treat each external setting as a deliberate owner action and
verify live state after any separately approved change.

Treat brand assets as an interface with size-specific responsibilities. Use the
light/dark master SVGs for large surfaces, the pixel-hinted micro variants for
favicon-sized rendering, and an opaque, exact-size raster for social previews. Keep
all variants on the same geometry and palette, reject external SVG references and
vendor marks mechanically, allow only the SVG elements and attributes the masters
need, and compare light/dark path geometry in order. Verify every PNG chunk and CRC,
then boundedly decode the scanlines so valid framing cannot hide transparency or a
broken image stream. Do not imply that a checked-in preview is active in GitHub
repository settings.

A clean worktree does not prove that a committed pull-request patch passes
`git diff --check`. CI must check the GitHub event's immutable base-to-head range:
base...head for pull requests, before..head for ordinary pushes, and the empty tree
to head for an all-zero initial push. Give checkout enough history for those objects;
do not repair a missing range by fetching an extra untrusted ref inside the gate.
Repository `.gitattributes` can classify a path as `-diff` and make Git's own check
skip its content, so pair that check with a globally bounded, linear raw-blob scan of
every changed regular head file. The stricter scan rejects pre-existing hygiene
defects in a changed file and rejects binary, oversized, or unsupported committed
types fail-closed; it does not run diff algorithms or attribute-selected drivers.
Do not launch `git cat-file` once per changed blob: the maximum-path fixture turns
that design into thousands of processes and can consume the shared CI deadline.
Feed fixed, full object IDs to one bounded batch reader and bind every response's
order, ID, type, declared size, delimiter, total bytes, stderr, and completion.

Do not make destructive lifecycle recovery an automatic continuation of old
approval. Bind a private canonical state file to the exact repository, worktree,
branch ref, immutable base, job ID, Receipt bytes, and candidate digest; advance it
with sequence and previous-state hashes. Persist cleanup-in-progress before removing
anything, record each completed Git step durably, and require fresh current-state,
job, and candidate approvals on every new invocation. If reconciliation observes a
completed worktree-removal step, publish that truth and stop before deleting the ref;
the newly written state needs new approval. Remove a branch only with exact
compare-and-delete against the recorded base, never a force-delete shortcut.

A worktree is not an execution sandbox. `git worktree add` can run repository
checkout hooks and content filters before a worker ever starts. Use one fixed
sanitized Git runner, disable hooks and ambient helpers, inspect local included
config, and reject every effective content-filter attribute before checkout. Branch
validation must bind Git's canonical stdout rather than only its exit code: checkout
shorthand such as `@{-1}` can canonicalize to a different ref. During cleanup, a ref
probe's fatal exit is uncertainty, not absence; only the command's documented
missing-ref status can advance a durable cleaned tombstone.

Repository forms rejected by the semantic snapshot must fail before lifecycle state
is queued. In particular, a partial/promisor clone is a known unsupported form, so
the same bounded snapshot observation should raise one fixed sanitized full-clone
diagnostic during initial-state construction. Persisting a `None` baseline merely
defers the known failure to the controller, consumes a cycle, and loses the actionable
cause behind a generic binding failure.

A symlink inside a candidate is not automatically foreign data. The canonical gate
digest binds its path, mode, and target. A cleanup scan may therefore delete the link
node when the whole current candidate still matches the rejected Receipt, but it must
use lstat-only traversal and never follow the target. Nested repositories, initialized
submodules, mount/device changes, special nodes, and any digest drift remain manual
recovery boundaries.

Hard-link publication has a real two-name lifecycle. Record staging and final as the
same owned inode with derived `nlink=2`, unlink staging without a signal checkpoint or
injected durability hook, then record and reopen-verify final `nlink=1` before polling.
Rollback must decrement the remaining exact shared-link expectation after unlink;
foreign replacement paths remain reserved residual shape, never deletion authority.

A CLI that must make signal handling and durable acceptance agree should own its
process through the boundary. A Python handler should only accumulate signals; safe
checkpoints choose from the accumulated set by a documented fixed priority and freeze
that choice, which is not a claim about chronological delivery. Preserve inherited
ignored handlers and leave caller-blocked signals outside the owned set; never consume
their pending signals as lifecycle evidence. Keep owned signals unblocked and poll
through large copies and hashes,
provisional publication, validation, durability, and the complete success flush while
rollback descriptors remain open. Then block signals, take one completion snapshot,
and call `os._exit(0)` without restoring handlers or unblocking. An embedded API
cannot make the final restore-mask handoff atomic: signals absent from its snapshot
become caller-owned. Polling between
1 MiB userspace chunks bounds observation opportunities, not a single kernel syscall.


Hashing an opaque “approval” file is not review evidence. Parse and cohere canonical
Receipt, dispatch, tool/version, selection, verifier, candidate-diff, approval, and
human-review records, then read their exact `100644` blobs from immutable Git objects.
Require evidence, approval/review, and transition as strict ancestor stages. Be honest
about the boundary: protected-main ancestry proves ordering under the maintainer and
local-Git TCB, not human identity or a cryptographic signature.

Frequent upstream releases should not require a new local version registry. Probe
the required interface before each launch and bind the executable immediately before
use. Do not infer model availability, task quality, or permission from those probes.

A local notifier is a process supervisor, not a cron-shaped shell shortcut. Bind the
complete transitive executable/data manifest, derive HOME from the account database,
serialize lifecycle operations, reconcile launchd state after every ambiguous call,
and retain authenticated uninstall authority through partial cleanup. Parent-death
notification needs an acknowledgement that nested groups actually closed. A desktop
notification is an irreversible final side effect; record only an attempt and never
claim it can be rolled back.

Changing a closed notifier source manifest can retire the installed record format.
Reject that old format read-only before creating a lock or directory or invoking
launchctl or the network. Leave its snapshot and schedule untouched; authenticated
uninstall belongs to the creating release at its original bound source/Git identity.
After that uninstall confirms unloaded status, the owner archives its retained inert
recovery directory privately before a new explicit install creates current authority. Do not accept arbitrary manifest
subsets, rewrite authority in place, or delete an unauthenticated ledger.

A published tag, a checked-out repository, an installed skill, and a loaded notifier
snapshot are separate states. Updating or verifying one does not establish the
others. Read back the exact tag/commit, installed bundle parity, and notifier source
binding before claiming the intended installation is current.

Resource limits must apply while bytes cross the trust boundary, not after a helper
has already copied or buffered them. Bound regular-file snapshots by both initial
size and bytes actually read, parse direct inputs through the same ceiling, and stop
child stdout incrementally before it can exhaust memory. CI checkout credentials are
another ambient capability: disable persistence unless a later reviewed step needs
them, even when repository workflow permissions are read-only.

Provider failures require strictly framed, bounded terminal facts. Denial presence
remains permission-required even when the controller deadline also fired; preserve
truthful limit metadata and a valid bound candidate. Cancellation, binding failure,
and output bounds take precedence. No denial, timeout, quota prose, or nonzero exit
grants automatic retry or model changes.

Untrusted feedback prose is agent input, even when it arrives through a familiar
GitHub issue form. A prompt-injection blacklist or a security-keyword classifier is
not a proof that prose is safe. Keep titles, bodies, comments, usernames, labels, and
link text out of agent prompts, logs, workflow summaries, and automated decisions;
derive periodic signals only from a closed metadata projection with byte, record,
time, and pagination bounds. Public submission is a separate exact-byte decision:
route explicit security reports privately, treat keyword matching only as an extra
deny barrier, and require a fresh human acknowledgement bound to the reviewed digest
before sending a non-security draft to the fixed public destination.

## Route context and verification through one authority

Large reference files are opt-in context, not a default startup bundle. Route a task
through one relevant `REPO_MAP` row, open only the matching lesson or public-doc
section, and use a fresh Graphify index only for a narrow relationship or impact gap.
The map owns human intent and verification routing; Graphify owns machine-derived
edges. Generated graph data remains ignored local cache, but Git ignore alone does not
exclude it from provider reads, and an explicit task path does not isolate it. Keep it
absent from the disposable worktree or approve the whole worktree before dispatch.

The same single-authority rule applies to verification. During iteration, run the
owning focused suite. Once bytes are stable, run the canonical `ci-offline.sh` gate
once and bind review to that candidate. PR templates should request the canonical gate
and exact focused evidence instead of copying every suite command; mechanical tests
should derive the inventory from the runner rather than enforce duplicate checklists.

For a remediation regression, use the existing
`AGY_WORKER_REMEDIATION_FOCUSED_CHECK` exact check label before repeating its owning
group. Keep passed groups as evidence when their relevant bytes are unchanged.
For a shell-suite failure investigation, set `KEEP_AGY_WORKER_TEST_TMP=1` so the
failing fixtures survive the exit trap. Capture the exit code and process handle
along with output; a missing observation is not permission to start a duplicate run.

### Privacy-safe per-suite CI timing telemetry and gate boundaries (2026-08-28)

Observation: Optimizing a long-running offline gate across PR iterations requires empirical
per-stage durations, but collecting telemetry must not leak local environments, commands,
logs, credentials, or timestamps, nor can wall-clock timing be conflated with reduced compute
or weakened acceptance.
Change: `scripts/ci_timing.py` provides an explicit `--timing-report <PATH>` mode for
`ci-offline.sh`. It records observational monotonic wall time (`time.monotonic()`) per
canonical stage in a mode-0600 no-overwrite JSON report after requiring a clean
tracked/untracked worktree and binding the exact Git HEAD SHA and canonical inventory
digest. Raw commands, file paths, logs, environment variables,
timestamps, and host identity are strictly excluded. The default fail-fast gate behavior
and full suite inventory remain unchanged, and timing reports are explicitly distinct
from CI sharding or acceptance decisions.

### Exact-PR-head fail-closed CI sharding and receipt verification (2026-08-28)

Observation: Parallelizing a long-running offline CI gate across shard jobs reduces PR turnaround time,
but sharded workflows must not silently drop stages, reuse cross-run artifacts, weaken checkout
immutability, or conflate lower wall time with lower total compute or weaker acceptance.
Change: Four frozen shard IDs and stage memberships (`dispatcher`, `dispatcher-remediation`, `other-a`,
`other-b`) partition the canonical 40-stage inventory. In CI, each shard checks out the exact immutable
head SHA (`github.event.pull_request.head.sha` for pull requests or validated `head_sha` for manual dispatch),
enforces committed diff hygiene, executes its stage subset, and emits a local mode-0600 shard receipt
binding the schema, exact head SHA, inventory digest, shard ID, expected and observed stage lists, and outcome.
The required aggregate `test` job runs with `if: always()` and verifies that all four shard receipts exist,
all producer jobs succeeded, all receipts bind the identical expected head and inventory, no duplicate shard
or stage exists, and every canonical stage appears exactly once. GitHub retains the privacy-safe uploaded
receipt artifacts for one day under repository Actions access. Any failure, cancellation, skip, missing receipt,
or schema mismatch fails closed. Local `./scripts/ci-offline.sh` retains its default all-stage execution, and
lower CI wall time is explicitly documented as not reducing total compute, provider usage, tokens, cost, or
verification rigor.

### Conformance workspace ownership and concurrent isolation (2026-08-30)

Observation: Global filesystem cleanup assertions that match all temporary workspace directories
cause false positive failures during concurrent test execution or when foreign residual directories exist,
creating an accidental coupling between unrelated jobs.
Change: The public conformance suite records and proves the cleanup of only its own owned workspaces.
A concurrent foreign workspace is preserved, ignored, and causes zero test failure, while adversarial
fail-closed cleanup and workspace mutation assertions remain fully enforced without global set diffs.

### Declarative canonical stage manifest, shard monotonic durations, and pure model selection validation (2026-08-30)

Observation: Duplicating the offline CI stage inventory across shell scripts, timing observers, and
sharding verifiers creates inventory drift hazards and maintenance overhead. In addition, exhaustive
combinatorial matrix testing in full subprocess wrappers consumes excessive process execution time.
Change: `scripts/ci_stages.py` defines the single declarative canonical stage manifest (stage ID,
announcement, shard, exact argv, and receipt metadata) from which execution, timing, sharding, inventory digest,
and gate validation are derived without `eval` or unsafe shell reconstruction. Shard receipts include
per-stage monotonic durations (`stage_durations`) under schema v2 with strict fail-closed validation;
same-run publication and aggregation require v2, while standalone validation preserves the frozen v1
shape and its historical stage-ID/announcement digest. The runner routes explicit syntax-check bytecode
to a disposable cache without leaking `PYTHONPYCACHEPREFIX` into ordinary suites whose negative controls
must observe fixture-local bytecode. Pure selection validation retains representative
end-to-end cases for CLI/environment provenance, conflicts, literal forwarding, and
capability failures.

### Narrow provider scope and external 0700 staged worktree (2026-08-30)

Observation: Whole-worktree dispatch gives an external provider read and write visibility over
the entire disposable repository, which can be unnecessarily broad for a bounded task.
Change: An optional closed `--provider-scope` policy binds readable and writable file-or-tree
entries, the selected-content manifest, and approval under one transmission SHA. Each provider
attempt materializes only that scope into a fresh Git-less owner-private mode-0700 stage and runs
agy there. Descriptor-relative no-follow copying rejects aliases, hardlinks, special nodes, Git
administration, and normalization collisions. After the child is reaped, source and stage are
revalidated and only authorized mutations are reconciled transactionally with durable backups,
fsync, an atomic recovery ledger, equality checks, and exact rollback. The stage narrows provider
scope but is not an OS sandbox and grants no execution, Git, acceptance, or publication authority.

### Raw dispatch must preserve the facade's transmission choice (2026-09-01)

Observation: Requiring an explicit transmission mode only in the ordinary facade left the
advanced raw initial dispatch as an implicit whole-worktree bypass.
Change: Both initial launch paths now recommend selected-content scope and require exactly
one explicit mode. The broad exception is bound to the current path/kind manifest and
rechecked immediately before the initial provider process. Later same-job actions preserve
the frozen mode but bind exact controller state and candidate evidence rather than the
original manifest, because legitimate provider output changes the worktree during project
repair cycles. This closes the approval gap without removing whole-worktree capability or
deadlocking continuation. At that release, legacy records and already-queued states
remained readable, but an unapproved broad record could not launch through dispatcher
`run`/`start`. Retired job formats are now subject to the
[current-only format policy](PROJECT_WORKFLOW.md#retired-job-formats-and-flags).

## Transparent provider dispatch notice and truthful boundaries

When Codex delegates to an external worker CLI backed by provider services, transparency
and truthful boundary accounting are essential. Before every provider-launch attempt—whether
initial run/start, same-conversation resume, candidate continuation, or fresh restart—Codex
must inform the user in one or two concise user-facing sentences what task is being sent,
the caller-selected model, caller-selected effort (or that effort is not separately selectable
for fixed/compound/literal models), and the exact resolved model slug.

When no model is selected or the default tier is used, state truthfully that the provider
default model is used and that model or effort is unresolved, without inventing a resolved
slug or thinking level.

This notice must precede every dispatch attempt and remain accurate afterward.
Provider-boundary honesty is paramount:
- Do not infer hidden backend reasoning or invent thinking levels for fixed or literal models.
- State provider-default usage truthfully when model resolution is not explicitly selected.
- If preflight fails before provider launch, explicitly state that the task was not sent to AGY.
- If provider reach is genuinely uncertain, state that it is unverified rather than claiming success.
- Direct model and effort selection remain caller-owned; recommendations are advisory.


### Reuse human authority across bounded repairs

Distinguish driver-generated state/digest approvals from human authority. A changed
candidate hash does not by itself require a new human prompt. Review foreseeable
provider startup needs before freezing a live package, and include bounded same-scope
repairs in its shared budget. Reuse exact-candidate test evidence; run the required
full suite once the candidate is stable. New data, permissions, destinations, or
budget still need authority. A Goal continuation is not a missing user decision.

## Static checks must respect deliberate dynamic bindings

A globals-injected helper needs a source-proven static declaration for each injected
name. Keep those declarations under `TYPE_CHECKING`; never invent live defaults or
remove imports whose values are passed through a context dictionary. Type narrowing
must follow existing validation, and a tool diagnostic alone does not justify a
runtime behavior change. Keep formatting migrations separate from a first lint
baseline, with each excluded rule or exact-line exception explained.
