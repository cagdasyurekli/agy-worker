# Architectural lessons

These principles explain maintained boundaries. Commands and recovery procedures belong
in the [task guides](PROJECT_WORKFLOW.md), not in a second operational history.

## A worker report is never evidence

Treat envelopes as untrusted claims, including reported commands and test results.
The driver reviews the actual diff and runs independently selected checks against the
bound candidate; neither a report nor a receipt creates acceptance authority.

## Git scope must be immutable and complete

Derive candidate facts from an immutable base, tracked changes and relevant untracked
or ignored state. Harden Git reads against hooks, fsmonitor, inherited configuration
and content filters; a repository must not execute programs merely by being inspected.

## Provider reads and requested writes are different boundaries

Prompt denylist and gate path policies govern task writes or candidate acceptance,
not provider reads. Approve all whole-worktree exposure explicitly, or stage exact
reviewed scope entries; selected staging still does not isolate a session-mode provider
from the host.

## Human authority and mechanical bindings serve different purposes

A digest binds reviewed bytes and policy to an existing human decision; refreshing it
does not itself grant or revoke approval. Reuse authority for covered same-scope repairs,
but stop for changed exposure, destination, isolation, permissions or budget.

## Preserve candidates when verification fails

A failed check is useful feedback, not permission to erase work or silently change
models, conversations or implementers. Return sanitized findings to the same conversation
within budget, and preserve a partial candidate when further repair is unavailable.

## Capabilities and response semantics are separate

Help establishes whether the required interface is present, not whether authentication,
a model or a task will work. Keep provider failure classification conservative and
version-independent, preserve bound candidates, and let driver verification decide assurance.

## Process ownership must remain explicit

Reap an exited leader before binding its surviving process group, and bound output
capture even when descendants retain pipe descriptors. Progress renews only the idle
lease; cancellation, hard limits and the original total budget keep their own authority.

## Finite snapshots are observations, not tamper resistance

Keep no-follow root/Git bindings, bounded scans and final revalidation in a defined order.
A trusted same-user process can mutate after a final read, so report that residual
instead of claiming continuous observation or adding endless rescans.

## Reconciliation needs durable rollback

Stage only authorized changes, rebind the source, preserve backups and persist recovery
state around each mutation. On drift or uncertain cleanup, preserve the residual for
recovery instead of chasing moved paths or claiming successful reconciliation.

## Private evidence must be private when created

Use owner-private directories, bounded no-follow reads and explicit publication paths;
redaction after a leak is not a boundary. Keep prompts, raw logs, credentials and private
controller records out of provider inputs and public artifacts.

## Distribution and updates must preserve authority

A portable package must include its actual runtime and instructions without relying
on untracked files or a developer checkout. Updates use reviewed official sources and
explicit apply authority; source, release, catalog and installed snapshots are separate facts.

## Diagnostics observe; they do not repair

Readiness, update checks and status should expose bounded facts without account discovery,
configuration changes or hidden retry. Name the failed prerequisite and preserve caller
choices rather than treating a diagnostic as new execution authority.

## Keep one owner for each contract

Put behavior in source, executable inventories in their registry, operations in task
guides and concise responsibility/test routing in the [repository map](REPO_MAP.md).
Use types and small helpers to expose real state and resource ownership, not to hide
unchecked dynamic bindings behind broad casts or duplicated controllers.

## Verification strength must match the claim

Fixture conformance is exercised compatibility, not certification; offline checks do
not establish live provider or host behavior. Preserve independent review for material
work and report exactly what was verified, what remains partial and what is blocked.
