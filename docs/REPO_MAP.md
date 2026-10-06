# Repository map

Open the row relevant to the change, then read its source. Commands below run from the
repository root; `python3` suites are standard-library offline tests. The canonical
portable runtime is `skills/agy-worker/runtime/`; matching root launchers are wrappers.
Runtime-relative paths in the first table use that prefix.

## Runtime components

| Component and paths | Responsibility | Owning checks |
|---|---|---|
| Facade: `workflow.sh`, `scripts/workflow.py`, `schemas/workflow-state.schema.json` | `run`, `status`, `verify-finalize` delegate to existing lifecycle and evidence authorities. | `python3 -B tests/test-workflow.py`; `python3 -B tests/test-workflow-integration.py` |
| Dispatcher: `agy-worker.sh`, `scripts/agy_dispatch.py` | Explicit transmission approvals, capability preflight, process ownership, typed state validation and candidate lifecycle. | `bash tests/test-agy-worker.sh`; `python3 -B tests/test-agy-worker-remediation.py --group core` |
| Worktree engine: `scripts/agy_dispatch_worktree.py` | Bounded Git/snapshot phases, scoped staging, durable reconciliation and no-follow candidate copying. | `python3 -B tests/test-agy-worker-remediation.py` |
| Runtime recovery: `scripts/agy_dispatch.py` | Controller cancellation, budgets, child cleanup and post-provider publication. | `python3 -B tests/test-agy-worker-remediation.py --group runtime` |
| Native containment: `scripts/agy_dispatch_containment.py` | Scoped macOS provider isolation, private HOME/TMP and bound grant reuse; no session fallback. | `python3 -B tests/test-provider-containment.py` |
| Advisory verification: `scripts/agy_dispatch_verification.py` | Optional driver-selected checks, isolated copies, private output and candidate-bound feedback. | `python3 -B tests/test-self-verification.py`; `python3 -B tests/test-self-verification-lifecycle.py` |
| Job lifecycle: `job.sh`, `scripts/job_lifecycle.py`, `schemas/job-state.schema.json` | Private state, disposable worktree ownership, receipt-bound cleanup and interrupted-action recovery. | `python3 -B tests/test-job-lifecycle.py` |
| Candidate/Git facts: `scripts/candidate_state.py` | Shared hardened Git and semantic candidate digest used by lifecycle and gate. | `bash tests/test-qa-gate.sh`; `python3 -B tests/test-job-lifecycle.py` |
| Gate: `qa-gate.sh` | Git-derived scope, envelope rejection and driver-owned verifier execution. | `bash tests/test-qa-gate.sh` |
| Receipt: `verify-job.sh`, `scripts/evidence_receipt.py`, `schemas/evidence-receipt.schema.json` | Exact input/policy binding and private, durable, unsigned receipt publication. | `bash tests/test-evidence-receipt.sh` |
| Report: `evidence-report.sh`, `scripts/evidence_report.py` | Pure receipt rendering and explicit private output; never dispatches or changes a verdict. | `bash tests/test-evidence-report.sh` |
| Selection: `model-selection.sh`, `scripts/model_selection.py`, `schemas/model-selection.schema.json` | Literal caller model/effort and shared bounded capability/executable checks. | `bash tests/test-agy-worker.sh`; `bash tests/test-doctor.sh` |
| Delegation policy: `delegation-policy.sh`, `scripts/delegation_policy.py`, `schemas/delegation-policy.schema.json` | Explicit delegation-first policy without implicit driver fallback authority. | `python3 -B tests/test-delegation-policy.py` |
| Scope preview and launch approval: `scripts/transmission_preview.py`, `scripts/launch_authority.py` | Provider-free review of content and exact initial task/settings; canonical approval and pre-spawn binding. | `python3 -B tests/test-launch-authority.py`; `python3 -B tests/test-agy-worker-remediation.py --group recovery` |
| Doctor/ground truth: `doctor.sh`, `ground-truth.sh` | Readiness and local help/version observation; account discovery is a separate explicit phase. | `bash tests/test-doctor.sh`; `bash tests/test-packaging.sh` |
| Envelope: `schemas/`, `scripts/validate-envelope.py` | Closed worker result shapes; a valid envelope is still a claim. | `bash tests/test-agy-worker.sh`; `bash tests/test-qa-gate.sh` |

## Repository components

These paths are relative to the repository root.

| Component and paths | Responsibility | Owning checks |
|---|---|---|
| Package: `install.sh`, `skills/agy-worker/README.md`, `SKILL.md`, `references/`, `agents/openai.yaml`, `scripts/resolve-pipeline.sh` (last five under the skill) | Portable core and progressive instructions; checkout, plugin and folder-only resolution. | `bash tests/test-packaging.sh` |
| Host manifests: `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.claude-plugin/` | One skill identity across Codex and Claude Code; host operation has bounded live evidence. | `bash tests/test-packaging.sh` |
| Updates: `update.sh`, `scripts/official_github.py`, `scripts/compatibility_probe.py` | Project-release observation, bounded official transport and explicit authenticated apply. | `bash tests/test-update.sh`; `python3 -B tests/test-official-github.py`; `python3 -B tests/test-compatibility-probe.py` |
| Notifier: `update-notifier.sh`, `scripts/update_notifier.py`, `scripts/update_notifier_child.py` | Opt-in local scheduled observation, snapshot binding and authenticated lifecycle; no update apply. | `python3 -B tests/test-update-notifier.py` |
| Starter proof: `proof-demo.sh`, `conformance/v1/` | Provider-free synthetic demonstration of maintained gate outcomes. | `bash tests/test-proof-demo.sh` |
| Conformance: `conformance/run.sh`, `docs/CONFORMANCE.md` | Public fixture contract, bounded supplied-gate execution and fail-closed cleanup residuals. | `python3 -B tests/test-conformance.py` |
| CI: `.github/workflows/test.yml`, `scripts/ci-offline.sh`, `scripts/ci_stages.py`, `scripts/ci_sharding.py`, `scripts/ci_timing.py` | Canonical stage inventory, exact-head shards and bounded timing receipts. | `python3 -B tests/test-ci-sharding.py`; `python3 -B tests/test-ci-timing.py` |
| Diff/worktree gate: `scripts/ci-worktree-check.sh`, `scripts/ci-diff-check.sh`, `scripts/ci_diff_check.py` | Candidate hygiene and committed-range diff checks. | `python3 -B tests/test-ci-worktree-check.py` |
| Development tools: `pyproject.toml`, `requirements-dev.txt`, `CONTRIBUTING.md` | Python target, pinned tools and local verification commands. | `RUFF_NO_CACHE=true ruff check .`; `mypy` |
| Docs: `README.md`, `docs/DOCUMENTATION_POLICY.md`, `docs/public-files.allowlist`, `scripts/validate-docs.py` | Onboarding, size limits, links, public inventory and Pages mappings. | `python3 scripts/validate-docs.py . --readme-max-lines 250`; `bash tests/test-packaging.sh` |
| Pages/brand: `docs/index.md`, `docs/_layouts/`, `docs/_config.yml`, `docs/sitemap.xml`, `docs/assets/brand/`, `scripts/validate-brand-assets.py` | Static presentation, canonical metadata and validated assets. | `bash tests/test-packaging.sh` |
| Contributor policy: `AGENTS.md`, `SECURITY.md`, `PRIVACY.md`, `SUPPORT.md`, `TERMS.md`, `CODE_OF_CONDUCT.md`, `.github/pull_request_template.md` | Authority, disclosures and contribution/reporting routes. | `bash tests/test-packaging.sh`; independent review |

## Where detail belongs

[Usage](USAGE.md) owns flags and transmission choices;
[Project workflow](PROJECT_WORKFLOW.md) owns lifecycle, verification and recovery;
[Installation](INSTALLATION.md) owns readiness and compatibility;
[Operations](OPERATIONS.md) owns updates and CI;
[Lessons](lessons_learned.md) owns durable rationale;
[Roadmap](ROADMAP.md) owns product direction.

Use `python3 scripts/ci_stages.py --list` for the executable stage inventory and
`./scripts/ci-offline.sh` for the complete offline gate. The full remediation command
loads its existing case modules; `--group core`, `runtime`, or `recovery` selects an
owning group without changing full coverage.

Keep private evidence and generated indexes outside Git and provider prompts.
`graphify-out/` is an ignored structural aid, not a competing contract; verify any
material relationship against current source.
