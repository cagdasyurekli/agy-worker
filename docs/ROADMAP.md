# Product roadmap

Package metadata declares **0.22.0**. This page describes the checked-out product;
a version string does not prove publication or installation.
Release history lives in [git tags](https://github.com/cagdasyurekli/codex-agy-worker/tags)
and [GitHub releases](https://github.com/cagdasyurekli/codex-agy-worker/releases).

## Direction

Keep useful AGY delegation small and understandable: choose `explore`, `task`, or
`project`; approve the actual transmission boundary; review the candidate; verify
it independently; repair in the same conversation within budget.

The core uses capability checks instead of exact-version activation. Model and effort
remain caller-owned. Optional local self-verification supplies advisory feedback;
the driver retains acceptance authority. [Usage](USAGE.md) and
[Project workflow](PROJECT_WORKFLOW.md) own the current interfaces.

## Next

- Make the worker's initial instructions easier to follow while preserving the output
  contract, hard boundaries and optional verification behavior.
- Exercise realistic workflows independently with bounded synthetic inputs, and
  document the observed provider and host limitations honestly.
- Verify installed-package and host behavior separately from source tests before
  claiming support or publication. Catalog updates require owner approval.

## Known limits

- Session mode retains normal user filesystem and network access. Scoped staging
  narrows copied content and reconciliation, not provider host authority.
- Native mode is scoped macOS containment with explicit network/Keychain grants and
  cleanup residuals, not a universal sandbox. See the
  [security reference](../skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md).
- Capability acceptance cannot establish authentication, model availability or task
  quality. Provider help and live behavior are separate evidence.
- Claude Code remains experimental pending live verification. Native Windows is
  untested. [Installation](INSTALLATION.md) owns compatibility observations.
- Old dispatch formats are not migrated; finish or discard them with their creating
  release. Useful candidates survive failed checks or exhausted repair budgets.
- Offline tests and fixture conformance establish only exercised contracts. A worker
  envelope, receipt or green gate is not general correctness or security certification.

No roadmap item authorizes provider exposure, Git actions, installation or publication.
