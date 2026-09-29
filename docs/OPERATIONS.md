# Operations and maintenance

Use this guide for repository checks, update observation, explicit updates, the
optional macOS notifier, bounded evidence rendering, and sanitized feedback. None of
these maintenance surfaces authorizes an agy provider dispatch, changes a model, or
accepts a worker candidate.

For contribution and release checks, start with
[CONTRIBUTING.md](../CONTRIBUTING.md). For current product and release state, use the
[roadmap](ROADMAP.md); this page intentionally does not repeat version history.

## Run the repository checks

The required GitHub `test` job is a fail-closed aggregate over four shards:
`dispatcher`, `dispatcher-remediation`, `other-a`, and `other-b`. A single preflight
checks committed-range diff hygiene before the shards start.
Each job checks out the exact pull-request head (or validated exact manual-dispatch
head). Each shard runs its registered stage subset and publishes a
mode-`0600` receipt bound to the head and canonical inventory. The aggregate succeeds
only when preflight and all four producers succeeded, every receipt matches the
expected head and inventory, and every canonical stage ran exactly once.

GitHub retains the uploaded privacy-safe receipt artifact for one day. The receipt
contains no paths, commands, environment values, logs, or credentials. It is workflow
evidence for that exact run, not an owner-private local evidence file and not a
general correctness claim. Lower wall time from sharding does not establish lower
compute, provider usage, token usage, cost, or weaker verification.

When hosted Actions are unavailable or inappropriate for a private fork, run the
same canonical fail-fast suite locally from the repository root:

```bash
./scripts/ci-offline.sh
```

The canonical offline stages need no agy provider call, network access, API key, or
GitHub login. Ambient local tools may still consult their ordinary user
configuration. Keep the exact summary with the commit, tree, and `git diff --check`
evidence. On a clean tracked and untracked worktree, an optional timing report records
ordered observational wall time without changing the gate:

```bash
./scripts/ci-offline.sh --timing-report /absolute/new/private/timing.json
```

The timing report is mode `0600`, no-overwrite, and bound to the exact HEAD and
canonical inventory. It contains no paths, commands, environment values, logs,
credentials, provider data, timestamps, or host identity. A local pass never
satisfies the protected GitHub `test` check. For an exact release comparison after
hosted capacity returns, manually dispatch the workflow with committed `base_sha` and
`head_sha` values before publication unless the repository owner explicitly changes
that policy.

Billing depends on repository visibility and account policy. Consult GitHub's
[Actions billing guidance](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [workflow concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
rather than inferring cost from a faster wall-clock result.

## Check for updates without applying them

There is no automatic updater. The read-only check is explicit:

```bash
./update.sh check
```

The check compares the current checkout with the latest stable release of this
project, using its exact verified tag-to-commit binding. It does not inspect installed
AGY/Codex versions, model inventories, distribution manifests, or review dates.
`check --watch` performs the same project-release observation for the notifier.

| Exit | Meaning |
|---:|---|
| `0` | The verified release commit matches this checkout. |
| `3` | A different verified stable release commit is available. |
| `2` | Evidence or the expected origin is unavailable or invalid. |

A different commit is an update observation, not proof of ordering or permission to
downgrade; an untagged checkout is identified explicitly. Signal exits are preserved.
The stdlib observer uses fixed project GitHub REST endpoints, disables ambient HTTP
proxies, rejects redirects, validates bounded metadata/JSON and tag targets, and
closes child process groups. Neither check mode fetches with Git, installs, changes
records, or invokes AGY or a provider.

## Apply a reviewed update explicitly

Applying is a separate state transition:

```bash
./update.sh apply v1.2.3       # or omit the tag to select the latest stable release
```

`apply` refuses a dirty or detached checkout, accepts only stable release tags from
the expected GitHub origin, verifies that the fetched tag resolves to the exact
remote commit and is a fast-forward, and runs Bash syntax, a temporary skill-install
preflight, and every offline suite in a disposable candidate worktree. It refuses an
update that would begin tracking and overwrite an ignored local file. Candidate
failure leaves the checkout unchanged.

Only after those checks does it fast-forward the current branch and rerun
`install.sh` against the real Codex skill destination. A real-destination permission
failure after the fast-forward exits `4` with `PARTIAL UPDATE`; fix the destination
and rerun this checkout's `install.sh`. Unlike the read-only observer, this explicit
apply path uses `git fetch` and therefore honors caller Git transport configuration,
including URL rewrites and proxies. Protect the GitHub account and tag-publication
process as part of that trust boundary.

## Inspect the local AGY interface

Before changing AGY-facing flags or claims, inspect the current local interface:

```bash
./ground-truth.sh
```

The default phase uses local version/help probes. `--account` remains a separate
explicit account-state inspection; it is not part of update checks or launch readiness.
The retired hosted compatibility watcher does not monitor project releases.

## Install the optional macOS notifier

The owner-private LaunchAgent runs the same read-only watch once per day and displays
a notification only when its sanitized update fingerprint changes:

```bash
./update-notifier.sh install
./update-notifier.sh status
./update-notifier.sh run       # manual one-shot check
./update-notifier.sh refresh   # explicit rebind after maintenance-required
./update-notifier.sh uninstall
```

The notifier has no independent network, provider, update, or mutating Git authority.
Its hash-bound snapshot invokes `update.sh check --watch`; it never applies an update,
edits a baseline, dispatches work, or reads personal configuration. Installation
binds the complete behavior-bearing source manifest, canonical account HOME, launchd
label, private state, and authenticated resumable uninstall ledger.

Source drift enters `maintenance-required` instead of silently rebinding. At most one
sanitized maintenance notification is sent, ordinary monitoring pauses, and only an
explicit `refresh` may rebind through the serialized uninstall/install lifecycle.
Refresh does not update code or a tool. Signals, overlapping
operations, ambiguous launchctl outcomes, nested process groups, replacement files,
and unknown or tampered legacy state fail closed. A completed uninstall deliberately
retains an authenticated inert ledger/tombstone, prior result, and lock for resumable
recovery and deduplication; additional private residuals may remain after drift or
failure. A notification is an irreversible UI side effect and cannot be retracted.

Older notifier formats are retired; `refresh` does not migrate them. New tooling
rejects an old record before creating locks/directories or calling launchctl/network
helpers, leaving the installed snapshot and schedule untouched. Recovery requires
these explicit owner actions:

1. Use the actual creating release at its bound source location and Git identity to
   run `./update-notifier.sh uninstall`.
2. Confirm that release's `./update-notifier.sh status` reports
   `not installed; authenticated recovery record retained` (launchd is unloaded),
   and review any `preserved replacement files` before proceeding.
3. Explicitly archive the now-inert
   `$HOME/Library/Application Support/codex-agy-worker/update-notifier` directory to
   a chosen owner-private location, preserving the recovery record. Do not archive
   LaunchAgents or unrelated configuration. Uninstall retains the old ledger and
   tombstone, so the new install still rejects it until this owner action is complete.
4. From the intended new release checkout, run `./update-notifier.sh install`.

An unrelated checkout has no authority to remove the old installation. Do not edit
its private ledger to force compatibility. Current-format source drift still uses
ordinary explicit `refresh`; there is no automatic old-format migration or cleanup.

## Render bounded evidence in automation

Evidence Receipt v1 creation, validation, report commands, GitHub Step Summary
redirection, privacy limits, and the process-owning file-output boundary have one
authoritative owner: [Project workflow](PROJECT_WORKFLOW.md#preserve-a-local-evidence-receipt-v1).
Use that reviewed recipe in automation; this operations guide does not maintain a
second copy.

## Report a problem or request an improvement

Open the appropriate issue form with a minimal synthetic reproduction and sanitized
version, expected-result, and actual-result details. [SUPPORT.md](../SUPPORT.md) owns
the required information, privacy precautions, and private security-report route.

## Related references

- [Installation and compatibility](INSTALLATION.md)
- [Using agy-worker](USAGE.md)
- [Project workflow and Verification v2](PROJECT_WORKFLOW.md)
- [Repository ownership and verification commands](REPO_MAP.md)
- [Architectural lessons](lessons_learned.md)
