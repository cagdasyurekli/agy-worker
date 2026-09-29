# Contributing

Thank you for helping improve `codex-agy-worker`. Human contributors should open
only the section relevant to the change: [README.md](README.md) for the first-visit
journey, the matching task guide for detailed user behavior, the matching
[repository-map](docs/REPO_MAP.md) row for ownership and tests, or the matching
[architectural lesson](docs/lessons_learned.md) when prior rationale is needed. README
and public-documentation changes must also follow the
[documentation policy](docs/DOCUMENTATION_POLICY.md).

## Before opening a change

- Keep the worker outside the trust boundary. Do not weaken `qa-gate.sh` to make a
  candidate pass.
- Keep the runtime Bash + Python 3.9+ + git. Do not add a package manager or daemon.
- Preserve explicit permission, privacy, and external-action boundaries.
- Open security reports through the private route in [SECURITY.md](SECURITY.md), not
  a public issue.

For a code or documentation change, describe the bounded problem, the paths in scope,
and the evidence that will show the change works. Add both an accept and a reject case
when introducing a new gate check.

## Verify locally

During implementation, run the owning focused suite from the relevant
[`REPO_MAP`](docs/REPO_MAP.md) row. Do not repeatedly run the full suite while the
same candidate bytes are unchanged.

Install the pinned development tools in a temporary virtual environment (Python
3.9 or newer), leaving the shipped runtime and system Python unchanged:

```bash
QUALITY_VENV="$(mktemp -d)/quality-venv"
python3 -m venv "$QUALITY_VENV"
"$QUALITY_VENV/bin/python" -m pip --isolated install --no-cache-dir -r requirements-dev.txt
. "$QUALITY_VENV/bin/activate"
```

The local quality command is required before review:

```bash
RUFF_NO_CACHE=true ruff check . && mypy
```

`pyproject.toml` owns the Python 3.9 target and the documented lint baseline;
Mypy checks the canonical runtime scripts, and its cache is disabled. Exact direct
and transitive development versions live in `requirements-dev.txt`. They are not
runtime dependencies. Dependency hashes are not locked: the version pins allow
platform-specific wheels and do not claim artifact integrity. Upgrade the pins as a
reviewed unit while preserving Python 3.9 support.

CI runs this command in a separate required `quality` job. The aggregate `test`
check requires its explicit success, including rejecting skipped or cancelled jobs.
The canonical offline registry remains standard-library-only and does not install
or depend on the development tools.

Once the candidate is stable, run the canonical offline CI body once before
requesting review:

```bash
./scripts/ci-offline.sh
```

It is fail-fast, requires no network or provider call, does not intentionally inspect
account-HOME contents, externalizes temporary bytecode, and runs shell/Python syntax checks plus
all registered offline stages. Ambient local tools may still consult ordinary user
configuration. In GitHub Actions, the suite is partitioned across four fail-closed shards
(`dispatcher`, `dispatcher-remediation`, `other-a`, `other-b`) and validated by the required aggregate
`test` check; lower CI wall time from parallelization does not mean lower total compute, provider usage,
token usage, cost, or weaker verification. On a clean tracked/untracked worktree, an optional
`./scripts/ci-offline.sh --timing-report <PATH>` mode captures ordered per-stage
observational monotonic wall time in an owner-private mode-0600 JSON report without
recording commands, logs, environment variables, or timestamps. For a quota-unavailable
private fork this is evidence to attach to review, not a replacement for the protected
GitHub `test` check; manually dispatch the exact committed range after Actions becomes
available and before publication. List the current commands directly from the
canonical registry:

```bash
/usr/bin/python3 -I -S -B scripts/ci_stages.py --list
```

The listing shows stage ID, shard, and registered command without running tests.
Suite commands can be run directly; syntax stages use runner-provided environment.
Use the matching repository-map row to choose the owning suite. For remediation,
select the natural group that owns the change:

```bash
/usr/bin/python3 -I -S -B tests/test-agy-worker-remediation.py --group core
/usr/bin/python3 -I -S -B tests/test-agy-worker-remediation.py --group runtime
/usr/bin/python3 -I -S -B tests/test-agy-worker-remediation.py --group recovery
```

Omitting `--group` runs the full remediation inventory. A focused pass accelerates
iteration but does not replace the stable-candidate full gate.

Report exact summaries and any checks you could not run. Passing tests do not replace
human diff review or justify unrelated cleanup.

Classify a failed check before retrying: a reproducible code failure needs a fix,
a timing-sensitive test needs a deterministic reproduction, and an environment or
service failure needs its prerequisite restored. Do not increase timeouts or change
models as a substitute for diagnosing the failure. Reuse passing evidence while the
candidate bytes and relevant environment remain unchanged; after an edit, rerun the
owning checks and apply the stable-candidate full-gate rule above.

When a release is also claimed to be installed, verify that machine state separately
after publication. A clean tagged checkout does not establish that the global Codex
skill was recopied or that the LaunchAgent snapshot was rebound. Read back
installed-bundle parity and notifier status before making those claims.

## Pull requests

Keep each pull request focused. Explain the trust boundary affected, list changed
paths, identify user-visible claims that changed, and include the exact verification
results. Maintainers may ask for a smaller slice when unrelated work obscures review.

By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
