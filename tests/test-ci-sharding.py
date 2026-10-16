#!/usr/bin/env python3
"""Focused positive and adversarial checks for CI sharding and aggregate verification."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT = ROOT / "scripts" / "ci_sharding.py"
SPEC = importlib.util.spec_from_file_location("ci_sharding_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

import ci_stages as STAGE_MODULE  # noqa: E402 -- sibling imports follow startup isolation/path setup

passed = 0
failed = 0


def check(label: str, test: Callable[[], bool] | bool) -> None:
    global passed, failed
    try:
        result = test() if callable(test) else test
    except Exception as exc:
        print(f"  EXC  {label}: {exc}")
        result = False
    if result:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}")


# 1. Shard Partition Invariants
check("inventory has 26 ordered unique stage IDs", len(MODULE.STAGES) == 26 and len({s.id for s in MODULE.STAGES}) == 26)
check("exactly seven frozen shard IDs exist", set(MODULE.SHARDS) == {"dispatcher-a", "dispatcher-b", "dispatcher-remediation-a", "dispatcher-remediation-b", "dispatcher-remediation-c", "other-a", "other-b"})

all_shard_stages: list[str] = []
for shard_id, stages in MODULE.SHARDS.items():  # noqa: B007 -- retain tuple binding; this pass uses only the other field
    all_shard_stages.extend(stages)

check("total stage count across seven shards is 26", len(all_shard_stages) == 26)
check("all stages across seven shards are disjoint and unique", len(set(all_shard_stages)) == 26)
check("union of shard stages equals canonical inventory stages", set(all_shard_stages) == {s.id for s in MODULE.STAGES})

canonical_order_index = {stage.id: idx for idx, stage in enumerate(MODULE.STAGES)}
for shard_id, stages in MODULE.SHARDS.items():
    indexes = [canonical_order_index[s] for s in stages]
    check(f"shard {shard_id} stages strictly preserve canonical inventory order", indexes == sorted(indexes))

check("inventory digest is lowercase SHA-256", MODULE.SHA256_RE.fullmatch(MODULE.inventory_digest()) is not None)

def _stage_environment_isolated() -> bool:
    ambient = {
        "PYTHONPYCACHEPREFIX": "/ambient/cache",
        "AGY_WORKER_CI_PYCACHE_DIR": "/ambient/private-cache",
        "PRESERVED": "yes",
    }
    pycache = Path("/private/ci-python-cache")
    syntax_stage = next(stage for stage in MODULE.STAGES if stage.id == "python-syntax")
    dispatcher_stage = next(stage for stage in MODULE.STAGES if stage.id == "dispatcher-a")
    syntax_env = STAGE_MODULE.stage_environment(ambient, syntax_stage, pycache)
    dispatcher_env = STAGE_MODULE.stage_environment(ambient, dispatcher_stage, pycache)
    return (
        syntax_env["AGY_WORKER_CI_PYCACHE_DIR"] == str(pycache)
        and "PYTHONPYCACHEPREFIX" not in syntax_env
        and syntax_env["PYTHONDONTWRITEBYTECODE"] == "1"
        and "PYTHONPYCACHEPREFIX" not in dispatcher_env
        and "AGY_WORKER_CI_PYCACHE_DIR" not in dispatcher_env
        and dispatcher_env["PYTHONDONTWRITEBYTECODE"] == "1"
        and dispatcher_env["PRESERVED"] == "yes"
        and ambient["PYTHONPYCACHEPREFIX"] == "/ambient/cache"
    )


check(
    "runner isolates syntax bytecode without leaking a cache prefix to ordinary stages",
    _stage_environment_isolated,
)

TIMING_SCRIPT = ROOT / "scripts" / "ci_timing.py"
TIMING_SPEC = importlib.util.spec_from_file_location("ci_timing_inventory", TIMING_SCRIPT)
assert TIMING_SPEC is not None and TIMING_SPEC.loader is not None
TIMING_MODULE = importlib.util.module_from_spec(TIMING_SPEC)
TIMING_SPEC.loader.exec_module(TIMING_MODULE)
check(
    "timing and sharding share the exact canonical inventory",
    MODULE.STAGES == TIMING_MODULE.STAGES
    and MODULE.inventory_digest() == TIMING_MODULE.inventory_digest(),
)
check(
    "sharding module import does not chmod its own source",
    "os.chmod(Path(__file__).resolve()" not in SCRIPT.read_text(encoding="utf-8"),
)


def _workflow_preflight_contract() -> bool:
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    required = (
        "  preflight:\n",
        "      - name: committed diff hygiene\n",
        "    needs: [preflight, quality, shard]\n",
        "          PREFLIGHT_RESULT: ${{ needs.preflight.result }}\n",
        "          SHARD_RESULT: ${{ needs.shard.result }}\n",
        '          if [[ "${PREFLIGHT_RESULT}" != success ]]; then\n',
        '            --producer-result "${SHARD_RESULT}"\n',
    )
    return (
        all(workflow.count(value) == 1 for value in required)
        and workflow.count("        run: ./scripts/ci-diff-check.sh\n") == 1
        and workflow.count("    needs: [preflight]\n") == 2
    )


check(
    "workflow gates all shards on one preflight and aggregate on all required producer results",
    _workflow_preflight_contract,
)



def _quality_workflow_contract() -> bool:
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    quality = workflow.split("  quality:\n", 1)[1].split("  shard:\n", 1)[0]
    return all(value in quality for value in (
        "    needs: [preflight]\n",
        "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "persist-credentials: false",
        "inputs.head_sha || github.event.pull_request.head.sha",
        'RUFF_NO_CACHE: "true"',
        '"$QUALITY_VENV/bin/python" -m pip --isolated install --no-cache-dir -r requirements-dev.txt',
        '"$QUALITY_VENV/bin/ruff" check .',
        '"$QUALITY_VENV/bin/mypy"',
    )) and "          QUALITY_RESULT: ${{ needs.quality.result }}\n" in workflow


def _quality_aggregate_status(result: str) -> bool:
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    start = workflow.index('          if [[ "${QUALITY_RESULT}" != success ]]; then\n')
    stop = workflow.index("          fi\n", start) + len("          fi\n")
    guard = workflow[start:stop]
    environment = dict(os.environ, QUALITY_RESULT=result)
    observed = subprocess.run(["bash", "-c", guard], env=environment, capture_output=True, check=False)
    return observed.returncode == (0 if result == "success" else 1)


check("quality job uses pinned tools at the immutable head without source caches", _quality_workflow_contract)
for quality_result in ("success", "failure", "cancelled", "skipped", ""):
    check(
        f"aggregate quality guard handles {quality_result or 'missing'} result",
        lambda result=quality_result: _quality_aggregate_status(result),
    )


def _stage_manifest_announcements() -> list[str]:
    manifest_script = ROOT / "scripts" / "ci_stages.py"
    content = manifest_script.read_bytes()
    pattern = MODULE.re.compile(rb'''Stage\(\s*"[^"]+",\s*"([^"]+)",''')
    return [m.group(1).decode("utf-8") for m in pattern.finditer(content)]


check(
    "stage manifest announcements match canonical 26 stages exactly",
    _stage_manifest_announcements() == [s.announcement for s in MODULE.STAGES],
)


# 2. Receipt Factory and Validation
def valid_receipt(shard_id: str = "other-a", outcome: str = "passed", failed_index: int = 2) -> dict[str, Any]:
    expected = list(MODULE.SHARDS[shard_id])
    if outcome == "passed":
        observed = list(expected)
    else:
        observed = list(expected[:failed_index])
    stage_durations = [
        {"id": stage_id, "duration_seconds": 0.05}
        for stage_id in observed
    ]
    return {
        "schema_version": 3,
        "kind": "agy-worker-ci-shard-receipt",
        "head_sha": "a" * 40,
        "inventory_sha256": MODULE.inventory_digest(),
        "shard_id": shard_id,
        "expected_stage_ids": expected,
        "observed_stage_ids": observed,
        "expected_case_ids": [case for stage in expected for case in STAGE_MODULE.stage_case_ids(stage)],
        "observed_case_ids": [case for stage in observed for case in STAGE_MODULE.stage_case_ids(stage)] if outcome == "passed" else [],
        "stage_durations": stage_durations,
        "outcome": outcome,
        "integrity": {
            "signed": False,
            "tamper_evident": False,
            "statement": MODULE.INTEGRITY_STATEMENT,
        },
    }


def receipt_rejected(receipt: dict[str, Any], expected_head: str = "a" * 40) -> bool:
    try:
        MODULE.validate_receipt(receipt, expected_head, MODULE.inventory_digest())
    except MODULE.ShardingError:
        return True
    return False


def legacy_receipt(shard_id: str, version: int) -> dict[str, Any]:
    receipt = valid_receipt(shard_id)
    receipt["schema_version"] = version
    receipt.pop("expected_case_ids")
    receipt.pop("observed_case_ids")
    if version == 1:
        receipt.pop("stage_durations")
    return receipt


for legacy_version in (1, 2):
    check(f"standalone validator rejects historical receipt v{legacy_version}",
          receipt_rejected(legacy_receipt("other-a", legacy_version)))


for shard in tuple(MODULE.SHARDS):
    rec = valid_receipt(shard)
    check(f"valid passed receipt for {shard} validates", not receipt_rejected(rec))
    failed_rec = valid_receipt(shard, "failed", 1)
    check(f"valid failed receipt for {shard} validates", not receipt_rejected(failed_rec))

passed_receipt = valid_receipt("other-a")
failed_receipt = valid_receipt("other-a", "failed", 3)

for label, mutate in (
    ("extra root field is rejected", lambda r: r.__setitem__("path", "/private/example")),
    ("missing root field is rejected", lambda r: r.pop("shard_id")),
    ("wrong schema_version is rejected", lambda r: r.__setitem__("schema_version", 4)),
    ("wrong kind is rejected", lambda r: r.__setitem__("kind", "wrong-kind")),
    ("malformed head_sha is rejected", lambda r: r.__setitem__("head_sha", "A" * 40)),
    ("short head_sha is rejected", lambda r: r.__setitem__("head_sha", "a" * 39)),
    ("mismatched head_sha is rejected", lambda r: r.__setitem__("head_sha", "b" * 40)),
    ("malformed inventory_sha256 is rejected", lambda r: r.__setitem__("inventory_sha256", "Z" * 64)),
    ("mismatched inventory_sha256 is rejected", lambda r: r.__setitem__("inventory_sha256", "b" * 64)),
    ("unknown shard_id is rejected", lambda r: r.__setitem__("shard_id", "unknown-shard")),
    ("expected_stage_ids mismatch is rejected", lambda r: r.__setitem__("expected_stage_ids", ["diff-hygiene"])),
    ("reordered expected_stage_ids is rejected", lambda r: r["expected_stage_ids"].reverse()),
    ("passed outcome with missing observed stage is rejected", lambda r: r["observed_stage_ids"].pop()),
    ("passed outcome with reordered observed stages is rejected", lambda r: r["observed_stage_ids"].reverse()),
    ("failed outcome with empty observed stages is rejected", lambda r: (r.__setitem__("observed_stage_ids", []), r.__setitem__("stage_durations", []))),
    ("failed outcome with non-prefix observed stages is rejected", lambda r: (r.__setitem__("observed_stage_ids", ["qa-gate"]), r.__setitem__("stage_durations", [{"id": "qa-gate", "duration_seconds": 0.1}]))),
    ("invalid outcome value is rejected", lambda r: r.__setitem__("outcome", "cancelled")),
    ("tampered integrity block is rejected", lambda r: r["integrity"].update(signed=True)),
    ("tampered integrity statement is rejected", lambda r: r["integrity"].update(statement="changed")),
    ("missing stage_durations is rejected", lambda r: r.pop("stage_durations")),
    ("stage_durations not list is rejected", lambda r: r.__setitem__("stage_durations", "bad")),
    ("stage_durations count mismatch is rejected", lambda r: r["stage_durations"].pop()),
    ("stage_durations extra key is rejected", lambda r: r["stage_durations"][0].update(extra="val")),
    ("stage_durations missing key is rejected", lambda r: r["stage_durations"][0].pop("duration_seconds")),
    ("stage_durations wrong stage ID is rejected", lambda r: r["stage_durations"][0].update(id="wrong-stage")),
    ("stage_durations reordered is rejected", lambda r: r["stage_durations"].reverse()),
    ("stage_durations negative duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds=-1.0)),
    ("stage_durations boolean duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds=True)),
    ("stage_durations NaN duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds=float("nan"))),
    ("stage_durations inf duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds=float("inf"))),
    ("stage_durations huge integer duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds=10**309)),
    ("stage_durations string duration is rejected", lambda r: r["stage_durations"][0].update(duration_seconds="0.5")),
):
    candidate = copy.deepcopy(failed_receipt if "failed outcome with non-prefix" in label or "failed outcome with empty" in label else passed_receipt)
    mutate(candidate)
    check(label, receipt_rejected(candidate))

complete_failed_receipt = copy.deepcopy(passed_receipt)
complete_failed_receipt["outcome"] = "failed"
check(
    "failed outcome may observe every stage when the final stage fails",
    not receipt_rejected(complete_failed_receipt),
)


def _huge_duration_cli_rejected() -> bool:
    with tempfile.TemporaryDirectory() as temp_dir:
        receipt_path = Path(temp_dir) / "huge-duration.json"
        candidate = copy.deepcopy(passed_receipt)
        candidate["stage_durations"][0]["duration_seconds"] = 10**309
        receipt_path.write_text(json.dumps(candidate), encoding="utf-8")
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-S",
                "-B",
                os.fspath(SCRIPT),
                "validate-receipt",
                os.fspath(receipt_path),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return (
            result.returncode == 1
            and result.stdout == b""
            and result.stderr == b"ci sharding error: invalid stage duration at index 0\n"
            and b"Traceback" not in result.stderr
            and os.fspath(receipt_path).encode() not in result.stderr
        )


check(
    "validate-receipt CLI rejects huge integer duration without traceback or path",
    _huge_duration_cli_rejected,
)

for forbidden in ("command", "environment", "logs", "credential", "provider", "account", "timestamp", "hostname", "cost", "path"):
    check(f"receipt schema excludes {forbidden}", forbidden not in json.dumps(passed_receipt, sort_keys=True).lower())


privacy_receipts = []
for shard_id, stage_ids in MODULE.SHARDS.items():
    nonce = "d" * 64
    raw = b"".join(
        f"@@agy-worker-ci-shard:{nonce}:{MODULE.STAGE_MAP[stage_id]}\n".encode()
        + b"".join(
            f"@@agy-worker-ci-case:{nonce}:{stage_id}:{identity}\n".encode()
            for identity in STAGE_MODULE.stage_case_ids(stage_id)
        )
        for stage_id in stage_ids
    )
    return_code, observed_receipt = MODULE.observe_stream(
        io.BytesIO(raw), lambda: 0, "a" * 40, shard_id, nonce, io.BytesIO(),
    )
    privacy_receipts.append(observed_receipt)
    case_fields = observed_receipt["expected_case_ids"] + observed_receipt["observed_case_ids"]
    serialized_cases = json.dumps(case_fields).lower()
    check(
        f"observer receipt case fields contain only neutral identities for {shard_id}",
        return_code == 0
        and len(case_fields) == 2 * sum(len(STAGE_MODULE.stage_case_ids(stage)) for stage in stage_ids)
        and all(MODULE.re.fullmatch(r"dispatcher(?:-remediation)?:[0-9a-f]{64}", identity) for identity in case_fields)
        and not any(word in serialized_cases for word in ("command", "environment", "logs", "credential", "provider", "account", "timestamp", "hostname", "cost", "path"))
        and not any(label in serialized_cases for stage in stage_ids for label in STAGE_MODULE.CASE_LABELS.get(stage, ())),
    )
check("all seven observer-produced neutral receipt fields still aggregate", lambda: (
    MODULE.validate_aggregate_receipts(privacy_receipts, "a" * 40) or True))


def _shell_success_emits_neutral_completion() -> bool:
    source = (ROOT / "tests/test-agy-worker.sh").read_text(encoding="utf-8")
    body = source.split("ok() {\n", 1)[1].split("\n}\n", 1)[0]
    label = STAGE_MODULE.CASE_LABELS["dispatcher-a"][0]
    nonce = "d" * 64
    with tempfile.TemporaryDirectory() as temporary:
        result = subprocess.run(
            ["bash", "-c", 'ROOT="$1"; TMP="$2"; pass=0\nok() {\n' + body + '\n}\nok "$3"',
             "success-fixture", str(ROOT), temporary, label],
            env=dict(os.environ, AGY_WORKER_CI_CASE_NONCE=nonce, AGY_WORKER_CI_CASE_STAGE="dispatcher-a"),
            capture_output=True, check=False,
        )
        identity = STAGE_MODULE.case_identity("dispatcher", label)
        return (
            result.returncode == 0
            and MODULE.re.fullmatch(r"dispatcher:[0-9a-f]{64}", identity) is not None
            and result.stdout == f"  ok   {label}\n@@agy-worker-ci-case:{nonce}:dispatcher-a:{identity}\n".encode()
            and Path(temporary, "completed-cases").read_text() == label + "\n"
        )


check("actual shell success path emits a neutral case ID and keeps its human label", _shell_success_emits_neutral_completion)


# 3. Publication Security
def _publication_cases() -> bool:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        private = root / "private"
        private.mkdir(mode=0o700)
        os.chmod(private, 0o700)
        target = private / "receipt.json"
        MODULE.publish_receipt(target, passed_receipt)
        if stat.S_IMODE(target.stat().st_mode) != 0o600:
            return False
        # Overwrite attempt must fail
        try:
            MODULE.publish_receipt(target, passed_receipt)
        except MODULE.ShardingError:
            pass
        else:
            return False
        # Non-0700 parent must fail
        open_parent = root / "open"
        open_parent.mkdir(mode=0o755)
        try:
            MODULE.validate_publication_target(open_parent / "receipt.json")
        except MODULE.ShardingError:
            pass
        else:
            return False
        # Symlink target parent must fail
        symlink = root / "linked"
        symlink.symlink_to(private)
        try:
            MODULE.validate_publication_target(symlink / "receipt.json")
        except MODULE.ShardingError:
            return True
    return False


check("publication is 0600, no-overwrite, 0700-parent, and no-follow", _publication_cases)


# 4. Clean HEAD Git Binding
def _clean_head_cases() -> bool:
    inherited_ci_head = os.environ.pop("AGY_WORKER_CI_HEAD_SHA", None)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "CI Shard Test"], cwd=repo, check=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
            sha = MODULE.resolve_clean_head(repo)
            if not MODULE.COMMIT_RE.fullmatch(sha):
                return False
            tracked.write_text("dirty\n", encoding="utf-8")
            try:
                MODULE.revalidate_clean_head(repo, sha)
            except MODULE.ShardingError:
                pass
            else:
                return False
            tracked.write_text("clean\n", encoding="utf-8")
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            try:
                MODULE.resolve_clean_head(repo)
            except MODULE.ShardingError:
                return True
        return False
    finally:
        if inherited_ci_head is not None:
            os.environ["AGY_WORKER_CI_HEAD_SHA"] = inherited_ci_head


check("HEAD binding accepts clean Git and rejects dirty tracked/untracked bytes", _clean_head_cases)


# 5. Stream Observation and Shard Runner
NONCE = "e" * 64


def observed_shard(
    shard_id: str, return_code: int, count: int, spoof_stdout: bool = False
) -> tuple[int, dict[str, Any]]:
    lines: list[bytes] = []
    stages = MODULE.SHARDS[shard_id]
    if spoof_stdout:
        lines.append(f"==> {MODULE.STAGE_MAP[stages[0]]}\n".encode())
    for s in stages[:count]:
        ann = MODULE.STAGE_MAP[s]
        lines.append(f"==> {ann}\n".encode())
        lines.append(f"@@agy-worker-ci-shard:{NONCE}:{ann}\n".encode())
        for case in STAGE_MODULE.stage_case_ids(s):
            lines.append(f"@@agy-worker-ci-case:{NONCE}:{s}:{case}\n".encode())
    raw = b"".join(lines)
    return MODULE.observe_stream(
        io.BytesIO(raw), lambda: return_code, "c" * 40, shard_id, NONCE, io.BytesIO()
    )


def _successful_shard_observation() -> bool:
    for shard_id, stages in MODULE.SHARDS.items():
        rc, rec = observed_shard(shard_id, 0, len(stages))
        if rc != 0 or rec["outcome"] != "passed" or rec["observed_stage_ids"] != list(stages):
            return False
    return True


check("observer records all stages for successful shard run", _successful_shard_observation)


def _failed_shard_observation() -> bool:
    rc, rec = observed_shard("other-a", 1, 3)
    return rc == 1 and rec["outcome"] == "failed" and rec["observed_stage_ids"] == list(MODULE.SHARDS["other-a"][:3])


check("observer records prefix up to failed stage on shard failure", _failed_shard_observation)
check(
    "observer preserves a failed receipt when the final stage fails",
    lambda: observed_shard("other-a", 1, len(MODULE.SHARDS["other-a"]))[1]["outcome"]
    == "failed",
)
check(
    "ordinary stdout cannot spoof shard control marker",
    lambda: observed_shard("dispatcher-a", 0, 1, spoof_stdout=True)[1]["outcome"] == "passed",
)


def _duplicate_control_rejected() -> bool:
    ann = MODULE.STAGE_MAP[MODULE.SHARDS["dispatcher-a"][0]]
    raw = (
        f"@@agy-worker-ci-shard:{NONCE}:{ann}\n"
        f"@@agy-worker-ci-shard:{NONCE}:{ann}\n"
    ).encode()
    try:
        MODULE.observe_stream(
            io.BytesIO(raw), lambda: 1, "c" * 40, "dispatcher-a", NONCE, output=io.BytesIO()
        )
    except MODULE.ShardingError:
        return True
    return False


check("duplicate shard control marker is rejected", _duplicate_control_rejected)


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def _deterministic_stage_durations() -> bool:
    stages = MODULE.SHARDS["other-a"][:3]
    raw = b"ordinary output\n" + b"".join(
        f"@@agy-worker-ci-shard:{NONCE}:{MODULE.STAGE_MAP[stage_id]}\n".encode()
        for stage_id in stages
    )
    output = io.BytesIO()
    return_code, receipt = MODULE.observe_stream(
        io.BytesIO(raw),
        lambda: 1,
        "c" * 40,
        "other-a",
        NONCE,
        output,
        clock=FakeClock([10.0, 11.25, 13.75, 14.5]),
    )
    return (
        return_code == 1
        and output.getvalue() == b"ordinary output\n"
        and receipt["schema_version"] == 3
        and receipt["stage_durations"]
        == [
            {"id": stages[0], "duration_seconds": 1.25},
            {"id": stages[1], "duration_seconds": 2.5},
            {"id": stages[2], "duration_seconds": 0.75},
        ]
    )


check(
    "observer preserves sixth-positional output and records fake-clock intervals",
    _deterministic_stage_durations,
)


# 6. Aggregate Verification
def all_seven_passed_receipts(head_sha: str = "a" * 40) -> list[dict[str, Any]]:
    res = []
    for shard in tuple(MODULE.SHARDS):
        rec = valid_receipt(shard)
        rec["head_sha"] = head_sha
        res.append(rec)
    return res


valid_aggregate = all_seven_passed_receipts()
check("valid seven-shard aggregate passes validation", lambda: (MODULE.validate_aggregate_receipts(valid_aggregate, "a" * 40) or True))


def aggregate_rejected(receipts: list[dict[str, Any]], expected_head: str = "a" * 40) -> bool:
    try:
        MODULE.validate_aggregate_receipts(receipts, expected_head, MODULE.inventory_digest())
    except MODULE.ShardingError:
        return True
    return False


legacy_aggregate = [legacy_receipt(shard, 2) for shard in MODULE.SHARDS]
check(
    "same-run aggregate rejects otherwise valid legacy receipt v1 artifacts",
    lambda: aggregate_rejected(legacy_aggregate),
)


check("missing shard receipt (3 receipts) is rejected", aggregate_rejected(valid_aggregate[:3]))

duplicate_shard_set = copy.deepcopy(valid_aggregate)
duplicate_shard_set[-1] = copy.deepcopy(valid_aggregate[-2])
check("duplicate shard receipt in aggregate is rejected", aggregate_rejected(duplicate_shard_set))

failed_shard_set = copy.deepcopy(valid_aggregate)
failed_shard_set[0] = valid_receipt("dispatcher-a", "failed", 1)
check("aggregate with a failed shard receipt is rejected", aggregate_rejected(failed_shard_set))

wrong_sha_set = copy.deepcopy(valid_aggregate)
wrong_sha_set[1]["head_sha"] = "b" * 40
check("aggregate with mismatched head SHA is rejected", aggregate_rejected(wrong_sha_set))

wrong_inv_set = copy.deepcopy(valid_aggregate)
wrong_inv_set[0]["inventory_sha256"] = "c" * 64
check("aggregate with mismatched inventory SHA is rejected", aggregate_rejected(wrong_inv_set))


def _write_receipt_tree(root: Path) -> list[Path]:
    files: list[Path] = []
    for rec in valid_aggregate:
        sub = root / f"shard-receipt-{rec['shard_id']}"
        sub.mkdir(mode=0o700)
        path = sub / f"{rec['shard_id']}.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        files.append(path)
    return files


def _valid_directory_aggregate() -> bool:
    with tempfile.TemporaryDirectory() as temp_dir:
        receipts_dir = Path(temp_dir) / "receipts"
        receipts_dir.mkdir(mode=0o700)
        _write_receipt_tree(receipts_dir)
        MODULE.verify_aggregate(receipts_dir, "a" * 40, "success")
        return True


check("verify_aggregate accepts exactly seven successful bound artifacts", _valid_directory_aggregate)


def _producer_results_fail_closed() -> bool:
    with tempfile.TemporaryDirectory() as temp_dir:
        receipts_dir = Path(temp_dir) / "receipts"
        receipts_dir.mkdir(mode=0o700)
        _write_receipt_tree(receipts_dir)
        for result in ("failure", "cancelled", "skipped", ""):
            try:
                MODULE.verify_aggregate(receipts_dir, "a" * 40, result)
            except MODULE.ShardingError:
                continue
            return False
    return True


check("failed, cancelled, skipped, and missing producer results fail closed", _producer_results_fail_closed)


def _artifact_tree_rejected(mutate: Callable[[Path, list[Path]], None]) -> bool:
    with tempfile.TemporaryDirectory() as temp_dir:
        receipts_dir = Path(temp_dir) / "receipts"
        receipts_dir.mkdir(mode=0o700)
        files = _write_receipt_tree(receipts_dir)
        mutate(receipts_dir, files)
        try:
            MODULE.verify_aggregate(receipts_dir, "a" * 40, "success")
        except MODULE.ShardingError:
            return True
    return False


def _replace_duration_with_huge_integer(_root: Path, files: list[Path]) -> None:
    receipt = json.loads(files[0].read_text(encoding="utf-8"))
    receipt["stage_durations"][0]["duration_seconds"] = 10**309
    files[0].write_text(json.dumps(receipt), encoding="utf-8")


check(
    "aggregate artifact rejects huge integer duration through ShardingError",
    lambda: _artifact_tree_rejected(_replace_duration_with_huge_integer),
)


check(
    "duplicate extra receipt artifact is rejected",
    lambda: _artifact_tree_rejected(
        lambda root, files: (root / "duplicate.json").write_bytes(files[0].read_bytes())
    ),
)
check(
    "unexpected non-JSON artifact is rejected",
    lambda: _artifact_tree_rejected(
        lambda root, files: (root / "unexpected.txt").write_text("x", encoding="utf-8")
    ),
)
check(
    "malformed receipt JSON is rejected",
    lambda: _artifact_tree_rejected(lambda root, files: files[0].write_text("{", encoding="utf-8")),
)
check(
    "duplicate receipt JSON key is rejected",
    lambda: _artifact_tree_rejected(
        lambda root, files: files[0].write_text(
            '{"schema_version":2,' + json.dumps(valid_aggregate[0])[1:], encoding="utf-8"
        )
    ),
)
check(
    "oversized receipt artifact is rejected",
    lambda: _artifact_tree_rejected(
        lambda root, files: files[0].write_bytes(b"x" * (MODULE.MAX_RECEIPT_BYTES + 1))
    ),
)


def _replace_with_symlink(root: Path, files: list[Path]) -> None:
    target = root / "target.json"
    target.write_bytes(files[0].read_bytes())
    files[0].unlink()
    files[0].symlink_to(target)


check("symlink receipt artifact is rejected", lambda: _artifact_tree_rejected(_replace_with_symlink))


# 7. Shell Wrapper Argument Rejection
invalid_cli = subprocess.run(
    ["./scripts/ci-offline.sh", "--invalid"], cwd=ROOT,
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("ci-offline.sh rejects --invalid", invalid_cli.returncode == 2 and b"rejected arguments" in invalid_cli.stderr)

invalid_shard = subprocess.run(
    ["./scripts/ci-offline.sh", "--shard", "invalid-shard"], cwd=ROOT,
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("ci-offline.sh rejects unknown shard ID", invalid_shard.returncode == 2 and b"rejected arguments" in invalid_shard.stderr)

missing_shard_arg = subprocess.run(
    ["./scripts/ci-offline.sh", "--shard"], cwd=ROOT,
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("ci-offline.sh rejects missing shard argument", missing_shard_arg.returncode == 2 and b"rejected arguments" in missing_shard_arg.stderr)

duplicate_shell_shard = subprocess.run(
    ["./scripts/ci-offline.sh", "--shard", "dispatcher-a", "--shard", "other-a"],
    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("ci-offline.sh rejects duplicate shard selection", duplicate_shell_shard.returncode == 2)

duplicate_run_shard = subprocess.run(
    [
        "/usr/bin/python3", "-I", "-S", "-B", "scripts/ci_sharding.py", "run-shard",
        "--shard", "dispatcher-a", "--shard", "other-a", "--receipt", "/tmp/unused.json",
    ],
    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("run-shard CLI rejects duplicate shard selection", duplicate_run_shard.returncode != 0)

missing_producer = subprocess.run(
    [
        "/usr/bin/python3", "-I", "-S", "-B", "scripts/ci_sharding.py",
        "verify-aggregate", "--receipts-dir", "/tmp/none", "--expected-head", "a" * 40,
    ],
    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("aggregate CLI requires producer result", missing_producer.returncode == 2)

duplicate_producer = subprocess.run(
    [
        "/usr/bin/python3", "-I", "-S", "-B", "scripts/ci_sharding.py",
        "verify-aggregate", "--receipts-dir", "/tmp/none", "--expected-head", "a" * 40,
        "--producer-result", "success", "--producer-result", "success",
    ],
    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
check("aggregate CLI rejects duplicate producer result", duplicate_producer.returncode != 0)

# Case identities are completion evidence, independently of stage announcements.
def _case_stream_rejected(cases: list[str], *, nonce: str = NONCE,
                          before_stage: bool = False, returncode: int = 0) -> bool:
    stage = "dispatcher-a"
    announcement = f"@@agy-worker-ci-shard:{NONCE}:{MODULE.STAGE_MAP[stage]}\n".encode()
    records = b"".join(f"@@agy-worker-ci-case:{nonce}:{stage}:{case}\n".encode() for case in cases)
    raw = records + announcement if before_stage else announcement + records
    try:
        MODULE.observe_stream(io.BytesIO(raw), lambda: returncode, "c" * 40,
                              stage, NONCE, io.BytesIO())
    except MODULE.ShardingError:
        return True
    return False


case_ids = list(STAGE_MODULE.stage_case_ids("dispatcher-a"))
for case_label, mutated_cases in (
    ("omitted", case_ids[:-1]),
    ("duplicated", case_ids + case_ids[-1:]),
    ("unassigned", case_ids + ["dispatcher:unassigned new assertion"]),
    ("renamed", case_ids[:-1] + ["dispatcher:renamed assertion"]),
    ("wrong partition", case_ids[:-1] + [STAGE_MODULE.stage_case_ids("dispatcher-b")[0]]),
):
    check(f"successful stage with {case_label} case completion fails closed",
          lambda cases=mutated_cases: _case_stream_rejected(cases))
check("case completion before stage announcement fails closed",
      lambda: _case_stream_rejected(case_ids, before_stage=True))
for fake_nonce in ("0" * 64, "short", "G" * 64):
    check(f"case completion rejects nonce {fake_nonce[:5]}",
          lambda value=fake_nonce: _case_stream_rejected(case_ids, nonce=value))
check("all completed cases cannot turn a failed stage into success",
      lambda: observed_shard("dispatcher-a", 1, 1)[1]["outcome"] == "failed")

for mutation in ("omit", "duplicate", "new"):
    receipts = copy.deepcopy(valid_aggregate)
    cases = receipts[0]["observed_case_ids"]
    if mutation == "omit": cases.pop()
    elif mutation == "duplicate": cases.append(cases[0])
    else: cases.append("dispatcher:unassigned new assertion")
    check(f"seven receipts reject {mutation} case evidence", aggregate_rejected(receipts))


def _source_mutation_rejected(relative: str, old: str, new: str) -> bool:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for source in STAGE_MODULE.SHELL_SOURCES:
            target = root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            text = (ROOT / source).read_text(encoding="utf-8")
            if source == relative:
                assert old in text
                text = text.replace(old, new, 1)
            target.write_text(text, encoding="utf-8")
        try:
            STAGE_MODULE.validate_shell_inventory(root)
        except ValueError:
            return True
    return False


shell_source = "tests/test-agy-worker.sh"
multiline_completion = "ok " + chr(92) + '\n    "unassigned multiline assertion"\nfi # part b'
check("multiline source fixture contains a real shell continuation", lambda: (
    multiline_completion.encode().startswith(b"ok " + bytes((92, 10)))))
for description, old, new in (
    ("literal rename in unselected part", 'ok "installer copies the canonical bundle and records the exact clone path"', 'ok "renamed installer assertion"'),
    ("new literal in unselected part", 'fi # part b', 'ok "unassigned new assertion"\nfi # part b'),
    ("duplicate declaration", 'fi # part b', 'ok "installer copies the canonical bundle and records the exact clone path"\nfi # part b'),
    ("missing declaration", '    ok "installer copies the canonical bundle and records the exact clone path"', ':'),
    ("helper completion template rename", 'ok "$name (exit $got)"', 'ok "$name changed (exit $got)"'),
    ("loop completion template rename", 'ok "$preamble_workflow/$preamble_mode provider-bound preamble and existing contract order"', 'ok "$preamble_workflow/$preamble_mode changed contracts"'),
    ("unknown wrapper invocation", 'fi # part b', 'expect_new_assertion "unassigned literal"\nfi # part b'),
    ("subshell completion", 'fi # part b', '(ok "unassigned subshell assertion")\nfi # part b'),
    ("pipeline completion", 'fi # part b', ': | ok "unassigned pipeline assertion"\nfi # part b'),
    ("multiline completion", 'fi # part b', multiline_completion),
    ("quoted completion command", 'fi # part b', '"ok" "unassigned new assertion"\nfi # part b'),
    ("escaped completion command", 'fi # part b', 'o\\k "unassigned new assertion"\nfi # part b'),
    ("wrapped completion", 'fi # part b', 'command ok "unassigned wrapped assertion"\nfi # part b'),
    ("unknown assertion wrapper", 'fi # part b', 'new_check() { ok "new assertion wrapper"; }\nnew_check\nfi # part b'),
    ("unknown sourced subshell", 'fi # part b', '(. "$ROOT/tests/new_cases.sh")\nfi # part b'),
    ("unknown sourced pipeline", 'fi # part b', ': | source "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("unknown sourced file", 'fi # part b', '. "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("quoted source command", 'fi # part b', '"source" "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("escaped source command", 'fi # part b', 's\\ource "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("assignment-prefixed source command", 'fi # part b', 'FOO=x source "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("multiple assignment and builtin source prefixes", 'fi # part b', 'FOO=x BAR=y builtin source "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("source behind command prefix options", 'fi # part b', 'command -p source "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("dot source behind builtin prefix options", 'fi # part b', 'builtin -- . "$ROOT/tests/new_cases.sh"\nfi # part b'),
    ("case-producing loop domain addition", 'for capability_case in resume continue scoped-repair effort no-effort restart; do', 'for capability_case in resume continue scoped-repair effort no-effort restart new-case; do'),
    ("case-producing loop domain omission", 'for capability_case in resume continue scoped-repair effort no-effort restart; do', 'for capability_case in resume continue scoped-repair effort no-effort; do'),
    ("nested case-producing loop domain change", 'for preamble_mode in whole scoped; do', 'for preamble_mode in whole scoped extra; do'),
    ("helper public-label third argument rename", 'project continuation rejects a 4097-byte marker before state replacement or provider call', 'renamed oversized marker assertion'),
    ("helper non-label argument change", 'expect_exit "installer accepts replacement metacharacters in clone path" 0 "$rc"', 'expect_exit "installer accepts replacement metacharacters in clone path" 1 "$rc"'),
    ("source argument addition", '. "$ROOT/tests/agy_worker_project_lifecycle_cases.sh"', '. "$ROOT/tests/agy_worker_project_lifecycle_cases.sh" extra'),
    ("unsupported quoted declaration shape", 'fi # part b', '"ok unassigned malformed assertion\nfi # part b'),
):
    check(f"source guard rejects {description}",
          lambda a=old, b=new: _source_mutation_rejected(shell_source, a, b))

artifact_fixture_entry = '    "three-key-direct": {"schema_version": 5, "kind": "agy-worker-selection", "selection_mode": "exact-model"},'
artifact_fixture_mutations = (
    ("new literal fixture key", artifact_fixture_entry, artifact_fixture_entry + '\n    "new-unassigned": {"schema_version": 5},'),
    ("renamed literal fixture key", artifact_fixture_entry, artifact_fixture_entry.replace("three-key-direct", "renamed-unassigned")),
    ("omitted literal fixture key", artifact_fixture_entry, ""),
    ("duplicated literal fixture key", artifact_fixture_entry, artifact_fixture_entry + "\n" + artifact_fixture_entry),
    ("dynamic fixture key", artifact_fixture_entry, artifact_fixture_entry.replace('"three-key-direct"', 'f"three-key-{\'direct\'}"')),
    ("new retired schema fixture", "for schema in (1, 2, 3, 4):", "for schema in (1, 2, 3, 4, 6):"),
    ("omitted retired schema fixture", "for schema in (1, 2, 3, 4):", "for schema in (1, 2, 3):"),
    ("duplicated retired schema fixture", "for schema in (1, 2, 3, 4):", "for schema in (1, 2, 3, 4, 4):"),
    ("changed retired fixture expansion", 'cases[f"retired-{schema}"]', 'cases[f"old-{schema}"]'),
    ("changed fixture filename expansion", 'root / f"{name}.json"', 'root / f"renamed-{name}.json"'),
    ("additional fixture writer", 'for name, value in cases.items():', '(root / "new-unassigned.json").write_text("{}")\nfor name, value in cases.items():'),
    ("unknown fixture producer header", 'python3 -B - "$VALID_DIRECT_RECORD" "$VALID_DEFAULT_RECORD" "$ARTIFACT_CASES"', 'python3 -I -B - "$VALID_DIRECT_RECORD" "$VALID_DEFAULT_RECORD" "$ARTIFACT_CASES"'),
    ("malformed fixture producer", 'cases = {\n    "three-key-direct"', 'cases = {\n    ?"three-key-direct"'),
)
for description, old, new in artifact_fixture_mutations:
    check(f"source guard rejects {description} in unselected part a",
          lambda a=old, b=new: _source_mutation_rejected(shell_source, a, b))
check("source guard derives all 15 fixture filename labels before selection", lambda: (
    tuple(label for part, kind, label in STAGE_MODULE.shell_declarations(
        (ROOT / shell_source).read_text(encoding="utf-8"), "common") if kind == "fixture")
    == tuple(label for label in STAGE_MODULE.CASE_LABELS["dispatcher-a"]
             if label.startswith("runtime validator rejects "))))
check("source guard accepts both complete real shell sources", lambda: (
    STAGE_MODULE.validate_shell_inventory(ROOT) is None))
check("source guard accepts the existing non-command dot pattern", lambda: (
    STAGE_MODULE.shell_declarations("grep -q .\n", "common") == ()))
check("source guard covers sourced lifecycle assertions", lambda: _source_mutation_rejected(
    "tests/agy_worker_project_lifecycle_cases.sh",
    'ok "project workflow exposes pending Codex-owned verification without changing resume semantics"',
    'ok "renamed sourced assertion"'))


def _digest_binds_case_assignment() -> bool:
    before = MODULE.inventory_digest()
    original = STAGE_MODULE.CASE_LABELS["dispatcher-a"]
    try:
        STAGE_MODULE.CASE_LABELS["dispatcher-a"] = original[::-1]
        return before != MODULE.inventory_digest()
    finally:
        STAGE_MODULE.CASE_LABELS["dispatcher-a"] = original


check("case identity/order assignment changes inventory digest", _digest_binds_case_assignment)


def _digest_binds_case_identity_encoding() -> bool:
    before = MODULE.inventory_digest()
    original = STAGE_MODULE.case_identity
    try:
        STAGE_MODULE.case_identity = lambda suite, label: original(suite, label) + "0"
        return before != MODULE.inventory_digest()
    finally:
        STAGE_MODULE.case_identity = original


check("case identity encoding changes inventory digest", _digest_binds_case_identity_encoding)
check("case digest separates logical suite and label boundaries", lambda: (
    STAGE_MODULE.case_identity("dispatcher", "a:b").rsplit(":", 1)[-1]
    != STAGE_MODULE.case_identity("dispatcher:a", "b").rsplit(":", 1)[-1]))


def _digest_binds_fixture_producer() -> bool:
    before = MODULE.inventory_digest()
    original = STAGE_MODULE.SELECTION_ARTIFACT_PRODUCER
    try:
        STAGE_MODULE.SELECTION_ARTIFACT_PRODUCER = original.replace(
            'cases[f"retired-{schema}"]', 'cases[f"old-{schema}"]')
        return before != MODULE.inventory_digest()
    finally:
        STAGE_MODULE.SELECTION_ARTIFACT_PRODUCER = original


check("fixture producer structure changes inventory digest", _digest_binds_fixture_producer)
check("409 explicit case identities are unique and assigned", lambda: (
    len(STAGE_MODULE.all_case_ids()) == len(set(STAGE_MODULE.all_case_ids())) == 409))
check("all seven receipts stay within the existing fixed artifact size bound", lambda: all(
    len(MODULE.canonical_bytes(receipt)) + 1 <= MODULE.MAX_RECEIPT_BYTES for receipt in valid_aggregate))


def _remediation_declaration_mutation_rejected(mutation: str) -> bool:
    source = (ROOT / "tests/test-agy-worker-remediation.py").read_text(encoding="utf-8")
    label = STAGE_MODULE.CASE_LABELS["dispatcher-remediation-a"][0]
    if mutation == "rename":
        source = source.replace(label, "unassigned new remediation assertion", 1)
    elif mutation == "duplicate":
        source = source.replace('if tuple(DECLARED_LABELS) != CANONICAL_LABELS:', f'check({label!r}, lambda: None)\nif tuple(DECLARED_LABELS) != CANONICAL_LABELS:', 1)
    else:
        source = source.replace('    DECLARED_LABELS.append(label)', '    return\n    DECLARED_LABELS.append(label)', 1)
    command = (
        "import sys; sys.argv=['test', '--ci-part', 'c', '--inventory-only']; "
        "exec(compile(" + repr(source) + ", " + repr(str(ROOT / 'tests/test-agy-worker-remediation.py'))
        + ", 'exec'), {'__name__':'__main__', '__file__':" + repr(str(ROOT / 'tests/test-agy-worker-remediation.py')) + "})"
    )
    result = subprocess.run(["/usr/bin/python3", "-I", "-S", "-B", "-c", command],
                            capture_output=True, check=False)
    return result.returncode != 0 and b"declaration inventory" in result.stderr


for mutation in ("rename", "duplicate", "omit"):
    check(f"remediation registers all declarations before filtering: {mutation}",
          lambda value=mutation: _remediation_declaration_mutation_rejected(value))

def _failed_callback_emits_no_completion() -> bool:
    import ast
    from types import SimpleNamespace

    source = (ROOT / "tests/test-agy-worker-remediation.py").read_text(encoding="utf-8")
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == "check")
    label = STAGE_MODULE.CASE_LABELS["dispatcher-remediation-a"][0]
    emitted: list[str] = []
    namespace: dict[str, Any] = {
        "CHECKS_RUN": 0, "DECLARED_LABELS": [], "COMPLETED_LABELS": [],
        "CANONICAL_LABELS": (label,), "PART_LABELS": (label,),
        "SELECTION": SimpleNamespace(inventory_only=False), "SELECTED_GROUP": None,
        "FOCUSED_CHECK": None, "emit_case_completion": emitted.append,
        "case_identity": STAGE_MODULE.case_identity,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "callback-fixture", "exec"), namespace)
    def fail_action() -> None:
        raise RuntimeError("assertion failed")
    try:
        namespace["check"](label, fail_action)
    except AssertionError:
        return not emitted and not namespace["COMPLETED_LABELS"] and namespace["CHECKS_RUN"] == 0
    return False


check("failed callback emits no success case control record", _failed_callback_emits_no_completion)
check("heredoc embedded fake assertions are data, not source declarations", lambda: (
    STAGE_MODULE.shell_declarations("cat <<'DATA'\nok \"fake assertion\"\nDATA\n", "common") == ()))
check("source guard rejects inline conditional unassigned assertion", lambda: _source_mutation_rejected(
    shell_source, 'fi # part b', 'if ok "unassigned inline assertion"; then :; fi\nfi # part b'))
check("source guard rejects malformed assertion declaration", lambda: _source_mutation_rejected(
    shell_source, 'fi # part b', 'ok\nfi # part b'))

print()
print(f"PASSED: {passed} tests")
if failed:
    print(f"FAILED: {failed} tests")
    raise SystemExit(1)
