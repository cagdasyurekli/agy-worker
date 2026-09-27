# Repository map

This is the human-maintained routing and intent map. Update it when entry points,
trust boundaries, ownership, or test-suite responsibility changes. Keep implementation
detail in source and durable rationale in `docs/lessons_learned.md`.

Use one relevant row to choose the canonical source and owning check; do not preload
this whole file. A fresh local Graphify index complements the map only for cross-file
relationships, paths, and impact analysis. Query it narrowly, then verify material
edges against the mapped source and tests. Generated `graphify-out/` data is ignored
local cache, not repository authority, and must not be copied into this map. The
ignore rule removes Git noise only; it does not exclude the cache from provider reads.
Keep the cache absent from the disposable worktree used for dispatch.

| Need | Start here | Add Graphify only when |
|---|---|---|
| Change one component | Its ownership row and owning suite below | Impact crosses unclear call/import boundaries |
| Understand lifecycle or trust | The relevant flow and trust-boundary bullets | A path between three or more components is unclear |
| Update public claims | The mapped source, then the exact README/docs section | Never; source and rendered copy are authoritative |
| Find historical rationale | One matching lesson heading via `rg` | Never; Graphify is structural, not decision history |

## Core delegation flow

```text
driver task
  -> model-recommendation.sh --stage pre-dispatch (visible advisory only)
  -> agy-worker.sh selector preflight
       -> caller-owned tier/model/effort selection
       -> bounded safe-target version/help probes for the shared required capabilities;
          version text is diagnostic, without registry or help-SHA approval
       -> private selection.json freezes the exact caller choice and executable binding
  -> agy-worker.sh / agy_dispatch.py (private staged prompt,
       process-owning per-job controller, idle/hard/max clocks)
       -> every provider attempt: final capability and executable-binding recheck
          immediately before launch, including default/tier and native/session paths
       -> preflight failure: preserve evidence, name the missing capability, and stop;
          no provider launch or silent selector fallback
  -> agy (untrusted worker; NDJSON is consumed incrementally)
  -> provider result (`SUCCESS`, `ERROR`, or `CANCELED`; a valid candidate may survive)
  -> provider schema (report-only `commands_run`/`tests_run` may be omitted)
  -> canonical envelope (both arrays restored and required; summary <= 8192)
  -> skills/agy-worker/runtime/scripts/validate-envelope.py (shape and contract only)
  -> one caller-chosen verification path:
       -> verify-job.sh (receipt-producing wrapper)
            -> sanitized, capability-bound launch with a pre-opened evidence FD
               owned only by the gate parent
            -> qa-gate.sh (Git scope, immutable base, policy, escalation)
                 -> isolated gate helpers
                 -> driver-owned argv/shell verifier children started only after the evidence
                    FD is closed in the existing gate process
            -> validated unsigned receipt, atomic no-overwrite local publication
            -> optional evidence-report.sh pure rendering of validated bounded fields
       -> or direct qa-gate.sh (same gate and verifiers, no receipt)
  -> model-recommendation.sh --stage post-gate (visible advisory only)
  -> human diff review and deliberate integration
```

The task, path policy, immutable base commit, verification commands, caller selector,
selection provenance, and routing evidence belong to the driver. A routing recommendation is display-only:
it does not alter the selected tier or participate in gate acceptance. The worker may
edit only the isolated worktree and may report claims, but its
commands never execute. Schema validation proves shape, not truth. The gate derives
Git-visible state independently, rejects undeclared, phantom, wrong-kind, outside-
policy, and verifier-created changes, and routes non-completed outcomes without
accepting them.

The optional local lifecycle wraps that same authority without adding autonomy:

```text
job.sh init (explicit repo/worktree/branch/full base/job ID -> private state v1)
  -> separately approved agy-worker.sh dispatch in the bound worktree
       -> `run` foreground or one explicit owner-private `start` controller
       -> local current-schema `status|wait|result|extend|cancel|resume|restart` state only
  -> job.sh verify -> exact verify-job.sh / qa-gate.sh receipt path
  -> job.sh status (read-only facts and current approval hashes)
  -> gate-passed: preserve-instructions only, never execution
  -> receiptless terminal dispatch failure: exact dispatch binding + `job.sh abort`
       with fresh state/candidate approvals; empty or explicitly discarded candidate
  -> rejected exit 10-14 only: fresh triple-approved cleanup
       -> durable cleanup-in-progress
       -> exact registered worktree removal
       -> exact unchanged branch ref compare-and-delete
       -> private cleaned tombstone
```

The lifecycle cannot dispatch, accept, commit, publish, or clean routed/passed work.
Reconciliation never spends an approval for stale state bytes on a later destructive
step. Its deletion scan does not follow symlinks and rejects nested repositories,
initialized submodules, special nodes, device/mount changes, and unbound digest drift.
The current state schema is defined by `CURRENT_STATE_SCHEMA` in
`skills/agy-worker/runtime/scripts/agy_dispatch.py`; that module also owns command
validation and schema emission.
The dispatch controller is intentionally not a daemon: one explicitly started job
owns one local process group and private state. Its status and cancellation do not
assert remote/provider job state or remote cancellation; a local cancellation retains
`remote_cancel_unverified`. A candidate-free failure may be SHA-approved for exact
conversation `resume` or visibly fresh `restart`. A valid `ERROR` candidate (exit 25)
goes to `result`, driver Verification v2, then `continue`/`finalize`; it is never
resumed. A valid `CANCELED` candidate (exit 22) is preserved for `result` and
finalization or explicit fresh restart; it is never resumed or continued. No branch is
automatic. Only `init`, `step_update`, and terminal `result` update `last_activity` to
`provider_initialized`, `progress_signal`, or `terminal_received`; that activity is
nonsemantic and renews only the idle lease. The current state uses `dispatching` for an active
initial, resume, or restart attempt; `attempt-failed` for a pre-candidate failure;
`awaiting-verification` for a recognized candidate; `repairing` for an active
continuation; and `repair-failed` for an actual failed continuation attempt. Controller
terminal phases are `completed` or `blocked`; exact Codex driver decisions/dispositions
are `verified`, `partially_verified`, `rejected`, or `blocked`. Its additive candidate recognition/source/availability, driver
disposition, failure stage, `last_activity`, mechanically derived `available_actions`,
deprecated mechanical `next_action`/safe-current-SHA aliases,
and worktree-reconciliation fields are controller facts. `has_prior_candidate` is
deprecated and does not assert cleanliness. Reconciliation captures the pre-provider
baseline, the post-group-reap terminal candidate, and an exact recomputation before
queued `Popen`, `continue`, or `finalize`. Under controller-managed provider quiescence
it performs a bounded no-follow double-manifest comparison and binds the Git, index,
root, and selected-Git target facts; drift or unavailable evidence fails closed. This
is neither a filesystem snapshot/FSEvents monitor nor hostile same-user tamper
resistance; it proves no clean
worktree, review, or acceptance and makes no semantic recommendation. The local owner,
same-UID processes, and OS administrators remain the TCB; mutation after an entry's
final read is the portable residual. Dispatch readers and writers accept only
`CURRENT_STATE_SCHEMA` and `CURRENT_COMMAND_SCHEMA`; retired records fail before
projection or mutation, with creating-release recovery guidance. The worktree helper
owns only the current semantic snapshot algorithm. Its separate no-follow root/Git
boundary identity excludes mutable worktree/index/HEAD/ref/object content.
`status`, `wait`, `result`, `resume`, `restart`,
`continue`, and `finalize` default to public JSON and accept three sanitized
driver-owned text lines. Every emitted action or stale-approval rerun command uses the
caller-resolved symbolic launcher `"$PIPELINE/agy-worker.sh"`. `result` returns only a
bound canonical candidate and remains separate from provider or driver acceptance.
Every explicit
`explore`/`task`/`project` workflow consumes candidate-SHA-bound Verification v2 for
`continue`/`finalize`, never a worker command. For `verified`, explore needs complete
coverage, zero unresolved gaps, zero failed checks, and zero missing checks;
task/project need at least one pass, zero failed/missing checks, and completed diff review. Plan mode stages the full prompt
privately and relies on upstream plan transformation plus the disposable
worktree/no-change gate, not mode as a filesystem isolation guarantee.

The repository-only starter proof has a deliberately smaller flow:

```text
canonical synthetic fixtures
  -> proof-demo.sh
  -> two independent private temporary Git repositories
  -> fixed repository qa-gate.sh
  -> exact honest exit 0 and mismatch exit 10
  -> cleanup, then bounded three-line summary
```

It demonstrates only those maintained gate outcomes. It does not dispatch a worker,
accept a candidate, replace human diff review, or certify correctness or security.

The public conformance kit expands that teaching subset without adding acceptance
authority:

```text
conformance/run.sh --gate PATH
  -> strict SHA-pinned conformance/v1 manifest and static sources
  -> eleven independent private disposable Git repositories
  -> supplied gate entry point under fixed time/output/process-group bounds
  -> exact expected gate exits 0, 10, 11, 12, 13, 14, 15, and 64
  -> cleanup, then one bounded fixture-compatibility result
```

The supplied gate is user-approved executable code, not sandboxed content. A passing
result means only that entry point matched the public fixtures; it is not security,
real-job, Receipt v1, report, lifecycle, or worker-quality certification. The gate,
loaded code, local owner/same-UID processes, and OS administrators form the cleanup
TCB. Cleanup is bounded, no-follow, and descriptor-relative only while exact original
parent/root identities remain; final pathname removal trusts that TCB. Drift fails
closed with a possible residual, never a parent scan or moved-directory chase, and
does not establish same-user tamper resistance.

## Opt-in maintenance flows

- `update.sh check` and `check --watch` observe only this project's latest official
  stable release through fixed REST paths, a proxyless redirect-rejecting strict JSON
  client, and bounded process-group supervision. Exact release commit equality with
  checkout HEAD returns 0; a different verified commit returns 3; unavailable evidence
  or an unexpected origin returns 2. Difference is not an ordering or downgrade claim.
  Neither path probes installed AGY/Codex, uses Git network transport, or changes files.
  `update.sh apply [TAG]` remains explicit: it verifies the tag and fast-forward,
  protects ignored-path collisions, runs candidate suites and install preflight in a
  temporary worktree, then fast-forwards and reinstalls. Candidate scripts run with
  user privileges; the temporary worktree is not a security sandbox.
- `skills/agy-worker/` is the canonical Agent Skill and owns the complete core runtime.
  A skill-folder-only copy resolves `runtime/` without the repository or a network
  fetch. Repository-root core commands are compatibility wrappers; maintenance entrypoints invoke repository-owned `scripts/` and assets outside the
  skill. Core modules never import those tools; tools may reuse canonical core helpers.
  `install.sh` copies the same core bundle and adds a local `.pipeline-root` marker so
  checkout maintenance remains available. `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`
  describe that same root package: the marketplace source is exactly `.` and may not
  introduce a copied `plugins/` skill or runtime. `docs/MARKETPLACE.md` records the
  local contract; adding it to Codex remains separately approved. The tested public
  installation paths are the Git-backed Codex marketplace and GitHub clone plus
  explicit install; neither installation authorizes provider dispatch or repository
  transmission. `SKILL.md` declares Codex compatibility and experimental Claude Code
  support and links its
  package-owned progressive-disclosure guides: `README.md` owns standalone package
  orientation, `PROJECT_LIFECYCLE_AND_VERIFICATION.md` owns lifecycle and Verification
  v2 procedures, `SECURITY_AND_COMPATIBILITY.md` owns provider/verifier boundaries,
  and `TROUBLESHOOTING.md` owns actionable failure recovery. These guides require no
  repository-root prose or decorative assets. Provider model names do not expand host
  support. `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
  describe the same root with Claude source `./`; live Claude verification remains
  pending. Both plugin identities are `agy-worker`.
- `doctor.sh` delegates to the bundled doctor and shared capability probe. It checks
  local prerequisites without provider, account, network, update, or repair work.
  Version text is diagnostic. A green result does not establish authentication, model
  availability, native permissions, or task quality. It isolates bounded probes in a
  private external workspace, forwards signals to the active process group, and
  rejects symlinked package parents.

## Ownership and test coverage

| Path | Responsibility | Owning offline suite |
|---|---|---|
| `agy-worker.sh`, `skills/agy-worker/runtime/agy-worker.sh`, `skills/agy-worker/runtime/scripts/agy_dispatch.py`, `skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py`, `scripts/transmission_preview.py`, `skills/agy-worker/runtime/scripts/transmission_preview.py` | Root compatibility entry point plus canonical runtime entry point; explicitly mirrored helpers remain byte-synchronized. Caller-owned selection, workflow resolution (`explore`/`task`: 1..2, default 2; `project`: 1..5, default 5), private prompt/log staging, a closed provider/probe environment baseline with exact-name `--provider-env` opt-ins bound into command state, deterministic external state root derivation under `XDG_STATE_HOME`/`HOME` when unset, prospective and post-resolution fail-closed rejection of project roots inside the target worktree before prompt staging or recovery dispatch, process-owning progress-aware dispatch with explicit claim, launch, monitor, reap, reconciliation, and publication phases whose typed records preserve resource ownership, and a normally imported sibling engine owning bounded no-follow Git/worktree observations, shared exceptions, and explicitly patched module dependencies. Provider-free `transmission-preview` runs before prompt, selection, provider, state, log, stdin, or network work. It retains the schema-v1 path/kind review manifest and, for whole-worktree approval, adds a bounded descriptor-relative double content scan binding file bytes, kinds, permissions, and literal symlink targets without logging content. Scoped preview hashes only selected entries. Approval digests include the persisted native grant profile; retired dispatch formats are rejected before projection or mutation. Fixed bounded `/usr/bin/git worktree list` plumbing verifies real registration without hooks, prompts, provider, or network; streamed directory enumeration applies count/time bounds before sorting. It excludes the root `.git` marker, lists contained symlink aliases without targets, rejects drift, escapes, special nodes, and limits, and is review evidence rather than approval or provider-launch binding. The current state/command contract supports an explicit transmission choice and a closed read/write file-or-tree provider scope whose policy, readable manifest, selected-content manifest, and approval are bound by one transmission SHA. Each attempt uses a fresh external owner-private mode-0700 Git-less stage as provider cwd. Descriptor-relative no-follow copies reject aliases, hardlinks, special nodes, Git administration, and casefold/NFC/NFD collisions under count, byte, depth, and deadline bounds. A strictly framed terminal `denied_actions` field yields `permission_required` for any field value, without automatic continuation; a valid bound candidate remains reviewable. This denial outranks a hard-deadline reason while preserving truthful limit metadata; cancellation, output bounds, and binding failures remain higher priority. Exact-shape headless refusals also yield `permission_required`. An exact duration-bound partial-output timeout yields `provider_timeout` across versions, including exit zero. A nonzero provider exit with an otherwise valid success report yields `agy_failed_unclassified`; valid candidates remain available for driver review. Invalid framing never becomes a success. An exited provider whose descendant holds the output pipe open may preserve that exact partial candidate at idle expiry; unrelated idle failures retain their prior behavior. Scoped report paths accept canonical absolute descendants of the exact staged root as relative equivalents before the existing exact mutation comparison. Recognized success, error, and cancelled reports preserve and transactionally reconcile only authorized stage mutations after source rebind; durable backups, fsync, an atomic recovery ledger, prior/post identities, post-reconcile equality, and exact rollback fail closed on drift or uncertainty. Initial launch has no implicit transmission mode: provider scope is recommended, while whole-worktree dispatch remains a manifest-bound exception rechecked immediately before the initial provider process. Only current state and command formats load; old-format jobs must be finished or discarded with their creating release. Current candidate/lifecycle writes preserve semantic-v1 candidate snapshots plus stable root/Git boundary identity and sanitized `provider_terminal_status` (`unknown`, `success`, `error`, `cancelled`) without exposing provider status in public driver disposition or altering action thresholds. A terminal scoped candidate is read and finalized against its stored post-provider snapshot, including authorized deletions; changed scoped bytes can continue only under an explicit initial scoped-repair grant, which binds scope, model, conversation, candidate lineage, and budgets; otherwise they remain result/finalize-only. Verification v2 rebinds result/schema/root/candidate before and after a no-follow isolated verification copy. It preserves regular bytes/executable bits, rebases every contained symlink inside the copy, and rejects broken/outward/Git-admin links (no `.git`) so writable driver checks do not reconcile ignored drift into the candidate. Partial/promisor clones fail synchronously with a fixed sanitized full-clone diagnostic before queued state or provider launch. A valid, non-empty REUC observation immediately before provider launch yields the bounded public reason `resolve_undo_present`, existing exit code 20, and `failure_stage=binding_failure` without provider launch or clearing index metadata; malformed, duplicate, or racing observations remain generic `status_unavailable`. Wrapper parse errors remain `64`; post-parse copy runtime/binding/destination failures map to `20`. Explicit native scoped provider attempts additionally use the native macOS containment helper described below; ordinary verification copies and environment filtering alone do not provide OS isolation. A preserved current-schema job already inside its worktree keeps exact command/schema/root/result readback and driver-only non-verified finalization, while verified finalization, verification-copy, and provider continuation/restart remain unavailable. Other current finalization retains artifact/schema/root/worktree rebinding; preserved provider-error/cancelled candidates, queued SHA+entry rebinding remain unchanged; no version-specific quota countdown or retry authority is inferred. Provider-scope approval grants neither provider execution, Git action, driver acceptance, nor publication. | `tests/test-agy-worker.sh` (288 cases), including its sourced `tests/agy_worker_project_lifecycle_cases.sh`; `tests/test-agy-worker-remediation.py` (118 focused cases); its non-discoverable case modules are loaded by that canonical suite |
| `model-selection.sh`, `skills/agy-worker/runtime/model-selection.sh`, `skills/agy-worker/runtime/scripts/model_selection.py` | Caller-owned literal model/effort forwarding and named tier conveniences; shared bounded version/help capability probe for every launch; version text is diagnostic only. Private selection records bind the caller choice and safe executable identity. Immediate prelaunch revalidation preserves no-follow content/path binding and process-group/signal limits without exact-version activation or help-SHA approval. | dispatcher, doctor, and packaging suites |
| `model-recommendation.sh`, `skills/agy-worker/runtime/model-recommendation.sh`, `skills/agy-worker/runtime/scripts/model-recommendation.py` | Root compatibility entry plus side-effect-free pre/post recommendations; direct selections are labelled but unranked and never applied | `tests/test-agy-worker.sh` (shared dispatcher suite) |
| `delegation-policy.sh`, `skills/agy-worker/runtime/delegation-policy.sh`, `skills/agy-worker/runtime/scripts/delegation_policy.py`, `skills/agy-worker/runtime/schemas/delegation-policy.schema.json` | Root compatibility entry plus closed evaluator for explicit opt-in delegation-first coordinator policy; assigns AGY as first substantive repository actor after discovery/worktree/verification setup; fails closed on missing approvals, hard stops, preflight failures, or budget exhaustion without silent fallback to Codex. | `tests/test-delegation-policy.py` plus doctor, resolver, packaging, and CI sharding/timing suites |
| `workflow.sh`, `skills/agy-worker/runtime/workflow.sh`, `skills/agy-worker/runtime/scripts/workflow.py`, `skills/agy-worker/runtime/schemas/workflow-state.schema.json` | Root compatibility entry plus canonical thin workflow facade (`run`, `status`, `verify-finalize`) over existing job lifecycle, dispatch, and verification authorities. Ordinary run accepts an absolute repo/job ID, binds omitted base to `HEAD` once, derives deterministic owner-private state plus an isolated lifecycle-owned branch/worktree under safe XDG/HOME state, and retains preview resources for the approved second call. Launch requires either the exact whole-worktree manifest approval or an exact provider-scope policy plus selected-content transmission digest; the scoped path delegates to the canonical staging boundary without `--add-dir`. The all-explicit state/worktree/branch/base tuple remains advanced compatibility. Persisted workflow records use only `BOUND_SCHEMA_VERSION` or `BOUND_FACADE_SCHEMA_VERSION`; older formats and referenced retired dispatch records reject with actionable guidance. Status output has its own version and projects supported facade, job-lifecycle, or dispatcher sources read-only without migration; verification remains driver-owned. Preview/run/status expose advisory delegation decisions without fallback authority. Finalization binds the dispatcher job ID and its exact log parent before invoking the public wrapper. Same-invocation pre-dispatch rollback delegates exact clean facade-created deletion to the lifecycle and refuses drift or dispatch evidence. | `tests/test-workflow.py` (29 cases), `tests/test-workflow-integration.py` (installed CLI with a synthetic worker; detects an injected outside-write regression without claiming native provider containment), plus doctor, resolver, packaging, and CI sharding/timing suites |
| `doctor.sh`, `skills/agy-worker/runtime/doctor.sh`, `skills/agy-worker/runtime/scripts/model_selection.py` | Root wrapper plus offline prerequisite and shared capability checks; no account/provider/network work or repair; repository-only tooling is not required for readiness | `tests/test-doctor.sh` (181 cases) plus packaging synchronization checks |
| `install.sh`, `skills/agy-worker/README.md`, `skills/agy-worker/SKILL.md`, `skills/agy-worker/agents/openai.yaml`, `skills/agy-worker/references/`, `skills/agy-worker/scripts/resolve-pipeline.sh` | Install and resolve complete-plugin, explicit-checkout, or folder-only skill layouts without fetching code. `SKILL.md` stays the concise progressive-disclosure router and preserves mandatory user-facing provider dispatch notices across initial, resume, continue, and restart launches, authority/privacy stops, workflow choice, and independent plan governance; the standalone README and references own package orientation, detailed lifecycle/Verification v2, security/compatibility, and actionable troubleshooting. Package metadata states its truthful use case. All internal package links resolve without repository-root files, and decorative assets are optional rather than a completeness requirement. | `tests/test-packaging.sh` (300 cases), including package-document presence, link, metadata, standalone-completeness, and no-required-asset guards |
| `skills/agy-worker/runtime/schemas/`, `skills/agy-worker/runtime/scripts/validate-envelope.py` | Dependency-free envelope contract validation | dispatcher and gate suites |
| `qa-gate.sh`, `skills/agy-worker/runtime/qa-gate.sh` | Root compatibility entry plus canonical immutable-base Git audit through the shared hardened candidate-state reader, effective content-filter rejection, bounded envelope intake, segment-aware path policy, escalation, ordered no-shell canonical argv verification, explicitly acknowledged shell compatibility, a default verifier baseline without `HOME`, separately acknowledged credential-name opt-ins delivered only through a private descriptor, sanitized label/mode diagnostics, and internal pre-opened structured evidence handoff | `tests/test-qa-gate.sh` (69 shell assertions, including the shared 27-case Git/path-policy regression helper) plus receipt suite no-FD compatibility checks |
| `verify-job.sh`, `skills/agy-worker/runtime/verify-job.sh`, `skills/agy-worker/runtime/scripts/evidence_receipt.py`, `skills/agy-worker/runtime/schemas/evidence-receipt.schema.json` | Root compatibility entry plus exact input hashing, strict selection/advisory binding, startup-isolated parent-exclusive gate evidence, domain-separated canonical verifier-spec hashes, mode/acknowledgement/ordinary-and-credential environment-name policy hashing, private value handoff without value persistence, interruption cleanup, structurally compatible unsigned Receipt v1 validation, and private durable no-overwrite publication | `tests/test-evidence-receipt.sh` (100 shell assertions, including the shared 27-case Git/path-policy regression helper) |
| `evidence-report.sh`, `skills/agy-worker/runtime/evidence-report.sh`, `skills/agy-worker/runtime/scripts/evidence_report.py`, `skills/agy-worker/runtime/scripts/recommendation_record.py` | Root compatibility entry plus pure Receipt v1 validation, deterministic bounded text/canonical-JSON/Markdown/GitHub-Step-Summary rendering, final workflow-command and Markdown safety checks, separately trusted binding checks, privacy filtering, and optional mode-0600 no-overwrite publication; the renderer never discovers the GitHub summary environment path; stdout-only `main(argv)` returns, while file-output `main(argv)` is process-owning through `os._exit(0)` and must run as a command/subprocess; never dispatches, routes, gates, uploads, or changes a verdict | `tests/test-evidence-report.sh` (80 cases), receipt back-compat, and packaging checks |
| `job.sh`, `skills/agy-worker/runtime/job.sh`, `skills/agy-worker/runtime/scripts/job_lifecycle.py`, `skills/agy-worker/runtime/scripts/candidate_state.py`, `skills/agy-worker/runtime/schemas/job-state.schema.json` | Root compatibility entry plus process-owning lifecycle CLI, external private state, canonical branch-backed worktree init/status, fixed sanitized Git execution with incrementally bounded stdout and no checkout hook/filter authority, exact Receipt delegation/binding, read-only preserve instructions, interrupted-progress reconciliation, receipt-bound rejected-only cleanup, and separately bound pre-gate abort. Optional facade-created schema-v2 provenance leaves legacy v1 unchanged; lifecycle-owned `rollback-ready` deletes only an exact ready, empty, drift-free pre-dispatch facade resource set with current approvals and absent dispatch evidence. The shared candidate helper is also the gate's sole digest implementation. | `tests/test-job-lifecycle.py` (132 cases), gate parity, doctor, and packaging suites |
| `proof-demo.sh`, `conformance/v1/envelopes/honest.json`, conformance content sources | Repository-only offline starter proof using the two-state teaching subset of the public versioned contract | `tests/test-proof-demo.sh` (22 cases) |
| `conformance/run.sh`, `conformance/v1/`, `docs/CONFORMANCE.md` | Repository-only public qa-gate v1 fixture contract, strict manifest/source binding, private normally disposable repositories, bounded supplied-gate execution, FD-relative no-follow cleanup under an explicit same-UID TCB, fail-closed residual policy, and non-certification claim | `tests/test-conformance.py` (83 cases) plus packaging policy checks |
| `update.sh`, `ground-truth.sh`, `skills/agy-worker/runtime/ground-truth.sh`, `scripts/compatibility_probe.py`, `scripts/official_github.py` | Explicit project releases and project-only read-only check/watch; fixed REST release/ref binding including bounded annotated tags; separate document bounds and process-group/signal cleanup. Ground truth exposes bounded local version/help and an explicitly separate account-state phase. Apply-time Git fetch remains ambient-configuration-aware. | `tests/test-update.sh`, `tests/test-compatibility-probe.py`, `tests/test-official-github.py`, plus packaging ground-truth checks |
| `update-notifier.sh`, `scripts/update_notifier.py`, `scripts/update_notifier_child.py` | Optional macOS daily LaunchAgent over a hash-bound project update snapshot. Canonical account HOME, closed source manifest, serialized lifecycle, launchctl reconciliation, parent-death acknowledgement, process-owned signals, update-fingerprint deduplication, and resumable uninstall; no apply/provider authority. Current-format source drift requires explicit refresh. Retired records reject read-only before lock/directory creation, launchctl, or network; use the creating release at its authenticated source location to uninstall, confirm unloaded status, archive the inert recovery directory privately, then explicitly install the new release. Existing snapshots and schedules remain untouched. | `tests/test-update-notifier.py` with offline fake controls |
| `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `docs/MARKETPLACE.md` | Shared `agy-worker` identity with a root-source Codex (`.`) marketplace and experimental Claude Code (`./`) marketplace. The entry names the one canonical `skills/agy-worker/` bundle/runtime and is not installation or publication evidence. | `tests/test-packaging.sh` (300 cases) plus platform validators |
| `PRIVACY.md`, `TERMS.md`, `SUPPORT.md` | Public data disclosure, project policy, and support route | `tests/test-packaging.sh` (300 cases) plus review |
| `docs/index.md`, `docs/VERIFYING_AGENT_OUTPUT.md`, `docs/_layouts/`, `docs/_config.yml`, `docs/sitemap.xml` | Static GitHub Pages landing, source-grounded verification tutorial, canonical metadata, mobile table/inline-code overflow containment, and sitemap; enabling Pages and submitting the sitemap through Search Console remain external | `tests/test-packaging.sh` (300 cases) plus rendered desktop/mobile review |
| `docs/assets/brand/`, `scripts/validate-brand-assets.py` | Approved light/dark master marks, pixel-hinted micro variants, favicon PNGs, social preview, and dependency-free asset validation | `tests/test-packaging.sh` (300 cases) plus rendered review |
| `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.github/pull_request_template.md` | Contribution workflow, private vulnerability route, conduct enforcement, and review checklist | human review plus relevant offline suites |
| `skills/agy-worker/runtime/scripts/agy_dispatch_containment.py` | Native macOS scoped provider launch and identity rebinding for a fresh Gitless stage, private HOME/TMP, and inherited filesystem restrictions. The bound provider image receives metadata/existence access to only its executable's exact parent for Core Foundation SSL initialization; directory listing, sibling access, and exec helpers remain denied, and self-verification receives no exception. The exact provider image also receives metadata-only access to private HOME ancestors so SQLite can resolve its conversation database path; ancestor data/listing and other images stay denied. The bound provider image receives non-local TCP 443, local resolver and TCP listener permissions, and reviewed Keychain access; no recipient allowlist is claimed. A bounded read-only default-Keychain lookup supplies an owner-validated file locator and minimal private-HOME preference, without copying owner preferences or reading/hashing credentials. Exact `/usr/bin/security` shares the reviewed Keychain services and receives read-only access to that literal file; provider/other-executable file access, parent access, writes, and network authority do not expand. Prelaunch rebinding and exact repair reuse reject locator/preference drift. Native preparation also binds generated private AGY settings that express staged reads and exact scope write selectors for bounded attempts; current-stage OS containment remains unchanged, owner settings are neither copied nor changed, and drift rejects repair. Session and self-verification receive no permission settings. Arguments, items, and service read/change/delete operations cannot be restricted by this rule. The macOS listener rule permits wildcard binds; local TCP outbound remains denied. Self-verification denies network and credentials. Process cleanup covers only the bound process group; detached descendants remain confined but are not proven reaped. Unsupported hosts reject native launch. Real-provider compatibility still requires version-specific live qualification. | `tests/test-provider-containment.py` (native cases require an unsandboxed macOS test runner; Linux checks unsupported-host rejection) |
| `skills/agy-worker/runtime/scripts/agy_dispatch_verification.py` | Optional verification manifests, required/optional check selection, selected-content copies, bounded private logs, and advisory-only V2 feedback. The existing dispatcher binds candidate/manifest authority, permits one check action per attempt, shares the total budget, and recovers interrupted actions without replay. Stored advisory feedback can feed the same conversation; worker text never becomes a command or feedback log. Final acceptance remains driver-owned. | `tests/test-self-verification.py` (portable contracts plus native macOS containment), `tests/test-self-verification-lifecycle.py` (real controller state and scoped copies; mocked check execution) |
| `.github/workflows/test.yml`, `scripts/ci-offline.sh`, `scripts/ci_stages.py`, `scripts/ci-worktree-check.sh`, `scripts/ci-diff-check.sh`, `scripts/ci_diff_check.py`, `scripts/ci_timing.py`, `scripts/ci_sharding.py`, `pyproject.toml`, `requirements-dev.txt` | Required `test` verifies exact full macOS offline coverage via four parallel fail-closed shards (`dispatcher`, `dispatcher-remediation`, `other-a`, `other-b`) on PRs (and explicit exact-SHA manual dispatch), cancels stale same-PR runs, and does not repeat the suite after a normal merge. A single committed-range diff-hygiene preflight gates the shards. Each job checks out the exact immutable head SHA; each shard runs its registered stage subset from the 22-stage canonical manifest (`scripts/ci_stages.py`), and emits a mode-0600 no-overwrite privacy-safe v2 receipt with per-stage monotonic durations; standalone validation retains read-only v1 shape/digest compatibility, but same-run publication and aggregate acceptance require v2. GitHub retains the uploaded workflow artifact for one day under repository Actions access. The aggregate `test` job runs with `if: always()` and succeeds only when all four unique shard receipts exist, preflight, the separate pinned Ruff/Mypy quality job, and all producer jobs succeeded, all match the expected head and inventory, and every canonical stage appears exactly once. Lower CI wall time from sharding does not mean lower compute, token usage, cost, or weaker verification. Canonical local runner `./scripts/ci-offline.sh` checks tracked changes and non-ignored untracked candidate files for whitespace, then runs all 22 offline stages, including all 18 registered suite commands, by default without network or provider calls; explicit syntax bytecode is externalized without leaking the cache prefix into ordinary suites, and `--timing-report` observes monotonic wall time. | `tests/test-ci-sharding.py` (109 cases), `tests/test-ci-timing.py` (46 cases), `tests/test-ci-worktree-check.py`, plus packaging policy tests and GitHub Actions |
| `README.md`, `docs/INSTALLATION.md`, `docs/USAGE.md`, `docs/PROJECT_WORKFLOW.md`, `docs/OPERATIONS.md`, `docs/DOCUMENTATION_POLICY.md`, `docs/public-files.allowlist`, `scripts/validate-docs.py` | Compact first-visit onboarding plus task-owned installation, usage, project-lifecycle, and operations guides under a progressive-disclosure, single-owner, public-claim, inline-link/anchor, ordered-onboarding, Pages-mapping, complete public-docs inventory, and permanent 450-line README contract | `python3 scripts/validate-docs.py . --readme-max-lines 450`, `tests/test-packaging.sh`, and `agents-md-auditor` |
| `docs/ROADMAP.md` | Dependency-ordered product slices with explicit candidate and publication status; historical release behavior remains bound to its release commit. Source, tests, and the owning task guide define current behavior. Release, installation, marketplace, and live-provider claims require separate evidence; the informational last provider-tested observation is owned by the installation guide. | human review; publication claims remain prohibited until their gates complete |
| `AGENTS.md`, `docs/lessons_learned.md`, this file | Durable contributor rules, context routing, and architecture rationale | `agents-md-auditor` after material changes plus packaging policy checks |

## Trust boundaries

- No initial facade or raw dispatch has an implicit provider-read mode: whole-worktree launch
  requires the preview’s `launch_approval_sha256`, binding the manifest and execution mode, while scoped launch requires the
  reviewed scope plus transmission SHA. Whole-worktree mode exposes the entire
  disposable `--workdir` as potentially provider-readable; prompt denylists, gate
  paths, and `--add-dir` do not narrow it.
  Recommended provider-scope mode binds exact reviewed read entries, a write subset, the
  complete local path/kind enumeration, and selected-content bytes into one approved
  transmission SHA, then stages only selected entries in a fresh owner-private
  mode-`0700` Gitless cwd. The controller still locally enumerates and validates
  worktree/scope paths. Default session mode uses normal user host authority;
  explicit native mode adds macOS scoped containment with documented network and
  cleanup limits. The mode is bound in the initial approval and job lifecycle;
  its approval grants no provider execution, Git action,
  driver acceptance, or publication. Secrets, denied paths, and unrelated private
  content must remain outside all entries approved for either mode.
- `agy` and every envelope field are untrusted. The driver's immutable base, path
  policy, and verification commands are trusted inputs and must be authored before
  dispatch.
- Model-routing evidence is a driver-owned classification, not worker prose. The
  recommender is outside the dispatch and acceptance paths, cannot execute either,
  and never applies its output. Default/custom tiers and the highest named tier fail
  safely to `no-escalation` when no ordered higher tier can be proved.
- An Evidence Receipt v1 is a private, unsigned serialization of one gate execution,
  not another acceptance authority. `verify-job.sh` can bind hashes and bounded
  optional G1/advisory data only after `qa-gate.sh` supplies the exact outcome through
  its internal wrapper-bound pre-opened descriptor. Direct `qa-gate.sh` is the
  no-receipt alternative; the evidence capability is not a public direct-call mode.
  Receipt validation never converts a rejected/routed
  result to `gate-passed`, and even `gate-passed` still needs human diff review.
- Model and effort are caller-owned inputs. Capability checks cannot select a tier,
  infer model availability, recommend escalation, or accept a candidate. Forward
  direct values without constructing compound slugs, and preserve exact selection
  binding across repairs and driver receipts.
- Project update observations never install a release or authorize provider work.
- Read-only GitHub evidence never uses Git transport. `scripts/official_github.py`
  owns the exact API repository/path policy and response validation;
  `scripts/compatibility_probe.py` owns process, time, byte, environment, and signal
  bounds. These guarantees do not extend to the explicit `update.sh apply` Git fetch.
- `--workdir` is the single audited repository. User-supplied `--add-dir` roots must
  resolve inside it; multi-repository mutation is unsupported.
- Release tags are observed through fixed official REST endpoints and an apply
  candidate must match that observed commit. The apply-time Git fetch still honors
  ambient Git transport settings. Candidate validation executes release code and
  therefore relies on that transport plus the maintainer account and tag-publishing
  boundary.
- Sanitization reduces accidental disclosure but does not replace exact human review.
  The reviewed hash must bind the bytes actually sent.
- A plugin install is local enablement, not consent to send repository content.
  Dispatch through agy can expose the approved prompt and worker-read files to
  Google/Gemini; the skill must obtain explicit approval for that named scope first.
- The Codex package manifest and repo-scoped marketplace descriptor are not
  publication evidence. The root-source marketplace entry exposes no copied skill or
  runtime, and installation or external catalog enablement remains a separate owner
  action. This project is distributed from its public GitHub repository and does not
  maintain Claude catalogs.
- README and Pages copy may describe only the checks this repository actually runs:
  independent Git-scope inspection and driver-owned verification. Passing them is not
  proof of general correctness or security. GitHub About fields, topics, homepage,
  and social-preview settings are external repository-owner state.

## Generated and private artifacts

- `logs/<job>/` contains the task, full prompt, stream, stderr, staged oversized
  prompt, extracted envelope, and driver-owned selection record. The record freezes
  selector provenance and executable binding but is not a gate receipt. The dispatcher
  creates this job tree owner-only
  even under a permissive caller umask. A missing log root is created privately; an
  existing final root must be current-user-owned, non-symlink, and not group/other
  writable before its physical path is used. The caller-owned root is not rewritten.
  This final-component check is not full ancestor-chain or TOCTOU protection. Job
  paths are created exclusively rather than reused, and staged prompt modes are
  restored on completion, early exit, and handled termination signals. Treat the
  tree as private evidence; do not commit or paste it into reports.
- Temporary worktrees, envelopes, updater candidates, and bug drafts normally live
  outside the repository. Preserve accepted work before cleanup; force removal is only
  for deliberately rejected disposable changes.
- Receipt files live only at a caller-selected new canonical path outside the audited
  repository, under an owner-private real parent. They are published mode `0600` by
  same-directory file `fsync`, atomic no-overwrite hard link, and parent `fsync`.
  They contain hashes and bounded labels rather than source, paths, commands, output,
  logs, or worker prose. They are unsigned and not self-authenticating; retain or
  delete them according to the caller's local evidence policy.
- `~/.gemini/` contains agy state. `~/.codex/skills/agy-worker/` is written only by an
  explicit `install.sh` or successful `update.sh apply`; its `.pipeline-root` is a
  local install artifact and must never enter the public skill bundle. Repository
  changes must not silently edit user configuration.
- Folder-only skill installs keep private job artifacts under their bundled
  `runtime/logs/`; repository-root and explicit-checkout installs retain the root
  `logs/` location.
- Ignored files are still part of the gate and updater collision checks. “Ignored”
  never means “outside the trust boundary.”
