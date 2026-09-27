# Product roadmap

This document describes dependency-ordered work. The current command surface and
verified limitations remain in [README.md](../README.md). An item explicitly marked
implemented has code, adversarial tests, and documentation in its isolated slice; it
is not a released/public capability until that slice is reviewed and merged.

Capability checks precede provider launches; selection remains caller-owned and
receipts bind driver evidence. The offline starter proof depends only on the maintained gate
and can remain an independent slice. Each slice must stay within applicable approved
scope; reuse existing authority when it covers the work. This roadmap does not itself
authorize code, commit, push, pull-request, merge,
release, live model use, or another external action.

## Unreleased — capability-based AGY integration

The candidate checks required local AGY capabilities before every provider launch,
rechecks the bound executable immediately before starting it, and treats the version
string as diagnostic. It removes version registries, model matrices, capture and
attestation tools, and help-SHA approval. Model and effort pass through as caller
choices. [Capability and response rules](INSTALLATION.md#agy-capability-requirements)
state the limits; passing help checks does not qualify authentication or task quality.
Project update checks remain, while old notifier formats require authenticated
uninstall with their creating release, owner archiving of the confirmed inert recovery
record, and an explicit new install. Existing old
records, snapshots, and schedules are not rewritten or deleted. These changes are
unreleased.

## Unreleased — smaller core surface

This development candidate removes the unused research, measurement, reporting,
benchmark, usage-report, and prompt-specialization tools. Ordinary delegation,
selection, gate, receipt, lifecycle, native isolation, self-verification, updater,
and notifier behavior remain in scope. This is an unreleased change, not a version
bump or publication claim. Skill size describes tracked source files or a fresh copy;
it does not describe a full marketplace download or promise pruning of older installs.

## Unreleased — retired job formats and approval aliases

This development candidate makes a breaking change for in-flight jobs written in
retired dispatch or workflow formats: readers reject them without projection or
migration. Finish or discard those jobs with the release that created them;
Current dispatcher formats are state V15 and command V13, with selection V4.
All earlier formats are retired, including ordinary jobs that used no removed feature. Old job artifacts remain untouched. Current formats are defined
by the runtime constants linked from the
[recovery guide](PROJECT_WORKFLOW.md#retired-job-formats-and-flags).

The candidate removes the facade approval aliases `--approve-preview-sha`,
`--legacy-preview-approval`, and `--approve-state-sha`, plus dispatcher
`--approve-migration-sha`, and the retired `--boost`, `--approve-boost-risk-sha`, and
`--persona` options, with actionable errors. Canonical advanced state approvals,
named tiers, raw dispatch, and independent evidence formats remain supported.
These changes are unreleased; this entry does not change the package version or
claim a publication.

## Unreleased — development quality gate

The local candidate adds pinned development-only Ruff and Mypy checks targeting
Python 3.9. CI requires their separate job alongside the existing offline shards;
the shipped runtime and canonical offline registry remain standard-library-only.
See [contributor setup](../CONTRIBUTING.md#verify-locally). This is not released.

## Unreleased — dual-host package identity

The plugin and marketplace identity becomes `agy-worker` on Codex and Claude Code;
the repository name and URLs remain unchanged. Existing Codex installations need the
[post-publication migration](INSTALLATION.md#codex-plugin-identity-migration).
Claude Code is experimental: pending live verification. The local candidate adds
shared-runtime layouts and instructions, not a released support claim. SkillStore,
catalog updates, and release publication require separate owner approval.

## Unreleased — gate Git and path-policy hardening

The gate now neutralizes fsmonitor and caller Git configuration, and fails closed
on effective clean/process/required filter definitions before reading candidate
content. This includes Git LFS configurations. Gate `--only` and `--allow` now use
segment-aware patterns: `*` and `?` no longer span directories, narrowing prior
matches; `**` matches zero or more whole segments, so patterns such as
`src/**/*.py` newly include `src/x.py` as well as nested files. Review existing
policies for both effects. These changes have not been released.

## v0.22.0 — AGY 1.2.11 compatibility and workflow usability

v0.22.0 recorded an AGY compatibility baseline. Its retained release commit owns the historical version and model evidence; the unreleased capability-based integration no longer carries that registry.

This release also exposes advisory delegation decisions through the ordinary workflow, fixes finalization through the public dispatcher wrapper, rejects repeated model/effort/tier options, and clarifies checkout freshness and ignored-cache diagnostics. Bounded live session editing and same-conversation refinement were verified; native and effective accept-edits semantics remain unqualified for AGY 1.2.11.

## v0.20.0 — AGY 1.2.7 compatibility

v0.20.0 activates AGY 1.2.7 compatibility following candidate-bound live canary
qualification (fixed `gemini-3.8-flash-high`) across session and native normal
execution, session and native same-conversation repair, native permission refusal
(`permission_required` exit 6 with `denied_actions`), and controller hard-deadline
timeout (`hard_deadline_exceeded` exit 16 at 8 seconds, with no provider timeout
warning or live exit-3 sample observed). Candidate driver CI passed all 44 canonical
offline stages exactly once across the four canonical shards, including 114 remediation
cases (manifest aggregate `486d5999a6d4cd6cf60c50bbd8b9b988e9b4dc20326a5dcc2cb486a8ea1c2661`),
with candidate bytes and executable modes unchanged. Runtime and metadata review found
no remaining executable findings, and the mirrored `clientInfo` 0.20.0 correction passed
17 owning usage tests. Final independent acceptance remains a release requirement.
Release publication and installation are verified separately against the exact public
commit; marketplace visibility is a separate external state.

## v0.19.0 — released

Official v0.19.0 publication is bound to commit `412831c`. It activated AGY 1.2.2 after
bounded session and native normal and same-conversation repair qualification. It recognizes
refused actions and observed partial-output timeouts, preserves useful candidates, repairs
native conversation persistence, and shortens the skill's main instructions. Its release commit retains the historical compatibility evidence and limits. The stable implementation passed all 44 offline CI stages and independent
acceptance. Release publication and installation are verified separately against
the exact public commit; marketplace visibility is a separate external state.

## v0.18.0 — released

v0.18.0 established the prior AGY 1.1.27 normal-session compatibility baseline.
Its release commit retains the accepted cases and their qualification limits. Marketplace visibility
is verified separately from the GitHub release.

## v0.17.0 — released

[v0.17.0](https://github.com/cagdasyurekli/codex-agy-worker/releases/tag/v0.17.0)
made normal AGY session access the default, retained optional native isolation,
and improved workspace reconciliation and scoped repair without repeated approval
for mechanical digest refreshes. Its release commit retains the historical AGY
qualification limits.

## Product direction

`codex-agy-worker` should remain a small Codex-to-agy pipeline whose differentiator is
independent evidence, not feature-count parity. Codex owns planning, scope, acceptance
criteria, verification, and human-facing judgment. agy performs bounded worker tasks.
The worker envelope remains a claim.

Nearby projects demonstrate useful demand for asynchronous jobs, lifecycle tools,
diagnostics, multiple backends, MCP servers, and broad automation:

- [codex-agy-delegator](https://github.com/swjturay/codex-agy-delegator)
  exposes asynchronous multi-backend runs, report/apply/cleanup tools, and worktree
  isolation through an MCP server.
- [codex-antigravity-bridge](https://github.com/Common-ka/codex-antigravity-bridge)
  provides asynchronous status/result tools, capability and smoke probes, compact
  result modes, and retained local run artifacts.
- [agy-mcp](https://github.com/Boulea7/agy-mcp) combines typed MCP tools, a doctor,
  long-task supervision, skill bundles, worktrees, and safety policy.
- [antigravity-for-claude-code](https://github.com/VKirill/antigravity-for-claude-code)
  pursues detached jobs, multi-role orchestration, automatic commits, pushes, and
  deployment.

Those primary project sources motivate better diagnostics, lifecycle ergonomics, and
portable evidence here. They do **not** justify adopting their MCP, daemon,
multi-backend, or autonomous-shipping architecture. This project should make its
narrow evidence boundary easier to see and use.

## Evidence terminology

Use these terms consistently in code, tests, documentation, and reports:

- **Worker envelope:** schema-valid worker-authored claims. Shape is validated; truth
  is not implied.
- **Driver input:** immutable base, audited repository, path policy, verification
  commands, and controlled routing evidence selected before or after dispatch by the
  driver.
- **Gate observation:** facts independently derived by `qa-gate.sh` from Git and
  driver-owned verification.
- **Accepted candidate:** gate exit `0` followed by human diff review. It is not a
  commit, merge, release, or proof of general correctness or security.
- **Evidence receipt:** a local, versioned record binding a gate invocation to hashes
  of its inputs and observed outcome. It is not a signature or a new acceptance
  authority.
- **Receipt verdict:** exactly `gate-passed`, `rejected`, or `routed`. A receipt is
  never “accepted.” `gate-passed` records gate exit `0`; only the required later human
  diff review can turn that candidate into an accepted candidate.
- **Human report:** a sanitized rendering of a validated receipt. It cannot improve
  or reinterpret the underlying outcome.
- **Provider-reported usage:** token, duration, or turn telemetry supplied by agy. It
  is not independent billing or quota evidence.

## Immutable cross-slice rules

Every roadmap slice must preserve all of these rules:

1. `agy`, its stream, and every envelope field remain untrusted.
2. Acceptance continues to require an immutable base, complete Git-visible scope,
   driver-owned verification, unchanged candidate state during verification, and
   human diff review.
3. No receipt, report, usage number, or CI rendering may
   become an alternative acceptance path.
4. The caller selects the tier or explicit model/effort input. Recommendations remain
   visible and advisory, with `recommendation_only: true` and `applied: false`.
5. Never add automatic tier/model/effort changes or invent a `--thinking-level`
   control. After G0 reconciles the exact agy contract, G1 may expose agy's real
   model and effort vocabulary as explicit wrapper choices only. The wrapper resolves
   a verified pair to one exact agy model slug; it does not assume agy's two CLI
   selectors compose. Every explicit continuation attempt keeps the caller's resolved
   selection byte-for-byte; no continuation is automatic.
6. Permission, authentication, scope-policy, invalid-contract, untrusted-claim, and
   human-required outcomes are non-escalatable.
7. No feature may automatically commit, push, open a pull request, merge, release,
   submit an issue, enable a service, or publish an artifact.
8. No feature may silently edit `~/.codex`, `~/.gemini`, or another user
   configuration location.
9. The runtime remains Bash 3.2-compatible shell, Python 3 standard library, and git.
   Do not add Node, Bun, an MCP daemon, or a package-manager runtime dependency.
10. Offline suites remain independent of agy, network, provider credentials, and
    paid quota. Every new enforcement check needs both an accept and reject case.
11. The canonical runtime remains under `skills/agy-worker/runtime/`; root runtime
    commands are compatibility wrappers. Repository-only demonstrations and
    conformance fixtures may remain outside the public skill when documented as such.
12. External data transmission, live provider use, destructive cleanup, and GitHub
    or release actions keep separate explicit approval gates.

## Release groups and slices

Each slice below is independently reviewable. A later slice must not be smuggled into
an earlier implementation because it shares a schema or helper.

### v0.16.0 agy 1.1.24 compatibility

**Status:** Local candidate; not published. This candidate activates the independently
reconciled agy `1.1.24` fourteen-model inventory, including Gemini 3.8 Flash low,
medium, and high compound slugs. Provider execution, Git actions, publication, and
marketplace updates remain separate authority gates.

### v0.15.0 product simplification

**Status:** Published. Publication is established by the annotated `v0.15.0` tag at
`0878bd6019d31bf2659e7c95da560c3b9adf6ac9` and GitHub Release readback.

The release retired unused optional registries. It made no marketplace or SkillStore
assessment claim. Its historical job-format handling does not define current support.

### v0.14.1 direct-dispatch transmission parity

**Status:** Published. Publication is established by the annotated `v0.14.1` tag at
`9bdfb520cf34d9ab3a233bb6287114a4f614948c` and GitHub Release readback.

The advanced `agy-worker.sh` initial run/start path now requires the same explicit
transmission choice as the ordinary facade. Provider scope is the recommended bounded
path; whole-worktree dispatch remains available only with an exact current path/kind
manifest approval that is rechecked immediately before the initial provider launch.
This intentionally rejects previously unapproved raw invocations without removing the
whole-worktree capability. Same-job continuation and repair remain bound to exact
controller state and candidate evidence so legitimate provider-created files do not
deadlock the lifecycle. Legacy command records and already-queued states remain readable,
but an unapproved broad record cannot launch through dispatcher `run`/`start`. This
release made no SkillStore assessment claim.

### v0.14.0 explicit provider-transmission choice

**Status:** Published. Publication is established by the protected exact-head `test`,
squash merge commit `02886961c7a0d6357808316b15abedd279a778a9`, the annotated
`v0.14.0` tag, and GitHub Release readback. The separately governed SkillStore
reassessment was submitted from that tag and remains under marketplace review.

This release removes the ordinary facade's implicit provider-read mode. Callers must
approve either the current whole-worktree manifest or an exact provider-scope policy
and selected-content transmission digest. Scoped facade dispatch delegates to the
existing canonical staging boundary without the conflicting whole-worktree `--add-dir`
grant. Stale digests and conflicting modes fail before provider launch.

The old `--approve-preview-sha` spelling remains available through at least v0.16.x
only behind an explicit migration acknowledgement and warning. The release does not
expand Claude or Claude Code support, turn selected-content staging into a sandbox, or
grant provider execution, Git, acceptance, or publication authority.

### v0.13.0 safer verification and lower-friction lifecycle

**Status:** Published. Publication is established by the annotated `v0.13.0` tag at
`48ab30fda2ee78bb30c551723514a590cbde97eb` and GitHub Release readback.

This release adds the ordinary `run`, `status`, and structured-argv
`verify-finalize` lifecycle facade while retaining low-level recovery commands. It
also adds provider-free transmission preview, Gitless allowlisted provider staging,
manifest-derived CI stages and timing receipts, and manifest-driven version compatibility. Conformance
cleanup is restricted to work-owned temporary roots, and the scoped-staging acceptance
matrix directly covers denied or omitted paths, symlinks, special files, races, drift,
unauthorized writes, exact binary bytes, and executable modes.

The release preserves caller-owned provider/model selection, Codex-owned final
acceptance and fail-closed handling of stale or
incompatible evidence. It does not establish provider isolation, general model
superiority, guaranteed time or token savings, or exhaustive correctness.

### v0.12.0 verified delegation and agy 1.1.22 compatibility

**Status:** Published. Publication is established by the rewritten annotated
`v0.12.0` tag and GitHub Release readback; the exact history rewrite changed commit
identities while preserving the release tree.

This release collects the completed post-v0.11.0 goal without adding a new product
slice. It activates the human-reconciled agy 1.1.22 baseline and unchanged 14-slug
inventory; adds account-capture classification,
exact-head CI timing and four-way sharding; discloses every AGY dispatch model and
effort; adds evidence-bound model/delegation guidance plus the V10 sanitized outer-terminal diagnostic/state migration; and adds
repository-scoped marketplace metadata/tutorial, progressive documentation, Pages
source, and verification assets.

The release also includes the bounded follow-up fixes for capture reprofile identity,
controller log-root isolation, resolve-undo diagnostics, close-then-exec conformance
timing, and tracked/untracked whitespace hygiene. These mechanisms improve observable
failure handling and verification; they do not establish a general model winner,
guaranteed token savings, provider quality, or exhaustive correctness. Issue #105 was
outside this immutable release and was resolved later on `main` for v0.13.0.

### v0.11.0 observation-only release scope and dogfood record

**Status:** Published. The reduced observation-only scope was explicitly approved.
The required single no-retry 1.1.22 account observation failed without inventory
evidence; the approval did not activate it, so the active baseline for this immutable
release remained 1.1.16. Publication was later established by protected CI, exact
merged `main` commit `7fe59599ef26773f9ab6537e1ecf31ec8ddc00b9`, the annotated
`v0.11.0` tag, and GitHub Release readback; a source checkout alone was not evidence.

This candidate records agy `1.1.22` as a non-activating compatibility observation,
Codex `0.150.1` as observation-only, pins `actions/checkout` v6.0.2 by immutable
commit, and aligns the Codex plugin manifest to `0.11.0` source metadata.

The release campaign also exercised the public worker surface against this repository:

- A Flash-high `task` produced the checkout-pin candidate and a separate Flash-high
  `explore` produced a read-only repository inventory. Codex reviewed material claims,
  ran the owning checks, and retained no exhaustive-coverage claim.
- A Pro-high `task` produced the Codex compatibility candidate. Codex independently
  corrected, tested, reviewed, and accepted the exact candidate that reached protected
  CI.
- A Pro-high `project` for the agy reconciliation produced physical edits but no valid
  structured envelope. One bounded same-conversation repair repeated the same contract
  failure. The candidate was rejected; there was no automatic retry or model change,
  and the approved Codex fallback rebuilt and verified the slice.
- The 1.1.22 help surface exposes slash-command/skill expansion but no reviewed isolated
  owner-private skill root. The campaign therefore did not modify `~/.gemini` or claim a
  headless `/skill-name` canary.

These observations keep provider terminal state, structured output, physical diff,
Receipt/gate state, and Codex disposition separate. They establish bounded workflow
exercise, not a general model ranking or provider-quality guarantee,
or proof that delegation reduces Codex allowance usage.

### Historical v0.2.0 release scope

Version 0.2.0 released the completed provider-independent roadmap through P2-A:
G0/G1, P0-A through P0-D, P1-A through P1-E, and P2-A. P2-B and P2-C are not release
blockers and are deferred rather than left as active implementation goals. Their
sections retain the exact evidence and policy prerequisites required before either
may be reconsidered. Deferral did not weaken the then-active agy `1.1.10` baseline,
advance the unreconciled `1.1.11` evidence, or claim live provider or cleanup
behavior.

### G0 — Historical compatibility reconciliation

The exact-version reconciliation, capture, attestation, and scheduled compatibility
watch surfaces are retired by the unreleased capability-based integration. Their
historical release commits retain the corresponding evidence. Current local probes
and explicit project updates are documented in [operations](OPERATIONS.md).

### Usability-first project workflow

**Current status:** Implemented, offline-verified, and published in v0.7.0.
The product provides three explicit Codex
workflows: read-only `explore`, implementation `task`, and repo-wide iterative
`project`. Unknown final file lists, broad architecture work, missing initial test
commands are not admission failures.

Project jobs bind a bounded local cycle count and let Codex provide strict,
sanitized, driver-owned verification JSON to `continue` the exact conversation after
an observed check failure. `finalize` records only Codex's `verified`,
`partially_verified`, or `blocked` assurance conclusion; it will not execute the JSON
as a command or allow agy to self-assign quality. A useful unresolved candidate is
preserved for review instead of being silently retried, discarded, or presented as
complete.

### Project maintenance and caller-owned selection

Maintenance and the notifier were published in v0.8.0; bounded lifecycle recovery,
driver-owned verification, and Codex-owned assurance were published in v0.10.0.
The project updater resolves a bounded annotated tag to its commit. A current-format
notifier snapshot with changed source bytes reports `maintenance-required` and waits
for explicit owner `refresh`; malformed or unsafe state remains inert.

Project updates and the optional local notifier remain explicit maintenance tools;
see [operations](OPERATIONS.md). The notifier does not apply updates. Old source
manifest formats require the creating release's authenticated uninstall, owner
archiving of the confirmed inert recovery record, and an explicit current install; there is no legacy manifest reader or in-place migration.

Direct model and effort values remain caller-owned. The capability probe checks the
interface the runtime dispatches, not model availability or account entitlement.
Selection provenance binds the exact choice through repair and receipt validation;
recommendations remain advisory. See [usage](USAGE.md#common-options).

### P0 — make the evidence boundary visible and usable

#### P0-A — Evidence Receipt v1

**Status:** Implemented, offline-verified, and published in v0.2.0.

- **User job:** Preserve what the driver checked, against which immutable base and
  policy, and what the gate concluded without sharing source, prompts, raw logs, or
  worker prose.
- **Intended surface:** Add canonical
  `skills/agy-worker/runtime/verify-job.sh`, root `verify-job.sh`,
  `skills/agy-worker/runtime/schemas/evidence-receipt.schema.json`, and a
  dependency-free receipt validator. The wrapper creates a private temporary receipt
  and pre-opens a driver-owned structured-evidence sink, then invokes the gate with an
  internal capability-bound `--evidence-fd FD` handoff. This evidence mode is owned by
  `verify-job.sh`, not supported as an arbitrary direct-call interface. When that
  option is absent, `qa-gate.sh` output, side effects, and exit behavior remain
  identical to today. With it, the gate writes
  exactly one bounded JSON handoff to the already-open descriptor; it never owns or
  chooses the destination path. Optional `--pre-recommendation FILE` may bind an
  already-rendered pre-dispatch advisory. The receipt command never generates or
  applies a recommendation.
- **Gate evidence handoff:** The structured handoff is the receipt's bounded source
  for driver-derived facts. It includes the hash of the exact envelope snapshot the
  gate validated, the resolved immutable base, the gate's internal initial and final
  candidate-state digests, and its exact outcome and exit. The wrapper validates the
  complete handoff, cross-checks it against its immutable inputs, and refuses missing,
  malformed, duplicate, or mismatched evidence. It never parses gate prose or
  reconstructs candidate truth from outer-wrapper observations alone.
- **Receipt v1 minimum:** Version and kind; gate-resolved immutable base; hash of the
  exact envelope snapshot validated by the gate; ordered path-policy hash; verifier
  labels and command hashes; the gate-supplied initial and final candidate-state
  digests; actual gate exit/outcome; a verdict restricted to `gate-passed`, `rejected`,
  or `routed`; optional caller-selection object with exactly one resolved mode,
  distinct tier/user-model/user-effort values, CLI/environment/default provenance,
  exact caller model/effort choice and executable binding under the current selection
  contract; optional validated pre-dispatch advisory retaining its
  rationale, controlled driver evidence, relative cost impact,
  `recommendation_only: true`, `applied: false`, and `stage: pre-dispatch`;
  `gate_authority: qa-gate`; and an explicit statement that the receipt is unsigned
  and recommendations did not participate in acceptance.
- **Exit and publication contract:** Wrapper preflight/input errors exit `64` before
  the gate and publish no receipt. Gate outcomes `0` and `10`–`15` may publish a
  receipt with the exact `gate_exit`; after successful receipt validation, file
  `fsync`, atomic publication, and parent-directory durability, the wrapper returns
  that gate exit. Gate exit `64` publishes no receipt and returns `64`. A missing or
  mismatched handoff, unknown gate exit, signal, or other internal protocol failure
  publishes no receipt and returns reserved exit `70`. Receipt validation, `fsync`,
  or atomic-publication failure removes the private temporary file, publishes no
  partial receipt, and returns reserved exit `74`. The wrapper never returns `0`
  unless the gate returned `0` **and** the receipt was durably published.
- **Exclude:** Diff/source content, prompt, worker summary/confidence, raw verifier
  commands or output, credentials, absolute repository paths, provider pricing, and
  an applied recommendation.
- **Dependencies:** Existing `qa-gate.sh`, envelope validator, accepted G1 selection
  contract, Python SHA-256, and git.
- **Trust boundary:** A receipt records a gate execution. It must not reproduce gate
  acceptance logic, treat its own existence as acceptance, use `accepted` as a
  verdict, or map any nonzero gate result to `gate-passed`. A receipt path inside the
  audited repository is rejected. Schema validation, canonical serialization, and
  internal-invariant checks can detect malformed or inconsistent receipts, but an
  unsigned receipt cannot detect arbitrary schema-valid tampering by an actor who can
  rewrite the document and recompute its embedded hashes. Validation can detect a
  mismatch when the caller separately supplies the bound envelope, candidate
  artifact, pre-dispatch advisory, or a trusted external digest. Receipt v1 makes no
  self-hash authenticity or signing claim; signing remains deferred to an approved
  threat model and external signer.
- **Minimum accept tests:** An honest edit with passing driver verification yields a
  durably published, schema-valid receipt with verdict `gate-passed`, actual
  `gate_exit: 0`, the gate's exact envelope snapshot hash, resolved base, and internal
  initial/final state digests; the wrapper returns `0`. Each normal gate result
  `10`–`14` durably publishes verdict `rejected`, result `15` publishes `routed`, and
  the wrapper returns that exact gate exit. A valid pre-dispatch advisory is bound
  without changing the selected input, executable binding, or gate
  result. The tests never call a candidate accepted before human review. Direct
  `qa-gate.sh` calls without the internal evidence capability retain their
  current stdout/stderr and exit contract.
- **Minimum reject tests:** Scope failure, malformed envelope, untrusted command/test
  claim, missing edits, verifier failure/mutation, and human-required outcome retain
  their gate classification and are never rendered as acceptance. Reject overwrite,
  symlink target, in-repository output, unknown schema version, inconsistent receipt,
  separately bound artifact/digest mismatch, malformed or duplicate handoff, envelope
  snapshot/base/state/outcome/exit mismatch, post-gate or cross-stage advisory input,
  selected-input or executable-binding mismatch, ambiguous selector provenance, or an
  advisory that claims it was applied. Wrapper/gate
  preflight `64`, unknown exit, signal, missing evidence, internal `70`, and durable
  publication `74` paths publish no receipt; injected validation, `fsync`, rename, and
  parent-directory durability failures leave no final or partial receipt. An unsigned
  receipt rewritten with recomputed hashes must not be falsely described as
  tamper-evident without a separately trusted binding.
- **Docs and AGENTS impact:** Update README, SKILL, privacy disclosure, REPO_MAP, and
  architectural lessons only after implementation. AGENTS then gains the actual new
  suite/count and a concise durable rule that receipts do not replace gate or human
  review. Run `agents-md-auditor` before and after.
- **Size:** M.
- **Done/exit criteria:** One isolated PR; no behavior change when `verify-job.sh` is
  unused and no behavior/output/exit change when `qa-gate.sh` is called without its
  optional evidence handoff; all current suites plus the `0`, `10`–`15`, `64`, `70`,
  and `74` receipt matrix green; no receipt on unknown/signal/missing-evidence or
  publication failure; no raw private data in the receipt; no post-gate recommendation
  binding in P0-A; and an independent verifier confirms no weaker gate path.

The existing post-gate recommender remains external and unchanged. P0-A does not
auto-run it or bind its output after a synchronous gate completes. A later, separate
contract may bind a post-gate advisory without rewriting the canonical one-pass
receipt or creating chronology ambiguity.

#### P0-B — Human Report renderer

**Status:** Implemented, offline-verified, and published in v0.2.0. Receipt-only selection and recommendation-record
validation is side-effect-free; canonical recommendation generation remains only an
explicit pre-gate publication-input check.

- **User job:** Read or share a compact bounded result without pasting private job
  artifacts.
- **Intended surface:** Add canonical `evidence-report.sh --receipt FILE
  --format text|markdown` plus a root wrapper. Output defaults to stdout; writing a
  file requires an explicit path and refuses overwrite.
- **Dependencies:** Validated Receipt v1 schema and validator; no dispatch dependency.
- **Trust boundary:** Rendering only. It cannot invoke agy, git, gate, routing, or a
  network client. Rejected and routed receipts must be headed plainly as such. It may
  state only the receipt's bounded observations.
- **Minimum accept tests:** Receipts whose verdicts are `gate-passed`, `rejected`, and
  `routed` render stable, escaped text and Markdown with exact exit/outcome and
  verification labels.
- **Minimum reject tests:** Malformed, internally inconsistent, unsupported-version,
  control-character, Markdown-link-injection, forbidden-private-field, or separately
  bound artifact/trusted-digest mismatch produces no report. Do not claim detection
  of arbitrary unsigned receipt rewriting with recomputed hashes.
- **Docs and AGENTS impact:** Add report examples to README/SKILL and ownership to
  REPO_MAP; update privacy language. Change AGENTS only for an actual suite/count.
- **Size:** S.
- **Done/exit criteria:** Deterministic output; no raw command, source, prompt, log, or
  absolute-path disclosure; renderer has no execution or submission capability.

#### P0-C — Read-only Doctor

**Status:** Implemented and offline-verified; live authentication/provider readiness
remains intentionally outside the Doctor contract.

- **User job:** Diagnose readiness before spending provider quota or changing personal
  configuration.
- **Intended surface:** Add canonical `doctor.sh [--repo DIR]
  [--format text|json]` plus root wrapper. Default execution is offline and read-only.
- **Checks:** Runtime resolution; Bash compatibility; Python 3 and git availability;
  Git worktree support; agy presence and required capabilities; target repository
  validity; and safe executable binding. Version text is diagnostic only.
- **Dependencies:** Existing resolver, shared capability probe, and `ground-truth.sh`
  facts. It is independent of Receipt v1.
- **Trust boundary:** A green result means only that offline prerequisites passed. It
  does not certify authentication, provider availability, sandbox permission, task
  quality, or future dispatch success. It never repairs configuration. Optional
  config inspection requires an explicit path; it does not scan home files silently.
- **Minimum accept tests:** A fake compatible toolchain yields structured green output
  and a before/after filesystem snapshot is unchanged.
- **Minimum reject tests:** Missing agy/Python/git, missing required capabilities, incomplete bundle,
  invalid target repo, and unsafe executable binding fail closed; no `agy auth` or unknown-subcommand probing; no network or
  configuration writes.
- **Docs and AGENTS impact:** Add onboarding/troubleshooting to README and SKILL,
  ownership to REPO_MAP, and a durable no-auto-fix lesson. AGENTS receives only the
  implemented suite/count and current doctor boundary.
- **Size:** M.
- **Done/exit criteria:** Stable text/JSON contract, no live prompt, no personal-config
  mutation, and offline fake-tool coverage for every reported state.

#### P0-D — 60-second offline proof demo

**Status:** Implemented as the bounded starter subset retained by conformance v1.

- **User job:** See the project's differentiator in under one minute without agy,
  credentials, network, or API credits.
- **Intended surface:** Add repository-only `proof-demo.sh` and a minimal fixture
  pair, now retained as the `conformance/v1/` starter subset. It creates a temporary
  Git repository, demonstrates one
  honest candidate that is `gate-passed` by driver verification and one plausible
  worker claim rejected because Git reality disagrees, prints a short explanation,
  and cleans only its own temporary directory. The demo performs no human review and
  therefore labels no candidate accepted.
- **Dependencies:** Current `qa-gate.sh`; use Receipt v1 when available without making
  the demo block P0-A.
- **Trust boundary:** This is a demonstration, not certification, a benchmark, or
  evidence of real agy quality. It must not edit the checkout or use the current
  repository as the fixture.
- **Minimum accept tests:** Runs offline on macOS Bash 3.2 in less than 60 seconds and
  shows the expected accept/reject exits.
- **Minimum reject tests:** A deliberately trusting substitute gate cannot make the
  demo pass; temporary-path collision and interrupted cleanup fail safely; no agy or
  network executable is invoked.
- **Docs and AGENTS impact:** README quick proof and Pages link; REPO_MAP ownership.
  AGENTS changes only if this becomes a named completion check.
- **Size:** S.
- **Done/exit criteria:** Two bounded cases, deterministic summary, verified offline,
  and explicit “starter proof, not conformance certification” wording.

### P1 — integrate the evidence boundary without broadening autonomy

#### P1-A — Safe local lifecycle (implemented)

- **User job:** Create, inspect, verify, and deliberately clean an isolated job without
  manually reproducing the full worktree recipe.
- **Intended surface:** `job.sh init|status|verify|preserve-instructions|cleanup` with
  a private mode-`0600` state file binding exact target, worktree, branch, immutable
  base, and job ID. `verify` delegates to Receipt v1. `preserve-instructions` prints
  deliberate commands; it does not run them.
- **Dependencies:** Receipt v1; Doctor is recommended but not required.
- **Trust boundary:** No persistent daemon, shared polling service, commit, push, PR,
  merge, release, auto-dispatch, or auto-model choice. One explicitly started,
  owner-private per-job controller may supervise its own agy process group; its
  status/cancel facts are local and do not assert remote provider state or cancellation.
  Destructive cleanup is allowed only
  after explicit user approval for the exact job ID and exact hash-bound candidate
  state recorded with receipt verdict `rejected`. Immediately before deletion it
  re-derives that digest and refuses any mismatch. It refuses `gate-passed` or
  accepted candidates, routed outcomes, tampered/stale state, foreign or unbound
  artifacts, and every uncommitted state that does not exactly match the recorded
  rejected digest.
- **Minimum accept tests:** Init creates the exact branch-backed worktree; status
  detects current state; verify produces the expected receipt; after explicit user
  approval, cleanup removes only the exact uncommitted rejected candidate whose
  current digest matches the hash-bound rejected receipt.
- **Minimum reject tests:** Mutable base, path/branch collision, foreign or moved
  worktree, tampered/stale state, changed-since-verification digest, outside-repo root,
  symlink escape, missing explicit approval, `gate-passed`/accepted/routed outcome,
  foreign or unbound artifact, uncommitted state not exactly matching the recorded
  rejected digest, and any GitHub or commit command.
- **Docs and AGENTS impact:** Replace the README's manual path with a primary lifecycle
  example while retaining the manual reference; update SKILL, REPO_MAP, lessons, and
  current completion checks after implementation.
- **Size:** L.

#### P1-A.1 — Progress-aware local dispatch lifecycle (implemented)

- **Intended surface:** The canonical dispatcher keeps synchronous `run` and adds
  explicit `start|status|wait|result|extend|cancel|resume|restart` around one private
  local controller. Valid `init`, `step_update`, and terminal `result` events renew a
  `10m` idle lease only; the initial hard deadline is `2h`, the caller-owned absolute
  maximum is `12h`, and agy receives that maximum as `--print-timeout`.
- **Trust boundary:** NDJSON progress content, prompts, raw stderr, and conversation
  IDs remain private. Public state is sanitized elapsed/progress-age/count, attempt
  origin, terminal reason, and resume availability. No automatic retry is allowed:
  resume uses the exact frozen conversation/selection, while restart visibly begins a
  new conversation. Local cancellation ends/reaps the process group but records
  `remote_cancel_unverified`; it is not provider cancellation evidence. The narrow
  controller is not a daemon or MCP service.
- **Mode boundary:** Plan stages the complete prompt privately and leaves slash
  expansion available only for its fixed driver prompt so the documented upstream plan
  transform can apply. Accept-edits keeps slash expansion disabled by default. Plan is
  not filesystem isolation; the disposable worktree and no-change gate remain the
  enforcement path.
- **Pre-gate residual:** `job.sh abort` is separately hash-approved and accepts only a
  lifecycle-created exact terminal dispatch residual with a closed controller group and
  empty or explicitly discarded candidate. Receipt-bound cleanup remains rejected-only.
- **Exit criteria:** Offline subprocess tests cover fresh heartbeat, idle/hard/max
  expiry, malformed event non-heartbeat, group reaping, evidence-gated terminal
  taxonomy with unknown failures left unclassified,
  explicit resume/restart distinction, stale control approvals, plan argv/prompt
  staging, and bounded pre-gate abort. A separate authorized synthetic live exercise
  is still required before any live-coverage claim.
- **Done/exit criteria:** Crash-safe state transitions; cleanup only for an explicitly
  approved, exact hash-bound rejected disposable state; no loss of gate-passed or
  accepted work; no external action; and independent destructive-target review.
- **Implemented boundary:** The canonical portable runtime owns the v1 state machine,
  shared candidate-state digest, Receipt validation, progress reconciliation, and
  compare-and-delete cleanup. The root command is only a compatibility wrapper.
  One hundred offline cases cover accepted and rejected lifecycle paths, canonical
  branch authority, hook/filter-free fixed Git execution, durability, stale approval,
  ref-error separation, deletion-domain, signal, and weakened-authority mutations.
  Cleanup never follows symlinks, never deletes a commit, and retains the cleaned
  state file.

#### P1-B — Full public conformance kit (implemented)

- **User job:** Let integrations and forks test the published contract rather than
  claim compatibility from prose.
- **Intended surface:** `conformance/run.sh --gate PATH`, versioned
  `conformance/v1/manifest.json`, synthetic repositories/envelopes, and
  `docs/CONFORMANCE.md`. P0-D fixtures become the small starter subset.
- **Dependencies:** Stable gate behavior and Receipt v1 if receipts are part of the
  conformance claim.
- **Trust boundary:** Conformance means only that the implementation passes the
  published fixtures. It is not a security certification or real-job quality proof.
- **Minimum accept tests:** Current gate passes every required v1 fixture with exact
  documented exits.
- **Minimum reject tests:** Deliberately permissive gates that trust worker claims,
  ignore ignored files, accept mutable bases, skip verification, accept verifier
  mutation, or accept human-required outcomes must fail the kit.
- **Docs and AGENTS impact:** Add conformance specification and bounded README badge
  wording; update REPO_MAP and lessons. AGENTS receives actual suite/count only.
- **Size:** L.
- **Done/exit criteria:** Public versioned fixture contract, malicious reference
  implementations rejected, and no “certified secure” language.
- **Implemented boundary:** The repository-only v1 kit binds eleven exact synthetic
  gate cases, manifest/source hashes, fixed verifier kinds, private disposable Git
  repositories, and per-process time/output limits. Eighty-one offline adversarial
  cases reject source drift and permissive gates while proving HUP/INT/TERM cleanup,
  FD-relative no-follow deletion, cleanup bounds, and fail-closed residual handling
  under an explicit gate/loaded-code/local-owner/same-UID/OS-admin TCB. The runner
  never scans for or chases a drifted root and claims no same-user tamper resistance.
  The claim is direct gate fixture compatibility only; it excludes Receipt/report,
  lifecycle, dispatch, provider, real-job quality, security, and human acceptance.

#### P1-E — CI-safe JSON, Markdown, and GitHub Step Summary reporter

**Status:** Implemented as an offline-only extension of the pure P0-B renderer; no
GitHub API, comment, upload, or implicit environment-file write was added.

- **User job:** Render an already produced receipt in CI without custom parsing or a
  networked bot.
- **Intended surface:** Extend the report command with `--format json|markdown|github-step-summary`.
  Output goes to stdout or an explicit file. Documentation shows explicit redirection
  to `$GITHUB_STEP_SUMMARY`; the tool does not discover or write that environment file
  implicitly.
- **Dependencies:** Receipt v1 and Human Report renderer.
- **Trust boundary:** Reporter never dispatches agy, runs the gate, comments on a PR,
  calls GitHub APIs, or publishes artifacts. It escapes workflow-command and Markdown
  injection. JSON is the validated bounded report representation, not the raw
  envelope.
- **Minimum accept tests:** Receipts whose verdicts are `gate-passed`, `rejected`, and
  `routed` render exact status in all three formats and preserve stable
  machine-readable fields.
- **Minimum reject tests:** Workflow-command injection, Markdown links/HTML/control
  characters, malformed receipt, forbidden private fields, implicit environment-file
  writes, and external command/network invocation.
- **Docs and AGENTS impact:** Add a GitHub Actions snippet and fork/secret warning;
  update REPO_MAP. No GitHub integration claim beyond local rendering.
- **Size:** M.
- **Done/exit criteria:** Offline deterministic reporters, no network permissions, and
  exact rejected-state visibility.
- **Implemented evidence:** Eighty offline cases bind canonical bounded JSON,
  Markdown and Step Summary bytes, all three receipt verdicts, explicit private
  no-overwrite publication, workflow-command/Markdown rejection, environment-file
  non-discovery, signals, and weakening mutations.

Do not commit to SARIF: a gate run is not naturally a static-analysis result with
locations/rules. Do not add JUnit unless a concrete consumer first demonstrates a
semantically honest mapping; “job rejected” is not automatically a test-case failure.

### P2 — optional local ergonomics and telemetry

#### P2-B — Provider-reported usage and latency

**Status:** Deferred; no implementation path exists within the current evidence
boundary. The repository's
historical agy `1.1.9` observation and synthetic test streams do not establish the
current contract for usage, duration, or turn fields. Unblocking requires a separately
approved, executable/version-bound one-attempt public synthetic run; owner-private raw
NDJSON; and a sanitized reviewed record binding event order and cardinality, exact
field names and types, null/missing behavior, nested usage keys, duplicate/failure
semantics, and invocation/source/version hashes. Official docs/source must be
reconciled, and any undocumented behavior remains explicitly version-pinned empirical
evidence. Until then no usage parser or schema may be treated as current.

- **User job:** Inspect one run's reported token, turn, and duration telemetry to make
  a manual batching decision.
- **Intended surface:** `usage-report.sh --stream FILE` for one explicitly selected
  NDJSON stream, optionally folded into a receipt/report as
  `provider_reported_usage`.
- **Dependencies:** Stable receipt/report schema and confirmed agy terminal-event
  shape.
- **Trust boundary:** No automatic log-directory scan. Provider telemetry is not bill,
  price, remaining quota, or independent evidence; it never changes acceptance,
  routing, selected tier, or retry count.
- **Minimum accept tests:** One valid terminal result yields labeled token/turn/duration
  fields and preserves missing values honestly.
- **Minimum reject tests:** Multiple ambiguous result events, malformed stream,
  inferred currency, inferred quota, auth/permission failure treated as cost evidence,
  implicit log scanning, and routing changes.
- **Docs and AGENTS impact:** README limitations, privacy disclosure, REPO_MAP, and
  model-routing lesson. AGENTS need not grow unless a new suite is added.
- **Size:** S–M.
- **Done/exit criteria:** No exact monetary/quota claims without a future official
  stable source and a separately approved contract.

#### P2-C — Optional local list/show/prune

**Status:** Deferred; no implementation path exists until recurring accumulation is
demonstrated and a managed-root contract is reviewed. The stable per-job lifecycle
does not yet define a canonical inventory root
or prove that manual cleanup is recurring friction. Unblocking requires opt-in,
sanitized evidence from explicit owner-private lifecycle roots showing repeated
retention or cleanup burden without paths or raw state, followed by an explicit
contract for the managed-root inventory, list/show scope, exact prune deletion domain,
and approval binding. Existing current-state, rejected-Receipt, and candidate-digest
checks remain mandatory; age alone never authorizes deletion.

- **User job:** Find and deliberately remove old locally managed job records after the
  lifecycle format is stable.
- **Intended surface:** `job.sh list|show|prune`, limited to a single explicit managed
  state root. `list`/`show` are read-only; `prune` requires exact job IDs and shows
  targets before deletion.
- **Dependencies:** Safe lifecycle plus a demonstrated accumulation problem. Do not
  implement speculatively.
- **Trust boundary:** Never scan arbitrary home/repository trees, infer ownership from
  names alone, remove `gate-passed`/accepted/routed or changed-since-verification
  worktrees, remove any uncommitted state not exactly matching its hash-bound rejected
  receipt, or run on a timer. Every prune remains an explicitly approved destructive
  action for exact job IDs.
- **Minimum accept tests:** Bound stale rejected records are listed and an explicitly
  approved prune removes only records whose current state still matches the recorded
  rejected digest.
- **Minimum reject tests:** Broad root, symlink escape, unknown/active/
  `gate-passed`/accepted/routed job, changed or unbound state, ambiguous ID, missing
  approval, implicit age-only deletion, and background scheduling.
- **Docs and AGENTS impact:** Lifecycle docs and destructive-action lesson only when a
  real need and implementation exist.
- **Size:** M.
- **Done/exit criteria:** Implement only after lifecycle usage supplies evidence that
  manual cleanup is a recurring problem.

#### P2-E — Exact-head CI timing telemetry and fail-closed sharding

**Status:** Implemented in delivery slices: timing telemetry (GitHub issue #73A) and exact-PR-head fail-closed CI sharding across four frozen shards (GitHub issue #73B).

- **User job:** Observe monotonic per-stage gate timings and parallelize offline CI across four
  frozen shards (`dispatcher`, `dispatcher-remediation`, `other-a`, `other-b`) on the exact PR head
  commit without publishing telemetry, dropping stages, or claiming compute savings.
- **Intended surface:** `scripts/ci-offline.sh --timing-report <PATH>`, `scripts/ci-offline.sh --shard <SHARD> --receipt <PATH>`,
  and `scripts/ci_sharding.py verify-aggregate`.
- **Primary source:** Observational monotonic wall time (`time.monotonic()`) during local
  or CI gate execution; fail-closed receipt aggregation in GitHub Actions.
- **Report boundary:** Binds exact Git HEAD commit SHA and deterministic canonical
  inventory digest after requiring a clean tracked/untracked worktree; publishes mode
  0600 without overwrite in an owner-private directory.
  Excludes paths, commands, environment values, logs, credentials, provider/account data,
  timestamps, host identity, and cost claims.
- **Acceptance:** Negative tests verify fail-closed behavior on existing files, non-0700
  parent directories, dirty worktrees, malformed HEAD/inventory digests, missing or
  reordered/dropped stages, duplicate shard/stage evidence, and unexpected fields.
  Aggregate `test` check with `if: always()` succeeds only when all four unique shard receipts
  exist, all producers succeeded, all match expected head/inventory, and all 49 canonical stages
  appear exactly once. Local gate default fail-fast execution remains unchanged, and lower CI wall
  time does not reduce total compute, provider usage, token usage, cost, or verification rigor.

### Deferred or rejected

- **Cryptographic signing — deferred.** Receipt v1 may expose deterministic SHA-256
  digests, which prove byte equality only. Signing needs a threat model, identity and
  key-discovery policy, revocation, CI key custody, and explicit approval of an
  external signer/tool. Never invent a home-grown signature or call a self-signed
  digest trusted provenance.
- **Persistent async jobs, background daemon, MCP server — rejected.** They add
  retention, authentication, and cleanup boundaries while duplicating the main
  competitor niche. The implemented exception is one explicitly started, local,
  per-job controller with owner-private state and no provider status API claim.
- **Dashboard or cloud service — rejected.** It would create storage, hosting,
  authentication, privacy, and telemetry obligations unrelated to the local gate.
- **Windows parity race — deferred.** Do not claim parity until maintainers can run
  native adversarial suites and own the support burden. Portable code remains welcome,
  but macOS correctness takes priority.
- **Multiple worker backends — rejected for this product direction.** It would dilute
  agy-specific ground truth and compatibility review.
- **Automatic tier/model/effort selection, inferred thinking controls, or quota
  routing — rejected.** Recommendations remain advisory and caller selection remains
  explicit. G1 may expose agy's verified `--model` and `--effort` only as direct,
  non-inferred caller controls; no `--thinking-level` is planned.
- **Automatic commit, push, PR, merge, release, issue submission, or deployment —
  rejected.** These remain deliberate user-owned workflows with separate approvals.
- **Escalating permission, authentication, scope-policy, invalid-contract,
  untrusted-claim, or human-required outcomes — rejected.** More model spend cannot
  repair those boundaries.

### Delegation-First Coordinator Policy

**Status:** Implemented (GitHub issue #81).
**Goal:** Provide a deterministic, side-effect-free evaluator for explicit opt-in delegation-first coordinator policy.
**Deliverable:** `delegation-policy.sh` with `eval` subcommand, schema `delegation-policy.schema.json`, and SKILL.md coordinator guidance. Assigns AGY as first substantive repository actor after discovery/worktree/verification setup. Missing transmission/scope approvals, hard stops, preflight failures, or budget exhaustion fail closed without silent fallback to direct Codex execution. Fixed overhead notices and token observation disclaimers are strictly enforced.

### Sanitized Outer Terminal Disposition (State Schema V10 Migration)

**Status:** Implemented (GitHub issue #82).
**Goal:** State schema migration to V10 with sanitized outer terminal disposition tracking.
**Deliverable:** `CURRENT_STATE_SCHEMA = 10` with enum `provider_terminal_status: "unknown" | "success" | "error" | "cancelled"`. Reportless terminal framing sets the sanitized enum without recognizing phantom candidate files or corrupting candidate state. V3..V9 eligible lifecycle transitions initialize `provider_terminal_status: "unknown"`; V1 remains read-only evidence.

## Approval gates

Roadmap priority is not authorization. Apply these gates independently:

1. **Feature implementation:** use the user's approved scope across its planned
   slices and repairs; ask again only when authority or scope materially changes.
2. **Compatibility watch enablement:** merging or scheduling the daily external
   watcher and changing a verified baseline each require explicit approval. A baseline
   change also requires the G0 reconciliation record; the watcher cannot approve it.
3. **External data/live model:** name the repository and paths sent through agy and
   obtain explicit approval before a live dispatch.
4. **Destructive local lifecycle:** allow cleanup only for the exact hash-bound state
   recorded as rejected and disposable, then re-derive its digest and obtain explicit
   user approval for those exact job/worktree/branch targets. Refuse every other
   state; cleanup is never authorized merely because a job is old or uncommitted.
5. **GitHub:** staging and local commits may occur only when requested; push, PR,
   merge, and release each follow the user's explicit authorization boundary.
6. **External distribution/search:** marketplace, directory, Search Console, or other
   service enablement remains out of scope unless newly approved. The current product
   direction is public GitHub distribution.
7. **Signing:** requires an approved threat model and signer dependency before code.

## Honest success measures

Establish a dated baseline before the first P0 release, then review at 30, 60, and 90
days. Do not add install beacons, hidden analytics, fake installs, fake stars, paid
reviews, or automated promotional submissions.

### 30 days — onboarding and proof

- Require every scheduled G0 result to distinguish unchanged, review-due, and
  evidence-unavailable; target zero false green on missing official evidence.
- Measure median fresh-clone-to-offline-proof time in small opt-in sessions; target
  under 10 minutes and keep P0-D itself under 60 seconds.
- Record whether Doctor identifies the real blocker before any paid dispatch; report
  misses as product defects, not user error.
- Require 100% of published P0 examples to identify exact suite, fixture, base, and
  bounded claim. No example may imply general correctness/security.
- Track GitHub unique visitors and unique cloners around the release as interest only;
  never call a clone an install or activation.

### 60 days — qualified external use

- Measure compatibility-review lead time from first daily drift signal to a recorded
  human disposition; do not count an automatic metadata change as resolution.
- Count distinct public external repositories or opt-in users that demonstrate a
  valid receipt or starter proof. Verify each signal manually instead of inferring it
  from stars.
- Measure the share of inbound bug reports that include sanitized Doctor output or a
  receipt identifier and sufficient reproduction data.
- Review GitHub Traffic referral domains and, if separately approved and configured,
  Search Console non-branded impressions/clicks for relevant delegation and evidence
  queries. Report trends, not guaranteed ranking.
- Keep zero regressions in the existing adversarial gate suite and zero external
  actions performed by a reporter or lifecycle command.

### 90 days — reusable evidence ecosystem

- Audit every compatibility baseline advance for fixed primary sources, ground-truth
  evidence, full offline gates, and any separately approved behavior-changing live
  fixture; target zero unreviewed advances and zero watcher mutations.
- Count verified external workflows that link to or run the conformance kit or local
  reporter. A public repository reference is stronger than a raw star.
- Require the full conformance kit to reject every deliberately trusting reference
  gate and accept the maintained implementation.
- Reassess P2 from observed friction. Do not build profiles, pruning, quota, or
  signing merely because they appear on this roadmap.

## Sequencing reminder

Keep compatibility reconciliation separate from model/effort selection and receipt
work. The offline starter proof may evolve independently because it relies only on
the maintained gate. Do not mix otherwise independent slices merely because they
touch shared documentation, and require fresh approval and independent verification
for each implementation.
