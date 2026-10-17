#!/usr/bin/env python3
"""Declarative canonical stage manifest for offline CI execution, timing, and sharding."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any, NamedTuple, Sequence

sys.dont_write_bytecode = True


class Stage(NamedTuple):
    id: str
    announcement: str
    shard: str
    argv: tuple[str, ...]
    receipt_metadata: dict[str, Any]


STAGES: tuple[Stage, ...] = (
    Stage(
        "diff-hygiene",
        "working-tree diff hygiene",
        "other-a",
        ("bash", "scripts/ci-worktree-check.sh"),
        {"receipt_id": "diff-hygiene"},
    ),
    Stage(
        "shell-syntax",
        "shell syntax",
        "other-a",
        (
            "bash",
            "-c",
            "for file in ./*.sh conformance/*.sh scripts/*.sh tests/*.sh skills/*/scripts/*.sh skills/*/runtime/*.sh; do bash -n \"$file\" || exit 1; done",
        ),
        {"receipt_id": "shell-syntax"},
    ),
    Stage(
        "python-syntax",
        "Python syntax",
        "other-a",
        (
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            "-c",
            "import glob, os, py_compile, sys\n"
            "sys.pycache_prefix = os.environ['AGY_WORKER_CI_PYCACHE_DIR']\n"
            "[py_compile.compile(f, doraise=True) for f in sorted(set(glob.glob('conformance/v1/*.py') + glob.glob('scripts/*.py') + glob.glob('skills/*/runtime/scripts/*.py')))]",
        ),
        {"receipt_id": "python-syntax"},
    ),
    Stage(
        "qa-gate",
        "qa-gate suite",
        "other-b",
        ("./tests/test-qa-gate.sh",),
        {"receipt_id": "qa-gate"},
    ),
    Stage(
        "evidence-receipt",
        "Evidence Receipt suite",
        "other-b",
        ("./tests/test-evidence-receipt.sh",),
        {"receipt_id": "evidence-receipt"},
    ),
    Stage(
        "evidence-report",
        "Evidence Report suite",
        "other-b",
        ("./tests/test-evidence-report.sh",),
        {"receipt_id": "evidence-report"},
    ),
    Stage(
        "job-lifecycle",
        "local job lifecycle suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-job-lifecycle.py"),
        {"receipt_id": "job-lifecycle"},
    ),
    Stage(
        "dispatcher-a",
        "dispatcher suite part a",
        "dispatcher-a",
        ("./tests/test-agy-worker.sh", "--ci-part", "a"),
        {"receipt_id": "dispatcher-a"},
    ),
    Stage(
        "dispatcher-b",
        "dispatcher suite part b",
        "dispatcher-b",
        ("./tests/test-agy-worker.sh", "--ci-part", "b"),
        {"receipt_id": "dispatcher-b"},
    ),
    Stage(
        "dispatcher-remediation-a",
        "dispatcher remediation suite part a",
        "dispatcher-remediation-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-agy-worker-remediation.py", "--ci-part", "a"),
        {"receipt_id": "dispatcher-remediation-a"},
    ),
    Stage(
        "dispatcher-remediation-b",
        "dispatcher remediation suite part b",
        "dispatcher-remediation-b",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-agy-worker-remediation.py", "--ci-part", "b"),
        {"receipt_id": "dispatcher-remediation-b"},
    ),
    Stage(
        "dispatcher-remediation-c",
        "dispatcher remediation suite part c",
        "dispatcher-remediation-c",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-agy-worker-remediation.py", "--ci-part", "c"),
        {"receipt_id": "dispatcher-remediation-c"},
    ),
    Stage(
        "provider-containment",
        "provider containment suite",
        "other-b",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-provider-containment.py"),
        {"receipt_id": "provider-containment"},
    ),
    Stage(
        "self-verification",
        "self-verification suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-self-verification.py"),
        {"receipt_id": "self-verification"},
    ),
    Stage(
        "self-verification-lifecycle",
        "self-verification lifecycle suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-self-verification-lifecycle.py"),
        {"receipt_id": "self-verification-lifecycle"},
    ),
    Stage(
        "updater",
        "updater suite",
        "other-a",
        ("./tests/test-update.sh",),
        {"receipt_id": "updater"},
    ),
    Stage(
        "update-notifier",
        "local update notifier suite",
        "other-b",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-update-notifier.py"),
        {"receipt_id": "update-notifier"},
    ),
    Stage(
        "delegation-policy",
        "delegation policy suite",
        "other-b",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-delegation-policy.py"),
        {"receipt_id": "delegation-policy"},
    ),
    Stage(
        "workflow",
        "workflow facade suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-workflow.py"),
        {"receipt_id": "workflow"},
    ),
    Stage(
        "workflow-integration",
        "installed workflow integration suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-workflow-integration.py"),
        {"receipt_id": "workflow-integration"},
    ),
    Stage(
        "launch-authority",
        "full launch approval suite",
        "other-a",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-launch-authority.py"),
        {"receipt_id": "launch-authority"},
    ),
    Stage(
        "packaging",
        "Codex distribution suite",
        "other-a",
        ("./tests/test-packaging.sh",),
        {"receipt_id": "packaging"},
    ),
    Stage(
        "doctor",
        "read-only doctor suite",
        "other-a",
        ("./tests/test-doctor.sh",),
        {"receipt_id": "doctor"},
    ),
    Stage(
        "conformance",
        "public gate conformance suite",
        "other-b",
        ("/usr/bin/python3", "-I", "-S", "-B", "tests/test-conformance.py"),
        {"receipt_id": "conformance"},
    ),
    Stage(
        "proof-demo",
        "starter proof suite",
        "other-a",
        ("./tests/test-proof-demo.sh",),
        {"receipt_id": "proof-demo"},
    ),
    Stage(
        "bytecode-hygiene",
        "repository bytecode hygiene",
        "other-b",
        (
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            "-c",
            "import os, sys\nfor root, dirs, files in os.walk('.'):\n    if '__pycache__' in dirs:\n        sys.stderr.write('ci offline: repository bytecode detected\\n')\n        sys.exit(1)\n    for f in files:\n        if f.endswith('.pyc') or f.endswith('.pyo'):\n            sys.stderr.write('ci offline: repository bytecode detected\\n')\n            sys.exit(1)\n",
        ),
        {"receipt_id": "bytecode-hygiene"},
    ),
)

STAGE_MAP: dict[str, str] = {stage.id: stage.announcement for stage in STAGES}
ANNOUNCE_MAP: dict[str, str] = {stage.announcement: stage.id for stage in STAGES}

SHARDS: dict[str, tuple[str, ...]] = {
    shard: tuple(stage.id for stage in STAGES if stage.shard == shard)
    for shard in (
        "dispatcher-a", "dispatcher-b", "dispatcher-remediation-a",
        "dispatcher-remediation-b", "dispatcher-remediation-c", "other-a", "other-b",
    )
}

# Public success labels are stable case identities, independent of execution counters.
# Explicit per-part tuples make additions, omissions, and moves reviewable.
CASE_LABELS: dict[str, tuple[str, ...]] = {
    'dispatcher-a': (
        'preview is stable, content-free, provider-free, bounded, and fail-closed',
        'provider scope parser validates schema, paths, and write-covered-by-read invariants',
        'provider scope reads and verification-copy immediate-parent boundary are strict and explicit',
        'top-level help distinguishes worker and lifecycle stdout; invalid usage is sanitized',
        'help states workflow-specific cycle limits',
        'raw dispatch requires an explicit transmission mode before provider or job artifacts',
        'raw whole-worktree approval is exact and stale-safe before provider launch',
        'post-preview whole content binding failure is bounded and publishes no provider command',
        'literal model produces an envelope (exit 0)',
        'literal model is forwarded after CLI parsing and keeps the ordinary writable preamble',
        'small prompt keeps --print and its value last',
        'direct dispatcher rejects a fresh legacy broad command before provider launch',
        'scoped repair opt-in writes one immutable command authority',
        'scoped repair rejects missing scope and unsupported workflow or cycle bounds',
        'explore/whole provider-bound preamble and existing contract order',
        'explore/scoped provider-bound preamble and existing contract order',
        'task/whole provider-bound preamble and existing contract order',
        'task/scoped provider-bound preamble and existing contract order',
        'project/whole provider-bound preamble and existing contract order',
        'project/scoped provider-bound preamble and existing contract order',
        'non-interactive preamble reaches all six workflow/transmission combinations',
        'self-verification CLI copies and binds the private manifest with an ID-only prompt',
        'self-verification CLI rejects non-private, symlinked, and hard-linked manifests before provider launch',
        'self-verification CLI rejects explore before provider launch',
        'stored self-verification feedback is explicit, continue-only, and single-use',
        'scoped launch approval is bound to provider isolation',
        'normal scoped dispatch pins the final stage root in its file-tool prompt',
        'normal whole-worktree dispatch pins its approved root in the file-tool prompt',
        'whole-worktree drift is rejected by the supervisor before provider launch',
        'ambient secret is absent from agy probes and provider launch',
        'explicit provider environment name reaches agy children',
        'runtime-injection provider environment name is rejected (exit 64)',
        'unsafe GIT_CONFIG_COUNT rejects before selector or job allocation',
        'unsafe GIT_DIR rejects before selector or job allocation',
        'unsafe AGY_WORKER_SCHEMA rejects before selector or job allocation',
        'failed mktemp exits before dispatcher fixture setup',
        'raw flash-high stays exact pass-through with no effort argument',
        'bound agy default preserves executable checks and emits no model or effort',
        'literal model routing stays version-independent while version observation remains non-gating',
        'complete structural probe proceeds without version approval',
        'option prose does not override the structural capability check',
        'direct selector accepts diagnostic version and exposes no executable path',
        'only the documented macOS /var alias has a normalized executable path digest',
        'literal caller values and transport boundaries without a model catalog',
        'representative pair gemini-3.7-flash/high accepts cli-cli',
        'representative pair gemini-3.6-flash/medium accepts cli-env',
        'representative pair gemini-3.8-flash/low accepts env-cli',
        'representative pair gemini-3.1-pro/high accepts env-env',
        'representative exact model gemini-3.7-flash-high accepts cli',
        'representative exact model gemini-3.6-flash-low accepts env',
        'representative fixed model claude-sonnet-4-6 accepts cli',
        'representative fixed model gpt-oss-120b-medium accepts env',
        'repeated model is ambiguous (exit 64, zero agy calls)',
        'repeated effort is ambiguous (exit 64, zero agy calls)',
        'removed tier is unknown (exit 64, zero agy calls)',
        'retired literal alias rejects before task or provider (exit 64, zero agy calls)',
        'overlong model is rejected (exit 64, zero agy calls)',
        'empty CLI model is rejected (exit 64, zero agy calls)',
        'empty CLI effort is rejected (exit 64, zero agy calls)',
        'effort without model is rejected (exit 64, zero agy calls)',
        'padded direct model is rejected (exit 64, zero agy calls)',
        'invented thinking-level flag is rejected (exit 64, zero agy calls)',
        'retired disposition flag is actionable rejection (exit 64, zero agy calls)',
        'retired help approval flag is actionable rejection (exit 64, zero agy calls)',
        'same model in CLI and environment conflicts (exit 64, zero agy calls)',
        'same effort in CLI and environment conflicts (exit 64, zero agy calls)',
        'retired environment is rejected (exit 64, zero agy calls)',
        'explicit empty environment model is rejected (exit 64, zero agy calls)',
        'explicit empty environment effort is rejected (exit 64, zero agy calls)',
        'selector fixtures exclude ambient bytecode but detect fixture-generated bytecode',
        'default missing --add-dir rejects before provider, job and lock mutation',
        'direct missing --add-dir rejects before provider, job and lock mutation',
        'default missing --disable-slash-commands rejects before provider, job and lock mutation',
        'direct missing --disable-slash-commands rejects before provider, job and lock mutation',
        'default missing --json-schema rejects before provider, job and lock mutation',
        'direct missing --json-schema rejects before provider, job and lock mutation',
        'default missing --mode rejects before provider, job and lock mutation',
        'direct missing --mode rejects before provider, job and lock mutation',
        'default missing --model rejects before provider, job and lock mutation',
        'direct missing --model rejects before provider, job and lock mutation',
        'default missing --output-format rejects before provider, job and lock mutation',
        'direct missing --output-format rejects before provider, job and lock mutation',
        'default missing --print rejects before provider, job and lock mutation',
        'direct missing --print rejects before provider, job and lock mutation',
        'default missing --print-timeout rejects before provider, job and lock mutation',
        'direct missing --print-timeout rejects before provider, job and lock mutation',
        'default session explore ignores unused --sandbox with fresh launch probes',
        'model session explore ignores unused --sandbox with fresh launch probes',
        'default session explore ignores unused --conversation with fresh launch probes',
        'model session explore ignores unused --conversation with fresh launch probes',
        'default session explore ignores unused --effort with fresh launch probes',
        'model session explore ignores unused --effort with fresh launch probes',
        'cli effort requires its capability before task consumption',
        'environment effort requires its capability before task consumption',
        'native requires sandbox capability before task consumption or containment',
        'non-semver diagnostic permits default launch with literal caller choices',
        'non-semver diagnostic permits direct launch with literal caller choices',
        'standalone base probe uses its own effort context',
        'standalone base rejects selection-only isolation context (exit 64)',
        'standalone record probe uses its own effort context',
        'standalone record rejects selection-only isolation context (exit 64)',
        'fail version evidence is unavailable (exit 8, calls 1, zero worker dispatch)',
        'empty version evidence is unavailable (exit 8, calls 1, zero worker dispatch)',
        'oversize version evidence is unavailable (exit 8, calls 1, zero worker dispatch)',
        'hang version evidence is unavailable (exit 8, calls 1, zero worker dispatch)',
        'missing help preflight is pre-provider and task-unread',
        'duplicate help preflight is pre-provider and task-unread',
        'malformed help preflight is pre-provider and task-unread',
        'utf8 help preflight is pre-provider and task-unread',
        'nul help preflight is pre-provider and task-unread',
        'oversize help preflight is pre-provider and task-unread',
        'fail help preflight is pre-provider and task-unread',
        'hang help preflight is pre-provider and task-unread',
        'executable binding drift stops before task read or provider dispatch',
        'same-length restored-mtime executable mutation stops before task or provider',
        'atomic same-target executable symlink replacement stops before task or provider',
        'different executable symlink target stops before task or provider',
        'unsafe executable mode stops before task or provider',
        'unsafe executable parent authority stops before task or provider',
        'continuous-stream version evidence is bounded (exit 8, calls 1, zero worker dispatch)',
        'continuous-stream probe fails promptly without reading the task',
        'oversized child stream is handshake-bound, prompt, and group-clean',
        'child-stream handshake and process-group cleanup are stable across 20 runs',
        'HUP interrupts the version probe with exit 129, no group, and no artifacts',
        'INT interrupts the version probe with exit 130, no group, and no artifacts',
        'TERM interrupts the version probe with exit 143, no group, and no artifacts',
        'direct selector reports missing agy as unavailable before task read',
        'direct selector reports non-executable agy as unavailable before task read',
        'direct selector sanitizes an agy launch failure before task read',
        'model missing-agy fails before task intake',
        'documented prefixed agy version is accepted',
        'runtime validator accepts a complete direct artifact',
        'runtime validator accepts a complete default artifact',
        'runtime validator rejects default-with-direct-fields.json',
        'runtime validator rejects direct-extra-field.json',
        'runtime validator rejects direct-invalid-sha.json',
        'runtime validator rejects direct-invalid-source.json',
        'runtime validator rejects direct-missing-provenance.json',
        'runtime validator rejects effort-provenance-missing.json',
        'runtime validator rejects missing-binding.json',
        'runtime validator rejects model-transplant.json',
        'runtime validator rejects retired-1.json',
        'runtime validator rejects retired-2.json',
        'runtime validator rejects retired-3.json',
        'runtime validator rejects retired-4.json',
        'runtime validator rejects retired-matrix-field.json',
        'runtime validator rejects tampered-binding.json',
        'runtime validator rejects three-key-direct.json',
        'retired selection 1 rejects launch authorization without rewriting history',
        'retired selection 2 rejects launch authorization without rewriting history',
        'retired selection 3 rejects launch authorization without rewriting history',
        'retired selection 4 rejects launch authorization without rewriting history',
        'failure never starts an automatic fresh retry and preserves frozen selection',
        'root wrapper derives deterministic external state root and rejects project log root in worktree',
        'dispatcher keeps a new job private under umask 022 and a traversable custom log root',
        'dispatcher keeps artifacts private under umask 000 without changing the agy child umask',
        'a missing custom log root is created owner-only under caller umask 000',
        'mode 0777 log root is rejected before prompt staging or agy',
        'mode 0775 log root is rejected before prompt staging or agy',
        'symlink log root is rejected before prompt staging or agy',
        'log-root acceptance rejects a runtime with final-root validation bypassed',
        'supervisor fails closed when a mutation weakens private creation',
        'pre-existing job directory is rejected before invoking agy or touching its sentinel',
        'pre-existing job file is rejected before invoking agy or touching its sentinel',
        'pre-existing job symlink is rejected before invoking agy or touching its target',
        'generic plan dispatches and receives the read-only file-tool preamble',
        '--add-dir outside audited workdir is rejected (exit 64)',
        '--workdir missing operand is controlled (exit 64)',
        '--mode missing operand is controlled (exit 64)',
        '--model missing operand is controlled (exit 64)',
        '--add-dir missing operand is controlled (exit 64)',
        'oversized job produces an envelope (exit 0)',
        'oversized staged prompt preserves task and output contract',
        'oversized job grants only its staged prompt directory',
        'oversized dispatch points agy at the complete staged prompt',
        'oversized staged prompt is read-only during agy execution',
        'oversized staged prompt is private again after agy returns',
        'oversized prompt keeps --print and its value last',
        'supervisor fails closed when a mutation restores staged artifacts publicly',
        'failed oversized child restores staged artifacts before the wrapper exits',
        'HUP restores staged artifacts and preserves signal exit semantics',
        'INT restores staged artifacts and preserves signal exit semantics',
        'TERM restores staged artifacts and preserves signal exit semantics',
        'non-success terminal status fails closed (exit 4)',
        'dispatcher independently rejects schema-invalid output (exit 4)',
    ),
    'dispatcher-b': (
        'raw start requires an explicit transmission mode before queueing or provider launch',
        'partial/promisor clones fail synchronously before queueing or provider launch',
        'plan stages the complete prompt and leaves slash expansion available only for its fixed driver prompt',
        'valid init and step updates renew the idle lease without changing hard limits',
        'silent worker terminates at the independent idle deadline',
        'malformed events never renew the idle lease',
        'oversized stream events fail closed and never renew the idle lease',
        'worker rejects exit-zero empty provider output',
        'advanced controls resolve only a job-bound workflow log root without environment',
        'verification-copy and restart accept bound --state before eligibility checks',
        'successful structured output ignores stderr diagnostics and preserves UTF-8',
        'unproven authentication_text remains unclassified without free-form guessing',
        'unproven provider_text remains unclassified without free-form guessing',
        'unproven unknown_text remains unclassified without free-form guessing',
        'native nested-sandbox denial is actionable and interrupted candidate-free budget is explained',
        'command diagnostic version is bounded text without a semantic-version gate',
        'quota prose without report fails across ready without retry',
        'quota prose without report fails across quota113 without retry',
        'quota prose without report fails across drift999 without retry',
        'fresh heartbeats cannot exceed hard deadline and process-group descendants are reaped',
        'foreground TERM is forwarded through the controller and leaves no late process-group side effect',
        'status/wait/result formats preserve JSON and expose three sanitized driver-owned text lines',
        'fast controller ownership handoff is stable without a competing parent PID transition',
        'stale/over-max extend is rejected; fresh state-SHA extend changes only the local hard deadline',
        'max runtime remains an absolute cap even after an approved hard-deadline extension',
        'concurrent cancel is state-SHA-gated, reaps the local process group, and does not claim remote cancellation',
        'queued cancel is consumed by inherited controller ownership without starting agy',
        'state snapshot serializes an approved atomic replacement without weakening identity checks',
        'orphaned dispatch is preserve-only and cannot resume or restart a provider call',
        'resume text succeeds with the exact private conversation and no private output',
        'restart is explicit fresh origin and remains distinct from resume',
        'provider check-id regex remains RE2-compatible and driver validation stays strict',
        'unavailable resume preserves failure state and starts no probes or provider',
        'resume checks only active flags with fresh probes and preserves prior evidence',
        'continue checks only active flags with fresh probes and preserves prior evidence',
        'scoped-repair checks only active flags with fresh probes and preserves prior evidence',
        'effort checks only active flags with fresh probes and preserves prior evidence',
        'no-effort checks only active flags with fresh probes and preserves prior evidence',
        'restart checks only active flags with fresh probes and preserves prior evidence',
        'project workflow exposes pending Codex-owned verification without changing resume semantics',
        'scoped deletion remains result/finalize-bound and requires fresh approval before continuation',
        'project continuation text keeps trigger evidence while the replacement candidate resets stored evidence',
        'project continuation preserves initial-only whole-worktree approval after provider-created paths',
        'project finalization text is three-line, driver-owned, and invokes no provider',
        'project continuation is same-conversation, feedback-private, and bounded to initial plus four repairs',
        'project finalization is a SHA-bound no-provider Codex quality decision',
        'project workflow rejects Git-admin aliases while allowing ordinary contained links',
        'project workflow requires a linked-worktree Git marker file',
        'project shell preflight rejects every nested Git marker before provider setup',
        'project shell preflight rejects casefold nested .GIT aliases before provider setup',
        'project workflow binds the linked-worktree marker before and after provider execution',
        'project post-provider boundary rejects a sparse oversized marker without accepting a result',
        'project continuation rejects between-cycle marker drift without provider call or state replacement',
        'project continuation rejects a 4097-byte marker before state replacement or provider call',
        'project continuation rejects a sparse oversized marker before state replacement or provider call',
        'orphaned project state is preserve-only across continuation, finalization, and result surfaces',
        'verification staging rolls back exactly on injected state-write failure and retries cleanly',
        'project boundary accepts the exact entry cap and rejects one entry over it',
        'concurrent continue and finalize on one approved SHA publish exactly one winner',
        'cancelled repair can partially finalize and return the prior bound success',
        'control state refuses symlink replacement rather than following a swapped state file',
        'folder-only core resolves and completes synthetic ordinary workflow verification',
        'installer accepts replacement metacharacters in clone path (exit 0)',
        'installer copies the canonical bundle and records the exact clone path',
    ),
    'dispatcher-remediation-a': (
        'controller pure monitor decisions preserve lazy limit precedence',
        'controller pure wait uses each clock and the zero floor',
        'controller pure terminal policy preserves candidate facts',
        'controller signals and context ownership stay isolated',
        'ERROR plus valid provider report is preserved and normalized',
        'outer status accepts only exact provider tokens',
        'SUCCESS missing a critical canonical value is not a candidate',
        'provider extra field is rejected',
        'framing and structured-output failures remain distinct',
        'structured output preserves short writes and rejects no progress',
        'private dispatcher reads reject FIFO and bounded content identity drift',
        'direct preview and worktree entries suppress repository bytecode',
        'only commands and tests arrays normalize',
        'provider schema permits only bounded command/test ergonomics',
        'wrong type NaN invalid UTF-8 and oversized reports fail closed',
        'text status is private and never promotes worker completion prose',
        'control formats and stale reruns are private copyable and pre-provider',
        'stale approval guidance includes only required placeholders and invents no values',
        'private self-verification manifest is exact and changes the scoped repair grant',
        'new current legacy attempts expose a strict nonrepair lifecycle',
        'worktree reconciliation hashes outward symlinks and rejects nested Git administration',
        'controller rejects outward symlinks before provider launch for every workflow while allowing internal links',
        'worktree snapshot never runs repo programs or mutates normal and linked indexes',
        'worktree snapshot compares staged state to HEAD and rejects unsupported Git states',
        'worktree snapshot declines promisor blobs without invoking repo ext helper',
        'snapshot and shared Git readers reject races floods and pipe-holding descendants',
        'worktree snapshot rejects index file post-read and Git target drift',
        'worktree snapshot uses a marker-only preflight plus two bounded manifests and documents post-final-entry mutation as residual',
        'worktree snapshot closes manifest scandir descriptors on success and failure',
        'worktree snapshot fails closed when the recursive manifest exceeds the interpreter depth',
        'tracked untracked ignored deleted symlink and mode changes alter the bounded digest',
        'snapshot accepts staged and unstaged nested deletions but rejects missing-parent replacement races',
        'semantic snapshots survive driver cache cleanup and ordinary Git index refresh',
        'schema and candidate worktree bindings reject drift',
        'baseline/candidate snapshots and unavailable SUCCESS ERROR CANCELLED terminal bindings fail closed',
        'controller maps ERROR plus valid report to failed unreviewed exit 25',
        'version independent terminal policy and denial deadline collision preserve candidate and block reuse',
        'reviewed exact-version denied_actions presence blocks provider reuse but preserves a valid SUCCESS candidate',
        'exact 1.2.6 refusal canary yields permission_required without candidate and fails unknown shapes closed',
        '1.3.0 model effort conflict with empty conversation fails classified without candidate',
        'model selection rejection requires whole strict evidence and preserves every near miss',
        'provisional selection result keeps deadlines control output caps and child cleanup',
        'selection diagnostics and deferred framing preserve unconditional project boundary',
        'static agy_error serializer metadata parsed offline with closed schema and retains no live exit3 evidence',
        'exact reviewed 1.2.2 print-timeout stderr marks provider failure while preserving a valid partial candidate',
        'invalid outer status cannot become success while CANCELED report is preserved',
        'non-finite JSON and newline-incomplete terminal framing are rejected',
        'repair failure preserves exact candidate for result finalize and budgeted continue',
        'local terminal side paths project coherent JSON and preserve queued candidates',
        'explore and task allow two cycles while project allows five and legacy one',
        'stale SHA wrong candidate malformed v2 and worktree drift stop before provider',
        'verification v2 does not infer task driver review',
        'v1 cannot verify and explore requires complete gap-free coverage',
        'deeply nested event terminal and selection JSON fail closed',
        'critical help uses only option and enum structure, never provider prose',
        'exact 1.2.11 help and launch reprobe retain required options',
        'conditional capabilities follow operation and frozen caller effort',
        'current selection schema rejects records missing the current runtime binding',
        'completed success and nonzero version/help probes reap pipe-closing live descendants',
        'successful version/help probe accepts leader output before descendant-held pipe EOF',
        'selection validate and executable-verify actions reject each other in either order',
    ),
    'dispatcher-remediation-b': (
        'direct selections bind public startup, launch replacement windows, and provider runtime boundaries',
        'source guard rejects untracked changes in whole attempts',
        'source guard rejects untracked changes in scoped attempts',
        'source guard rejects tracked changes in whole attempts',
        'source guard rejects tracked changes in scoped attempts',
        'source guard rejects staging changes in whole attempts',
        'source guard rejects staging changes in scoped attempts',
        'source guard rejects head changes in whole attempts',
        'source guard rejects head changes in scoped attempts',
        'source guard budget exhaustion blocks provider spawn with actionable status',
        'source guard preserves stage workdir dirty-source and ignored-output controls',
        'source guard helper skips a verified main workdir without changing write behavior',
        'source guard defers no-candidate failures cancellation and interrupt until relaunch',
        'source guard detects an independent owner edit during native containment',
        'source guard preserves the job baseline across repairs and clears inherited candidate authority',
        'source guard checks exception reaps and blocks orphan or transplanted baselines',
        'source guard uses fixed hardened Git rejects effective filters and never follows content parents',
        'source guard bounds metadata and listings without rereading clean large tracked bytes',
        'source guard schema veto rejects forged authority and old state without recovery writes',
        'initial resume restart and continue rebind queued worktree before provider Popen',
        'empty directory create remove and metadata changes bind snapshot digest and entries',
        'candidate drift names mode and verifier-cache paths without accepting edits',
        'snapshot and root binding reject unsafe or repository-controlled Git before execution',
        'partial finalization returns current ERROR/CANCELED candidate and rejects A verification or B tamper',
        'current records and public status retire unsupported quota retry contract',
        'Current repository-controlled Git fails closed before status result continue or finalize',
        'outward symlink keeps candidate lifecycle status and commands in parity',
        'internal Git-alias symlink is rejected by lifecycle candidate guards',
        'stale ignored pyc makes direct driver imports unusable while a bound verification copy preserves finalization',
    ),
    'dispatcher-remediation-c': (
        'verification copy rebases all contained symlinks before driver writes',
        'verification copy retains readonly nested directory mode and candidate binding',
        'verification copy rejects unsafe links and source drift without a usable destination',
        'public verification-copy wrapper preserves output privacy and maps runtime failures',
        'current stable Git boundary permits provider content while rejecting root and Git authority replacement',
        'core.worktree redirection fails closed for snapshots and candidate action parity',
        'bounded Git reads reject caller-supplied context overrides',
        'snapshot pins Git context while retaining initial/final root checks',
        'paired snapshot metadata preserves framing budgets and filesystem binding order',
        'whole-worktree two-cycle prompt preserves created change against immutable base',
        'retired and malformed dispatch schemas reject every entrypoint without effects',
        'removed migration flags fail before artifacts while option-looking values retain parsing',
        'retired feature flags reject before effects and preserve prompt values',
        'current commands reject retired feature authority and preserve prompt text',
        'current commands reject unapproved option --dangerously-skip-permissions',
        'current commands reject unapproved option --log-file',
        'current commands reject unapproved option --continue',
        'current commands reject unapproved option -c',
        'current commands reject unapproved option --prompt-interactive',
        'current commands reject unapproved option -i',
        'actual dispatch launch authority rejects auto mode split and equals',
        'linked preview SHA authorizes exact V11 initial and prelaunch scope binding',
        'mid-write materialization failure removes the partial private stage',
        'pre-chmod failure removes only the bound own-created stage',
        'pre-lstat cleanup is exact and preserves a replacement path',
        'cleanup failure is visible and fail closed',
        'narrow stage rejects unselected writes and reconciles an authorized replacement',
        'narrow launch stays Gitless while opt-in repair binds descendants and rejects external drift',
        'optional provider init cwd accepts only the exact canonical launch directory',
        'scoped files_changed must declare each reconciled mutation exactly once',
        'scoped absolute stage declarations reconcile only exact canonical stage children',
        'scoped file declarations retain authorized nested directory reconciliation',
        'scoped no-net stage writes accept an empty files_changed declaration',
        'narrow reconciliation rejects unauthorized paths symlinks and concurrent source drift',
        'narrow preflight symlink stage-race and copy-drift failures never launch provider',
        'reconciliation preparation failures recover owned backups and permit corrected retry',
        'preparation checkpoints recover only durably bound identities',
        'reconciliation backup and preparation FIFO swaps reject without blocking',
        'rollback accepts genuinely absent parents and preserves existing directory modes',
        'failed reconciliation temps are removed only while their identity remains owned',
        'later failure recreates deleted nested empty directories before clearing the ledger',
        'interrupted empty-directory reconciliation recovers durably and idempotently',
        'standard snapshots remain supported while current launch requires a linked worktree',
        'nested .git file directory symlink and special entries fail before snapshot, boundary, actions, or provider',
        'casefold nested .GIT aliases fail before Git, project, result, continue, finalize, or provider actions',
        'resolve-undo state fails closed for current snapshots and result continue finalize parity',
        'malformed duplicate and racing resolve-undo output fails closed',
        'resolve-undo observation immediately before launch fails closed with bounded reason and zero provider calls',
        'malformed debug stat cache fails closed while numeric zero-flag records preserve candidate parity',
        'intent-to-add fails closed for snapshots and result continue finalize parity',
        'relocated current candidate remains result-finalize only without provider mutation',
        'independent non-empty per-path reference preserves the current semantic snapshot digest',
        'current states persist the independently checked semantic-v1 snapshot algorithm',
        'safe agy executable rejects setuid and setgid metadata before any probe',
        'regular-to-FIFO race fails promptly before task provider state or selection',
        'bound executable reader accepts regular limits and rejects nonregular or blocking fallbacks',
        'available candidate actions rebind live artifacts and disappear during an active repair',
        'stale recognized candidates project bound availability and private binding failure',
        'resume and extend action predicates reject missing conversation and sub-second headroom',
        'continue accepts a bounded Codex advisory repair intent',
        'finalize records the bounded Codex declaration without reinterpreting check counts',
        'verified finalization requires workflow evidence without rewriting other Codex dispositions',
        'available recovery actions use the same bound command/schema/root/selection guard as mutation',
        'stage provider-schema and root drift have status-command recovery parity',
        'task explore and legacy same-path repository replacement hides recovery before mutation',
        'selection tamper hides result continue and finalize and leaves candidate state untouched',
        'text status distinguishes unreviewed, finalized, and non-result sanitized snapshots',
        'public candidate digest follows only the bound result and result text leaves disposition to Codex',
        'published Verification v2 examples execute from one public snapshot and bind the current candidate',
        'current state validates terminal-status schema, framing privacy, invalid unknown, and action parity',
    ),
}

# The sole fixture-generated label domain in the shell suite is finite. Parse
# this reference and the actual heredoc with the same interpreter; AST equality
# rejects a changed producer without executing fixture code or hashing source.
SELECTION_ARTIFACT_HEADER = 'python3 -B - "$VALID_DIRECT_RECORD" "$VALID_DEFAULT_RECORD" "$ARTIFACT_CASES" <<\'PY\''
SELECTION_ARTIFACT_PRODUCER = r'''
import copy
import json
from pathlib import Path
import sys

direct = json.load(open(sys.argv[1], encoding="utf-8"))
default = json.load(open(sys.argv[2], encoding="utf-8"))
root = Path(sys.argv[3])
assert direct["schema_version"] == 5
cases = {
    "three-key-direct": {"schema_version": 5, "kind": "agy-worker-selection", "selection_mode": "exact-model"},
    "default-with-direct-fields": {**default, "user_model": "untrusted"},
    "direct-missing-provenance": {key: value for key, value in direct.items() if key != "user_model_source"},
    "direct-invalid-source": {**direct, "user_model_source": "worker"},
    "direct-invalid-sha": {**direct, "probed_executable": {**direct["probed_executable"], "content_sha256": "z" * 64}},
    "direct-extra-field": {**direct, "applied": False},
    "missing-binding": {key: value for key, value in direct.items() if key != "probed_executable"},
    "tampered-binding": {**direct, "probed_executable": {**direct["probed_executable"], "target_lstat": {**direct["probed_executable"]["target_lstat"], "inode": 0}}},
    "model-transplant": {**direct, "resolved_agy_model": "other-model"},
    "effort-provenance-missing": {key: value for key, value in direct.items() if key != "user_effort_source"},
    "retired-matrix-field": {**direct, "matrix_sha256": "a" * 64},
}
for schema in (1, 2, 3, 4):
    cases[f"retired-{schema}"] = {**direct, "schema_version": schema}
for name, value in cases.items():
    (root / f"{name}.json").write_text(json.dumps(value) + "\n", encoding="utf-8")
'''

SHELL_DECLARATIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    'tests/test-agy-worker.sh': (
        ('common', 'function', 'tmp_identity'),
        ('common', 'function', 'ok'),
        ('common', 'function', 'bad'),
        ('common', 'function', 'expect_exit'),
        ('common', 'assertion', 'if [[ "$got" == "$want" ]]; then ok "$name (exit $got)"; else bad "$name (exit $got, wanted $want)"; fi'),
        ('common', 'function', 'expect_print_last'),
        ('common', 'assertion', 'then ok "$name"; else bad "$name"; fi'),
        ('common', 'function', 'private_tree_is_private'),
        ('common', 'function', 'mode_is'),
        ('common', 'function', 'log_root_is_acceptable'),
        ('common', 'function', 'process_group_is_gone'),
        ('common', 'function', 'wait_probe_cleanup'),
        ('common', 'loop', 'for (( wait_index=0; wait_index<100; wait_index++ )); do'),
        ('common', 'function', 'whole_worktree_manifest_sha'),
        ('dispatcher-a', 'assertion', 'ok "preview is stable, content-free, provider-free, bounded, and fail-closed"'),
        ('dispatcher-a', 'assertion', 'bad "preview is stable, content-free, provider-free, bounded, and fail-closed"'),
        ('dispatcher-a', 'assertion', 'ok "provider scope parser validates schema, paths, and write-covered-by-read invariants"'),
        ('dispatcher-a', 'assertion', 'bad "provider scope parser validates schema, paths, and write-covered-by-read invariants"'),
        ('dispatcher-a', 'assertion', 'ok "provider scope reads and verification-copy immediate-parent boundary are strict and explicit"'),
        ('dispatcher-a', 'assertion', 'bad "provider scope reads and verification-copy immediate-parent boundary are strict and explicit"'),
        ('dispatcher-a', 'loop', "for help_command in '' run start status wait result extend cancel resume restart continue self-verify finalize; do"),
        ('dispatcher-a', 'assertion', 'ok "top-level help distinguishes worker and lifecycle stdout; invalid usage is sanitized"'),
        ('dispatcher-a', 'assertion', 'bad "help stdout contract or sanitized invalid usage"'),
        ('common', 'function', 'run_worker'),
        ('common', 'loop', 'for fake_provider_env_name in          FAKE_AGY_STATUS FAKE_ARGV_FILE FAKE_BAD_ENVELOPE FAKE_CALLED_FILE          FAKE_CALLS_FILE FAKE_CHILD_PID_FILE FAKE_DIRS_FILE FAKE_DISPATCH_COUNT_FILE          FAKE_DISPATCH_MODE FAKE_ENV_OBSERVED_FILE FAKE_HOME_OBSERVED_FILE FAKE_ERROR_LINE          FAKE_DELETE_FROM_BOUND_ROOT FAKE_EDIT_CONTENT FAKE_EDIT_FROM_BOUND_ROOT          FAKE_EXECUTABLE_SYMLINK_TARGET          FAKE_EXIT_CODE FAKE_FAIL_FIRST FAKE_HEARTBEAT_AFTER_FIRST_READY          FAKE_HEARTBEAT_AFTER_FIRST_RELEASE FAKE_HEARTBEAT_BARRIER_READY          FAKE_HEARTBEAT_BARRIER_RELEASE FAKE_HEARTBEAT_COUNT FAKE_HEARTBEAT_DELAY          FAKE_HELP_MODE FAKE_MODEL_FILE FAKE_MUTATE_EXECUTABLE          FAKE_MUTATE_EXECUTABLE_MODE FAKE_MUTATE_EXECUTABLE_PARENT          FAKE_MUTATE_EXECUTABLE_SAME_LENGTH          FAKE_MUTATE_PROJECT_MARKER FAKE_MUTATION_MARKER FAKE_PROBE_PARENT_PID_FILE          FAKE_PROBE_PGID_FILE FAKE_PROBE_READY_FILE FAKE_PROBE_RELEASE_FILE          FAKE_PROMPT_FILE FAKE_QUOTA_ERROR FAKE_REPLACE_EXECUTABLE_SYMLINK          FAKE_PROVIDER_CREATE_PATH          FAKE_SIDE_EFFECT_FILE FAKE_SIGNAL_PARENT FAKE_SPARSE_PROJECT_MARKER          FAKE_STAGE_RESULT_FILE FAKE_TRY_STAGE_WRITE FAKE_UTF8_SUMMARY          FAKE_MUTATE_WORKTREE_PATH          FAKE_VERSION_MODE FAKE_WARNING_LINE FAKE_WORKER_CALLS_FILE          FAKE_WORKER_VERIFIED; do'),
        ('common', 'loop', 'for option in "$@"; do'),
        ('common', 'function', 'literal_smoke_setup'),
        ('dispatcher-a', 'assertion', 'ok "help states workflow-specific cycle limits"'),
        ('dispatcher-a', 'assertion', 'bad "help workflow-specific cycle limits"'),
        ('dispatcher-a', 'assertion', 'ok "raw dispatch requires an explicit transmission mode before provider or job artifacts"'),
        ('dispatcher-a', 'assertion', 'bad "raw dispatch missing transmission mode boundary"'),
        ('dispatcher-a', 'assertion', 'ok "raw whole-worktree approval is exact and stale-safe before provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "raw whole-worktree stale approval boundary"'),
        ('dispatcher-a', 'assertion', 'ok "post-preview whole content binding failure is bounded and publishes no provider command"'),
        ('dispatcher-a', 'assertion', 'bad "post-preview whole content binding failure boundary"'),
        ('dispatcher-a', 'assertion', 'expect_exit "literal model produces an envelope" 0 "$rc"'),
        ('dispatcher-a', 'assertion', 'ok "literal model is forwarded after CLI parsing and keeps the ordinary writable preamble"'),
        ('dispatcher-a', 'assertion', 'bad "literal model forwarding or ordinary writable preamble"'),
        ('dispatcher-a', 'assertion', 'expect_print_last "small prompt keeps --print and its value last" "$TMP/literal-smoke.argv"'),
        ('dispatcher-a', 'assertion', 'ok "direct dispatcher rejects a fresh legacy broad command before provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "direct dispatcher legacy broad initial boundary"'),
        ('dispatcher-a', 'syntax', 'CORE_TRANSMISSION_SHA="$('),
        ('dispatcher-a', 'syntax', ')"'),
        ('dispatcher-a', 'assertion', 'ok "scoped repair opt-in writes one immutable command authority"'),
        ('dispatcher-a', 'assertion', 'bad "scoped repair opt-in command authority"'),
        ('dispatcher-a', 'loop', 'for repair_case in no-scope workflow cycles; do'),
        ('dispatcher-a', 'assertion', 'ok "scoped repair rejects missing scope and unsupported workflow or cycle bounds"'),
        ('dispatcher-a', 'assertion', 'bad "scoped repair public constraints"'),
        ('dispatcher-a', 'loop', 'for preamble_workflow in explore task project; do'),
        ('dispatcher-a', 'loop', 'for preamble_mode in whole scoped; do'),
        ('dispatcher-a', 'assertion', 'ok "$preamble_workflow/$preamble_mode provider-bound preamble and existing contract order"'),
        ('dispatcher-a', 'assertion', 'bad "$preamble_workflow/$preamble_mode provider-bound preamble and existing contract order"'),
        ('dispatcher-a', 'assertion', 'ok "non-interactive preamble reaches all six workflow/transmission combinations"'),
        ('dispatcher-a', 'assertion', 'bad "non-interactive preamble reaches all six workflow/transmission combinations"'),
        ('dispatcher-a', 'assertion', 'ok "self-verification CLI copies and binds the private manifest with an ID-only prompt"'),
        ('dispatcher-a', 'assertion', 'bad "self-verification CLI manifest copy, command binding, or prompt boundary"'),
        ('dispatcher-a', 'loop', 'for unsafe_case in mode symlink hardlink; do'),
        ('dispatcher-a', 'assertion', 'ok "self-verification CLI rejects non-private, symlinked, and hard-linked manifests before provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "self-verification CLI unsafe manifest boundaries"'),
        ('dispatcher-a', 'assertion', 'ok "self-verification CLI rejects explore before provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "self-verification CLI workflow boundary"'),
        ('dispatcher-a', 'assertion', 'ok "stored self-verification feedback is explicit, continue-only, and single-use"'),
        ('dispatcher-a', 'assertion', 'bad "stored self-verification continue routing boundary"'),
        ('dispatcher-a', 'syntax', 'NORMAL_ROOT_TRANSMISSION_SHA="$('),
        ('dispatcher-a', 'syntax', ')"'),
        ('dispatcher-a', 'syntax', 'NORMAL_ROOT_SESSION_TRANSMISSION_SHA="$('),
        ('dispatcher-a', 'syntax', ')"'),
        ('dispatcher-a', 'assertion', 'ok "scoped launch approval is bound to provider isolation"'),
        ('dispatcher-a', 'assertion', 'bad "scoped launch approval provider-isolation binding"'),
        ('dispatcher-a', 'assertion', 'ok "normal scoped dispatch pins the final stage root in its file-tool prompt"'),
        ('dispatcher-a', 'assertion', 'bad "normal scoped file-tool root binding"'),
        ('dispatcher-a', 'assertion', 'ok "normal whole-worktree dispatch pins its approved root in the file-tool prompt"'),
        ('dispatcher-a', 'assertion', 'bad "normal whole-worktree file-tool root binding"'),
        ('dispatcher-a', 'assertion', 'ok "whole-worktree drift is rejected by the supervisor before provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "whole-worktree pre-provider drift boundary"'),
        ('dispatcher-a', 'assertion', 'ok "ambient secret is absent from agy probes and provider launch"'),
        ('dispatcher-a', 'assertion', 'bad "ambient secret is absent from agy probes and provider launch"'),
        ('dispatcher-a', 'assertion', 'ok "explicit provider environment name reaches agy children"'),
        ('dispatcher-a', 'assertion', 'bad "explicit provider environment name reaches agy children"'),
        ('dispatcher-a', 'assertion', 'expect_exit "runtime-injection provider environment name is rejected" 64 "$?"'),
        ('dispatcher-a', 'loop', 'for unsafe_provider_name in GIT_CONFIG_COUNT GIT_DIR AGY_WORKER_SCHEMA; do'),
        ('dispatcher-a', 'assertion', 'ok "unsafe $unsafe_provider_name rejects before selector or job allocation"'),
        ('dispatcher-a', 'assertion', 'else bad "unsafe $unsafe_provider_name early usage rejection"; fi'),
        ('dispatcher-a', 'syntax', 'mktemp_assignment="$(sed -n \'/^TMP="$(mktemp -d /p\' "$HERE/test-agy-worker.sh")"'),
        ('dispatcher-a', 'assertion', 'ok "failed mktemp exits before dispatcher fixture setup"'),
        ('dispatcher-a', 'assertion', 'else bad "failed mktemp must not reach dispatcher fixture setup"; fi'),
        ('dispatcher-a', 'assertion', 'ok "raw flash-high stays exact pass-through with no effort argument"'),
        ('dispatcher-a', 'assertion', 'bad "raw flash-high stays exact pass-through with no effort argument"'),
        ('dispatcher-a', 'assertion', 'then ok "bound agy default preserves executable checks and emits no model or effort"; else bad "bound agy default"; fi'),
        ('dispatcher-a', 'assertion', 'ok "literal model routing stays version-independent while version observation remains non-gating"'),
        ('dispatcher-a', 'assertion', 'bad "literal model version-independent contract (exit $rc)"'),
        ('dispatcher-a', 'function', 'assert_direct_result'),
        ('dispatcher-a', 'assertion', 'then ok "$name"; else bad "$name"; fi'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "complete structural probe proceeds without version approval"          exact-version-unseen-help gemini-3.6-flash gemini-3.6-flash high cli cli 5'),
        ('dispatcher-a', 'assertion', 'bad "exact-version structural probe boundary (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "option prose does not override the structural capability check"          help-option-negation gemini-3.6-flash gemini-3.6-flash high cli cli 5'),
        ('dispatcher-a', 'assertion', 'bad "exact-version option prose structural boundary (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'then ok "direct selector accepts diagnostic version and exposes no executable path"'),
        ('dispatcher-a', 'assertion', 'else bad "direct selector diagnostic/executable binding"; fi'),
        ('dispatcher-a', 'assertion', 'ok "only the documented macOS /var alias has a normalized executable path digest"'),
        ('dispatcher-a', 'assertion', 'bad "macOS executable path alias normalization boundary"'),
        ('dispatcher-a', 'assertion', 'ok "literal caller values and transport boundaries without a model catalog"'),
        ('dispatcher-a', 'assertion', 'bad "literal caller values and transport boundaries without a model catalog"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative pair gemini-3.7-flash/high accepts cli-cli"          "direct-pair-rep-cli-cli" "gemini-3.7-flash" "gemini-3.7-flash" "high"          "cli" "cli"'),
        ('dispatcher-a', 'assertion', 'bad "representative pair gemini-3.7-flash/high accepts cli-cli"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative pair gemini-3.6-flash/medium accepts cli-env"          "direct-pair-rep-cli-env" "gemini-3.6-flash" "gemini-3.6-flash" "medium"          "cli" "environment"'),
        ('dispatcher-a', 'assertion', 'bad "representative pair gemini-3.6-flash/medium accepts cli-env"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative pair gemini-3.8-flash/low accepts env-cli"          "direct-pair-rep-env-cli" "gemini-3.8-flash" "gemini-3.8-flash" "low"          "environment" "cli"'),
        ('dispatcher-a', 'assertion', 'bad "representative pair gemini-3.8-flash/low accepts env-cli"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative pair gemini-3.1-pro/high accepts env-env"          "direct-pair-rep-env-env" "gemini-3.1-pro" "gemini-3.1-pro" "high"          "environment" "environment"'),
        ('dispatcher-a', 'assertion', 'bad "representative pair gemini-3.1-pro/high accepts env-env"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative exact model gemini-3.7-flash-high accepts cli"          "direct-exact-rep-cli" "gemini-3.7-flash-high" "gemini-3.7-flash-high" ""          "cli" ""'),
        ('dispatcher-a', 'assertion', 'bad "representative exact model gemini-3.7-flash-high accepts cli"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative exact model gemini-3.6-flash-low accepts env"          "direct-exact-rep-env" "gemini-3.6-flash-low" "gemini-3.6-flash-low" ""          "environment" ""'),
        ('dispatcher-a', 'assertion', 'bad "representative exact model gemini-3.6-flash-low accepts env"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative fixed model claude-sonnet-4-6 accepts cli"          "direct-fixed-rep-cli" "claude-sonnet-4-6" "claude-sonnet-4-6" ""          "cli" ""'),
        ('dispatcher-a', 'assertion', 'bad "representative fixed model claude-sonnet-4-6 accepts cli"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "representative fixed model gpt-oss-120b-medium accepts env"          "direct-fixed-rep-env" "gpt-oss-120b-medium" "gpt-oss-120b-medium" ""          "environment" ""'),
        ('dispatcher-a', 'assertion', 'bad "representative fixed model gpt-oss-120b-medium accepts env"'),
        ('dispatcher-a', 'function', 'expect_selector_reject'),
        ('dispatcher-a', 'assertion', 'ok "$name (exit 64, zero agy calls)"'),
        ('dispatcher-a', 'assertion', 'bad "$name (exit $got, wanted 64 before task read and agy)"'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "repeated model is ambiguous" repeated-model      --model gemini-3.6-flash --model gemini-3.6-flash --effort high'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "repeated effort is ambiguous" repeated-effort      --model gemini-3.6-flash --effort high --effort high'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "removed tier is unknown" repeated-tier --tier bulk --tier bulk'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "retired literal alias rejects before task or provider" retired-literal      --literal-model future-model-1.2'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "overlong model is rejected" model-too-long --model "$model_too_long"'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "empty CLI model is rejected" empty-cli-model --model \'\''),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "empty CLI effort is rejected" empty-cli-effort      --model gemini-3.6-flash --effort \'\''),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "effort without model is rejected" effort-without-model --effort high'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "padded direct model is rejected" padded-direct      --model \' gemini-3.6-flash\' --effort high'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "invented thinking-level flag is rejected" thinking-flag      --model gemini-3.6-flash --thinking-level high'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "retired disposition flag is actionable rejection" retired-disposition      --model future-model --compatibility-disposition proceed'),
        ('dispatcher-a', 'assertion', 'expect_selector_reject "retired help approval flag is actionable rejection" retired-help-approval      --model future-model --approve-help-sha "$(printf \'a%.0s\' {1..64})"'),
        ('dispatcher-a', 'function', 'assert_env_reject'),
        ('dispatcher-a', 'assertion', 'ok "$name (exit 64, zero agy calls)"'),
        ('dispatcher-a', 'assertion', 'bad "$name (exit $got, wanted 64 before task read and agy)"'),
        ('dispatcher-a', 'assertion', 'assert_env_reject "same model in CLI and environment conflicts" same-model-conflict "$?"'),
        ('dispatcher-a', 'assertion', 'assert_env_reject "same effort in CLI and environment conflicts" same-effort-conflict "$?"'),
        ('dispatcher-a', 'assertion', 'assert_env_reject "retired environment is rejected" same-tier-conflict "$?"'),
        ('dispatcher-a', 'assertion', 'assert_env_reject "explicit empty environment model is rejected" empty-env-model "$?"'),
        ('dispatcher-a', 'assertion', 'assert_env_reject "explicit empty environment effort is rejected" empty-env-effort "$?"'),
        ('dispatcher-a', 'function', 'selector_fixture_has_no_bytecode'),
        ('dispatcher-a', 'function', 'make_selector_fixture'),
        ('dispatcher-a', 'assertion', 'ok "selector fixtures exclude ambient bytecode but detect fixture-generated bytecode"'),
        ('dispatcher-a', 'assertion', 'bad "selector fixture bytecode baseline or generated-bytecode detection"'),
        ('dispatcher-a', 'function', 'expect_compat_reject'),
        ('dispatcher-a', 'assertion', 'ok "$name (exit $got, calls $calls, zero worker dispatch)"'),
        ('dispatcher-a', 'assertion', 'bad "$name (exit $got/calls $calls, wanted $want/$calls_want and zero worker)"'),
        ('dispatcher-a', 'loop', 'for missing in add-dir disable-slash-commands json-schema mode model output-format print print-timeout; do'),
        ('dispatcher-a', 'loop', 'for route in default direct; do'),
        ('dispatcher-a', 'assertion', 'ok "$route missing --$missing rejects before provider, job and lock mutation"'),
        ('dispatcher-a', 'assertion', 'else bad "$route missing --$missing capability boundary (exit $rc)"; fi'),
        ('dispatcher-a', 'loop', 'for missing in sandbox conversation effort; do'),
        ('dispatcher-a', 'loop', 'for route in default model; do'),
        ('dispatcher-a', 'assertion', 'then ok "$route session explore ignores unused --$missing with fresh launch probes"'),
        ('dispatcher-a', 'assertion', 'else bad "$route session explore unused --$missing (exit $rc)"; fi'),
        ('dispatcher-a', 'loop', 'for effort_source in cli environment; do'),
        ('dispatcher-a', 'assertion', 'ok "$effort_source effort requires its capability before task consumption"'),
        ('dispatcher-a', 'assertion', 'else bad "$effort_source effort capability boundary (exit $rc)"; fi'),
        ('dispatcher-a', 'assertion', 'ok "native requires sandbox capability before task consumption or containment"'),
        ('dispatcher-a', 'assertion', 'else bad "native capability boundary (exit $rc)"; fi'),
        ('dispatcher-a', 'loop', 'for route in default direct; do'),
        ('dispatcher-a', 'assertion', 'then ok "non-semver diagnostic permits $route launch with literal caller choices"'),
        ('dispatcher-a', 'assertion', 'else bad "non-semver diagnostic $route launch boundary"; fi'),
        ('dispatcher-a', 'loop', 'for action in base record; do'),
        ('dispatcher-a', 'assertion', 'ok "standalone $action probe uses its own effort context"'),
        ('dispatcher-a', 'assertion', 'else bad "standalone $action effort context (exit $rc)"; fi'),
        ('dispatcher-a', 'assertion', 'expect_exit "standalone $action rejects selection-only isolation context" 64 "$?"'),
        ('dispatcher-a', 'loop', 'for version_mode in fail empty oversize hang; do'),
        ('dispatcher-a', 'assertion', 'expect_compat_reject "$version_mode version evidence is unavailable"          "$VERSION_FIXTURE" "version-$version_mode" 8 "$version_mode" 1'),
        ('dispatcher-a', 'loop', 'for help_mode in missing duplicate malformed utf8 nul oversize fail hang; do'),
        ('dispatcher-a', 'assertion', 'ok "$help_mode help preflight is pre-provider and task-unread"'),
        ('dispatcher-a', 'assertion', 'bad "$help_mode help preflight (exit $rc/calls $help_calls, wanted $help_expected/2)"'),
        ('dispatcher-a', 'assertion', 'ok "executable binding drift stops before task read or provider dispatch"'),
        ('dispatcher-a', 'assertion', 'bad "executable binding drift pre-provider boundary"'),
        ('dispatcher-a', 'assertion', 'ok "same-length restored-mtime executable mutation stops before task or provider"'),
        ('dispatcher-a', 'assertion', 'bad "same-length restored-mtime executable mutation boundary"'),
        ('dispatcher-a', 'assertion', 'ok "atomic same-target executable symlink replacement stops before task or provider"'),
        ('dispatcher-a', 'assertion', 'bad "atomic same-target executable symlink replacement boundary"'),
        ('dispatcher-a', 'assertion', 'ok "different executable symlink target stops before task or provider"'),
        ('dispatcher-a', 'assertion', 'bad "different executable symlink target boundary"'),
        ('dispatcher-a', 'assertion', 'ok "unsafe executable mode stops before task or provider"'),
        ('dispatcher-a', 'assertion', 'bad "unsafe executable mode boundary"'),
        ('dispatcher-a', 'assertion', 'ok "unsafe executable parent authority stops before task or provider"'),
        ('dispatcher-a', 'assertion', 'bad "unsafe executable parent authority boundary"'),
        ('dispatcher-a', 'assertion', 'expect_compat_reject "continuous-stream version evidence is bounded"      "$VERSION_FIXTURE" version-stream 8 stream 1'),
        ('dispatcher-a', 'assertion', 'ok "continuous-stream probe fails promptly without reading the task"'),
        ('dispatcher-a', 'assertion', 'bad "continuous-stream probe exceeded the byte-bound deadline (${stream_elapsed}s)"'),
        ('dispatcher-a', 'function', 'run_child_stream_probe'),
        ('dispatcher-a', 'loop', 'for (( child_wait=0; child_wait<200; child_wait++ )); do'),
        ('dispatcher-a', 'assertion', 'ok "oversized child stream is handshake-bound, prompt, and group-clean"'),
        ('dispatcher-a', 'assertion', 'bad "oversized child stream handshake, bound, prompt, or group cleanup"'),
        ('dispatcher-a', 'loop', 'for (( child_repeat=1; child_repeat<=20; child_repeat++ )); do'),
        ('dispatcher-a', 'assertion', 'ok "child-stream handshake and process-group cleanup are stable across 20 runs"'),
        ('dispatcher-a', 'assertion', 'bad "child-stream handshake or process-group cleanup flaked during 20 runs"'),
        ('dispatcher-a', 'loop', 'for signal_case in HUP INT TERM; do'),
        ('dispatcher-a', 'loop', 'for (( signal_wait=0; signal_wait<200; signal_wait++ )); do'),
        ('dispatcher-a', 'assertion', 'ok "$signal_case interrupts the version probe with exit $signal_exit, no group, and no artifacts"'),
        ('dispatcher-a', 'assertion', 'bad "$signal_case version-probe cleanup (ready $signal_ready/exit $rc/calls $signal_calls/artifacts $signal_artifacts/cleanup $signal_cleanup)"'),
        ('dispatcher-a', 'function', 'run_without_fake_agy'),
        ('dispatcher-a', 'assertion', 'ok "direct selector reports missing agy as unavailable before task read"'),
        ('dispatcher-a', 'assertion', 'bad "direct selector missing-agy boundary (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'ok "direct selector reports non-executable agy as unavailable before task read"'),
        ('dispatcher-a', 'assertion', 'bad "direct selector non-executable-agy boundary (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'ok "direct selector sanitizes an agy launch failure before task read"'),
        ('dispatcher-a', 'assertion', 'bad "direct selector launch-failure boundary (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'ok "model missing-agy fails before task intake"'),
        ('dispatcher-a', 'assertion', 'bad "model missing-agy preflight (exit $rc)"'),
        ('dispatcher-a', 'assertion', 'assert_direct_result "documented prefixed agy version is accepted" version-prefixed          gemini-3.6-flash gemini-3.6-flash high cli cli 5'),
        ('dispatcher-a', 'assertion', 'bad "documented prefixed agy version is accepted (exit $rc)"'),
        *(('dispatcher-a', 'fixture', label) for label in CASE_LABELS['dispatcher-a']
          if label.startswith('runtime validator rejects ')),
        ('dispatcher-a', 'function', 'expect_valid_selection_record'),
        ('dispatcher-a', 'assertion', 'if [[ "$got" == 0 && ! -s "$path.valid.out" ]]; then ok "$name"; else bad "$name (exit $got)"; fi'),
        ('dispatcher-a', 'function', 'expect_invalid_selection_record'),
        ('dispatcher-a', 'assertion', 'if [[ "$got" == 64 && ! -s "$path.invalid.out" ]]; then ok "$name"; else bad "$name (exit $got)"; fi'),
        ('dispatcher-a', 'assertion', 'expect_valid_selection_record "runtime validator accepts a complete direct artifact" "$VALID_DIRECT_RECORD"'),
        ('dispatcher-a', 'assertion', 'expect_valid_selection_record "runtime validator accepts a complete default artifact" "$VALID_DEFAULT_RECORD"'),
        ('dispatcher-a', 'loop', 'for record in "$ARTIFACT_CASES"/*.json; do'),
        ('dispatcher-a', 'assertion', 'expect_invalid_selection_record "runtime validator rejects $(basename "$record")" "$record"'),
        ('dispatcher-a', 'loop', 'for schema in 1 2 3 4; do'),
        ('dispatcher-a', 'assertion', 'ok "retired selection $schema rejects launch authorization without rewriting history"'),
        ('dispatcher-a', 'assertion', 'else bad "retired selection $schema launch boundary"; fi'),
        ('dispatcher-a', 'assertion', 'ok "failure never starts an automatic fresh retry and preserves frozen selection"'),
        ('dispatcher-a', 'assertion', 'bad "failure must not start an automatic fresh retry"'),
        ('dispatcher-a', 'loop', 'for test_case in equal child relative missing-child symlink-log symlink-worktree; do'),
        ('dispatcher-a', 'assertion', 'ok "root wrapper derives deterministic external state root and rejects project log root in worktree"'),
        ('dispatcher-a', 'assertion', 'bad "root wrapper derives deterministic external state root and rejects project log root in worktree"'),
        ('dispatcher-a', 'assertion', 'ok "dispatcher keeps a new job private under umask 022 and a traversable custom log root"'),
        ('dispatcher-a', 'assertion', 'bad "dispatcher keeps a new job private under umask 022 and a traversable custom log root"'),
        ('dispatcher-a', 'assertion', 'ok "dispatcher keeps artifacts private under umask 000 without changing the agy child umask"'),
        ('dispatcher-a', 'assertion', 'bad "dispatcher keeps artifacts private under umask 000 without changing the agy child umask"'),
        ('dispatcher-a', 'assertion', 'ok "a missing custom log root is created owner-only under caller umask 000"'),
        ('dispatcher-a', 'assertion', 'bad "a missing custom log root is created owner-only under caller umask 000"'),
        ('dispatcher-a', 'loop', 'for invalid_root_mode in 0777 0775; do'),
        ('dispatcher-a', 'assertion', 'ok "mode $invalid_root_mode log root is rejected before prompt staging or agy"'),
        ('dispatcher-a', 'assertion', 'bad "mode $invalid_root_mode log root is rejected before prompt staging or agy"'),
        ('dispatcher-a', 'assertion', 'ok "symlink log root is rejected before prompt staging or agy"'),
        ('dispatcher-a', 'assertion', 'bad "symlink log root is rejected before prompt staging or agy"'),
        ('dispatcher-a', 'assertion', 'ok "log-root acceptance rejects a runtime with final-root validation bypassed"'),
        ('dispatcher-a', 'assertion', 'bad "log-root acceptance rejects a runtime with final-root validation bypassed"'),
        ('dispatcher-a', 'assertion', 'ok "supervisor fails closed when a mutation weakens private creation"'),
        ('dispatcher-a', 'assertion', 'bad "privacy acceptance rejects a runtime with the private creation mask removed"'),
        ('dispatcher-a', 'assertion', 'ok "pre-existing job directory is rejected before invoking agy or touching its sentinel"'),
        ('dispatcher-a', 'assertion', 'bad "pre-existing job directory is rejected before invoking agy or touching its sentinel"'),
        ('dispatcher-a', 'assertion', 'ok "pre-existing job file is rejected before invoking agy or touching its sentinel"'),
        ('dispatcher-a', 'assertion', 'bad "pre-existing job file is rejected before invoking agy or touching its sentinel"'),
        ('dispatcher-a', 'assertion', 'ok "pre-existing job symlink is rejected before invoking agy or touching its target"'),
        ('dispatcher-a', 'assertion', 'bad "pre-existing job symlink is rejected before invoking agy or touching its target"'),
        ('dispatcher-a', 'assertion', 'ok "generic plan dispatches and receives the read-only file-tool preamble"'),
        ('dispatcher-a', 'assertion', 'bad "generic plan should remain usable"'),
        ('dispatcher-a', 'assertion', 'expect_exit "--add-dir outside audited workdir is rejected" 64 "$rc"'),
        ('dispatcher-a', 'loop', 'for option in --workdir --mode --model --add-dir; do'),
        ('dispatcher-a', 'assertion', 'expect_exit "$option missing operand is controlled" 64 "$rc"'),
        ('dispatcher-a', 'assertion', 'expect_exit "oversized job produces an envelope" 0 "$rc"'),
        ('dispatcher-a', 'assertion', 'ok "oversized staged prompt preserves task and output contract"'),
        ('dispatcher-a', 'assertion', 'bad "oversized staged prompt preserves task and output contract"'),
        ('dispatcher-a', 'assertion', 'ok "oversized job grants only its staged prompt directory"'),
        ('dispatcher-a', 'assertion', 'bad "oversized job grants only its staged prompt directory"'),
        ('dispatcher-a', 'assertion', 'ok "oversized dispatch points agy at the complete staged prompt"'),
        ('dispatcher-a', 'assertion', 'bad "oversized dispatch points agy at the complete staged prompt"'),
        ('dispatcher-a', 'assertion', 'ok "oversized staged prompt is read-only during agy execution"'),
        ('dispatcher-a', 'assertion', 'bad "oversized staged prompt is read-only during agy execution"'),
        ('dispatcher-a', 'assertion', 'ok "oversized staged prompt is private again after agy returns"'),
        ('dispatcher-a', 'assertion', 'bad "oversized staged prompt is private again after agy returns"'),
        ('dispatcher-a', 'assertion', 'expect_print_last "oversized prompt keeps --print and its value last" "$TMP/oversized.argv"'),
        ('dispatcher-a', 'assertion', 'ok "supervisor fails closed when a mutation restores staged artifacts publicly"'),
        ('dispatcher-a', 'assertion', 'bad "privacy acceptance rejects a runtime that restores staged artifacts publicly"'),
        ('dispatcher-a', 'assertion', 'ok "failed oversized child restores staged artifacts before the wrapper exits"'),
        ('dispatcher-a', 'assertion', 'bad "failed oversized child restores staged artifacts before the wrapper exits"'),
        ('dispatcher-a', 'loop', 'for signal_name in HUP INT TERM; do'),
        ('dispatcher-a', 'assertion', 'ok "$signal_name restores staged artifacts and preserves signal exit semantics"'),
        ('dispatcher-a', 'assertion', 'bad "$signal_name restores staged artifacts and preserves signal exit semantics"'),
        ('dispatcher-a', 'assertion', 'expect_exit "non-success terminal status fails closed" 4 "$rc"'),
        ('dispatcher-a', 'assertion', 'expect_exit "dispatcher independently rejects schema-invalid output" 4 "$rc"'),
        ('dispatcher-b', 'function', 'status_sha'),
        ('dispatcher-b', 'function', 'status_field'),
        ('dispatcher-b', 'function', 'wait_terminal'),
        ('dispatcher-b', 'loop', 'for (( index=0; index<40; index++ )); do'),
        ('dispatcher-b', 'function', 'control_worker'),
        ('dispatcher-b', 'function', 'start_worker'),
        ('dispatcher-b', 'loop', 'for fake_provider_env_name in          FAKE_AGY_STATUS FAKE_ARGV_FILE FAKE_BAD_ENVELOPE FAKE_CALLED_FILE          FAKE_CALLS_FILE FAKE_CHILD_PID_FILE FAKE_DIRS_FILE FAKE_DISPATCH_COUNT_FILE          FAKE_DISPATCH_MODE FAKE_ENV_OBSERVED_FILE FAKE_HOME_OBSERVED_FILE FAKE_ERROR_LINE          FAKE_DELETE_FROM_BOUND_ROOT FAKE_EDIT_CONTENT FAKE_EDIT_FROM_BOUND_ROOT          FAKE_EXECUTABLE_SYMLINK_TARGET FAKE_EXIT_CODE FAKE_FAIL_FIRST          FAKE_HEARTBEAT_AFTER_FIRST_READY FAKE_HEARTBEAT_AFTER_FIRST_RELEASE          FAKE_HEARTBEAT_BARRIER_READY FAKE_HEARTBEAT_BARRIER_RELEASE          FAKE_HEARTBEAT_COUNT FAKE_HEARTBEAT_DELAY FAKE_HELP_MODE FAKE_MODEL_FILE          FAKE_MUTATE_EXECUTABLE FAKE_MUTATE_EXECUTABLE_MODE          FAKE_MUTATE_EXECUTABLE_PARENT FAKE_MUTATE_EXECUTABLE_SAME_LENGTH          FAKE_MUTATE_PROJECT_MARKER FAKE_MUTATION_MARKER          FAKE_MUTATE_WORKTREE_PATH          FAKE_PROBE_PARENT_PID_FILE FAKE_PROBE_PGID_FILE FAKE_PROBE_READY_FILE          FAKE_PROBE_RELEASE_FILE FAKE_PROMPT_FILE FAKE_QUOTA_ERROR          FAKE_PROVIDER_CREATE_PATH          FAKE_REPLACE_EXECUTABLE_SYMLINK FAKE_SIDE_EFFECT_FILE FAKE_SIGNAL_PARENT          FAKE_SPARSE_PROJECT_MARKER FAKE_STAGE_RESULT_FILE FAKE_TRY_STAGE_WRITE          FAKE_UTF8_SUMMARY FAKE_VERSION_MODE FAKE_WARNING_LINE          FAKE_WORKER_CALLS_FILE FAKE_WORKER_VERIFIED; do'),
        ('dispatcher-b', 'loop', 'for option in "$@"; do'),
        ('dispatcher-b', 'assertion', 'ok "raw start requires an explicit transmission mode before queueing or provider launch"'),
        ('dispatcher-b', 'assertion', 'bad "raw start missing transmission mode boundary"'),
        ('dispatcher-b', 'assertion', 'ok "partial/promisor clones fail synchronously before queueing or provider launch"'),
        ('dispatcher-b', 'assertion', 'bad "partial/promisor clone synchronous preflight"'),
        ('dispatcher-b', 'assertion', 'ok "plan stages the complete prompt and leaves slash expansion available only for its fixed driver prompt"'),
        ('dispatcher-b', 'assertion', 'bad "plan staging/slash contract"'),
        ('dispatcher-b', 'assertion', 'ok "valid init and step updates renew the idle lease without changing hard limits"'),
        ('dispatcher-b', 'assertion', 'bad "valid stream heartbeats must complete below the hard deadline"'),
        ('dispatcher-b', 'assertion', 'ok "silent worker terminates at the independent idle deadline"'),
        ('dispatcher-b', 'assertion', 'bad "silent worker idle timeout classification"'),
        ('dispatcher-b', 'assertion', 'ok "malformed events never renew the idle lease"'),
        ('dispatcher-b', 'assertion', 'bad "malformed event heartbeat boundary"'),
        ('dispatcher-b', 'assertion', 'ok "oversized stream events fail closed and never renew the idle lease"'),
        ('dispatcher-b', 'assertion', 'bad "oversized event heartbeat boundary"'),
        ('dispatcher-b', 'assertion', 'ok "worker rejects exit-zero empty provider output"'),
        ('dispatcher-b', 'assertion', 'bad "worker exit-zero empty-output classification"'),
        ('dispatcher-b', 'assertion', 'ok "advanced controls resolve only a job-bound workflow log root without environment"'),
        ('dispatcher-b', 'assertion', 'bad "advanced control workflow state log-root binding"'),
        ('dispatcher-b', 'assertion', 'ok "verification-copy and restart accept bound --state before eligibility checks"'),
        ('dispatcher-b', 'assertion', 'bad "verification-copy and restart state-derived log root"'),
        ('dispatcher-b', 'assertion', 'ok "successful structured output ignores stderr diagnostics and preserves UTF-8"'),
        ('dispatcher-b', 'assertion', 'bad "structured-output diagnostic and UTF-8 boundary"'),
        ('dispatcher-b', 'loop', 'for classified_case in authentication_text provider_text unknown_text; do'),
        ('dispatcher-b', 'assertion', 'ok "unproven $classified_case remains unclassified without free-form guessing"'),
        ('dispatcher-b', 'assertion', 'bad "closed error classification for $classified_case"'),
        ('dispatcher-b', 'assertion', 'ok "native nested-sandbox denial is actionable and interrupted candidate-free budget is explained"'),
        ('dispatcher-b', 'assertion', 'bad "native host and interrupted budget status explanations"'),
        ('dispatcher-b', 'assertion', 'ok "command diagnostic version is bounded text without a semantic-version gate"'),
        ('dispatcher-b', 'assertion', 'bad "command diagnostic version type, control, byte-bound or free-text validation"'),
        ('dispatcher-b', 'loop', 'for version_mode in ready quota113 drift999; do'),
        ('dispatcher-b', 'assertion', 'ok "quota prose without report fails across $version_mode without retry"'),
        ('dispatcher-b', 'assertion', 'else bad "quota prose must not invent report or retry authority ($version_mode)"; fi'),
        ('dispatcher-b', 'assertion', 'ok "fresh heartbeats cannot exceed hard deadline and process-group descendants are reaped"'),
        ('dispatcher-b', 'assertion', 'bad "hard deadline/process-group boundary"'),
        ('dispatcher-b', 'assertion', 'ok "foreground TERM is forwarded through the controller and leaves no late process-group side effect"'),
        ('dispatcher-b', 'assertion', 'bad "foreground signal ownership/process-group cleanup"'),
        ('dispatcher-b', 'assertion', 'ok "status/wait/result formats preserve JSON and expose three sanitized driver-owned text lines"'),
        ('dispatcher-b', 'assertion', 'bad "async status/wait/result format and privacy lifecycle"'),
        ('dispatcher-b', 'loop', 'for (( startup_index=1; startup_index<=12; startup_index++ )); do'),
        ('dispatcher-b', 'assertion', 'ok "fast controller ownership handoff is stable without a competing parent PID transition"'),
        ('dispatcher-b', 'assertion', 'bad "fast controller ownership handoff race"'),
        ('dispatcher-b', 'loop', 'for (( extend_index=0; extend_index<200; extend_index++ )); do'),
        ('dispatcher-b', 'assertion', 'ok "stale/over-max extend is rejected; fresh state-SHA extend changes only the local hard deadline"'),
        ('dispatcher-b', 'assertion', 'bad "extend control lifecycle"'),
        ('dispatcher-b', 'assertion', 'ok "max runtime remains an absolute cap even after an approved hard-deadline extension"'),
        ('dispatcher-b', 'assertion', 'bad "max runtime cap after extension"'),
        ('dispatcher-b', 'loop', 'for (( cancel_barrier_index=0; cancel_barrier_index<200; cancel_barrier_index++ )); do'),
        ('dispatcher-b', 'assertion', 'ok "concurrent cancel is state-SHA-gated, reaps the local process group, and does not claim remote cancellation"'),
        ('dispatcher-b', 'assertion', 'bad "cancel control lifecycle"'),
        ('dispatcher-b', 'assertion', 'ok "queued cancel is consumed by inherited controller ownership without starting agy"'),
        ('dispatcher-b', 'assertion', 'bad "queued cancel/start ownership handoff"'),
        ('dispatcher-b', 'assertion', 'ok "state snapshot serializes an approved atomic replacement without weakening identity checks"'),
        ('dispatcher-b', 'assertion', 'bad "state snapshot atomic-replacement identity boundary"'),
        ('dispatcher-b', 'syntax', 'orphan_sha="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$ORPHAN_JOB/dispatch-state.json" <<\'PY\''),
        ('dispatcher-b', 'syntax', ')"'),
        ('dispatcher-b', 'assertion', 'ok "orphaned dispatch is preserve-only and cannot resume or restart a provider call"'),
        ('dispatcher-b', 'assertion', 'bad "orphaned dispatch continuation boundary"'),
        ('dispatcher-b', 'assertion', 'ok "resume text succeeds with the exact private conversation and no private output"'),
        ('dispatcher-b', 'assertion', 'bad "conversation resume format and privacy contract"'),
        ('dispatcher-b', 'assertion', 'ok "restart is explicit fresh origin and remains distinct from resume"'),
        ('dispatcher-b', 'assertion', 'bad "fresh restart contract"'),
        ('dispatcher-b', 'function', 'project_feedback'),
        ('dispatcher-b', 'function', 'project_verified_feedback'),
        ('dispatcher-b', 'function', 'project_missing_feedback'),
        ('dispatcher-b', 'assertion', 'then ok "provider check-id regex remains RE2-compatible and driver validation stays strict"'),
        ('dispatcher-b', 'assertion', 'else bad "provider check-id schema boundary"; fi'),
        ('dispatcher-b', 'assertion', 'ok "unavailable resume preserves failure state and starts no probes or provider"'),
        ('dispatcher-b', 'assertion', 'else bad "unavailable resume action parity"; fi'),
        ('dispatcher-b', 'loop', 'for capability_case in resume continue scoped-repair effort no-effort restart; do'),
        ('dispatcher-b', 'assertion', 'then ok "$capability_case checks only active flags with fresh probes and preserves prior evidence"'),
        ('dispatcher-b', 'assertion', 'else bad "$capability_case conditional recovery (initial $initial_rc, recovery $recovery_rc/$recovery_wait_rc)"; fi'),
        ('dispatcher-b', 'assertion', '. "$ROOT/tests/agy_worker_project_lifecycle_cases.sh"'),
        ('dispatcher-b', 'assertion', 'ok "project continuation text keeps trigger evidence while the replacement candidate resets stored evidence"'),
        ('dispatcher-b', 'assertion', 'bad "project continuation format and privacy contract"'),
        ('dispatcher-b', 'assertion', 'ok "project continuation preserves initial-only whole-worktree approval after provider-created paths"'),
        ('dispatcher-b', 'assertion', 'bad "project continuation provider-created path boundary"'),
        ('dispatcher-b', 'assertion', 'ok "project finalization text is three-line, driver-owned, and invokes no provider"'),
        ('dispatcher-b', 'assertion', 'bad "project finalization format and assurance contract"'),
        ('dispatcher-b', 'loop', 'for project_cycle in 2 3 4 5; do'),
        ('dispatcher-b', 'assertion', 'ok "project continuation is same-conversation, feedback-private, and bounded to initial plus four repairs"'),
        ('dispatcher-b', 'assertion', 'bad "project continuation cycle bound"'),
        ('dispatcher-b', 'assertion', 'ok "project finalization is a SHA-bound no-provider Codex quality decision"'),
        ('dispatcher-b', 'assertion', 'bad "project finalization contract"'),
        ('dispatcher-b', 'assertion', 'ok "project workflow rejects Git-admin aliases while allowing ordinary contained links"'),
        ('dispatcher-b', 'assertion', 'bad "project worktree symlink boundary"'),
        ('dispatcher-b', 'assertion', 'ok "project workflow requires a linked-worktree Git marker file"'),
        ('dispatcher-b', 'assertion', 'bad "project workflow main-checkout boundary"'),
        ('dispatcher-b', 'loop', 'for project_nested_kind in file directory symlink special; do'),
        ('dispatcher-b', 'assertion', 'ok "project shell preflight rejects every nested Git marker before provider setup"'),
        ('dispatcher-b', 'assertion', 'bad "project shell nested Git marker boundary"'),
        ('dispatcher-b', 'assertion', 'ok "project shell preflight rejects casefold nested .GIT aliases before provider setup"'),
        ('dispatcher-b', 'assertion', 'bad "project shell casefold nested Git marker boundary"'),
        ('dispatcher-b', 'function', 'project_corrupt_marker_stays_closed'),
        ('dispatcher-b', 'syntax', 'before_sha="$(python3 - "$TMP/logs/$job/dispatch-state.json" <<\'PY_HASH\''),
        ('dispatcher-b', 'syntax', ')"'),
        ('dispatcher-b', 'loop', 'for action in result resume restart; do'),
        ('dispatcher-b', 'syntax', 'after_sha="$(python3 - "$TMP/logs/$job/dispatch-state.json" <<\'PY_HASH\''),
        ('dispatcher-b', 'syntax', ')"'),
        ('dispatcher-b', 'assertion', 'project_corrupt_marker_stays_closed project-marker-drift && project_marker_recovery_closed=1'),
        ('dispatcher-b', 'assertion', 'ok "project workflow binds the linked-worktree marker before and after provider execution"'),
        ('dispatcher-b', 'assertion', 'bad "project workflow marker drift boundary"'),
        ('dispatcher-b', 'assertion', 'project_corrupt_marker_stays_closed project-marker-sparse-post && project_marker_sparse_recovery_closed=1'),
        ('dispatcher-b', 'assertion', 'ok "project post-provider boundary rejects a sparse oversized marker without accepting a result"'),
        ('dispatcher-b', 'assertion', 'bad "project post-provider sparse marker boundary"'),
        ('dispatcher-b', 'assertion', 'ok "project continuation rejects between-cycle marker drift without provider call or state replacement"'),
        ('dispatcher-b', 'assertion', 'bad "project continuation must not rebaseline a changed worktree boundary"'),
        ('dispatcher-b', 'function', 'project_oversized_boundary_case'),
        ('dispatcher-b', 'assertion', 'ok "$description"'),
        ('dispatcher-b', 'assertion', 'bad "$description"'),
        ('dispatcher-b', 'assertion', 'project_oversized_boundary_case project-between-cycle-oversized dense      "project continuation rejects a 4097-byte marker before state replacement or provider call"'),
        ('dispatcher-b', 'assertion', 'project_oversized_boundary_case project-between-cycle-sparse sparse      "project continuation rejects a sparse oversized marker before state replacement or provider call"'),
        ('dispatcher-b', 'syntax', 'project_orphan_sha="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$PROJECT_ORPHAN_JOB/dispatch-state.json" <<\'PY\''),
        ('dispatcher-b', 'syntax', ')"'),
        ('dispatcher-b', 'assertion', 'ok "orphaned project state is preserve-only across continuation, finalization, and result surfaces"'),
        ('dispatcher-b', 'assertion', 'bad "orphaned project state must not progress or expose a trusted partial result"'),
        ('dispatcher-b', 'assertion', 'ok "verification staging rolls back exactly on injected state-write failure and retries cleanly"'),
        ('dispatcher-b', 'assertion', 'bad "verification staging rollback and retry"'),
        ('dispatcher-b', 'assertion', 'ok "project boundary accepts the exact entry cap and rejects one entry over it"'),
        ('dispatcher-b', 'assertion', 'bad "project boundary entry cap"'),
        ('dispatcher-b', 'assertion', 'ok "concurrent continue and finalize on one approved SHA publish exactly one winner"'),
        ('dispatcher-b', 'assertion', 'bad "concurrent project continuation/finalization arbitration"'),
        ('dispatcher-b', 'loop', 'for (( project_cancel_index=0; project_cancel_index<500; project_cancel_index++ )); do'),
        ('dispatcher-b', 'assertion', 'ok "cancelled repair can partially finalize and return the prior bound success"'),
        ('dispatcher-b', 'assertion', 'bad "cancelled repair prior-candidate finalization"'),
        ('dispatcher-b', 'assertion', 'ok "control state refuses symlink replacement rather than following a swapped state file"'),
        ('dispatcher-b', 'assertion', 'bad "control state symlink replacement"'),
        ('dispatcher-b', 'assertion', 'ok "folder-only core resolves and completes synthetic ordinary workflow verification"'),
        ('dispatcher-b', 'assertion', 'bad "folder-only core resolves and completes synthetic ordinary workflow verification"'),
        ('dispatcher-b', 'assertion', 'expect_exit "installer accepts replacement metacharacters in clone path" 0 "$rc"'),
        ('dispatcher-b', 'assertion', 'ok "installer copies the canonical bundle and records the exact clone path"'),
        ('dispatcher-b', 'assertion', 'bad "installer copies the canonical bundle and records the exact clone path"'),
    ),
    'tests/agy_worker_project_lifecycle_cases.sh': (
        ('dispatcher-b', 'assertion', 'ok "project workflow exposes pending Codex-owned verification without changing resume semantics"'),
        ('dispatcher-b', 'assertion', 'bad "project workflow status contract"'),
        ('dispatcher-b', 'syntax', 'project_scoped_delete_transmission="$('),
        ('dispatcher-b', 'syntax', ')"'),
        ('dispatcher-b', 'assertion', 'ok "scoped deletion remains result/finalize-bound and requires fresh approval before continuation"'),
        ('dispatcher-b', 'assertion', 'bad "scoped terminal deletion or continuation approval boundary"'),
    ),
}

# This finite guard binds complete assertion/source statements and loop headers,
# including their arguments and quote spelling. It does not interpret shell;
# expanded identities are checked again on the real success path. Other heredocs
# are data; the one filename-producing fixture above also declares case labels.
SHELL_ASSERTIONS = frozenset({
    "ok", "bad", "expect_exit", "expect_print_last", "assert_direct_result",
    "expect_selector_reject", "assert_env_reject", "expect_compat_reject",
    "expect_valid_selection_record", "expect_invalid_selection_record",
    "project_corrupt_marker_stays_closed", "project_oversized_boundary_case",
})
SHELL_SOURCES = ("tests/test-agy-worker.sh", "tests/agy_worker_project_lifecycle_cases.sh")
CASE_CONTROL = b"@@agy-worker-ci-case:"


def selection_artifact_labels(source: str) -> tuple[str, ...]:
    """Derive the current fixture's filenames, rejecting any other producer shape."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("unsupported selection artifact producer syntax") from exc
    assignments = [node.value for node in tree.body if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == "cases"]
    loops = [node for node in tree.body if isinstance(node, ast.For)
             and isinstance(node.target, ast.Name) and node.target.id == "schema"]
    if len(assignments) != 1 or not isinstance(assignments[0], ast.Dict) \
            or len(loops) != 1 or not isinstance(loops[0].iter, ast.Tuple):
        raise ValueError("unsupported selection artifact producer shape")
    keys = assignments[0].keys
    schemas = loops[0].iter.elts
    if any(not isinstance(key, ast.Constant) or not isinstance(key.value, str) for key in keys) \
            or any(not isinstance(value, ast.Constant) or type(value.value) is not int for value in schemas):
        raise ValueError("selection artifact domains must be literal")
    names = [key.value for key in keys if isinstance(key, ast.Constant)]
    names.extend(f"retired-{value.value}" for value in schemas if isinstance(value, ast.Constant))
    labels = tuple(f"runtime validator rejects {name}.json" for name in sorted(names))
    expected = tuple(label for label in CASE_LABELS["dispatcher-a"]
                     if label.startswith("runtime validator rejects "))
    if len(set(names)) != len(names) or labels != expected:
        raise ValueError("selection artifact case inventory mismatch")
    if ast.dump(tree) != ast.dump(ast.parse(SELECTION_ARTIFACT_PRODUCER)):
        raise ValueError("unsupported selection artifact producer shape")
    return labels


def shell_declarations(source: str, initial_part: str) -> tuple[tuple[str, str, str], ...]:
    declarations: list[tuple[str, str, str]] = []
    heredocs: list[tuple[str, bool, list[str] | None]] = []
    pending = ""
    part = initial_part
    for line in source.splitlines():
        if heredocs:
            delimiter, tabs, fixture = heredocs[0]
            content = line.lstrip("\t") if tabs else line
            if content == delimiter:
                if fixture is not None:
                    declarations.extend((part, "fixture", label)
                                        for label in selection_artifact_labels("\n".join(fixture)))
                heredocs.pop(0)
            elif fixture is not None:
                fixture.append(content)
            continue
        pending += line
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        statement, pending = pending, ""
        if statement.startswith('if [[ "$CI_PART" != b ]]'):
            part = "dispatcher-a"
        elif statement == "fi # first assertions in part a; shared fake provider setup follows":
            part = "common"
        elif statement == "fi # part a":
            part = "common"
        elif statement.startswith('if [[ "$CI_PART" != a ]]'):
            part = "dispatcher-b"
        elif statement == "fi # part b":
            part = "common"
        function = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*\(\s*\)\s*\{", statement)
        if function:
            declarations.append((part, "function", function[1]))
        if re.match(r"\s*function\b", statement):
            raise ValueError("unsupported shell function declaration")
        # Current suite heredocs have literal delimiters. Reject unsupported forms.
        for match in re.finditer(r"(?<!<)<<(-?)(?!<)\s*(['\"]?)([A-Za-z_][A-Za-z_0-9]*)\2", statement):
            fixture = [] if statement == SELECTION_ARTIFACT_HEADER else None
            heredocs.append((match[3], bool(match[1]), fixture))
        if "<<" in statement and not heredocs:
            raise ValueError("unsupported shell heredoc declaration")
        if statement.lstrip().startswith("#"):
            continue
        try:
            lexer = shlex.shlex(statement, posix=True, punctuation_chars=";&|()")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError as exc:
            # Existing multiline command substitutions exceed shlex's line grammar.
            # Bind these boundaries verbatim rather than silently skipping them.
            boundary = (part, "syntax", statement.strip())
            if not any(boundary in expected for expected in SHELL_DECLARATIONS.values()):
                raise ValueError("unsupported shell declaration shape") from exc
            declarations.append(boundary)
            continue
        guarded = False
        command_start = True
        for index, token in enumerate(tokens):
            if re.fullmatch(r"(?:expect|assert)_[A-Za-z_0-9]+", token) and token not in SHELL_ASSERTIONS:
                raise ValueError("unregistered shell assertion wrapper")
            if token and all(char in ";&|()" for char in token):
                command_start = True
                continue
            if token in {"then", "else", "do", "{", "if", "elif", "!"}:
                command_start = True
                continue
            if command_start and token in {"for", "while", "until", "select"}:
                declarations.append((part, "loop", statement.strip()))
                if token in {"while", "until"}:
                    continue
            at_command = command_start
            if command_start and (token in {"command", "builtin"} or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*\+?=.*", token)):
                continue
            command_start = False
            if token not in SHELL_ASSERTIONS | {"source", "."}:
                continue
            # Reserve source spellings even behind unsupported command prefixes.
            # The sole existing non-command use is the literal grep pattern.
            if token == "." and not at_command and tokens[max(0, index - 2):index] == ["grep", "-q"]:
                continue
            if index + 1 == len(tokens):
                raise ValueError("shell assertion without a label")
            label = tokens[index + 1]
            if label in ("()", "("):
                continue  # function declaration; its completion sites are scanned
            if token in ("source", ".") and label != "$ROOT/tests/agy_worker_project_lifecycle_cases.sh":
                raise ValueError("unregistered shell source")
            guarded = True
        if guarded:
            declarations.append((part, "assertion", statement.strip()))
    if heredocs or pending:
        raise ValueError("unterminated shell declaration")
    return tuple(declarations)


def validate_shell_inventory(repo_root: Path) -> None:
    for relative, expected in SHELL_DECLARATIONS.items():
        part = "common" if relative == SHELL_SOURCES[0] else "dispatcher-b"
        observed = shell_declarations((repo_root / relative).read_text(encoding="utf-8"), part)
        if observed != expected:
            raise ValueError(f"shell declaration inventory mismatch: {relative}")


def case_identity(suite: str, label: str) -> str:
    digest = hashlib.sha256(
        b"agy-worker-ci-case-v1\0" + canonical_bytes((suite, label))
    ).hexdigest()
    return f"{suite}:{digest}"


def stage_case_ids(stage_id: str) -> tuple[str, ...]:
    suite = "dispatcher-remediation" if stage_id.startswith("dispatcher-remediation-") else "dispatcher"
    return tuple(case_identity(suite, label) for label in CASE_LABELS.get(stage_id, ()))


def all_case_ids() -> tuple[str, ...]:
    return tuple(identity for stage in STAGES for identity in stage_case_ids(stage.id))


def validate_case_inventory() -> None:
    identities = all_case_ids()
    if len(identities) != 409 or len(set(identities)) != len(identities):
        raise ValueError("case inventory must contain 409 unique assigned identities")
    if set(CASE_LABELS) != {stage.id for stage in STAGES if stage.id.startswith("dispatcher-")}:
        raise ValueError("case inventory assignment mismatch")
    for stage_id, labels in CASE_LABELS.items():
        if not labels or any(not label or "\n" in label or "\r" in label for label in labels):
            raise ValueError(f"invalid case label in {stage_id}")


def emit_case_completion(identity: str) -> None:
    nonce = os.environ.get("AGY_WORKER_CI_CASE_NONCE")
    if nonce is not None:
        stage_id = os.environ["AGY_WORKER_CI_CASE_STAGE"]
        if not re.fullmatch(r"[0-9a-f]{64}", nonce) or identity not in stage_case_ids(stage_id):
            raise ValueError("invalid case completion context")
        print(f"{CASE_CONTROL.decode()}{nonce}:{stage_id}:{identity}", flush=True)


def parse_case_completion(line: bytes, nonce: str, stage_id: str) -> str:
    prefix = CASE_CONTROL + nonce.encode("ascii") + b":" + stage_id.encode("ascii") + b":"
    if not re.fullmatch(r"[0-9a-f]{64}", nonce) or not line.startswith(prefix):
        raise ValueError("invalid case completion nonce or stage")
    return line[len(prefix):].decode("utf-8")


def validate_case_sequence(observed: Sequence[str], expected: Sequence[str], *, complete: bool) -> None:
    if list(observed) != list(expected[:len(observed)]) or (complete and len(observed) != len(expected)):
        raise ValueError("case completion inventory is omitted, duplicated, reordered, or unassigned")



def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def inventory_digest() -> str:
    serialized = [
        (s.id, s.announcement, s.shard, s.argv, s.receipt_metadata) for s in STAGES
    ]
    return hashlib.sha256(canonical_bytes([
        serialized, CASE_LABELS, SHELL_DECLARATIONS,
        SELECTION_ARTIFACT_HEADER, SELECTION_ARTIFACT_PRODUCER,
        [(stage.id, stage_case_ids(stage.id)) for stage in STAGES],
    ])).hexdigest()


def stage_environment(
    base_env: dict[str, str], stage: Stage, pycache: Path
) -> dict[str, str]:
    """Isolate runner imports without changing ordinary suite bytecode probes."""
    env = dict(base_env)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPYCACHEPREFIX", None)
    env.pop("AGY_WORKER_CI_PYCACHE_DIR", None)
    if stage.id == "python-syntax":
        env["AGY_WORKER_CI_PYCACHE_DIR"] = str(pycache)
    return env


def execute_stage(stage: Stage, repo_root: Path, env: dict[str, str]) -> int:
    expected = stage_case_ids(stage.id)
    if not expected:
        return subprocess.run(stage.argv, cwd=str(repo_root), env=env,
                              stdin=subprocess.DEVNULL, check=False).returncode
    nonce = env.pop("AGY_WORKER_CI_FORWARD_CASE_NONCE", "")
    forward = bool(nonce)
    nonce = nonce or secrets.token_hex(32)
    env["AGY_WORKER_CI_CASE_NONCE"] = nonce
    env["AGY_WORKER_CI_CASE_STAGE"] = stage.id
    observed: list[str] = []
    process = subprocess.Popen(stage.argv, cwd=str(repo_root), env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    assert process.stdout is not None
    error: ValueError | None = None
    try:
        for line in iter(lambda: process.stdout.readline(8192), b""):
            stripped = line.rstrip(b"\r\n")
            if stripped.startswith(CASE_CONTROL):
                try:
                    identity = parse_case_completion(stripped, nonce, stage.id)
                    if len(observed) >= len(expected) or identity != expected[len(observed)]:
                        raise ValueError("case completion inventory is duplicated, reordered, or unassigned")
                    observed.append(identity)
                except (ValueError, UnicodeDecodeError) as exc:
                    error = ValueError(str(exc))
                if forward and error is None:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
            else:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
        returncode = process.wait()
        if error:
            raise error
        validate_case_sequence(observed, expected, complete=returncode == 0)
        return returncode
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    finally:
        process.stdout.close()


def run_stages(
    repo_root: Path,
    target_shard: str | None = None,
    timing_nonce: str | None = None,
    shard_nonce: str | None = None,
) -> int:
    if target_shard is not None and target_shard not in SHARDS:
        sys.stderr.write("ci offline: rejected arguments\n")
        return 2

    validate_case_inventory()
    validate_shell_inventory(repo_root)
    matching_stages = [
        stage for stage in STAGES if target_shard is None or stage.shard == target_shard
    ]

    pycache = Path(tempfile.mkdtemp(prefix="agyworker-ci-pycache."))
    try:
        base_env = dict(os.environ)
        for name in ("AGY_WORKER_CI_CASE_NONCE", "AGY_WORKER_CI_CASE_STAGE", "AGY_WORKER_CI_FORWARD_CASE_NONCE"):
            base_env.pop(name, None)
        if shard_nonce:
            base_env["AGY_WORKER_CI_FORWARD_CASE_NONCE"] = shard_nonce

        for stage in matching_stages:
            sys.stdout.write(f"==> {stage.announcement}\n")
            if timing_nonce:
                sys.stdout.write(
                    f"@@agy-worker-ci-timing:{timing_nonce}:{stage.announcement}\n"
                )
            if shard_nonce:
                sys.stdout.write(
                    f"@@agy-worker-ci-shard:{shard_nonce}:{stage.announcement}\n"
                )
            sys.stdout.flush()

            returncode = execute_stage(
                stage, repo_root, stage_environment(base_env, stage, pycache)
            )
            if returncode != 0:
                return returncode
        return 0
    finally:
        shutil.rmtree(pycache, ignore_errors=True)


def main(argv: Sequence[str]) -> int:
    if list(argv[1:]) == ["--validate-shell-inventory"]:
        validate_case_inventory()
        validate_shell_inventory(Path(__file__).resolve().parent.parent)
        return 0
    if len(argv) == 4 and argv[1] == "--validate-shell-completions":
        part = argv[2]
        if part not in ("a", "b", "full"):
            raise ValueError("invalid shell completion partition")
        labels = tuple(Path(argv[3]).read_text(encoding="utf-8").splitlines())
        expected = tuple(label for key in ("dispatcher-a", "dispatcher-b") for label in CASE_LABELS[key]) if part == "full" else CASE_LABELS[f"dispatcher-{part}"]
        validate_case_sequence(labels, expected, complete=True)
        return 0
    if list(argv[1:]) == ["--list"]:
        for stage in STAGES:
            print(f"{stage.id}\t{stage.shard}\t{shlex.join(stage.argv)}")
        return 0
    repo_root = Path(__file__).resolve().parent.parent
    target_shard: str | None = None
    timing_nonce: str | None = None
    shard_nonce: str | None = None

    idx = 1
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--shard" and idx + 1 < len(argv):
            target_shard = argv[idx + 1]
            idx += 2
        elif arg.startswith("--shard="):
            target_shard = arg.partition("=")[2]
            idx += 1
        elif arg == "--shard-child" and idx + 2 < len(argv):
            shard_nonce = argv[idx + 1]
            target_shard = argv[idx + 2]
            idx += 3
        elif arg == "--timing-child" and idx + 1 < len(argv):
            timing_nonce = argv[idx + 1]
            idx += 2
        elif arg in ("run", "run-stages"):
            idx += 1
        else:
            sys.stderr.write("ci offline: rejected arguments\n")
            return 2

    return run_stages(repo_root, target_shard, timing_nonce, shard_nonce)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except ValueError as exc:
        sys.stderr.write(f"ci offline: {exc}\n")
        raise SystemExit(1) from None
