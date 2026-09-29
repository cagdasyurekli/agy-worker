#!/usr/bin/env bash
# Offline Codex package, skill-bundle, and landing-page contract tests.
set -uo pipefail

# Contract checks use Python assertions throughout this legacy shell harness.
# Keep inherited optimizer settings from silently disabling those checks.
unset PYTHONOPTIMIZE
# Repository-facing Python probes must not leave import caches behind. The dedicated
# negative-control subshell below explicitly unsets this when testing leak detection.
export PYTHONDONTWRITEBYTECODE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE/.."
CI_OFFLINE="$ROOT/scripts/ci-offline.sh"
CI_STAGES="$ROOT/scripts/ci_stages.py"
TMP="$(mktemp -d -t agyworker-packaging.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0

ok() { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail+1)); }

ci_stage_registered() {
    python3 -B - "$CI_STAGES" "$1" <<'PY'
from pathlib import Path
import sys

stages_file = Path(sys.argv[1])
cmd_str = sys.argv[2]

sys.path.insert(0, str(stages_file.parent))
import ci_stages

all_cmds = {" ".join(s.argv) for s in ci_stages.STAGES}
if cmd_str not in all_cmds:
    raise SystemExit(1)
PY
}

ground_truth_phase_contract() {
    local helper="$1" label="$2" fixture="$TMP/ground-truth-phase-$2" rc
    mkdir -p "$fixture/bin" "$fixture/home/.gemini/antigravity-cli"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'printf "%s\\n" "$*" >> "${0%/*}/../calls.log"' \
        'case "$*" in' \
        '  --version) printf "%s\\n" "1.1.16" ;;' \
        '  --help) printf "%s\\n" "  --add-dir  Directory" "  --conversation  Conversation" "  --disable-slash-commands  Disabled" "  --effort  Effort" "  --json-schema  Schema" "  --mode  Mode (plan, accept-edits)" "  --model  Model" "  --output-format  Format (stream-json)" "  --print  Prompt" "  --print-timeout  Timeout" "  --sandbox  Sandbox" ;;' \
        '  models) printf "%s\\n" "model-a" ;;' \
        '  agents) printf "%s\\n" "agent-a" ;;' \
        '  "plugin list") printf "%s\\n" "plugin-a" ;;' \
        '  *) exit 97 ;;' \
        'esac' > "$fixture/bin/agy"
    chmod +x "$fixture/bin/agy"
    printf '%s\n' '{"permissions":{"allow":["command(git)"],"ask":[],"deny":[]}}' \
        > "$fixture/home/.gemini/antigravity-cli/settings.json"

    HOME="$fixture/home" PATH="$fixture/bin:$PATH" \
    GROUND_TRUTH_LOG="$fixture/interface.log" "$helper" \
        > "$fixture/interface.out" 2> "$fixture/interface.err" || return 1
    [[ ! -s "$fixture/interface.err" ]] \
        && grep -Fxq 'interface' "$fixture/interface.out" \
        && ! grep -Fq 'account phase' "$fixture/interface.out" \
        && [[ "$(cat "$fixture/calls.log")" == $'--version\n--help' ]] \
        || return 1

    : > "$fixture/calls.log"
    HOME="$fixture/home" PATH="$fixture/bin:$PATH" \
    GROUND_TRUTH_LOG="$fixture/account.log" "$helper" --account \
        > "$fixture/account.out" 2> "$fixture/account.err" || return 1
    [[ ! -s "$fixture/account.err" ]] \
        && grep -Fxq 'account' "$fixture/account.out" \
        && grep -Fq 'models available to --model (account phase)' "$fixture/account.out" \
        && grep -Fq 'allow: [' "$fixture/account.out" \
        && [[ "$(cat "$fixture/calls.log")" == $'--version\n--help\nmodels\nagents\nplugin list' ]] \
        || return 1

    rm "$fixture/calls.log"
    HOME="$fixture/home" PATH="$fixture/bin:$PATH" \
    GROUND_TRUTH_LOG="$fixture/invalid.log" "$helper" --invalid \
        > "$fixture/invalid.out" 2> "$fixture/invalid.err"
    rc=$?
    [[ "$rc" == 64 ]] \
        && [[ ! -s "$fixture/invalid.out" ]] \
        && grep -Fxq 'usage: ground-truth.sh [--account]' "$fixture/invalid.err" \
        && [[ ! -e "$fixture/calls.log" ]]
}

echo "Codex distribution offline test suite"
echo

if python3 - "$ROOT" <<'PY'
from pathlib import Path
import os
import stat
import subprocess
import sys

root = Path(sys.argv[1])
listed = subprocess.run(
    ["git", "-C", str(root), "ls-files", "-z"],
    check=True,
    stdout=subprocess.PIPE,
).stdout.split(b"\0")
paths = {item.decode("utf-8") for item in listed if item}
for relative in sorted(paths):
    path = root / relative
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        continue
    if stat.S_ISREG(info.st_mode):
        content = path.read_bytes()
    elif stat.S_ISLNK(info.st_mode):
        content = os.readlink(path).encode("utf-8", "surrogateescape")
    else:
        continue
    forbidden = b"/Users/" + b"cagdasyurekli/"
    assert forbidden not in content, relative
PY
then
    ok "public repository sources contain no personal absolute path"
else
    bad "public repository sources contain no personal absolute path"
fi

ci_workflow_contract() {
    python3 - "$1" <<'PY'
from hashlib import sha256
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
info = path.lstat()
assert stat.S_ISREG(info.st_mode)
data = path.read_bytes()
assert sha256(data).hexdigest() == "67b5f4309e1f36898e8ca8f4b0a3ec165c5bd291f626a05dcb3ecffa0359c356"
text = data.decode("utf-8")
required = (
    "name: test\n",
    "  pull_request:\n",
    "  workflow_dispatch:\n",
    "  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}\n",
    "  cancel-in-progress: true\n",
    "permissions:\n  contents: read\n",
    "    timeout-minutes: 60\n",
    "    timeout-minutes: 10\n",
    "      base_sha:\n",
    "      head_sha:\n",
    "      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd\n        with:\n          fetch-depth: 0\n          persist-credentials: false\n          ref: ${{ github.event_name == 'workflow_dispatch' && inputs.head_sha || github.event.pull_request.head.sha }}\n",
    "          ref: ${{ github.event_name == 'workflow_dispatch' && inputs.head_sha || github.event.pull_request.head.sha }}\n",
    "      - name: committed diff hygiene\n",
    "          AGY_WORKER_CI_EVENT_NAME: ${{ github.event_name == 'workflow_dispatch' && 'push' || github.event_name }}\n",
    "          AGY_WORKER_CI_BASE_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.base_sha || github.event.pull_request.base.sha }}\n",
    "          AGY_WORKER_CI_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.head_sha || github.event.pull_request.head.sha }}\n",
    "        run: ./scripts/ci-diff-check.sh\n",
    "      - name: shard offline suite\n",
    "          RECEIPT_DIR: ${{ runner.temp }}/agyworker-shard-receipt-${{ matrix.shard }}\n",
    "          (umask 077 && mkdir \"$RECEIPT_DIR\")\n",
    "          chmod 0700 \"$RECEIPT_DIR\"\n",
    "          ./scripts/ci-offline.sh --shard \"${{ matrix.shard }}\" --receipt \"$RECEIPT_DIR/${{ matrix.shard }}.json\"\n",
    "      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n",
    "          name: shard-receipt-${{ matrix.shard }}\n",
    "          path: ${{ runner.temp }}/agyworker-shard-receipt-${{ matrix.shard }}/${{ matrix.shard }}.json\n",
    "          retention-days: 1\n",
    "  test:\n",
    "    name: test\n",
    "    if: always()\n",
    "    needs: [preflight]\n",
    "    needs: [preflight, quality, shard]\n",
    "      - name: download shard receipts\n",
    "        uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093\n",
    "          pattern: shard-receipt-*\n",
    "          path: ${{ runner.temp }}/downloaded-shard-receipts\n",
    "      - name: verify aggregate shard receipts\n",
    "          QUALITY_RESULT: ${{ needs.quality.result }}\n",
    "          SHARD_RESULT: ${{ needs.shard.result }}\n",
    "          RECEIPTS_DIR: ${{ runner.temp }}/downloaded-shard-receipts\n",
    "          /usr/bin/python3 -I -S -B scripts/ci_sharding.py verify-aggregate \\\n            --receipts-dir \"${RECEIPTS_DIR}\" \\\n            --expected-head \"${AGY_WORKER_CI_HEAD_SHA}\" \\\n            --producer-result \"${SHARD_RESULT}\"\n",
)
assert all(text.count(item) >= 1 for item in required)
assert "  push:\n" not in text
assert "git fetch" not in text
assert "run: git diff --check\n" not in text
assert "actions/checkout@v4" not in text
assert "\r" not in text
assert not text.endswith(("# timeout-minutes: 1\n", "# byte binding\n"))
assert "? if\n" not in text
assert "!policy" not in text
assert "&policy" not in text
assert "*policy" not in text
assert "continue-on-error: true" not in text
assert "mktemp -d -t agyworker-shard-receipt" not in text
assert "/tmp/agyworker-shard-receipt" not in text
assert text.count("timeout-minutes:") == 4
PY
}

workflow_checkout_policy_contract() {
    python3 - "$1" <<'PY'
from pathlib import Path
import stat
import sys

target = Path(sys.argv[1])
if target.is_file():
    workflow_files = [target]
elif target.is_dir():
    workflow_files = sorted(set(target.glob("*.yml")) | set(target.glob("*.yaml")))
else:
    raise AssertionError(f"Invalid target: {target}")

assert len(workflow_files) > 0, "No workflows found"
PINNED = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
EXPECTED_BLOCKS = {
    "test.yml": (
        f"      - uses: {PINNED}\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "          persist-credentials: false\n"
        "          ref: ${{ github.event_name == 'workflow_dispatch' && inputs.head_sha || github.event.pull_request.head.sha }}\n"
    ),
}
EXPECTED_COUNTS = {
    "test.yml": 4,
}

if target.is_dir():
    assert set(EXPECTED_BLOCKS).issubset({path.name for path in workflow_files})

for w in workflow_files:
    info = w.lstat()
    assert stat.S_ISREG(info.st_mode)
    text = w.read_text(encoding="utf-8")
    checkout_count = text.casefold().count("actions/checkout@")
    expected = EXPECTED_BLOCKS.get(w.name)
    count = EXPECTED_COUNTS.get(w.name, 1)
    if expected is None:
        assert checkout_count == 0, f"{w.name} has an ungoverned checkout reference"
        continue
    assert checkout_count == count, f"{w.name} expected {count} checkout reference(s), found {checkout_count}"
    assert text.count(expected) == count, f"{w.name} checkout block differs from policy"
    assert text.count("persist-credentials:") == count, f"{w.name} credential policy is ambiguous"
PY
}

ci_helper_contract() {
    python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys

shell = Path(sys.argv[1]).read_text(encoding="utf-8")
source = Path(sys.argv[2]).read_text(encoding="utf-8")
shell_required = (
    'exec /usr/bin/python3 -I -S -B "$script_dir/ci_diff_check.py"',
)
source_required = {
    'base + "..." + head, "--"': 1,
    '"merge-base", base, head, limit=128, overall_deadline=deadline': 1,
    'empty_tree + ".." + head, "--"': 1,
    'base + ".." + head, "--"': 1,
    '"--no-ext-diff", "--no-textconv"': 3,
    '"diff-tree",': 1,
    '"--raw",': 1,
    '"--full-index",': 1,
    '"--no-renames",': 1,
    '[GIT, "cat-file", "--batch"]': 1,
    'EXACT_BINARY_BLOBS.get(path)': 1,
    '_check_head_blob(blob)': 1,
    'deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS': 1,
    'if output_seen > stdout_limit:': 1,
    'if len(stderr_buffer) > MAX_BATCH_STDERR_BYTES:': 1,
    'or stderr_buffer': 1,
}
assert all(shell.count(item) == 1 for item in shell_required)
assert all(source.count(item) == count for item, count in source_required.items())
assert "difflib" not in source
assert "SequenceMatcher" not in source
assert "git fetch" not in shell + source
assert "shell=True" not in source
assert source.count("subprocess.Popen(") == 2
assert '"cat-file", "-s"' not in source
assert '"cat-file", "blob"' not in source
PY
}

ci_offline_contract() {
    python3 - "$1" "$ROOT/scripts/ci_stages.py" <<'PY'
from pathlib import Path
import sys

offline_text = Path(sys.argv[1]).read_text(encoding="utf-8")
stages_file = Path(sys.argv[2])

required_offline = (
    "set -eu\n",
    'exec /usr/bin/python3 -I -S -B "$root/scripts/ci_stages.py"',
    'exec /usr/bin/python3 -I -S -B "$root/scripts/ci_timing.py"',
    'exec /usr/bin/python3 -I -S -B "$root/scripts/ci_sharding.py"',
)
assert all(item in offline_text for item in required_offline)
assert "HOME" not in offline_text
assert not any(token in offline_text for token in ("curl ", "wget ", "git fetch", "agy "))

sys.path.insert(0, str(stages_file.parent))
import ci_stages

assert len(ci_stages.STAGES) == 22
assert len({s.id for s in ci_stages.STAGES}) == 22
assert set(ci_stages.SHARDS) == {"dispatcher", "dispatcher-remediation", "other-a", "other-b"}

required_stage_ids = (
    "diff-hygiene", "shell-syntax", "python-syntax", "qa-gate", "evidence-receipt",
    "evidence-report", "job-lifecycle",
    "dispatcher", "dispatcher-remediation", "provider-containment", "self-verification", "self-verification-lifecycle",
    "updater", "update-notifier",
    "delegation-policy", "workflow", "workflow-integration", "packaging",
    "doctor", "conformance", "proof-demo", "bytecode-hygiene",
)
assert tuple(s.id for s in ci_stages.STAGES) == required_stage_ids
stages_text = stages_file.read_text(encoding="utf-8")
assert "HOME" not in stages_text
assert not any(token in stages_text for token in ("curl ", "wget ", "git fetch", "agy "))
PY
}

init_ci_repo() {
    mkdir "$1"
    git -C "$1" init -q
    git -C "$1" config user.name test
    git -C "$1" config user.email test@example.com
}

run_ci_check() {
    (
        cd "$1" || exit 1
        AGY_WORKER_CI_EVENT_NAME="$2" \
            AGY_WORKER_CI_BASE_SHA="$3" \
            AGY_WORKER_CI_HEAD_SHA="$4" \
            "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
    )
}

if ci_workflow_contract "$ROOT/.github/workflows/test.yml" \
        && workflow_checkout_policy_contract "$ROOT/.github/workflows" \
        && ci_helper_contract "$ROOT/scripts/ci-diff-check.sh" \
            "$ROOT/scripts/ci_diff_check.py" \
        && ci_offline_contract "$CI_OFFLINE" \
        && [[ -x "$ROOT/scripts/ci-diff-check.sh" ]] \
        && [[ -x "$ROOT/scripts/ci_diff_check.py" ]] \
        && [[ -f "$ROOT/scripts/ci-worktree-check.sh" ]] \
        && [[ -f "$ROOT/scripts/ci_stages.py" ]] \
        && [[ -x "$ROOT/scripts/ci_timing.py" ]] \
        && [[ -x "$ROOT/scripts/ci_sharding.py" ]] \
        && [[ -x "$ROOT/scripts/ci-offline.sh" ]]; then
    ok "PR CI verifies the exact committed range, cancels stale runs, and uses the canonical offline runner"
else
    bad "PR CI verifies the exact committed range, cancels stale runs, and uses the canonical offline runner"
fi

if /usr/bin/python3 -I -S -B "$ROOT/tests/test-ci-diff-check.py"; then
    ok "CI batch reader rejects malformed, unbounded, and interrupted streams"
else
    bad "CI batch reader rejects malformed, unbounded, and interrupted streams"
fi

if /usr/bin/python3 -I -S -B "$ROOT/tests/test-ci-worktree-check.py"; then
    ok "local whitespace hygiene covers safe untracked candidates without index mutation"
else
    bad "local whitespace hygiene covers safe untracked candidates without index mutation"
fi

if /usr/bin/python3 -I -S -B "$ROOT/tests/test-ci-timing.py"; then
    ok "CI timing telemetry records monotonic wall time, validates schema, and publishes owner-private reports"
else
    bad "CI timing telemetry records monotonic wall time, validates schema, and publishes owner-private reports"
fi

if /usr/bin/python3 -I -S -B "$ROOT/tests/test-ci-sharding.py"; then
    ok "CI sharding partition invariants, receipt publication, and fail-closed aggregate validation"
else
    bad "CI sharding partition invariants, receipt publication, and fail-closed aggregate validation"
fi

workflow_mutations="$TMP/workflow-mutations"
mkdir "$workflow_mutations"
python3 - "$ROOT/.github/workflows/test.yml" "$workflow_mutations" <<'PY'
from pathlib import Path
import sys

canonical = Path(sys.argv[1]).read_bytes()
directory = Path(sys.argv[2])

def replace_once(old: bytes, new: bytes) -> bytes:
    assert canonical.count(old) == 1
    return canonical.replace(old, new)

mutations = {
    "job-if.yml": replace_once(b"  test:\n", b"  test:\n    if: false\n"),
    "step-if.yml": replace_once(b"      - name: committed diff hygiene\n        env:\n", b"      - name: committed diff hygiene\n        if: false\n        env:\n"),
    "job-continue-on-error.yml": replace_once(
        b"    timeout-minutes: 60\n",
        b"    timeout-minutes: 60\n    continue-on-error: true\n",
    ),
    "step-continue-on-error.yml": replace_once(
        b"      - name: committed diff hygiene\n        env:\n",
        b"      - name: committed diff hygiene\n        continue-on-error: true\n        env:\n",
    ),
    "step-timeout.yml": replace_once(
        b"      - name: committed diff hygiene\n        env:\n",
        b"      - name: committed diff hygiene\n        timeout-minutes: 1\n        env:\n",
    ),
    "commented-timeout.yml": canonical + b"\n# timeout-minutes: 1\n",
    "duplicate-timeout.yml": replace_once(
        b"    timeout-minutes: 60\n",
        b"    timeout-minutes: 60\n    timeout-minutes: 1\n",
    ),
    "alternate-timeout.yml": replace_once(
        b"    timeout-minutes: 60\n", b"    timeout-minutes: 1\n"
    ),
    "explicit-if.yml": canonical + b"\n? if\n: false\n",
    "tagged.yml": canonical + b"\npolicy_marker: !policy false\n",
    "anchored.yml": canonical + b"\npolicy_marker: &policy false\n",
    "alias.yml": canonical + b"\npolicy_anchor: &policy false\npolicy_marker: *policy\n",
    "single-byte.yml": b"m" + canonical[1:],
    "trailing-comment.yml": canonical + b"\n# byte binding\n",
    "crlf.yml": canonical.replace(b"\n", b"\r\n"),
}
for name, data in mutations.items():
    assert data != canonical
    (directory / name).write_bytes(data)
PY
workflow_mutations_rejected=true
for workflow in "$workflow_mutations"/*.yml; do
    if ci_workflow_contract "$workflow" 2>/dev/null; then
        workflow_mutations_rejected=false
        break
    fi
done
if [[ "$workflow_mutations_rejected" == true ]]; then
    ok "workflow policy rejects byte-level YAML and formatting mutations"
else
    bad "workflow policy rejects byte-level YAML and formatting mutations"
fi

if ! ci_workflow_contract "$TMP/missing-workflow.yml" 2>/dev/null; then
    ok "workflow policy fails closed for a missing workflow"
else
    bad "workflow policy fails closed for a missing workflow"
fi

ln -s "$ROOT/.github/workflows/test.yml" "$TMP/workflow-link.yml"
if ! ci_workflow_contract "$TMP/workflow-link.yml" 2>/dev/null; then
    ok "workflow policy fails closed for a symlinked workflow"
else
    bad "workflow policy fails closed for a symlinked workflow"
fi

mkdir "$TMP/workflow-directory.yml"
if ! ci_workflow_contract "$TMP/workflow-directory.yml" 2>/dev/null; then
    ok "workflow policy fails closed for a nonregular workflow"
else
    bad "workflow policy fails closed for a nonregular workflow"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/worktree-only.yml"
python3 - "$TMP/worktree-only.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "        run: ./scripts/ci-diff-check.sh\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "        run: git diff --check\n"), encoding="utf-8")
PY
if ! ci_workflow_contract "$TMP/worktree-only.yml" 2>/dev/null; then
    ok "workflow policy rejects a worktree-only diff check"
else
    bad "workflow policy rejects a worktree-only diff check"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/missing-diff-step.yml"
python3 - "$TMP/missing-diff-step.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "        run: ./scripts/ci-diff-check.sh\n"
assert text.count(old) == 1
path.write_text(text.replace(old, ""), encoding="utf-8")
PY
if ! ci_workflow_contract "$TMP/missing-diff-step.yml" 2>/dev/null; then
    ok "workflow policy rejects removal of the committed diff check"
else
    bad "workflow policy rejects removal of the committed diff check"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/persisted-checkout-credentials.yml"
python3 - "$TMP/persisted-checkout-credentials.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "          persist-credentials: false\n"
assert text.count(old) == 4
path.write_text(text.replace(old, "", 1), encoding="utf-8")
PY
if ! ci_workflow_contract "$TMP/persisted-checkout-credentials.yml" 2>/dev/null; then
    ok "workflow policy rejects persisted checkout credentials"
else
    bad "workflow policy rejects persisted checkout credentials"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/mutable-checkout-tag.yml"
python3 - "$TMP/mutable-checkout-tag.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
assert text.count(old) == 4
path.write_text(text.replace(old, "actions/checkout@v4", 1), encoding="utf-8")
PY
if ! ci_workflow_contract "$TMP/mutable-checkout-tag.yml" 2>/dev/null \
        && ! workflow_checkout_policy_contract "$TMP/mutable-checkout-tag.yml" 2>/dev/null; then
    ok "workflow policy rejects a mutable checkout tag"
else
    bad "workflow policy rejects a mutable checkout tag"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/different-checkout-sha.yml"
python3 - "$TMP/different-checkout-sha.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"
assert text.count(old) == 4
path.write_text(text.replace(old, "actions/checkout@1111111111111111111111111111111111111111", 1), encoding="utf-8")
PY
if ! ci_workflow_contract "$TMP/different-checkout-sha.yml" 2>/dev/null \
        && ! workflow_checkout_policy_contract "$TMP/different-checkout-sha.yml" 2>/dev/null; then
    ok "workflow policy rejects a different checkout SHA"
else
    bad "workflow policy rejects a different checkout SHA"
fi

cp "$ROOT/.github/workflows/test.yml" "$TMP/extra-unprotected-checkout.yml"
python3 - "$TMP/extra-unprotected-checkout.yml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "      - name: committed diff hygiene\n"
assert text.count(old) == 1
path.write_text(
    text.replace(old, "      - uses: \"Actions/Checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd\"\n" + old),
    encoding="utf-8",
)
PY
if ! ci_workflow_contract "$TMP/extra-unprotected-checkout.yml" 2>/dev/null \
        && ! workflow_checkout_policy_contract "$TMP/extra-unprotected-checkout.yml" 2>/dev/null; then
    ok "workflow policy rejects a quoted case-variant extra checkout step"
else
    bad "workflow policy rejects a quoted case-variant extra checkout step"
fi

mkdir "$TMP/workflow-policy-mutations"
for wf in "$ROOT/.github/workflows"/*.yml; do
    cp "$wf" "$TMP/workflow-policy-mutations/"
done

python3 - "$TMP/workflow-policy-mutations/test.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd", "actions/checkout@v4"), encoding="utf-8")
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects mutable checkout tag in any workflow"
else
    bad "workflow checkout policy rejects mutable checkout tag in any workflow"
fi
cp "$ROOT/.github/workflows/test.yml" "$TMP/workflow-policy-mutations/test.yml"

python3 - "$TMP/workflow-policy-mutations/test.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd", "actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"), encoding="utf-8")
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects different checkout SHA in any workflow"
else
    bad "workflow checkout policy rejects different checkout SHA in any workflow"
fi
cp "$ROOT/.github/workflows/test.yml" "$TMP/workflow-policy-mutations/test.yml"

python3 - "$TMP/workflow-policy-mutations/test.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
p.write_text(
    t.replace("          persist-credentials: false\n", "          fetch-depth: 1 # persist-credentials: false\n"),
    encoding="utf-8",
)
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects a credential marker hidden in a comment"
else
    bad "workflow checkout policy rejects a credential marker hidden in a comment"
fi
cp "$ROOT/.github/workflows/test.yml" "$TMP/workflow-policy-mutations/test.yml"

python3 - "$TMP/workflow-policy-mutations/test.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
old = "        with:\n          fetch-depth: 0\n          persist-credentials: false\n"
new = (
    "        env:\n"
    "          CHECKOUT_PERSIST_CREDENTIALS: \"false\" # persist-credentials: false\n"
)
assert t.count(old) == 4
p.write_text(t.replace(old, new), encoding="utf-8")
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects credentials mis-scoped under env"
else
    bad "workflow checkout policy rejects credentials mis-scoped under env"
fi
cp "$ROOT/.github/workflows/test.yml" "$TMP/workflow-policy-mutations/test.yml"

python3 - "$TMP/workflow-policy-mutations/test.yml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("      - name: committed diff hygiene", "      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd\n      - name: committed diff hygiene"), encoding="utf-8")
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects extra unprotected checkout step in any workflow"
else
    bad "workflow checkout policy rejects extra unprotected checkout step in any workflow"
fi

python3 - "$TMP/workflow-policy-mutations/unexpected.yaml" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(
    'jobs:\n  unexpected:\n    steps:\n      - uses: "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd"\n',
    encoding="utf-8",
)
PY
if ! workflow_checkout_policy_contract "$TMP/workflow-policy-mutations" 2>/dev/null; then
    ok "workflow checkout policy rejects checkout in an unexpected YAML workflow"
else
    bad "workflow checkout policy rejects checkout in an unexpected YAML workflow"
fi

mkdir "$TMP/ci-range-repo"
git -C "$TMP/ci-range-repo" init -q
git -C "$TMP/ci-range-repo" config user.name test
git -C "$TMP/ci-range-repo" config user.email test@example.com
printf 'base\n' > "$TMP/ci-range-repo/fixture.txt"
git -C "$TMP/ci-range-repo" add fixture.txt
git -C "$TMP/ci-range-repo" commit -qm base
ci_base="$(git -C "$TMP/ci-range-repo" rev-parse HEAD)"
printf 'good\n' > "$TMP/ci-range-repo/fixture.txt"
git -C "$TMP/ci-range-repo" add fixture.txt
git -C "$TMP/ci-range-repo" commit -qm good
ci_good="$(git -C "$TMP/ci-range-repo" rev-parse HEAD)"

(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_good" \
        "$ROOT/scripts/ci-diff-check.sh"
)
ci_good_rc=$?
if [[ "$ci_good_rc" == 0 ]]; then
    ok "committed PR range accepts a whitespace-clean patch"
else
    bad "committed PR range accepts a whitespace-clean patch"
fi

printf 'bad   \n' > "$TMP/ci-range-repo/fixture.txt"
git -C "$TMP/ci-range-repo" add fixture.txt
git -C "$TMP/ci-range-repo" commit -qm bad
ci_bad="$(git -C "$TMP/ci-range-repo" rev-parse HEAD)"
git -C "$TMP/ci-range-repo" diff --check >/dev/null 2>&1
plain_diff_rc=$?
(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_bad" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_bad_pr_rc=$?
if [[ "$plain_diff_rc" == 0 && "$ci_bad_pr_rc" != 0 ]]; then
    ok "committed PR range catches whitespace hidden by a clean worktree"
else
    bad "committed PR range catches whitespace hidden by a clean worktree"
fi

git -C "$TMP/ci-range-repo" checkout -q -b attribute-clean "$ci_base"
printf 'fixture.txt -diff\n' > "$TMP/ci-range-repo/.gitattributes"
printf 'clean\n' > "$TMP/ci-range-repo/fixture.txt"
git -C "$TMP/ci-range-repo" add .gitattributes fixture.txt
git -C "$TMP/ci-range-repo" commit -qm attribute-clean
ci_attr_clean="$(git -C "$TMP/ci-range-repo" rev-parse HEAD)"
(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_attr_clean" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_attr_clean_rc=$?
if [[ "$ci_attr_clean_rc" == 0 ]]; then
    ok "attribute-suppressed clean committed blobs are accepted"
else
    bad "attribute-suppressed clean committed blobs are accepted"
fi

printf 'bad   \n' > "$TMP/ci-range-repo/fixture.txt"
git -C "$TMP/ci-range-repo" add fixture.txt
git -C "$TMP/ci-range-repo" commit -qm attribute-bad
ci_attr_bad="$(git -C "$TMP/ci-range-repo" rev-parse HEAD)"
git -C "$TMP/ci-range-repo" diff --check "$ci_base...$ci_attr_bad" -- \
    >/dev/null 2>&1
attribute_git_rc=$?
(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_attr_bad" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_attr_bad_rc=$?
if [[ "$attribute_git_rc" == 0 && "$ci_attr_bad_rc" != 0 ]]; then
    ok "raw committed-blob scan rejects a gitattributes diff suppression bypass"
else
    bad "raw committed-blob scan rejects a gitattributes diff suppression bypass"
fi

mkdir "$TMP/scanner-mutation"
cp "$ROOT/scripts/ci-diff-check.sh" "$TMP/scanner-mutation/ci-diff-check.sh"
cp "$ROOT/scripts/ci_diff_check.py" "$TMP/scanner-mutation/ci_diff_check.py"
python3 - "$TMP/scanner-mutation/ci_diff_check.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "        _check_head_blob(blob)\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "        pass\n"), encoding="utf-8")
PY
chmod +x "$TMP/scanner-mutation/ci-diff-check.sh"
(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_attr_bad" \
        "$TMP/scanner-mutation/ci-diff-check.sh" >/dev/null 2>&1
)
scanner_mutation_rc=$?
if [[ "$scanner_mutation_rc" == 0 ]]; then
    ok "attribute bypass evidence kills raw committed-blob scanner removal"
else
    bad "attribute bypass evidence kills raw committed-blob scanner removal"
fi

cp "$ROOT/scripts/ci_diff_check.py" "$TMP/wrong-range.py"
python3 - "$TMP/wrong-range.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = 'base + "..." + head, "--"'
assert text.count(old) == 1
path.write_text(
    text.replace(old, 'head + "..." + base, "--"'),
    encoding="utf-8",
)
PY
if ! ci_helper_contract "$ROOT/scripts/ci-diff-check.sh" \
        "$TMP/wrong-range.py" 2>/dev/null; then
    ok "helper policy rejects a wrong-direction committed range"
else
    bad "helper policy rejects a wrong-direction committed range"
fi

cp "$ROOT/scripts/ci_diff_check.py" "$TMP/per-blob-process.py"
python3 - "$TMP/per-blob-process.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = '[GIT, "cat-file", "--batch"]'
assert text.count(old) == 1
path.write_text(
    text.replace(old, '[GIT, "cat-file", "blob", requested[0]]'),
    encoding="utf-8",
)
PY
if ! ci_helper_contract "$ROOT/scripts/ci-diff-check.sh" \
        "$TMP/per-blob-process.py" 2>/dev/null; then
    ok "helper policy rejects restoration of per-blob Git subprocesses"
else
    bad "helper policy rejects restoration of per-blob Git subprocesses"
fi

cp "$ROOT/scripts/ci_diff_check.py" "$TMP/unbounded-batch.py"
python3 - "$TMP/unbounded-batch.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "if output_seen > stdout_limit:"
assert text.count(old) == 1
path.write_text(text.replace(old, "if False:"), encoding="utf-8")
PY
if ! ci_helper_contract "$ROOT/scripts/ci-diff-check.sh" \
        "$TMP/unbounded-batch.py" 2>/dev/null; then
    ok "helper policy rejects removal of the batch output bound"
else
    bad "helper policy rejects removal of the batch output bound"
fi

cp "$ROOT/scripts/ci_diff_check.py" "$TMP/ignored-batch-stderr.py"
python3 - "$TMP/ignored-batch-stderr.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "            or stderr_buffer\n"
assert text.count(old) == 1
path.write_text(text.replace(old, ""), encoding="utf-8")
PY
if ! ci_helper_contract "$ROOT/scripts/ci-diff-check.sh" \
        "$TMP/ignored-batch-stderr.py" 2>/dev/null; then
    ok "helper policy rejects ignoring bounded nonempty batch stderr"
else
    bad "helper policy rejects ignoring bounded nonempty batch stderr"
fi

(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=push \
        AGY_WORKER_CI_BASE_SHA="$ci_good" \
        AGY_WORKER_CI_HEAD_SHA="$ci_bad" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_bad_push_rc=$?
if [[ "$ci_bad_push_rc" != 0 ]]; then
    ok "committed push range rejects whitespace errors"
else
    bad "committed push range rejects whitespace errors"
fi

(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=push \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_attr_clean" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_clean_push_rc=$?
if [[ "$ci_clean_push_rc" == 0 ]]; then
    ok "committed noninitial push range accepts a clean patch"
else
    bad "committed noninitial push range accepts a clean patch"
fi

mkdir "$TMP/ci-initial-repo"
git -C "$TMP/ci-initial-repo" init -q
git -C "$TMP/ci-initial-repo" config user.name test
git -C "$TMP/ci-initial-repo" config user.email test@example.com
printf 'initial   \n' > "$TMP/ci-initial-repo/fixture.txt"
git -C "$TMP/ci-initial-repo" add fixture.txt
git -C "$TMP/ci-initial-repo" commit -qm initial
ci_initial="$(git -C "$TMP/ci-initial-repo" rev-parse HEAD)"
(
    cd "$TMP/ci-initial-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=push \
        AGY_WORKER_CI_BASE_SHA=0000000000000000000000000000000000000000 \
        AGY_WORKER_CI_HEAD_SHA="$ci_initial" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_initial_rc=$?
if [[ "$ci_initial_rc" != 0 ]]; then
    ok "initial push checks the root commit against the empty tree"
else
    bad "initial push checks the root commit against the empty tree"
fi


mkdir "$TMP/ci-initial-clean-repo"
git -C "$TMP/ci-initial-clean-repo" init -q
git -C "$TMP/ci-initial-clean-repo" config user.name test
git -C "$TMP/ci-initial-clean-repo" config user.email test@example.com
printf 'initial\n' > "$TMP/ci-initial-clean-repo/fixture.txt"
git -C "$TMP/ci-initial-clean-repo" add fixture.txt
git -C "$TMP/ci-initial-clean-repo" commit -qm initial
ci_initial_clean="$(git -C "$TMP/ci-initial-clean-repo" rev-parse HEAD)"
(
    cd "$TMP/ci-initial-clean-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=push \
        AGY_WORKER_CI_BASE_SHA=0000000000000000000000000000000000000000 \
        AGY_WORKER_CI_HEAD_SHA="$ci_initial_clean" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
ci_initial_clean_rc=$?
if [[ "$ci_initial_clean_rc" == 0 ]]; then
    ok "initial push accepts a clean root commit"
else
    bad "initial push accepts a clean root commit"
fi

invalid_sha_rejected=1
for invalid_case in \
    "pull_request||$ci_good" \
    "pull_request|$ci_base|" \
    "pull_request|not-a-sha|$ci_good" \
    "pull_request|$ci_base|not-a-sha"; do
    IFS='|' read -r invalid_event invalid_base invalid_head <<EOF
$invalid_case
EOF
    (
        cd "$TMP/ci-range-repo" || exit 1
        AGY_WORKER_CI_EVENT_NAME="$invalid_event" \
            AGY_WORKER_CI_BASE_SHA="$invalid_base" \
            AGY_WORKER_CI_HEAD_SHA="$invalid_head" \
            "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
    )
    [[ "$?" != 0 ]] || invalid_sha_rejected=0
done
if [[ "$invalid_sha_rejected" == 1 ]]; then
    ok "missing and malformed event SHAs fail closed"
else
    bad "missing and malformed event SHAs fail closed"
fi

missing_object_rejected=1
for invalid_case in \
    "pull_request|1111111111111111111111111111111111111111|$ci_good" \
    "pull_request|$ci_base|2222222222222222222222222222222222222222"; do
    IFS='|' read -r invalid_event invalid_base invalid_head <<EOF
$invalid_case
EOF
    (
        cd "$TMP/ci-range-repo" || exit 1
        AGY_WORKER_CI_EVENT_NAME="$invalid_event" \
            AGY_WORKER_CI_BASE_SHA="$invalid_base" \
            AGY_WORKER_CI_HEAD_SHA="$invalid_head" \
            "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
    )
    [[ "$?" != 0 ]] || missing_object_rejected=0
done
if [[ "$missing_object_rejected" == 1 ]]; then
    ok "missing committed range objects fail closed"
else
    bad "missing committed range objects fail closed"
fi

(
    cd "$TMP/ci-range-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=workflow_dispatch \
        AGY_WORKER_CI_BASE_SHA="$ci_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_good" \
        "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
)
unknown_event_rc=$?
if [[ "$unknown_event_rc" != 0 ]]; then
    ok "unknown CI event names fail closed"
else
    bad "unknown CI event names fail closed"
fi

zero_sha_rejected=1
for invalid_case in \
    "pull_request|0000000000000000000000000000000000000000|$ci_good" \
    "pull_request|$ci_base|0000000000000000000000000000000000000000" \
    "push|$ci_base|0000000000000000000000000000000000000000"; do
    IFS='|' read -r invalid_event invalid_base invalid_head <<EOF
$invalid_case
EOF
    (
        cd "$TMP/ci-range-repo" || exit 1
        AGY_WORKER_CI_EVENT_NAME="$invalid_event" \
            AGY_WORKER_CI_BASE_SHA="$invalid_base" \
            AGY_WORKER_CI_HEAD_SHA="$invalid_head" \
            "$ROOT/scripts/ci-diff-check.sh" >/dev/null 2>&1
    )
    [[ "$?" != 0 ]] || zero_sha_rejected=0
done
if [[ "$zero_sha_rejected" == 1 ]]; then
    ok "zero PR base and zero event heads fail closed"
else
    bad "zero PR base and zero event heads fail closed"
fi

init_ci_repo "$TMP/ci-binary-repo"
printf 'base\n' > "$TMP/ci-binary-repo/fixture.txt"
git -C "$TMP/ci-binary-repo" add fixture.txt
git -C "$TMP/ci-binary-repo" commit -qm base
ci_binary_base="$(git -C "$TMP/ci-binary-repo" rev-parse HEAD)"
python3 - "$TMP/ci-binary-repo/binary.dat" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_bytes(b"binary\x00payload\n")
PY
git -C "$TMP/ci-binary-repo" add binary.dat
git -C "$TMP/ci-binary-repo" commit -qm binary
ci_binary_head="$(git -C "$TMP/ci-binary-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-binary-repo" pull_request \
        "$ci_binary_base" "$ci_binary_head"; then
    ok "binary committed additions fail closed"
else
    bad "binary committed additions fail closed"
fi

init_ci_repo "$TMP/ci-exact-brand-binary-repo"
printf 'base\n' > "$TMP/ci-exact-brand-binary-repo/fixture.txt"
git -C "$TMP/ci-exact-brand-binary-repo" add fixture.txt
git -C "$TMP/ci-exact-brand-binary-repo" commit -qm base
ci_exact_brand_base="$(git -C "$TMP/ci-exact-brand-binary-repo" rev-parse HEAD)"
mkdir -p "$TMP/ci-exact-brand-binary-repo/docs/assets/brand"
for asset in \
        logo-micro-dark-16.png \
        logo-micro-dark-32.png \
        logo-micro-dark-64.png \
        logo-micro-light-16.png \
        logo-micro-light-32.png \
        logo-micro-light-64.png \
        social-preview-1280x640.png; do
    cp "$ROOT/docs/assets/brand/$asset" \
        "$TMP/ci-exact-brand-binary-repo/docs/assets/brand/$asset"
done
git -C "$TMP/ci-exact-brand-binary-repo" add docs/assets/brand
git -C "$TMP/ci-exact-brand-binary-repo" commit -qm exact-brand-assets
ci_exact_brand_head="$(git -C "$TMP/ci-exact-brand-binary-repo" rev-parse HEAD)"
if run_ci_check "$TMP/ci-exact-brand-binary-repo" pull_request \
        "$ci_exact_brand_base" "$ci_exact_brand_head"; then
    ok "exact path and blob-bound brand PNG set is accepted"
else
    bad "exact path and blob-bound brand PNG set is accepted"
fi

git -C "$TMP/ci-exact-brand-binary-repo" checkout -q -b wrong-brand-bytes \
    "$ci_exact_brand_base"
mkdir -p "$TMP/ci-exact-brand-binary-repo/docs/assets/brand"
python3 - "$TMP/ci-exact-brand-binary-repo/docs/assets/brand/logo-micro-dark-16.png" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_bytes(b"different\x00brand\n")
PY
git -C "$TMP/ci-exact-brand-binary-repo" add docs/assets/brand
git -C "$TMP/ci-exact-brand-binary-repo" commit -qm wrong-brand-bytes
ci_wrong_brand_bytes="$(git -C "$TMP/ci-exact-brand-binary-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-exact-brand-binary-repo" pull_request \
        "$ci_exact_brand_base" "$ci_wrong_brand_bytes"; then
    ok "allowlisted brand path rejects different binary bytes"
else
    bad "allowlisted brand path rejects different binary bytes"
fi

git -C "$TMP/ci-exact-brand-binary-repo" checkout -q -b wrong-brand-path \
    "$ci_exact_brand_base"
mkdir -p "$TMP/ci-exact-brand-binary-repo/docs/assets/brand"
cp "$ROOT/docs/assets/brand/logo-micro-dark-16.png" \
    "$TMP/ci-exact-brand-binary-repo/docs/assets/brand/copied.png"
git -C "$TMP/ci-exact-brand-binary-repo" add docs/assets/brand
git -C "$TMP/ci-exact-brand-binary-repo" commit -qm wrong-brand-path
ci_wrong_brand_path="$(git -C "$TMP/ci-exact-brand-binary-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-exact-brand-binary-repo" pull_request \
        "$ci_exact_brand_base" "$ci_wrong_brand_path"; then
    ok "allowlisted brand blob rejects a different path"
else
    bad "allowlisted brand blob rejects a different path"
fi

git -C "$TMP/ci-exact-brand-binary-repo" checkout -q -b duplicate-brand-blob \
    "$ci_exact_brand_base"
mkdir -p "$TMP/ci-exact-brand-binary-repo/docs/assets/brand"
cp "$ROOT/docs/assets/brand/logo-micro-dark-16.png" \
    "$TMP/ci-exact-brand-binary-repo/docs/assets/brand/logo-micro-dark-16.png"
cp "$ROOT/docs/assets/brand/logo-micro-dark-16.png" \
    "$TMP/ci-exact-brand-binary-repo/docs/assets/brand/copied.png"
git -C "$TMP/ci-exact-brand-binary-repo" add docs/assets/brand
git -C "$TMP/ci-exact-brand-binary-repo" commit -qm duplicate-brand-blob
ci_duplicate_brand_blob="$(git -C "$TMP/ci-exact-brand-binary-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-exact-brand-binary-repo" pull_request \
        "$ci_exact_brand_base" "$ci_duplicate_brand_blob"; then
    ok "allowed and disallowed copies of one brand blob fail closed"
else
    bad "allowed and disallowed copies of one brand blob fail closed"
fi

mkdir "$TMP/ci-broad-brand-mutation"
cp "$ROOT/scripts/ci-diff-check.sh" \
    "$TMP/ci-broad-brand-mutation/ci-diff-check.sh"
cp "$ROOT/scripts/ci_diff_check.py" \
    "$TMP/ci-broad-brand-mutation/ci_diff_check.py"
python3 - "$TMP/ci-broad-brand-mutation/ci_diff_check.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """        if exact_binary_blob is not None:\n            if new_sha != exact_binary_blob:\n                raise CheckRejected("binary-pinning", path)\n            continue\n"""
new = """        if exact_binary_blob is not None:\n            continue\n"""
assert text.count(old) == 1
text = text.replace(old, new)
old_batch = "object_ids, deadline, frozenset(EXACT_BINARY_BLOBS.values())"
assert text.count(old_batch) == 1
path.write_text(
    text.replace(old_batch, "object_ids, deadline, frozenset(object_ids)"),
    encoding="utf-8",
)
PY
chmod +x "$TMP/ci-broad-brand-mutation/ci-diff-check.sh"
(
    cd "$TMP/ci-exact-brand-binary-repo" || exit 1
    AGY_WORKER_CI_EVENT_NAME=pull_request \
        AGY_WORKER_CI_BASE_SHA="$ci_exact_brand_base" \
        AGY_WORKER_CI_HEAD_SHA="$ci_wrong_brand_bytes" \
        "$TMP/ci-broad-brand-mutation/ci-diff-check.sh" >/dev/null 2>&1
)
ci_broad_brand_mutation_rc=$?
if [[ "$ci_broad_brand_mutation_rc" == 0 ]]; then
    ok "different-byte regression kills exact brand blob binding removal"
else
    bad "different-byte regression kills exact brand blob binding removal"
fi

init_ci_repo "$TMP/ci-oversize-repo"
printf 'base\n' > "$TMP/ci-oversize-repo/fixture.txt"
git -C "$TMP/ci-oversize-repo" add fixture.txt
git -C "$TMP/ci-oversize-repo" commit -qm base
ci_oversize_base="$(git -C "$TMP/ci-oversize-repo" rev-parse HEAD)"
python3 - "$TMP/ci-oversize-repo/oversize.txt" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_bytes(b"x" * (2 * 1024 * 1024 + 1))
PY
git -C "$TMP/ci-oversize-repo" add oversize.txt
git -C "$TMP/ci-oversize-repo" commit -qm oversize
ci_oversize_head="$(git -C "$TMP/ci-oversize-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-oversize-repo" pull_request \
        "$ci_oversize_base" "$ci_oversize_head"; then
    ok "oversized committed blobs fail closed"
else
    bad "oversized committed blobs fail closed"
fi

init_ci_repo "$TMP/ci-type-repo"
printf 'base\n' > "$TMP/ci-type-repo/fixture.txt"
git -C "$TMP/ci-type-repo" add fixture.txt
git -C "$TMP/ci-type-repo" commit -qm base
ci_type_base="$(git -C "$TMP/ci-type-repo" rev-parse HEAD)"
ln -s fixture.txt "$TMP/ci-type-repo/fixture-link"
git -C "$TMP/ci-type-repo" add fixture-link
git -C "$TMP/ci-type-repo" commit -qm symlink
ci_type_head="$(git -C "$TMP/ci-type-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-type-repo" pull_request \
        "$ci_type_base" "$ci_type_head"; then
    ok "nonregular committed path types fail closed"
else
    bad "nonregular committed path types fail closed"
fi

git -C "$TMP/ci-type-repo" checkout -q -b gitlink "$ci_type_base"
git -C "$TMP/ci-type-repo" update-index --add \
    --cacheinfo "160000,$ci_type_base,nested"
git -C "$TMP/ci-type-repo" commit -qm gitlink
ci_gitlink_head="$(git -C "$TMP/ci-type-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-type-repo" pull_request \
        "$ci_type_base" "$ci_gitlink_head"; then
    ok "committed gitlinks fail closed"
else
    bad "committed gitlinks fail closed"
fi

init_ci_repo "$TMP/ci-rename-repo"
printf 'clean\n' > "$TMP/ci-rename-repo/clean.txt"
printf 'bad   \n' > "$TMP/ci-rename-repo/bad.txt"
git -C "$TMP/ci-rename-repo" add clean.txt bad.txt
git -C "$TMP/ci-rename-repo" commit -qm base
ci_rename_base="$(git -C "$TMP/ci-rename-repo" rev-parse HEAD)"
git -C "$TMP/ci-rename-repo" mv clean.txt clean-renamed.txt
git -C "$TMP/ci-rename-repo" commit -qm clean-rename
ci_clean_rename="$(git -C "$TMP/ci-rename-repo" rev-parse HEAD)"
if run_ci_check "$TMP/ci-rename-repo" pull_request \
        "$ci_rename_base" "$ci_clean_rename"; then
    ok "clean committed renames are scanned and accepted"
else
    bad "clean committed renames are scanned and accepted"
fi
git -C "$TMP/ci-rename-repo" checkout -q -b bad-rename "$ci_rename_base"
git -C "$TMP/ci-rename-repo" mv bad.txt bad-renamed.txt
git -C "$TMP/ci-rename-repo" commit -qm bad-rename
ci_bad_rename="$(git -C "$TMP/ci-rename-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-rename-repo" pull_request \
        "$ci_rename_base" "$ci_bad_rename"; then
    ok "renamed committed blobs are rescanned in full"
else
    bad "renamed committed blobs are rescanned in full"
fi

init_ci_repo "$TMP/ci-full-blob-repo"
printf 'legacy   \nbase\n' > "$TMP/ci-full-blob-repo/fixture.txt"
git -C "$TMP/ci-full-blob-repo" add fixture.txt
git -C "$TMP/ci-full-blob-repo" commit -qm base
ci_full_blob_base="$(git -C "$TMP/ci-full-blob-repo" rev-parse HEAD)"
printf 'legacy   \nchanged\n' > "$TMP/ci-full-blob-repo/fixture.txt"
git -C "$TMP/ci-full-blob-repo" add fixture.txt
git -C "$TMP/ci-full-blob-repo" commit -qm changed
ci_full_blob_head="$(git -C "$TMP/ci-full-blob-repo" rev-parse HEAD)"
if ! run_ci_check "$TMP/ci-full-blob-repo" pull_request \
        "$ci_full_blob_base" "$ci_full_blob_head"; then
    ok "changed files reject preexisting full-blob whitespace defects"
else
    bad "changed files reject preexisting full-blob whitespace defects"
fi

init_ci_repo "$TMP/ci-linear-lines-repo"
printf 'base\n' > "$TMP/ci-linear-lines-repo/base.txt"
git -C "$TMP/ci-linear-lines-repo" add base.txt
git -C "$TMP/ci-linear-lines-repo" commit -qm base
ci_linear_lines_base="$(git -C "$TMP/ci-linear-lines-repo" rev-parse HEAD)"
python3 - "$TMP/ci-linear-lines-repo/repeated.txt" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_bytes(b"same line\n" * 16_384)
PY
git -C "$TMP/ci-linear-lines-repo" add repeated.txt
git -C "$TMP/ci-linear-lines-repo" commit -qm repeated
ci_linear_lines_head="$(git -C "$TMP/ci-linear-lines-repo" rev-parse HEAD)"
if run_ci_check "$TMP/ci-linear-lines-repo" pull_request \
        "$ci_linear_lines_base" "$ci_linear_lines_head"; then
    ok "16,384 repeated lines complete under the linear scanner bound"
else
    bad "16,384 repeated lines complete under the linear scanner bound"
fi

init_ci_repo "$TMP/ci-max-paths-repo"
printf 'base\n' > "$TMP/ci-max-paths-repo/base.txt"
git -C "$TMP/ci-max-paths-repo" add base.txt
git -C "$TMP/ci-max-paths-repo" commit -qm base
ci_max_paths_base="$(git -C "$TMP/ci-max-paths-repo" rev-parse HEAD)"
path_index=0
while [[ "$path_index" -lt 1024 ]]; do
    printf 'clean\n' > "$TMP/ci-max-paths-repo/path-$path_index.txt"
    path_index=$((path_index + 1))
done
git -C "$TMP/ci-max-paths-repo" add .
git -C "$TMP/ci-max-paths-repo" commit -qm max-paths
ci_max_paths_head="$(git -C "$TMP/ci-max-paths-repo" rev-parse HEAD)"
ci_max_started=$SECONDS
if run_ci_check "$TMP/ci-max-paths-repo" pull_request \
        "$ci_max_paths_base" "$ci_max_paths_head" \
        && [[ "$((SECONDS - ci_max_started))" -lt 10 ]]; then
    ok "one thousand twenty-four small files complete under the path bound"
else
    bad "one thousand twenty-four small files complete under the path bound"
fi

if python3 - "$ROOT" <<'PY'
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
manifest = json.loads((root / ".codex-plugin/plugin.json").read_text())
package_root = root / "skills/agy-worker"
package_readme = package_root / "README.md"
skill_path = package_root / "SKILL.md"
skill = skill_path.read_text(encoding="utf-8")
agents = (root / "AGENTS.md").read_text(encoding="utf-8")
agents_flat = " ".join(agents.split())
security_reference = package_root / "references/SECURITY_AND_COMPATIBILITY.md"
lifecycle_reference = package_root / "references/PROJECT_LIFECYCLE_AND_VERIFICATION.md"
troubleshooting_reference = package_root / "references/TROUBLESHOOTING.md"
assert manifest["name"] == "agy-worker"
assert manifest["version"] == "0.22.0"
assert manifest["skills"] == "./skills/"
assert manifest["license"] == "MIT"
prompts = manifest["interface"]["defaultPrompt"]
assert isinstance(prompts, list) and prompts
assert all(isinstance(prompt, str) and len(prompt) <= 128 for prompt in prompts)
assert manifest["interface"]["privacyPolicyURL"].startswith("https://")
assert manifest["interface"]["termsOfServiceURL"].startswith("https://")
assert not ({"apps", "mcpServers", "hooks"} & manifest.keys())
assert 'license: MIT' in skill
assert f'  version: "{manifest["version"]}"' in skill
assert 'OpenAI Codex CLI and Claude Code.' in skill
assert 'Requires Bash, Python 3, git, and agy with provider network access.' in skill
assert re.search(r"^description: (.+)$", skill, re.M).group(1) == 'Use when Codex or Claude Code should delegate repository exploration or implementation to Google Antigravity CLI (agy), then review, verify, repair, and deliver the result.'
assert len(skill.splitlines()) <= 180
frontmatter = skill.split("---", 2)[1]
assert set(re.findall(r"^([a-z-]+):", frontmatter, re.M)) == {
    "name", "description", "license", "compatibility", "metadata"
}
assert '${CLAUDE_SKILL_DIR}' in skill
assert 'run_in_background: true' in skill
assert 'Bash timeout as provider failure' in skill
assert 'permission approval is separate' in skill
assert '## Claude Code host operation' in lifecycle_reference.read_text()
assert 'direct driver implementation on either' in security_reference.read_text()
assert '[Package README](README.md)' in skill
assert '[Project lifecycle and verification](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md)' in skill
assert '[Security and compatibility](references/SECURITY_AND_COMPATIBILITY.md)' in skill
assert '[Troubleshooting](references/TROUBLESHOOTING.md)' in skill
for package_doc in (
    package_readme, skill_path, lifecycle_reference, security_reference,
    troubleshooting_reference,
):
    assert package_doc.is_file() and not package_doc.is_symlink(), package_doc
    assert "Issue #116 implementation placeholder" not in package_doc.read_text(encoding="utf-8")
assert '## Resolve the bundled runtime' in package_readme.read_text(encoding="utf-8")
assert '## Package guide' in package_readme.read_text(encoding="utf-8")
lifecycle_text = lifecycle_reference.read_text(encoding="utf-8")
assert '## Verification v2' in lifecycle_text
assert '## State approval is stale' in troubleshooting_reference.read_text(encoding="utf-8")

def lifecycle_invocation_contract(text: str) -> bool:
    approved_start = text.find('ENVELOPE="$STATE_DIR/envelope.json"')
    approved_end = text.find('This facade invocation explicitly approves whole-worktree dispatch;', approved_start)
    verify_start = text.find('RECEIPT="$STATE_DIR/evidence-receipt.json"')
    verify_end = text.find('\n```\n', verify_start)
    if min(approved_start, approved_end, verify_start, verify_end) < 0:
        return False
    approved = text[approved_start:approved_end]
    verify = text[verify_start:verify_end]
    return all((
        'test ! -e "$ENVELOPE"' in approved,
        '--approve-whole-worktree "$PREVIEW_SHA"' in approved,
        '> "$ENVELOPE"' in approved,
        'test -s "$ENVELOPE"' in approved,
        'test ! -e "$RECEIPT"' in verify,
        '--receipt "$RECEIPT"' in verify,
        '--envelope "$ENVELOPE"' in verify,
        '--approve-dispatch-sha "$DISPATCH_STATE_SHA"' in verify,
        '--verification-json "$STATE_DIR/verification-v2.json"' in verify,
        '--assurance verified' in verify,
    ))

assert lifecycle_invocation_contract(lifecycle_text)
for required_fragment in (
    '> "$ENVELOPE"', '--receipt "$RECEIPT"', '--envelope "$ENVELOPE"',
    'test ! -e "$RECEIPT"',
):
    if required_fragment == '> "$ENVELOPE"':
        start = lifecycle_text.index('ENVELOPE="$STATE_DIR/envelope.json"')
        end = lifecycle_text.index('This facade invocation explicitly approves whole-worktree dispatch;', start)
    else:
        start = lifecycle_text.index('RECEIPT="$STATE_DIR/evidence-receipt.json"')
        end = lifecycle_text.index('\n```\n', start)
    index = lifecycle_text.find(required_fragment, start, end)
    assert index >= 0, required_fragment
    assert lifecycle_invocation_contract(
        lifecycle_text[:index] + lifecycle_text[index + len(required_fragment):]
    ) is False, required_fragment
workflow_source = (
    root / "skills/agy-worker/runtime/scripts/workflow.py"
).read_text(encoding="utf-8")
assert 'vf_parser.add_argument("--receipt", required=True' in workflow_source
assert 'vf_parser.add_argument("--envelope", required=True' in workflow_source
assert '"--approve-whole-worktree"' in workflow_source
assert '"--approve-whole-worktree", approved_whole_worktree' in workflow_source
assert '"--provider-scope"' in workflow_source
assert '"--approve-transmission-sha"' in workflow_source
assert '"--legacy-preview-approval"' in workflow_source
assert 'was removed after {DISPATCH.LAST_DOCUMENTED_LEGACY_SCHEMA_RELEASE}' in workflow_source
assert 'run_parser.add_argument("--legacy-preview-approval"' not in workflow_source
runtime_wrapper = (
    root / "skills/agy-worker/runtime/agy-worker.sh"
).read_text(encoding="utf-8")
assert '--provider-scope conflicts with --add-dir' in runtime_wrapper
assert '--provider-scope requires --approve-transmission-sha' in runtime_wrapper
assert '--approve-whole-worktree LAUNCH_APPROVAL_SHA256' in runtime_wrapper
assert 'choose provider scope, or explicitly approve whole-worktree transmission' in runtime_wrapper
dispatcher_source = (
    root / "skills/agy-worker/runtime/scripts/agy_dispatch.py"
).read_text(encoding="utf-8")
assert dispatcher_source.count("_require_initial_transmission_choice(") == 2
scope_recovery_tests = (
    root / "tests/agy_worker_remediation_recovery_cases.py"
).read_text(encoding="utf-8")
for required_case in (
    "linked preview SHA authorizes exact V11 initial and prelaunch scope binding",
    "mid-write materialization failure removes the partial private stage",
    "cleanup failure is visible and fail closed",
    "narrow stage rejects unselected writes and reconciles an authorized replacement",
    "later failure recreates deleted nested empty directories before clearing the ledger",
):
    assert required_case in scope_recovery_tests, required_case
reference_text = security_reference.read_text(encoding="utf-8")
assert 'Codex CLI and\nClaude Code are supported driver hosts' in reference_text
assert '`verify-job.sh --verify-env NAME`' in reference_text
assert 'dispatch-time `agy` version, help, and model-selection' in reference_text
assert 'including diagnostics, are not provider dispatch' in reference_text
assert 'Provider children and local `agy` interface probes' not in reference_text
assert not (package_root / "assets").exists()
for package_doc in (
    package_readme, skill_path, lifecycle_reference, security_reference,
    troubleshooting_reference,
):
    text = package_doc.read_text(encoding="utf-8")
    assert "![" not in text and "<img" not in text, package_doc
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        resolved = (package_doc.parent / target).resolve()
        assert resolved.is_relative_to(package_root.resolve()), (package_doc, target)
        assert resolved.is_file() and not resolved.is_symlink(), (package_doc, target)
assert 'Run the owning focused suite for what you changed, then the dev gate' in agents_flat
assert '`./scripts/ci-offline.sh` once on the final bytes.' in agents_flat
assert 'No author is the sole acceptor of material work.' in agents_flat
PY
then ok "dual-host skill metadata matches the plugin version and public legal links"; else bad "dual-host skill metadata matches the plugin version and public legal links"; fi

if python3 -B "$ROOT/tests/test-doc-claims.py" "$ROOT"; then
    ok "public host, approval, and lifecycle claims match their documented limits"
else
    bad "public host, approval, and lifecycle claims match their documented limits"
fi

if python3 - "$ROOT" "$TMP/marketplace-contract" <<'PY'
import json
from pathlib import Path
import shutil
import stat
import sys

source_root = Path(sys.argv[1])
fixture = Path(sys.argv[2])
shutil.copytree(source_root / ".agents", fixture / ".agents")
shutil.copytree(source_root / ".codex-plugin", fixture / ".codex-plugin")
shutil.copytree(source_root / ".claude-plugin", fixture / ".claude-plugin")
shutil.copytree(source_root / "skills", fixture / "skills")


def require_regular(path: Path) -> None:
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode), path


def require_directory(path: Path) -> None:
    info = path.lstat()
    assert stat.S_ISDIR(info.st_mode), path


def validate(root: Path) -> None:
    marketplace_path = root / ".agents/plugins/marketplace.json"
    manifest_path = root / ".codex-plugin/plugin.json"
    require_regular(marketplace_path)
    require_regular(manifest_path)
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert set(marketplace) == {"name", "interface", "plugins"}
    assert marketplace["name"] == "agy-worker"
    assert marketplace["interface"] == {"displayName": "agy Worker"}
    assert isinstance(marketplace["plugins"], list) and len(marketplace["plugins"]) == 1
    entry = marketplace["plugins"][0]
    assert set(entry) == {"name", "source", "policy", "category"}
    assert entry["name"] == manifest["name"] == "agy-worker"
    assert entry["source"] == {"source": "local", "path": "."}
    assert entry["policy"] == {
        "installation": "AVAILABLE", "authentication": "ON_INSTALL"
    }
    assert entry["category"] == "Developer Tools"
    assert manifest["skills"] == "./skills/"
    claude_manifest_path = root / ".claude-plugin/plugin.json"
    claude_marketplace_path = root / ".claude-plugin/marketplace.json"
    require_regular(claude_manifest_path)
    require_regular(claude_marketplace_path)
    claude = json.loads(claude_manifest_path.read_text())
    catalog = json.loads(claude_marketplace_path.read_text())
    assert set(claude) == {"name", "version", "description", "author", "homepage", "repository", "license"}
    assert claude["name"] == catalog["name"] == manifest["name"] == "agy-worker"
    assert claude["version"] == manifest["version"]
    assert "Supports Claude Code; keep headless sessions active until dispatch completes." in claude["description"]
    assert claude["repository"] == manifest["repository"]
    assert claude["homepage"] == manifest["homepage"]
    assert claude["license"] == "MIT"
    assert set(catalog) == {"name", "description", "owner", "plugins"}
    assert catalog["description"] == claude["description"]
    assert catalog["owner"] == claude["author"]
    assert catalog["plugins"] == [{
        "name": "agy-worker", "source": "./", "description": claude["description"],
        "version": claude["version"],
    }]

    skill_root = root / "skills/agy-worker"
    runtime_root = skill_root / "runtime"
    require_directory(root)
    require_directory(root / "skills")
    require_directory(skill_root)
    require_directory(runtime_root)
    require_regular(skill_root / "README.md")
    require_regular(skill_root / "SKILL.md")
    require_directory(skill_root / "agents")
    require_regular(skill_root / "agents/openai.yaml")
    require_directory(skill_root / "references")
    require_regular(skill_root / "references/PROJECT_LIFECYCLE_AND_VERIFICATION.md")
    require_regular(skill_root / "references/SECURITY_AND_COMPATIBILITY.md")
    require_regular(skill_root / "references/TROUBLESHOOTING.md")
    require_directory(skill_root / "scripts")
    require_regular(skill_root / "scripts/resolve-pipeline.sh")
    assert [path.relative_to(root).as_posix() for path in root.rglob("SKILL.md")] == [
        "skills/agy-worker/SKILL.md"
    ]
    assert [path.relative_to(root).as_posix() for path in root.rglob("runtime") if path.is_dir()] == [
        "skills/agy-worker/runtime"
    ]
    assert not (root / "plugins").exists()


def rejected(root: Path) -> bool:
    try:
        validate(root)
    except (AssertionError, FileNotFoundError, IsADirectoryError, json.JSONDecodeError):
        return True
    return False


validate(fixture)
for relative, key, value in (
    (".claude-plugin/plugin.json", "name", "wrong"),
    (".claude-plugin/plugin.json", "version", "0.0.0"),
    (".claude-plugin/plugin.json", "hooks", {}),
    (".claude-plugin/marketplace.json", "owner", {}),
    (".claude-plugin/marketplace.json", "plugins", [{"name": "agy-worker", "source": "../escape"}]),
):
    path = fixture / relative
    original = path.read_bytes()
    payload = json.loads(original)
    payload[key] = value
    path.write_text(json.dumps(payload))
    assert rejected(fixture), (relative, key)
    path.write_bytes(original)
for relative in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
    path = fixture / relative
    original = path.read_bytes()
    path.unlink()
    assert rejected(fixture), relative
    path.symlink_to(source_root / relative)
    assert rejected(fixture), relative
    path.unlink()
    path.write_bytes(original)
marketplace_path = fixture / ".agents/plugins/marketplace.json"
manifest_path = fixture / ".codex-plugin/plugin.json"
original_marketplace = marketplace_path.read_bytes()
original_manifest = manifest_path.read_bytes()

payload = json.loads(original_marketplace)
payload["plugins"][0]["name"] = "wrong-name"
marketplace_path.write_text(json.dumps(payload), encoding="utf-8")
assert rejected(fixture), "marketplace must reject a plugin-manifest name mismatch"

marketplace_path.write_bytes(original_marketplace)
manifest_path.unlink()
assert rejected(fixture), "marketplace must reject a missing plugin manifest"
manifest_path.symlink_to(source_root / ".codex-plugin/plugin.json")
assert rejected(fixture), "marketplace must reject a symlinked plugin manifest"
manifest_path.unlink()
manifest_path.write_bytes(original_manifest)

payload = json.loads(original_marketplace)
payload["plugins"][0]["source"]["path"] = "../escape"
marketplace_path.write_text(json.dumps(payload), encoding="utf-8")
assert rejected(fixture), "marketplace must reject a source-path escape"

linked_source = fixture / "linked-source"
linked_source.symlink_to(fixture / "skills", target_is_directory=True)
payload["plugins"][0]["source"]["path"] = "linked-source"
marketplace_path.write_text(json.dumps(payload), encoding="utf-8")
assert rejected(fixture), "marketplace must reject a symlinked source path"

marketplace_path.write_bytes(original_marketplace)
linked_source.unlink()
source_root_link = fixture.parent / "marketplace-root-symlink"
source_root_link.symlink_to(fixture, target_is_directory=True)
assert rejected(source_root_link), "marketplace must reject a symlinked root source"
source_root_link.unlink()
duplicate = fixture / "plugins/agy-worker/skills"
duplicate.parent.mkdir(parents=True)
shutil.copytree(fixture / "skills", duplicate)
assert rejected(fixture), "marketplace must reject duplicate skill/runtime sources"
PY
then
    ok "root-source marketplace binds one canonical package and rejects source/name/layout mutants"
else
    bad "root-source marketplace contract"
fi

if python3 - "$ROOT" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
skill = (root / "skills/agy-worker/SKILL.md").read_text()
metadata = (root / "skills/agy-worker/agents/openai.yaml").read_text()
assert skill.startswith("---\nname: agy-worker\ndescription:")
assert len(re.search(r"^description: (.+)$", skill, re.M).group(1)) <= 1024
assert 'display_name: "Verified agy Worker"' in metadata
assert 'short_description: "Use when Codex should delegate repository work to agy and verify it"' in metadata
assert 'default_prompt: "Use $agy-worker when this repository task benefits from delegated exploration or implementation.' in metadata
assert 'provider transmission approval explicit' in metadata
assert 'inspect the actual diff' in metadata
assert 'run driver-owned checks' in metadata
assert "$agy-worker" in metadata
PY
then ok "canonical Agent Skill has matching OpenAI UI metadata"; else bad "canonical Agent Skill has matching OpenAI UI metadata"; fi

if ! grep -R -Fq '__REPO_ROOT__' "$ROOT/skills/agy-worker" \
        && ! grep -R -Fq '/Users/' "$ROOT/skills/agy-worker" \
        && [[ ! -e "$ROOT/skills/agy-worker/.pipeline-root" ]]; then
    ok "public skill bundle contains no checkout placeholder or local path marker"
else
    bad "public skill bundle contains no checkout placeholder or local path marker"
fi

if python3 - "$ROOT/skills/agy-worker" <<'PY'
import ast
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
for path in root.rglob("*"):
    if path.is_file():
        text = path.read_bytes().decode("utf-8", errors="replace")
        fragments = [text]
        if path.suffix == ".py":
            fragments.extend(
                node.value for node in ast.walk(ast.parse(text))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
        for fragment in fragments:
            assert "unreleased development version" not in re.sub(r"\s+", " ", fragment).lower(), path
PY
then
    ok "shipped skill uses release-neutral diagnostics and documentation"
else
    bad "shipped skill uses release-neutral diagnostics and documentation"
fi

if [[ -x "$ROOT/doctor.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/doctor.sh" ]] \
        && [[ -x "$ROOT/ground-truth.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/ground-truth.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/model_selection.py" ]] \
        && ground_truth_phase_contract "$ROOT/ground-truth.sh" root \
        && ground_truth_phase_contract "$ROOT/skills/agy-worker/runtime/ground-truth.sh" runtime; then
    ok "root and portable ground-truth phases preserve their read-only boundary"
else
    bad "root and portable ground-truth phases preserve their read-only boundary"
fi

if [[ -x "$ROOT/model-selection.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/model-selection.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/model_selection.py" ]]; then
    ok "root and portable packages include the canonical explicit selector"
else
    bad "root and portable packages include the canonical explicit selector"
fi

if [[ -x "$ROOT/verify-job.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/verify-job.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/evidence_receipt.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/schemas/evidence-receipt.schema.json" ]]; then
    ok "root and portable packages include Evidence Receipt v1"
else
    bad "root and portable packages include Evidence Receipt v1"
fi

if [[ -x "$ROOT/evidence-report.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/evidence-report.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/evidence_report.py" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/recommendation_record.py" ]]; then
    ok "root and portable packages include the pure Evidence Report renderer"
else
    bad "root and portable packages include the pure Evidence Report renderer"
fi

if [[ -x "$ROOT/job.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/job.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/job_lifecycle.py" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/candidate_state.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/schemas/job-state.schema.json" ]]; then
    ok "root and portable packages include the safe local job lifecycle"
else
    bad "root and portable packages include the safe local job lifecycle"
fi

if [[ -x "$ROOT/delegation-policy.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/delegation-policy.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/delegation_policy.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/schemas/delegation-policy.schema.json" ]]; then
    ok "root and portable packages include the Delegation Policy evaluator"
else
    bad "root and portable packages include the Delegation Policy evaluator"
fi

if [[ -x "$ROOT/workflow.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/workflow.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/workflow.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/schemas/workflow-state.schema.json" ]] \
        && grep -Fq '## Primary `run`, `status`, `verify-finalize` path' \
            "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && grep -Fq '## Primary run, status, verify-finalize path' "$ROOT/docs/USAGE.md" \
        && grep -Fq '## Primary facade and advanced recovery' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && ! grep -Fq 'os.chmod(' "$ROOT/skills/agy-worker/runtime/scripts/workflow.py"; then
    ok "root and portable packages include the canonical workflow facade"
else
    bad "root and portable packages include the canonical workflow facade"
fi

if [[ -x "$ROOT/agy-worker.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/agy-worker.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py" ]] \
        && [[ ! -x "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_containment.py" ]] \
        && [[ ! -x "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_containment.py" ]] \
        && [[ -f "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_verification.py" ]] \
        && [[ ! -x "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_verification.py" ]]; then
    ok "root and portable packages include the progress-aware local dispatcher"
else
    bad "root and portable packages include the progress-aware local dispatcher"
fi




if [[ -x "$ROOT/delegation-policy.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/delegation-policy.sh" ]] \
        && [[ -x "$ROOT/skills/agy-worker/runtime/scripts/delegation_policy.py" ]] \
        && grep -Fq 'delegation-policy.sh' "$ROOT/skills/agy-worker/scripts/resolve-pipeline.sh" \
        && grep -Fq 'scripts/delegation_policy.py' "$ROOT/skills/agy-worker/runtime/doctor.sh" \
        && [[ -f "$ROOT/skills/agy-worker/runtime/schemas/delegation-policy.schema.json" ]]; then
    ok "root and portable packages include Delegation-First Coordinator Policy"
else
    bad "root and portable packages include Delegation-First Coordinator Policy"
fi


if grep -Fq 'is process-owning: it keeps signal rollback authority' \
        "$ROOT/skills/agy-worker/runtime/scripts/evidence_report.py" \
        && grep -Fq 'The `--output` CLI path is deliberately process-owning' \
            "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'documented command or a subprocess; do not call its `main(argv)` from a host process.' \
            "$ROOT/docs/PROJECT_WORKFLOW.md"; then
    ok "Evidence Report documents its process-owning file-output boundary"
else
    bad "Evidence Report documents its process-owning file-output boundary"
fi

if grep -Fq 'REPORT_FORMATS = ("text", "json", "markdown", "github-step-summary")' \
        "$ROOT/skills/agy-worker/runtime/scripts/evidence_report.py" \
        && ! grep -Eq 'GITHUB_STEP_SUMMARY|os\.environ' \
            "$ROOT/skills/agy-worker/runtime/scripts/evidence_report.py"; then
    ok "portable Evidence Report owns exact CI-safe formats without environment discovery"
else
    bad "portable Evidence Report owns exact CI-safe formats without environment discovery"
fi

if grep -Fq -- '--format github-step-summary >> "${GITHUB_STEP_SUMMARY:?}"' \
        "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'fork-controlled paths, repository content, tokens, or secrets' \
            "$ROOT/docs/PROJECT_WORKFLOW.md"; then
    ok "project workflow guide keeps GitHub Step Summary redirection explicit and fork-safe"
else
    bad "project workflow guide keeps GitHub Step Summary redirection explicit and fork-safe"
fi

if grep -Fq 'step. The reporter never discovers or writes `GITHUB_STEP_SUMMARY` itself and does' \
        "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'never discovers or writes `GITHUB_STEP_SUMMARY`' \
            "$ROOT/PRIVACY.md"; then
    ok "workflow and privacy docs bound the local-only CI reporter surface"
else
    bad "workflow and privacy docs bound the local-only CI reporter surface"
fi

if python3 - "$ROOT" <<'PYCODE'
from pathlib import Path
import sys
root = Path(sys.argv[1])
runtime = root / "skills/agy-worker/runtime"
tooling = ['benchmark.sh', 'benchmarks/v1/manifest.json', 'benchmarks/v1/portable-source.json', 'benchmarks/v1/tasks/exact-edit/candidate.txt', 'benchmarks/v1/tasks/exact-edit/envelope.json', 'benchmarks/v1/tasks/exact-edit/initial.txt', 'benchmarks/v1/variants/bulk.json', 'codex-usage-report.sh', 'compat/model-intelligence/dataset.v1.json', 'feedback-triage.sh', 'model-evidence-campaign.sh', 'model-intelligence.sh', 'schemas/benchmark-plan.schema.json', 'schemas/benchmark-result.schema.json', 'schemas/model-evidence-campaign-advisory-preview.schema.json', 'schemas/model-evidence-campaign-advisory-summary.schema.json', 'schemas/model-evidence-campaign-aggregate-preview.schema.json', 'schemas/model-evidence-campaign-aggregate.schema.json', 'schemas/model-evidence-campaign-evaluation.schema.json', 'schemas/model-evidence-campaign-plan.schema.json', 'schemas/model-evidence-campaign-record.schema.json', 'schemas/model-intelligence-advisory.schema.json', 'schemas/model-intelligence-evidence.schema.json', 'schemas/swebench-workflow-study-advisory.schema.json', 'schemas/swebench-workflow-study-plan.schema.json', 'schemas/swebench-workflow-study-report.schema.json', 'scripts/benchmark.py', 'scripts/codex_usage_report.py', 'scripts/feedback-triage.py', 'scripts/model_evidence_campaign.py', 'scripts/model_intelligence.py', 'scripts/swebench_workflow_study.py', 'swebench-workflow-study.sh']
for relative in tooling:
    assert not (runtime / relative).exists(), relative
    assert not (root / relative).exists(), relative
PYCODE
then ok "retired tools are absent from the repository and package"; else bad "retired tools are absent from the repository and package"; fi

required_runtime_dependencies=(
    workflow.sh
    agy-worker.sh
    job.sh
    qa-gate.sh
    verify-job.sh
    evidence-report.sh
    model-recommendation.sh
    model-selection.sh
    doctor.sh
    ground-truth.sh
    delegation-policy.sh
    scripts/workflow.py
    scripts/validate-envelope.py
    scripts/evidence_receipt.py
    scripts/evidence_report.py
    scripts/recommendation_record.py
    scripts/model-recommendation.py
    scripts/model_selection.py
    scripts/candidate_state.py
    scripts/agy_dispatch.py
    scripts/agy_dispatch_worktree.py
    scripts/agy_dispatch_containment.py
    scripts/agy_dispatch_verification.py
    scripts/job_lifecycle.py
    scripts/delegation_policy.py
    schemas/workflow-state.schema.json
    schemas/worker-result.schema.json
    schemas/worker-result.provider.schema.json
    schemas/evidence-receipt.schema.json
    schemas/model-selection.schema.json
    schemas/model-recommendation.schema.json
    schemas/job-state.schema.json
    schemas/delegation-policy.schema.json
)
for dependency in "${required_runtime_dependencies[@]}"; do
    label="${dependency//\//-}"
    dependency_copy="$TMP/missing-$label"
    cp -R "$ROOT/skills/agy-worker" "$dependency_copy"
    rm -f "$dependency_copy/runtime/$dependency"
    PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/missing-$label.network" \
        bash "$dependency_copy/scripts/resolve-pipeline.sh" \
        > "$TMP/missing-$label.out" 2> "$TMP/missing-$label.err"
    rc=$?
    if [[ "$rc" == 2 && ! -s "$TMP/missing-$label.out" ]] \
            && grep -Fq 'complete agy-worker skill bundle' "$TMP/missing-$label.err" \
            && [[ ! -e "$TMP/missing-$label.network" ]]; then
        ok "resolver rejects a bundle missing $dependency"
    else
        bad "resolver rejects a bundle missing $dependency"
    fi
done

if python3 - "$ROOT" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
resolver = (root / "skills/agy-worker/scripts/resolve-pipeline.sh").read_text()
doctor = (root / "skills/agy-worker/runtime/doctor.sh").read_text()

def body(text: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}$", text, re.M | re.S)
    assert match is not None
    return match.group(1)

assert body(resolver, "pipeline_runtime_complete") == body(
    doctor, "doctor_runtime_complete"
)
assert "runtime-bundle.sh" not in resolver
assert "runtime-bundle.sh" not in doctor
assert not re.search(r"(?:^|[;&|()]\s*)(?:source|\.)\s+", resolver, re.M)
assert not re.search(r"(?:^|[;&|()]\s*)(?:source|\.)\s+", doctor, re.M)
PY
then ok "resolver and doctor use the same fixed non-sourced runtime predicate"; else bad "resolver and doctor use the same fixed non-sourced runtime predicate"; fi

real_parent_copy="$TMP/real-runtime-parents"
cp -R "$ROOT/skills/agy-worker" "$real_parent_copy"
real_parent_resolved="$(bash "$real_parent_copy/scripts/resolve-pipeline.sh" 2>/dev/null)"
if [[ "$real_parent_resolved" == "$(cd "$real_parent_copy/runtime" && pwd -P)" ]]; then
    ok "resolver accepts bundle-owned real runtime parent directories"
else
    bad "resolver accepts bundle-owned real runtime parent directories"
fi

# Git distributions contain files, never the checkout's empty directories.
tracked_source="$TMP/tracked-source"
tracked_install="$TMP/tracked-install"
if python3 -B - "$ROOT" "$tracked_source" <<'PYTRACKED'
from pathlib import Path
import shutil
import subprocess
import sys
root, target = map(Path, sys.argv[1:])
paths = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--", "install.sh", "skills/agy-worker"])
for raw in paths.split(b"\0"):
    if not raw:
        continue
    relative = Path(raw.decode("utf-8"))
    source = root / relative
    if not source.exists():  # Deleted tracked paths await the final commit.
        continue
    assert source.is_file() and not source.is_symlink(), relative
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
assert not (target / "skills/agy-worker/runtime/agents").exists()
PYTRACKED
then
    tracked_folder_root="$(bash "$tracked_source/skills/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
    HOME="$TMP/tracked-home" CODEX_SKILLS_DIR="$tracked_install" \
        bash "$tracked_source/install.sh" > "$TMP/tracked-install.out" 2> "$TMP/tracked-install.err"
    tracked_install_rc=$?
    # Remove the advisory checkout marker to prove installed runtime fallback.
    rm -f "$tracked_install/agy-worker/.pipeline-root"
    tracked_installed_root="$(bash "$tracked_install/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
    if [[ "$tracked_install_rc" == 0 \
            && "$tracked_folder_root" == "$(cd "$tracked_source/skills/agy-worker/runtime" && pwd -P)" \
            && "$tracked_installed_root" == "$(cd "$tracked_install/agy-worker/runtime" && pwd -P)" \
            && ! -e "$tracked_install/agy-worker/runtime/agents" ]]; then
        ok "tracked-file folder and installed bundle resolve without untracked empty directories"
    else
        bad "tracked-file folder and installed bundle resolve without untracked empty directories"
    fi
else
    bad "tracked-file folder and installed bundle resolve without untracked empty directories"
fi

for parent in scripts schemas; do
    for link_kind in absolute relative in-root; do
        parent_copy="$TMP/parent-$parent-$link_kind"
        foreign_parent="$TMP/foreign-$parent-$link_kind"
        cp -R "$ROOT/skills/agy-worker" "$parent_copy"
        if [[ "$link_kind" == in-root ]]; then
            mv "$parent_copy/runtime/$parent" \
                "$parent_copy/runtime/owned-$parent"
            ln -s "owned-$parent" "$parent_copy/runtime/$parent"
        else
            mv "$parent_copy/runtime/$parent" "$foreign_parent"
            if [[ "$link_kind" == absolute ]]; then
                ln -s "$foreign_parent" "$parent_copy/runtime/$parent"
            else
                ln -s "../../${foreign_parent##*/}" "$parent_copy/runtime/$parent"
            fi
        fi
        bash "$parent_copy/scripts/resolve-pipeline.sh" \
            > "$TMP/parent-$parent-$link_kind.out" \
            2> "$TMP/parent-$parent-$link_kind.err"
        rc=$?
        if [[ "$rc" == 2 \
                && ! -s "$TMP/parent-$parent-$link_kind.out" ]] \
                && grep -Fq 'complete agy-worker skill bundle' \
                    "$TMP/parent-$parent-$link_kind.err" \
                && ! grep -Fq "$TMP" "$TMP/parent-$parent-$link_kind.err"; then
            ok "resolver rejects $link_kind $parent parent symlink"
        else
            bad "resolver rejects $link_kind $parent parent symlink"
        fi
    done
done

for specification in \
    'workflow.sh:executable' \
    'job.sh:executable' \
    'qa-gate.sh:executable' \
    'verify-job.sh:executable' \
    'evidence-report.sh:executable' \
    'delegation-policy.sh:executable' \
    'scripts/workflow.py:executable' \
    'scripts/validate-envelope.py:executable' \
    'scripts/evidence_receipt.py:executable' \
    'scripts/evidence_report.py:executable' \
    'scripts/recommendation_record.py:executable' \
    'scripts/candidate_state.py:executable' \
    'scripts/agy_dispatch.py:executable' \
    'scripts/agy_dispatch_worktree.py:data' \
    'scripts/agy_dispatch_containment.py:data' \
    'scripts/agy_dispatch_verification.py:data' \
    'scripts/job_lifecycle.py:executable' \
    'scripts/model_selection.py:executable' \
    'scripts/delegation_policy.py:executable' \
    'schemas/workflow-state.schema.json:data' \
    'schemas/worker-result.schema.json:data' \
    'schemas/evidence-receipt.schema.json:data' \
    'schemas/job-state.schema.json:data' \
    'schemas/delegation-policy.schema.json:data'; do
    dependency="${specification%:*}"
    dependency_class="${specification##*:}"
    for wrong_type in directory symlink-directory symlink-foreign fifo wrong-mode; do
        label="${dependency//\//-}-$wrong_type"
        dependency_copy="$TMP/wrong-$label"
        cp -R "$ROOT/skills/agy-worker" "$dependency_copy"
        dependency_path="$dependency_copy/runtime/$dependency"
        rm -f "$dependency_path"
        case "$wrong_type" in
            directory) mkdir "$dependency_path" ;;
            symlink-directory) ln -s "$TMP" "$dependency_path" ;;
            symlink-foreign) ln -s /dev/null "$dependency_path" ;;
            fifo) mkfifo "$dependency_path" ;;
            wrong-mode)
                cp "$ROOT/skills/agy-worker/runtime/$dependency" "$dependency_path"
                if [[ "$dependency_class" == executable ]]; then
                    chmod -x "$dependency_path"
                else
                    chmod +x "$dependency_path"
                fi
                ;;
        esac
        PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/wrong-$label.network" \
            bash "$dependency_copy/scripts/resolve-pipeline.sh" \
            > "$TMP/wrong-$label.out" 2> "$TMP/wrong-$label.err"
        rc=$?
        if [[ "$rc" == 2 && ! -s "$TMP/wrong-$label.out" ]] \
                && grep -Fq 'complete agy-worker skill bundle' "$TMP/wrong-$label.err" \
                && [[ ! -e "$TMP/wrong-$label.network" ]] \
                && ! grep -Fq "$TMP" "$TMP/wrong-$label.err"; then
            ok "resolver rejects $wrong_type for $dependency_class $dependency"
        else
            bad "resolver rejects $wrong_type for $dependency_class $dependency"
        fi
    done
done

for helper_mode in malformed side-effect exit stale; do
    helper_copy="$TMP/helper-$helper_mode"
    cp -R "$ROOT/skills/agy-worker" "$helper_copy"
    helper="$helper_copy/runtime/scripts/runtime-bundle.sh"
    case "$helper_mode" in
        malformed) printf 'if then impossible\n' > "$helper" ;;
        side-effect) printf ': > %q\n' "$TMP/helper-side-effect.marker" > "$helper" ;;
        exit) printf 'exit 91\n' > "$helper" ;;
        stale) printf 'pipeline_runtime_complete() { return 1; }\n' > "$helper" ;;
    esac
    resolved="$(bash "$helper_copy/scripts/resolve-pipeline.sh" 2> "$TMP/helper-$helper_mode.err")"
    rc=$?
    if [[ "$rc" == 0 \
            && "$resolved" == "$(cd "$helper_copy/runtime" && pwd -P)" \
            && ! -s "$TMP/helper-$helper_mode.err" \
            && ! -e "$TMP/helper-side-effect.marker" ]]; then
        ok "resolver ignores $helper_mode candidate runtime helper"
    else
        bad "resolver ignores $helper_mode candidate runtime helper"
    fi
done

if ci_stage_registered './tests/test-doctor.sh' \
        && grep -Fq 'runs-on: macos-latest' "$ROOT/.github/workflows/test.yml"; then
    ok "macOS CI runs the dedicated offline doctor suite"
else
    bad "macOS CI runs the dedicated offline doctor suite"
fi




if ci_stage_registered './tests/test-evidence-report.sh' \
        && grep -Fq 'runs-on: macos-latest' "$ROOT/.github/workflows/test.yml"; then
    ok "macOS CI runs the dedicated offline Evidence Report suite"
else
    bad "macOS CI runs the dedicated offline Evidence Report suite"
fi

python_cache_exists() {
    python3 -B - "$1" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
raise SystemExit(
    0 if any(
        path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}
        for path in root.rglob("*")
    ) else 1
)
PY
}

workflow_compile_fixture="$TMP/workflow-compile-fixture"
mkdir -p "$workflow_compile_fixture/conformance/v1" \
    "$workflow_compile_fixture/scripts" \
    "$workflow_compile_fixture/skills/agy-worker/runtime/scripts"
cp "$ROOT/conformance/v1/run.py" "$workflow_compile_fixture/conformance/v1/run.py"
cp "$ROOT/scripts/official_github.py" "$workflow_compile_fixture/scripts/official_github.py"
cp "$ROOT/skills/agy-worker/runtime/scripts/model_selection.py" \
    "$workflow_compile_fixture/skills/agy-worker/runtime/scripts/model_selection.py"
(
    cd "$workflow_compile_fixture" || exit 1
    AGY_WORKER_CI_PYCACHE_DIR="$TMP/workflow-python-cache" \
        /usr/bin/python3 -I -S -B -c \
        "import glob, os, py_compile, sys; sys.pycache_prefix = os.environ['AGY_WORKER_CI_PYCACHE_DIR']; [py_compile.compile(f, doraise=True) for f in sorted(set(glob.glob('conformance/v1/*.py') + glob.glob('scripts/*.py') + glob.glob('skills/*/runtime/scripts/*.py')))]"
)
workflow_compile_rc=$?
python3 -B - "$CI_STAGES" <<'PY'
from pathlib import Path
import sys

stages_file = Path(sys.argv[1])
sys.path.insert(0, str(stages_file.parent))
import ci_stages

py_stage = [s for s in ci_stages.STAGES if s.id == "python-syntax"][0]
assert py_stage.argv[:5] == ("/usr/bin/python3", "-I", "-S", "-B", "-c")
assert "conformance/v1/*.py" in py_stage.argv[5]
assert "sys.pycache_prefix = os.environ['AGY_WORKER_CI_PYCACHE_DIR']" in py_stage.argv[5]
assert "PYTHONPYCACHEPREFIX" not in py_stage.argv[5]
assert "runner.temp" not in stages_file.read_text(encoding="utf-8")
PY
workflow_contract_rc=$?
if [[ "$workflow_compile_rc" == 0 ]] \
        && [[ "$workflow_contract_rc" == 0 ]] \
        && ! python_cache_exists "$workflow_compile_fixture" \
        && python_cache_exists "$TMP/workflow-python-cache"; then
    ok "workflow Python syntax check keeps bytecode outside the public checkout"
else
    bad "workflow Python syntax check keeps bytecode outside the public checkout"
fi

plain_compile_fixture="$TMP/plain-compile-fixture"
mkdir -p "$plain_compile_fixture/scripts" \
    "$plain_compile_fixture/skills/agy-worker/runtime/scripts"
cp "$ROOT/scripts/official_github.py" "$plain_compile_fixture/scripts/official_github.py"
cp "$ROOT/skills/agy-worker/runtime/scripts/model_selection.py" \
    "$plain_compile_fixture/skills/agy-worker/runtime/scripts/model_selection.py"
(
    cd "$plain_compile_fixture" || exit 1
    unset PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX
    python3 -I -S -B -c 'import py_compile, sys; sys.pycache_prefix = None; [py_compile.compile(path, doraise=True) for path in sorted(sys.argv[1:])]' scripts/*.py skills/*/runtime/scripts/*.py
)
plain_compile_rc=$?
if [[ "$plain_compile_rc" == 0 ]] \
        && python_cache_exists "$plain_compile_fixture/skills/agy-worker"; then
    ok "plain py_compile negative control is caught as a public bytecode leak"
else
    bad "plain py_compile negative control is caught as a public bytecode leak"
fi

if [[ -x "$ROOT/proof-demo.sh" ]] \
        && [[ -x "$ROOT/tests/test-proof-demo.sh" ]] \
        && [[ -f "$ROOT/conformance/v1/envelopes/honest.json" ]] \
        && [[ ! -L "$ROOT/conformance/v1/envelopes/honest.json" ]] \
        && grep -Fq 'conformance/v1/envelopes' "$ROOT/proof-demo.sh" \
        && [[ ! -e "$ROOT/demo/fixtures/honest-envelope.json" ]] \
        && [[ ! -e "$ROOT/demo/fixtures/scope-mismatch-envelope.json" ]] \
        && [[ ! -e "$ROOT/skills/agy-worker/runtime/proof-demo.sh" ]]; then
    ok "repository package binds starter proof to the public conformance subset"
else
    bad "repository package binds starter proof to the public conformance subset"
fi

if [[ -x "$ROOT/conformance/run.sh" ]] \
        && [[ -x "$ROOT/conformance/v1/run.py" ]] \
        && [[ -f "$ROOT/conformance/v1/manifest.json" ]] \
        && [[ -f "$ROOT/docs/CONFORMANCE.md" ]] \
        && grep -Fq 'MANIFEST_SHA256 = "9741584060f5391e5a79df1022c9cd574c28fdddefc75006b8b6e7ff0e5e36a0"' \
            "$ROOT/conformance/v1/run.py" \
        && grep -Fq '[Conformance](docs/CONFORMANCE.md)' "$ROOT/README.md" \
        && grep -Fq 'for these fixed fixtures. It is not a' "$ROOT/docs/CONFORMANCE.md" \
        && grep -Fq 'security certification' "$ROOT/docs/CONFORMANCE.md" \
        && ci_stage_registered '/usr/bin/python3 -I -S -B tests/test-conformance.py'; then
    ok "distribution includes the bounded non-certifying v1 conformance contract"
else
    bad "distribution includes the bounded non-certifying v1 conformance contract"
fi

if ci_stage_registered './tests/test-proof-demo.sh'; then
    ok "macOS CI runs the dedicated offline starter-proof suite"
else
    bad "macOS CI runs the dedicated offline starter-proof suite"
fi

if ci_stage_registered './tests/test-evidence-receipt.sh'; then
    ok "macOS CI runs the dedicated Evidence Receipt v1 suite"
else
    bad "macOS CI runs the dedicated Evidence Receipt v1 suite"
fi

if grep -Fq './proof-demo.sh' "$ROOT/README.md" \
        && grep -Fq 'starter proof' "$ROOT/README.md" \
        && grep -Fq 'proof-demo.sh' "$ROOT/docs/index.md" \
        && grep -Fq 'not human review' "$ROOT/docs/index.md"; then
    ok "public documentation links the bounded starter proof without claiming acceptance"
else
    bad "public documentation links the bounded starter proof without claiming acceptance"
fi

if grep -Fq 'gate="$script_dir/qa-gate.sh"' "$ROOT/proof-demo.sh" \
        && ! grep -Eq 'PROOF_GATE|--gate([=[:space:]]|$)' "$ROOT/proof-demo.sh" \
        && grep -Fq 'honest: gate-passed (exit 0)' "$ROOT/proof-demo.sh" \
        && grep -Fq 'mismatch: rejected (exit 10)' "$ROOT/proof-demo.sh" \
        && grep -Fq 'starter proof only; no candidate accepted because no human review occurred' \
            "$ROOT/proof-demo.sh"; then
    ok "starter proof fixes the maintained gate and its bounded success contract"
else
    bad "starter proof fixes the maintained gate and its bounded success contract"
fi

if python3 -B - "$ROOT/skills/agy-worker/runtime/schemas/model-selection.schema.json" <<'PYSCHEMA'
import copy
import json
import sys
schema = json.load(open(sys.argv[1], encoding="utf-8"))
def check_schema(value):
    assert value["additionalProperties"] is False
    assert set(value["required"]) == {"schema_version", "kind", "selection_mode", "resolved_agy_model"}
    props = value["properties"]
    assert props["schema_version"]["const"] == 4
    assert set(props) == {"schema_version", "kind", "selection_mode", "resolved_agy_model", "selected_tier", "selected_tier_source", "user_model", "user_model_source", "user_effort", "user_effort_source", "installed_agy_version", "probed_executable"}
    assert set(props["selection_mode"]["enum"]) == {"tier", "exact-model", "model-effort"}
    modes = {v["properties"]["selection_mode"]["const"]: v for v in value["oneOf"]}
    expected = {"tier": {"selected_tier", "selected_tier_source"}, "exact-model": {"user_model", "user_model_source"}, "model-effort": {"user_model", "user_model_source", "user_effort", "user_effort_source"}}
    selectors = set().union(*expected.values())
    for mode, required in expected.items():
        assert set(modes[mode]["required"]) == required
        assert {tuple(x["required"]) for x in modes[mode]["not"]["anyOf"]} == {(key,) for key in selectors - required}
    assert value["dependencies"] == {"installed_agy_version": ["probed_executable"], "probed_executable": ["installed_agy_version"]}
    binding = props["probed_executable"]
    assert binding["additionalProperties"] is False
    assert set(binding["required"]) == set(binding["properties"]) == {"path_sha256", "target_lstat", "symlink_chain", "components", "content_sha256"}
    assert binding["properties"]["content_sha256"] == {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    lstat = binding["properties"]["target_lstat"]
    assert lstat["additionalProperties"] is False
    assert set(lstat["required"]) == set(lstat["properties"]) == {"device", "inode", "mode", "uid", "gid", "size", "mtime_ns", "ctime_ns"}
    for key, rule in lstat["properties"].items():
        assert rule == {"type": "integer", "minimum": 1 if key in {"device", "inode", "mode"} else 0}
    for array, keys, bound in (("symlink_chain", {"path_sha256", "lstat", "target_sha256"}, 16), ("components", {"path_sha256", "lstat"}, 128)):
        rule = binding["properties"][array]
        assert rule["type"] == "array" and rule["maxItems"] == bound
        item = rule["items"]
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"]) == keys
        assert item["properties"]["lstat"] == lstat
    assert props["user_model_source"]["enum"] == props["user_effort_source"]["enum"] == ["cli", "environment"]
    tier = modes["tier"]["allOf"]
    assert tier == [
        {"if": {"required": ["selected_tier"], "properties": {"selected_tier": {"const": "default"}}},
         "then": {"properties": {"resolved_agy_model": {"type": "null"}}},
         "else": {"properties": {"resolved_agy_model": {"type": "string", "minLength": 1}}}},
        {"if": {"required": ["selected_tier_source"], "properties": {"selected_tier_source": {"const": "implicit-default"}}},
         "then": {"properties": {"selected_tier": {"const": "default"}}}},
    ]
    for mode in ("exact-model", "model-effort"):
        assert modes[mode]["properties"]["resolved_agy_model"] == {"type": "string", "minLength": 1}
check_schema(schema)
mutants = []
for kind in ("extra", "missing", "forbidden", "dependency", "binding", "lstat", "nested-lstat", "tier", "direct"):
    mutant = copy.deepcopy(schema)
    if kind == "extra": mutant["additionalProperties"] = True
    elif kind == "missing": mutant["oneOf"][2]["required"].remove("user_effort_source")
    elif kind == "forbidden": mutant["oneOf"][0]["not"]["anyOf"].pop()
    elif kind == "dependency": mutant["dependencies"].pop("probed_executable")
    elif kind == "binding": mutant["properties"]["probed_executable"]["required"].remove("content_sha256")
    elif kind == "lstat": mutant["properties"]["probed_executable"]["properties"]["target_lstat"]["required"].remove("ctime_ns")
    elif kind == "nested-lstat": mutant["properties"]["probed_executable"]["properties"]["components"]["items"]["properties"]["lstat"]["additionalProperties"] = True
    elif kind == "tier": mutant["oneOf"][0]["allOf"].pop()
    else: mutant["oneOf"][1]["properties"].pop("resolved_agy_model")
    mutants.append(mutant)
for mutant in mutants:
    try: check_schema(mutant)
    except (AssertionError, KeyError, TypeError): continue
    raise AssertionError("weakened packaged selection schema was accepted")
PYSCHEMA
then
    ok "selection v4 schema preserves exact choice, provenance, executable pairing and closed fields"
else
    bad "selection v4 schema preserves exact choice, provenance, executable pairing and closed fields"
fi

resolved="$(bash "$ROOT/skills/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
if [[ "$resolved" == "$(cd "$ROOT" && pwd -P)" ]]; then
    ok "Codex package resolver finds the adjacent canonical runtime"
else
    bad "Codex package resolver finds the adjacent canonical runtime"
fi

mkdir -p "$TMP/legacy-claude-only/.claude-plugin" \
    "$TMP/legacy-claude-only/skills"
cp "$ROOT/agy-worker.sh" "$ROOT/qa-gate.sh" \
    "$ROOT/model-recommendation.sh" "$TMP/legacy-claude-only/"
cp -R "$ROOT/skills/agy-worker" "$TMP/legacy-claude-only/skills/agy-worker"
printf '{}\n' > "$TMP/legacy-claude-only/.claude-plugin/plugin.json"
legacy_resolved="$(bash "$TMP/legacy-claude-only/skills/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
if [[ "$legacy_resolved" == "$(cd "$TMP/legacy-claude-only/skills/agy-worker/runtime" && pwd -P)" ]]; then
    ok "resolver rejects incomplete Claude root and uses complete bundled fallback"
else
    bad "resolver rejects incomplete Claude root and uses complete bundled fallback"
fi

# A Claude marker is only a locator; completeness still determines acceptance.
cp -R "$ROOT/skills/agy-worker/runtime" "$TMP/claude-complete"
mkdir -p "$TMP/claude-complete/.claude-plugin" "$TMP/claude-complete/skills"
cp "$ROOT/.claude-plugin/plugin.json" "$TMP/claude-complete/.claude-plugin/plugin.json"
cp -R "$ROOT/skills/agy-worker" "$TMP/claude-complete/skills/agy-worker"
claude_root="$(cd "$TMP/claude-complete" && pwd -P)"
if [[ "$(bash "$claude_root/skills/agy-worker/scripts/resolve-pipeline.sh")" == "$claude_root" ]]; then
    ok "Claude-only complete package root resolves"
else
    bad "Claude-only complete package root resolves"
fi
mkdir -p "$claude_root/.codex-plugin"
cp "$ROOT/.codex-plugin/plugin.json" "$claude_root/.codex-plugin/plugin.json"
if [[ "$(bash "$claude_root/skills/agy-worker/scripts/resolve-pipeline.sh")" == "$claude_root" ]]; then
    ok "both host markers resolve the same complete root"
else
    bad "both host markers resolve the same complete root"
fi
rm "$TMP/legacy-claude-only/skills/agy-worker/runtime/qa-gate.sh"
if bash "$TMP/legacy-claude-only/skills/agy-worker/scripts/resolve-pipeline.sh" > "$TMP/incomplete-claude.out" 2>/dev/null; then
    bad "incomplete Claude root and incomplete bundled runtime reject"
else
    if [[ ! -s "$TMP/incomplete-claude.out" ]]; then
        ok "incomplete Claude root and incomplete bundled runtime reject"
    else
        bad "incomplete Claude layout must not emit a runtime"
    fi
fi

mkdir -p "$TMP/skill-folder-copy" "$TMP/no-network-bin"
cp -R "$ROOT/skills/agy-worker" "$TMP/skill-folder-copy/agy-worker"
for command_name in agy curl wget git npm npx; do
    printf '#!/usr/bin/env bash\n: > "$NETWORK_MARKER"\nexit 99\n' \
        > "$TMP/no-network-bin/$command_name"
    chmod +x "$TMP/no-network-bin/$command_name"
done
mkdir -p "$TMP/claude home/.claude/skills"
cp -R "$ROOT/skills/agy-worker" "$TMP/claude home/.claude/skills/agy-worker"
claude_skill="$TMP/claude home/.claude/skills/agy-worker"
claude_resolved="$(PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/claude-network-called" \
    bash "$claude_skill/scripts/resolve-pipeline.sh")"
if [[ "$claude_resolved" == "$(cd "$claude_skill/runtime" && pwd -P)" && ! -e "$TMP/claude-network-called" ]]; then
    ok "Claude personal skill copy resolves offline without provider or network calls"
else
    bad "Claude personal skill copy resolves offline without provider or network calls"
fi

copied_pipeline="$(PATH="$TMP/no-network-bin:$PATH" \
    NETWORK_MARKER="$TMP/network-called" \
    bash "$TMP/skill-folder-copy/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/network-called" \
    "$copied_pipeline/model-recommendation.sh" --stage pre-dispatch \
    --selected-tier cheap --evidence bounded-routine \
    > "$TMP/copied-recommendation.json" 2> "$TMP/copied-recommendation.err"
rc=$?
if [[ "$rc" == "0" ]] \
        && [[ "$copied_pipeline" == "$(cd "$TMP/skill-folder-copy/agy-worker/runtime" && pwd -P)" ]] \
        && grep -Fq '"recommendation_only": true' "$TMP/copied-recommendation.json" \
        && grep -Fq '"applied": false' "$TMP/copied-recommendation.json" \
        && [[ ! -e "$TMP/network-called" ]]; then
    ok "skill-folder-only copy resolves and runs a bounded offline advisory"
else
    bad "skill-folder-only copy resolves and runs a bounded offline advisory"
fi

mkdir -p "$TMP/portable-receipt-repo" "$TMP/portable-receipts" \
    "$TMP/receipt-no-network-bin"
chmod 700 "$TMP/portable-receipts"
for command_name in agy curl wget npm npx; do
    printf '#!/usr/bin/env bash\n: > "$NETWORK_MARKER"\nexit 99\n' \
        > "$TMP/receipt-no-network-bin/$command_name"
    chmod +x "$TMP/receipt-no-network-bin/$command_name"
done
git -C "$TMP/portable-receipt-repo" init -q
git -C "$TMP/portable-receipt-repo" config user.email test@example.com
git -C "$TMP/portable-receipt-repo" config user.name test
printf 'before\n' > "$TMP/portable-receipt-repo/a.txt"
git -C "$TMP/portable-receipt-repo" add a.txt
git -C "$TMP/portable-receipt-repo" commit -qm init
portable_receipt_base="$(git -C "$TMP/portable-receipt-repo" rev-parse HEAD)"
printf 'after\n' > "$TMP/portable-receipt-repo/a.txt"
printf '%s\n' '{"status":"completed","summary":"done","files_changed":[{"path":"a.txt","change":"modified"}],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":1,"requires_human":false}' \
    > "$TMP/portable-envelope.json"
portable_receipt_parent="$(cd "$TMP/portable-receipts" && pwd -P)"
PATH="$TMP/receipt-no-network-bin:$PATH" NETWORK_MARKER="$TMP/receipt-network-called" \
    "$copied_pipeline/verify-job.sh" \
    --receipt "$portable_receipt_parent/receipt.json" \
    --envelope "$TMP/portable-envelope.json" \
    --repo "$TMP/portable-receipt-repo" --base "$portable_receipt_base" \
    --only a.txt --expect-edits --verify-argv '["true"]' \
    > "$TMP/portable-receipt.out" 2> "$TMP/portable-receipt.err"
portable_receipt_rc=$?
if [[ "$portable_receipt_rc" == 0 && ! -e "$TMP/receipt-network-called" ]] \
        && python3 -B - "$portable_receipt_parent/receipt.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["gate_exit"] == 0
assert value["verdict"] == "gate-passed"
assert value["gate_authority"] == "qa-gate"
assert value["integrity"]["signed"] is False
PY
then
    ok "skill-folder-only copy publishes a bounded receipt offline"
else
    bad "skill-folder-only copy publishes a bounded receipt offline"
fi

PATH="$TMP/receipt-no-network-bin:$PATH" NETWORK_MARKER="$TMP/receipt-network-called" \
    "$copied_pipeline/evidence-report.sh" \
    --receipt "$portable_receipt_parent/receipt.json" --format text \
    > "$TMP/portable-report.out" 2> "$TMP/portable-report.err"
portable_report_rc=$?
if [[ "$portable_report_rc" == 0 && ! -s "$TMP/portable-report.err" ]] \
        && grep -Fq 'Verdict: gate-passed' "$TMP/portable-report.out" \
        && grep -Fq 'Human review: required' "$TMP/portable-report.out" \
        && [[ ! -e "$TMP/receipt-network-called" ]]; then
    ok "skill-folder-only copy renders a bounded receipt offline"
else
    bad "skill-folder-only copy renders a bounded receipt offline"
fi

mkdir -p "$TMP/selector-bin"
printf '%s\n' '#!/usr/bin/env bash' \
    'case "$*" in' \
    '  --version) printf "1.2.11\n" ;;' \
    '  --help) printf "%s\n" "Usage of agy:" "  --add-dir  Add a directory" "  --conversation  Resume a conversation" "  --disable-slash-commands  Disable slash commands" "  --json-schema  Schema path" "  --mode  Execution mode (accept-edits, plan)" "  --model  Select a model" "  --effort  Reasoning effort (low|medium|high|max)" "  --output-format  Format (text, json, stream-json)" "  --print  Run a prompt" "  --print-timeout  Print timeout" "  --sandbox  Sandboxed" >&2 ;;' \
    '  *) exit 97 ;;' \
    'esac' > "$TMP/selector-bin/agy"
chmod +x "$TMP/selector-bin/agy"
PATH="$TMP/selector-bin:$PATH" NETWORK_MARKER="$TMP/network-called" \
    "$copied_pipeline/model-selection.sh" --model gemini-3.6-flash --effort high \
    > "$TMP/copied-selection.json" 2> "$TMP/copied-selection.err"
rc=$?
copied_selection_v4=0
if python3 -B - "$TMP/copied-selection.json" <<'PY'
import json
import sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["schema_version"] == 4
assert not ({"compatibility_disposition", "approved_help_sha256", "compatibility_decision_sha256"} & set(record))
PY
then
    copied_selection_v4=1
fi
if [[ "$rc" == 0 ]] \
        && grep -Fq '"resolved_agy_model": "gemini-3.6-flash"' \
            "$TMP/copied-selection.json" \
        && grep -Fq '"user_effort": "high"' "$TMP/copied-selection.json" \
        && [[ "$copied_selection_v4" == 1 ]] \
        && [[ ! -e "$TMP/network-called" ]]; then
    ok "skill-folder-only copy resolves an exact direct selector offline"
else
    bad "skill-folder-only copy resolves an exact direct selector offline"
fi

(
    unset PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX
    PATH="$TMP/selector-bin:$PATH" \
        "$copied_pipeline/model-selection.sh" \
        --model gemini-3.6-flash --effort high \
        > "$TMP/no-spill-selection.json" 2> "$TMP/no-spill-selection.err" \
    && "$copied_pipeline/model-recommendation.sh" \
        --stage pre-dispatch --selected-model gemini-3.6-flash \
        --selected-effort high --evidence bounded-routine \
        > "$TMP/no-spill-recommendation.json" 2> "$TMP/no-spill-recommendation.err"
)
no_spill_rc=$?
if [[ "$no_spill_rc" == 0 ]] \
        && python3 -B - "$copied_pipeline" "$ROOT/skills/agy-worker" <<'PY'
from pathlib import Path
import sys

for root_text in sys.argv[1:]:
    root = Path(root_text)
    leaked = [path for path in root.rglob("*") if path.name == "__pycache__" or path.suffix == ".pyc"]
    assert not leaked, leaked
PY
then
    ok "normal direct selector and recommendation runs leave no bytecode in public bundles"
else
    bad "normal direct selector and recommendation runs leave no bytecode in public bundles"
fi

mkdir -p "$TMP/incomplete-skill/agy-worker/agents" \
    "$TMP/incomplete-skill/agy-worker/scripts"
cp "$ROOT/skills/agy-worker/SKILL.md" "$TMP/incomplete-skill/agy-worker/SKILL.md"
cp "$ROOT/skills/agy-worker/agents/openai.yaml" \
    "$TMP/incomplete-skill/agy-worker/agents/openai.yaml"
cp "$ROOT/skills/agy-worker/scripts/resolve-pipeline.sh" \
    "$TMP/incomplete-skill/agy-worker/scripts/resolve-pipeline.sh"
bash "$TMP/incomplete-skill/agy-worker/scripts/resolve-pipeline.sh" \
    > "$TMP/incomplete.out" 2> "$TMP/incomplete.err"
rc=$?
if [[ "$rc" == "2" && ! -s "$TMP/incomplete.out" ]] \
        && grep -Fq 'complete agy-worker skill bundle' "$TMP/incomplete.err"; then
    ok "skill-folder-only resolver rejects an incomplete runtime bundle"
else
    bad "skill-folder-only resolver rejects an incomplete runtime bundle"
fi

cp -R "$ROOT/skills/agy-worker" "$TMP/missing-doctor-skill"
rm -f "$TMP/missing-doctor-skill/runtime/doctor.sh"
PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/missing-doctor-network" \
    bash "$TMP/missing-doctor-skill/scripts/resolve-pipeline.sh" \
    > "$TMP/missing-doctor.out" 2> "$TMP/missing-doctor.err"
rc=$?
if [[ "$rc" == "2" && ! -s "$TMP/missing-doctor.out" ]] \
        && grep -Fq 'complete agy-worker skill bundle' "$TMP/missing-doctor.err" \
        && [[ ! -e "$TMP/missing-doctor-network" ]]; then
    ok "resolver rejects a doctor-less bundle without fallback or network"
else
    bad "resolver rejects a doctor-less bundle without fallback or network"
fi

cp -R "$ROOT/skills/agy-worker" "$TMP/missing-ground-truth-skill"
rm -f "$TMP/missing-ground-truth-skill/runtime/ground-truth.sh"
PATH="$TMP/no-network-bin:$PATH" NETWORK_MARKER="$TMP/missing-ground-truth-network" \
    bash "$TMP/missing-ground-truth-skill/scripts/resolve-pipeline.sh" \
    > "$TMP/missing-ground-truth.out" 2> "$TMP/missing-ground-truth.err"
rc=$?
if [[ "$rc" == "2" && ! -s "$TMP/missing-ground-truth.out" ]] \
        && grep -Fq 'complete agy-worker skill bundle' "$TMP/missing-ground-truth.err" \
        && [[ ! -e "$TMP/missing-ground-truth-network" ]]; then
    ok "resolver rejects a ground-truth-less bundle without fallback or network"
else
    bad "resolver rejects a ground-truth-less bundle without fallback or network"
fi

mkdir -p "$TMP/bin" "$TMP/installed"
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/bin/agy"
chmod +x "$TMP/bin/agy"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$TMP/installed" "$ROOT/install.sh" \
    > "$TMP/install.out" 2> "$TMP/install.err"
rc=$?
installed_root=""
if [[ "$rc" == "0" ]]; then
    installed_root="$(bash "$TMP/installed/agy-worker/scripts/resolve-pipeline.sh" 2>/dev/null)"
fi

marketplace_installed_parity() {
    python3 - "$1" "$2" "$3" <<'PY'
from hashlib import sha256
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1]) / "skills/agy-worker"
installed = Path(sys.argv[2])
tampered = Path(sys.argv[3])

def snapshot(root: Path) -> dict[str, bytes]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == ".pipeline-root":
            continue
        assert not path.is_symlink(), path
        result[relative] = sha256(path.read_bytes()).digest()
    return result

source_snapshot = snapshot(source)
assert source_snapshot == snapshot(installed)
shutil.copytree(installed, tampered)
runtime = tampered / "runtime/agy-worker.sh"
runtime.write_bytes(runtime.read_bytes() + b"\n# marketplace tamper fixture\n")
assert source_snapshot != snapshot(tampered)
PY
}
CLAUDE_SKILLS_DIR="$TMP/claude installed" CODEX_SKILLS_DIR="$TMP/untouched-codex" \
    bash "$ROOT/install.sh" --host claude > "$TMP/claude-install.out" 2> "$TMP/claude-install.err"
claude_install_rc=$?
if [[ "$claude_install_rc" == 0 && ! -e "$TMP/untouched-codex" ]] \
    && [[ "$(bash "$TMP/claude installed/agy-worker/scripts/resolve-pipeline.sh")" == "$(cd "$ROOT" && pwd -P)" ]] \
    && marketplace_installed_parity "$ROOT" "$TMP/claude installed/agy-worker" "$TMP/claude-parity-mutant" \
    && grep -Fq 'new Claude Code session' "$TMP/claude-install.out"; then
    ok "Claude standalone install preserves bytes marker and host-specific destination"
else
    bad "Claude standalone install preserves bytes marker and host-specific destination"
fi
HOME="$TMP/claude default home" CLAUDE_SKILLS_DIR= bash "$ROOT/install.sh" --host claude > "$TMP/claude-default.out" 2>&1
if [[ $? == 0 && -f "$TMP/claude default home/.claude/skills/agy-worker/.pipeline-root" ]]; then
    ok "Claude default destination uses its host home"
else
    bad "Claude default destination uses its host home"
fi
for invalid in missing unsupported unknown; do
    case "$invalid" in
        missing) args=(--host) ;;
        unsupported) args=(--host invalid) ;;
        unknown) args=(--bogus) ;;
    esac
    HOME="$TMP/reject-$invalid" CODEX_SKILLS_DIR= CLAUDE_SKILLS_DIR= \
        bash "$ROOT/install.sh" "${args[@]}" > "$TMP/reject-$invalid.out" 2>&1
    if [[ $? == 64 && ! -e "$TMP/reject-$invalid" ]]; then
        ok "invalid installer $invalid arguments reject before writes"
    else
        bad "invalid installer $invalid arguments reject before writes"
    fi
done

if [[ "$installed_root" == "$(cd "$ROOT" && pwd -P)" ]]; then
    ok "standalone install resolves the checkout without rewriting SKILL.md"
else
    bad "standalone install resolves the checkout without rewriting SKILL.md"
fi
if [[ -x "$TMP/installed/agy-worker/runtime/ground-truth.sh" ]] \
        && ground_truth_phase_contract "$TMP/installed/agy-worker/runtime/ground-truth.sh" installed; then
    ok "installed skill includes the canonical ground-truth helper and phase boundary"
else
    bad "installed skill includes the canonical ground-truth helper and phase boundary"
fi
if [[ -x "$ROOT/agy-worker.sh" ]] \
        && grep -Fq 'skills/agy-worker/runtime/agy-worker.sh' "$ROOT/agy-worker.sh" \
        && [[ -x "$TMP/installed/agy-worker/runtime/doctor.sh" ]] \
        && [[ -x "$TMP/installed/agy-worker/runtime/ground-truth.sh" ]] \
        && grep -Fq '`"$PIPELINE/ground-truth.sh"`' "$TMP/installed/agy-worker/SKILL.md" \
        && grep -Fq '`"$PIPELINE/ground-truth.sh"`' \
            "$TMP/installed/agy-worker/references/SECURITY_AND_COMPATIBILITY.md" \
        && [[ -x "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch.py" ]] \
        && [[ -f "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_worktree.py" ]] \
        && [[ ! -x "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_worktree.py" ]] \
        && [[ -f "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_containment.py" ]] \
        && [[ ! -x "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_containment.py" ]] \
        && [[ -f "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_verification.py" ]] \
        && [[ ! -x "$TMP/installed/agy-worker/runtime/scripts/agy_dispatch_verification.py" ]] \
        && [[ -x "$TMP/installed/agy-worker/runtime/scripts/model_selection.py" ]] \
        && grep -Fq '`"$PIPELINE/scripts/agy_dispatch.py"`' \
            "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && cmp -s "$ROOT/skills/agy-worker/runtime/scripts/model_selection.py" \
            "$TMP/installed/agy-worker/runtime/scripts/model_selection.py" \
        && marketplace_installed_parity "$ROOT" "$TMP/installed/agy-worker" \
            "$TMP/tampered-installed-marketplace-skill"; then
    ok "root wrapper and installed skill preserve runtime authority, complete parity, and tamper evidence"
else
    bad "root wrapper and installed skill preserve runtime dispatcher authority and capability bytes"
fi

governance_clauses=(
    'For trust-boundary changes, write a short design note covering options considered and residual risk, and obtain independent review.'
    'No author is the sole acceptor of material work.'
    'Verification v2 binds candidate evidence; it does not establish reviewer identity.'
)

governance_lifecycle_contract() {
    local lifecycle_path="$1" clause
    for clause in "${governance_clauses[@]}"; do
        [[ "$(grep -Fxc "$clause" "$lifecycle_path")" == "1" ]] || return 1
    done
}

if [[ "$installed_root" == "$(cd "$ROOT" && pwd -P)" ]] \
        && governance_lifecycle_contract "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && governance_lifecycle_contract "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md"; then
    ok "installed lifecycle guide preserves trust-boundary design notes and independent acceptance"
else
    bad "installed lifecycle guide preserves trust-boundary design notes and independent acceptance"
fi

governance_mutants_rejected=1
governance_mutant_index=0
for clause in "${governance_clauses[@]}"; do
    for mutation in delete optional; do
        governance_mutant_index=$((governance_mutant_index + 1))
        mutant="$TMP/governance-lifecycle-mutant-$governance_mutant_index.md"
        if ! python3 -B - "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" "$mutant" "$clause" "$mutation" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
clause = sys.argv[3]
text = source.read_text(encoding="utf-8")
if text.count(clause) != 1:
    raise SystemExit(1)
replacement = "" if sys.argv[4] == "delete" else "Optional: " + clause
target.write_text(text.replace(clause, replacement, 1), encoding="utf-8")
PY
        then
            governance_mutants_rejected=0
            break
        fi
        if governance_lifecycle_contract "$mutant"; then
            governance_mutants_rejected=0
            break
        fi
    done
done
if [[ "$governance_mutants_rejected" == "1" ]]; then
    ok "source and installed governance reject each clause deletion or optionalization"
else
    bad "source and installed governance reject each clause deletion or optionalization"
fi

provider_notice_clauses=(
    'Before every provider-launch attempt (initial start/run, resume, continue, and restart), tell the user what task is being sent to AGY.'
    'Include a short public-safe task label and the exact resolved model slug when known.'
    'For default selection, say the provider default is used and the model is unresolved; do not invent a slug.'
    'Report caller-supplied effort when present; otherwise say effort is unresolved, without inferring backend reasoning.'
    'The notice must precede every dispatch attempt and remain accurate afterward.'
    'If preflight fails before provider launch, explicitly state that the task was not sent to AGY.'
    'If provider reach is genuinely uncertain, state that it is unverified rather than claiming success.'
    'Direct model and effort selection remain caller-owned; recommendations are advisory.'
)

provider_notice_lifecycle_contract() {
    local lifecycle_path="$1" clause
    for clause in "${provider_notice_clauses[@]}"; do
        [[ "$(grep -Fxc "$clause" "$lifecycle_path")" == "1" ]] || return 1
    done
}

if [[ "$installed_root" == "$(cd "$ROOT" && pwd -P)" ]] \
        && provider_notice_lifecycle_contract "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && provider_notice_lifecycle_contract "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md"; then
    ok "installed lifecycle guide preserves user-facing provider dispatch notice and boundary contract"
else
    bad "installed lifecycle guide preserves user-facing provider dispatch notice and boundary contract"
fi

provider_notice_mutants_rejected=1
provider_notice_mutant_index=0
for clause in "${provider_notice_clauses[@]}"; do
    provider_notice_mutant_index=$((provider_notice_mutant_index + 1))
    mutant="$TMP/provider-notice-lifecycle-mutant-$provider_notice_mutant_index.md"
    if ! python3 -B - "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" "$mutant" "$clause" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
clause = sys.argv[3]
text = source.read_text(encoding="utf-8")
if text.count(clause) != 1:
    raise SystemExit(1)
target.write_text(text.replace(clause, "", 1), encoding="utf-8")
PY
    then
        provider_notice_mutants_rejected=0
        break
    fi
    if provider_notice_lifecycle_contract "$mutant"; then
        provider_notice_mutants_rejected=0
        break
    fi
done
if [[ "$provider_notice_mutants_rejected" == "1" ]]; then
    ok "installed provider notice contract rejects every independent clause deletion"
else
    bad "installed provider notice contract rejects every independent clause deletion"
fi

provider_notice_weakening_mutants_rejected=1
provider_notice_weakening_mutant_index=0
weakening_replacements=(
    'tell the user what task is being sent to AGY::tell the user only if convenient'
    'the exact resolved model slug when known::any approximate model label'
    'the model is unresolved; do not invent a slug::invent a resolved model slug'
    'Report caller-supplied effort when present; otherwise say effort is unresolved, without inferring backend reasoning::Infer backend reasoning and effort'
    'precede every dispatch attempt::follow completion of the job'
    'explicitly state that the task was not sent to AGY::state that the task was sent to AGY'
    'state that it is unverified rather than claiming success::claim success'
    'Direct model and effort selection remain caller-owned::Direct model selection is superseded'
)
for pair in "${weakening_replacements[@]}"; do
    provider_notice_weakening_mutant_index=$((provider_notice_weakening_mutant_index + 1))
    old_fragment="${pair%%::*}"
    new_fragment="${pair##*::}"
    mutant="$TMP/provider-notice-weakened-$provider_notice_weakening_mutant_index.md"
    if ! python3 -B - "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" "$mutant" "$old_fragment" "$new_fragment" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
old_frag = sys.argv[3]
new_frag = sys.argv[4]
text = source.read_text(encoding="utf-8")
if text.count(old_frag) != 1:
    raise SystemExit(1)
target.write_text(text.replace(old_frag, new_frag, 1), encoding="utf-8")
PY
    then
        provider_notice_weakening_mutants_rejected=0
        break
    fi
    if provider_notice_lifecycle_contract "$mutant"; then
        provider_notice_weakening_mutants_rejected=0
        break
    fi
done
if [[ "$provider_notice_weakening_mutants_rejected" == "1" ]]; then
    ok "installed provider notice contract rejects every clause weakening mutation"
else
    bad "installed provider notice contract rejects every clause weakening mutation"
fi

if [[ "$installed_root" == "$(cd "$ROOT" && pwd -P)" ]] \
        && grep -Fq '[launch notices](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#approval-bindings-and-launch-notices)' "$ROOT/skills/agy-worker/SKILL.md" \
        && grep -Fq '[launch notices](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#approval-bindings-and-launch-notices)' "$TMP/installed/agy-worker/SKILL.md" \
        && grep -Fq '[Material planning governance](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#material-planning-governance)' "$ROOT/skills/agy-worker/SKILL.md" \
        && grep -Fq '[Material planning governance](references/PROJECT_LIFECYCLE_AND_VERIFICATION.md#material-planning-governance)' "$TMP/installed/agy-worker/SKILL.md"; then
    ok "source and installed skill entrypoints link to lifecycle-owned notice and governance contracts"
else
    bad "source and installed skill entrypoints link to lifecycle-owned notice and governance contracts"
fi

provider_read_scope_clauses=(
    'Prefer `--provider-scope FILE --approve-transmission-sha SHA256` for bounded jobs. It binds reviewed read entries, their content digest, and a write subset in a fresh owner-private mode-`0700` Gitless stage.'
    'Whole-worktree dispatch requires `--approve-whole-worktree LAUNCH_APPROVAL_SHA256`. Every disposable-worktree entry is provider-readable and may reach Google/Gemini; `--add-dir`, prompt denylists and gate path policies do not narrow that read boundary.'
    'Neither `workflow.sh run` nor the advanced `agy-worker.sh` initial dispatch has an implicit transmission mode.'
    'The whole-worktree digest binds content, kinds, full file mode bits, symlink target hashes, the'
    'readable manifest, provider isolation and native grant profile. The scoped digest'
    'binds canonical read/write policy, readable path/kind manifest, selected bytes and'
    'executable bits, isolation and grant profile; scoped mode rejects symlinks and does'
    'not bind full POSIX permissions. The controller rechecks the approved boundary'
    'Retired dispatch and workflow job formats are rejected; finish or discard them with their creating release, without migration.'
    'Default `--provider-isolation session` uses the existing AGY session. AGY has normal user filesystem/network authority; staging and reconciliation are not host isolation.'
    'Explicit `--provider-isolation native` requires supported macOS scoped containment; it never falls back to session mode. Preserve the recorded isolation mode and grant profile across repairs.'
    'Provider-scope approval grants neither provider execution, Git action, driver acceptance, nor publication.'
    'Exclude secrets, denied paths and unrelated private content from every approved entry; telling the worker not to read an approved entry is not a control.'
)

provider_read_scope_skill_contract() {
    local skill_path="$1" clause
    for clause in "${provider_read_scope_clauses[@]}"; do
        [[ "$(grep -Fxc "$clause" "$skill_path")" == "1" ]] || return 1
    done
}

if provider_read_scope_skill_contract "$ROOT/skills/agy-worker/SKILL.md" \
        && provider_read_scope_skill_contract "$TMP/installed/agy-worker/SKILL.md"; then
    ok "source and installed skills preserve whole-worktree and scoped provider read contracts"
else
    bad "source and installed skills preserve whole-worktree and scoped provider read contracts"
fi

provider_read_scope_mutants_rejected=1
provider_read_scope_mutant_index=0
for clause in "${provider_read_scope_clauses[@]}"; do
    provider_read_scope_mutant_index=$((provider_read_scope_mutant_index + 1))
    mutant="$TMP/provider-read-scope-mutant-$provider_read_scope_mutant_index.md"
    if ! python3 -B - "$TMP/installed/agy-worker/SKILL.md" "$mutant" "$clause" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
clause = sys.argv[3]
text = source.read_text(encoding="utf-8")
if text.count(clause) != 1:
    raise SystemExit(1)
target.write_text(text.replace(clause, "", 1), encoding="utf-8")
PY
    then
        provider_read_scope_mutants_rejected=0
        break
    fi
    if provider_read_scope_skill_contract "$mutant"; then
        provider_read_scope_mutants_rejected=0
        break
    fi
done
if [[ "$provider_read_scope_mutants_rejected" == "1" ]]; then
    ok "whole-worktree and scoped provider contracts reject every independent clause deletion"
else
    bad "whole-worktree and scoped provider contracts reject every independent clause deletion"
fi

provider_read_scope_weakening_mutants_rejected=1
provider_read_scope_weakening_mutant_index=0
provider_read_scope_weakening_replacements=(
    'The controller rechecks the approved boundary::The controller may skip rechecking the approved boundary'
    'Retired dispatch and workflow job formats are rejected::Retired dispatch and workflow job formats acquire current authority automatically'
    'do not narrow that read boundary::narrow that read boundary'
    'Neither `workflow.sh run` nor the advanced `agy-worker.sh` initial dispatch::Both `workflow.sh run` and the advanced `agy-worker.sh` initial dispatch'
    'a write subset::an unrelated write set'
    'AGY has normal user filesystem/network authority::AGY has restricted host authority'
    'it never falls back to session mode::it may fall back to session mode'
    'grants neither provider execution, Git action, driver acceptance, nor publication::grants provider execution and Git authority'
    'telling the worker not to read an approved entry is not a control::telling the worker not to read an approved entry is sufficient'
)
for pair in "${provider_read_scope_weakening_replacements[@]}"; do
    provider_read_scope_weakening_mutant_index=$((provider_read_scope_weakening_mutant_index + 1))
    old_fragment="${pair%%::*}"
    new_fragment="${pair##*::}"
    mutant="$TMP/provider-read-scope-weakened-$provider_read_scope_weakening_mutant_index.md"
    if ! python3 -B - "$TMP/installed/agy-worker/SKILL.md" "$mutant" \
            "$old_fragment" "$new_fragment" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
old_fragment = sys.argv[3]
new_fragment = sys.argv[4]
text = source.read_text(encoding="utf-8")
if text.count(old_fragment) != 1:
    raise SystemExit(1)
target.write_text(text.replace(old_fragment, new_fragment, 1), encoding="utf-8")
PY
    then
        provider_read_scope_weakening_mutants_rejected=0
        break
    fi
    if provider_read_scope_skill_contract "$mutant"; then
        provider_read_scope_weakening_mutants_rejected=0
        break
    fi
done
if [[ "$provider_read_scope_weakening_mutants_rejected" == "1" ]]; then
    ok "whole-worktree and scoped provider contracts reject every weakening mutation"
else
    bad "whole-worktree and scoped provider contracts reject every weakening mutation"
fi

if python3 -B - "$ROOT/skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md" \
        "$TMP/installed/agy-worker/references/SECURITY_AND_COMPATIBILITY.md" <<'PY_NATIVE_DOC'
from pathlib import Path
import sys

clauses = (
    "private persistent provider HOME, per-attempt TMP",
    "Preserve the selected mode and grant profile throughout repairs.",
    "wildcard binds, not just loopback",
    "arguments, operations or items; broader same-user Keychain reads, additions, changes and deletions may be allowed by the OS.",
    "detached descendants remain confined but are not proven reaped.",
)
for filename in sys.argv[1:]:
    text = " ".join(Path(filename).read_text(encoding="utf-8").split())
    def native_contract(value: str) -> bool:
        return all(clause in value for clause in clauses)
    assert native_contract(text), filename
    for clause in clauses:
        assert text.count(clause) == 1, clause
        assert not native_contract(text.replace(clause, "", 1)), clause
        assert not native_contract(text.replace(clause, "Full isolation and guaranteed cleanup.", 1)), clause
PY_NATIVE_DOC
then
    ok "source and installed security guides preserve native limits and reject stronger-isolation claims"
else
    bad "source and installed security guides preserve native limits and reject stronger-isolation claims"
fi

if python3 -B - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
required = {
    "README.md": (
        "Prefer `--provider-scope` for bounded jobs",
        "Whole-worktree dispatch remains an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception",
        "requires an explicit transmission choice",
        "it binds reviewed read entries, their content digest, and a write subset",
        "New jobs use the existing AGY session by default",
        "--provider-isolation native` optionally adds macOS containment",
    ),
    "PRIVACY.md": (
        "Prefer `--provider-scope` for bounded jobs",
        "Whole-worktree dispatch remains an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception",
        "--provider-isolation session",
        "never falls back to session mode",
    ),
    "SECURITY.md": (
        "Prefer `--provider-scope` for bounded jobs",
        "Whole-worktree dispatch remains an explicit manifest-bound exception",
    ),
    "AGENTS.md": (
        "Prefer scoped mode: `--provider-scope` plus `transmission_sha256`.",
        "Whole-worktree mode needs `launch_approval_sha256`.",
        "everything in the worktree is agy-readable and may reach Google/Gemini",
    ),
    "docs/USAGE.md": (
        "Prefer scoped dispatch for bounded jobs",
        "Whole-worktree dispatch remains an explicit manifest-bound exception",
        "New jobs default to `--provider-isolation session`",
        "--approve-whole-worktree LAUNCH_APPROVAL_SHA256",
    ),
    "docs/VERIFYING_AGENT_OUTPUT.md": (
        "Whole-worktree dispatch remains an explicit manifest-bound exception",
        "The recommended provider-scope mode instead binds exact reviewed read entries",
    ),
    "docs/MARKETPLACE.md": (
        "Prefer `--provider-scope` for bounded jobs",
        "Whole-worktree dispatch remains an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception",
        "new jobs default to `--provider-isolation session`",
    ),
    "docs/REPO_MAP.md": (
        "agy_dispatch.py", "agy_dispatch_worktree.py", "tests/test-agy-worker-remediation.py",
    ),
    "docs/index.md": (
        "No initial launch path has an implicit provider-read mode.",
        "<code>--approve-whole-worktree</code> binds current content, file kinds, permissions, symlink targets, and execution mode",
        "The recommended bounded-job path is <code>--provider-scope</code> plus the exact transmission digest",
        "session mode uses the existing AGY session; explicit native mode requires supported macOS containment",
    ),
    "docs/PROJECT_WORKFLOW.md": (
        "Choose the transmission mode explicitly",
        "`--provider-scope FILE --approve-transmission-sha SHA256`, which binds exact reviewed read/write entries",
        "--approve-whole-worktree LAUNCH_APPROVAL_SHA256",
        "session mode uses the existing AGY session; explicit native mode requires supported macOS containment",
    ),
    "skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md": (
        "Prefer scoped dispatch for bounded jobs",
        "Whole-worktree dispatch remains an explicit `--approve-whole-worktree LAUNCH_APPROVAL_SHA256` exception",
        "Default `--provider-isolation session` retains the caller's existing HOME/session",
        "Provider-scope approval binds reviewed content and policy; it grants neither provider execution, Git action, driver acceptance, nor publication.",
    ),
}
for relative, phrases in required.items():
    flattened = " ".join((root / relative).read_text(encoding="utf-8").split())
    assert all(phrase in flattened for phrase in phrases), (relative, phrases)

# Read authority is owned by the usage guide, independently of its write policy.
usage = " ".join((root / "docs/USAGE.md").read_text(encoding="utf-8").split())
assert "`--add-dir`, prompt instructions, and later gate paths do not narrow it." in usage
assert "AGY retains normal user filesystem/network authority" in usage
PY
then
    ok "public and contributor docs distinguish explicit whole-worktree and scoped staging boundaries"
else
    bad "public and contributor docs distinguish explicit whole-worktree and scoped staging boundaries"
fi

if grep -Fq 'Before every provider-launch attempt—initial `run`/`start`, `resume`, `continue`, and' \
        "$ROOT/docs/USAGE.md" \
        && provider_notice_lifecycle_contract "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && provider_notice_lifecycle_contract "$TMP/installed/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md"; then
    ok "package documentation describes mandatory user-facing provider dispatch notice contract"
else
    bad "package documentation describes mandatory user-facing provider dispatch notice contract"
fi

mkdir -p "$TMP/reject-relative/agy-worker"
cp -R "$ROOT/skills/agy-worker/"* "$TMP/reject-relative/agy-worker/"
printf '../relative\n' > "$TMP/reject-relative/agy-worker/.pipeline-root"
bash "$TMP/reject-relative/agy-worker/scripts/resolve-pipeline.sh" \
    > "$TMP/relative.out" 2> "$TMP/relative.err"
rc=$?
if [[ "$rc" == "2" && ! -s "$TMP/relative.out" ]]; then
    ok "standalone resolver rejects a relative pipeline marker"
else
    bad "standalone resolver rejects a relative pipeline marker"
fi

printf '/definitely/missing/codex-agy-worker\n' > "$TMP/reject-relative/agy-worker/.pipeline-root"
bash "$TMP/reject-relative/agy-worker/scripts/resolve-pipeline.sh" \
    > "$TMP/missing.out" 2> "$TMP/missing.err"
rc=$?
if [[ "$rc" == "2" && ! -s "$TMP/missing.out" ]]; then
    ok "standalone resolver rejects a missing pipeline runtime"
else
    bad "standalone resolver rejects a missing pipeline runtime"
fi

governance_docs_contract() {
    /usr/bin/python3 -I -S -B - "$CI_STAGES" "$ROOT/CONTRIBUTING.md" \
        "$ROOT/.github/pull_request_template.md" <<'PY'
from pathlib import Path
import sys

stages_file = Path(sys.argv[1])
contributing = Path(sys.argv[2]).read_text(encoding="utf-8")
template = Path(sys.argv[3]).read_text(encoding="utf-8")

sys.path.insert(0, str(stages_file.parent))
import ci_stages

suite_commands = [
    " ".join(s.argv)
    for s in ci_stages.STAGES
    if s.argv and (s.argv[0].startswith("./tests/test-") or (len(s.argv) > 4 and s.argv[4].startswith("tests/test-")))
]

valid = (
    len(suite_commands) == len(set(suite_commands)) == 18
    and "/usr/bin/python3 -I -S -B scripts/ci_stages.py --list" in contributing
    and {command for command in suite_commands if command in contributing}
    == {"/usr/bin/python3 -I -S -B tests/test-agy-worker-remediation.py"}
    and template.count("./scripts/ci-offline.sh") == 1
    and not any(command in template for command in suite_commands)
    and "Human diff review completed" in template
    and all(
        phrase in template
        for phrase in (
            "No worker-reported command or test was treated as evidence.",
            "No permission, authentication, privacy, or path-policy boundary was weakened.",
            "No commit, push, merge, release, issue submission, or external setting change",
        )
    )
)
if not valid:
    raise SystemExit(1)
PY
}

if governance_docs_contract \
        && grep -Fq 'The canonical offline stages' "$ROOT/docs/OPERATIONS.md" \
        && grep -Fq 'all registered offline stages' "$ROOT/CONTRIBUTING.md" \
        && grep -Fq 'tests/test-update-notifier.py' "$ROOT/docs/REPO_MAP.md" \
        && [[ -x "$ROOT/update-notifier.sh" ]] \
        && grep -Fq 'Google/Gemini' "$ROOT/PRIVACY.md" \
        && grep -Fq 'logs/' "$ROOT/PRIVACY.md" \
        && grep -Fq 'GitHub Issues' "$ROOT/SUPPORT.md" \
        && grep -Fq 'not legal advice' "$ROOT/TERMS.md"; then
    ok "governance keeps one canonical PR gate, targeted diagnostics, and public policy boundaries"
else
    bad "governance keeps one canonical PR gate, targeted diagnostics, and public policy boundaries"
fi

if grep -Fq '## AGY capability requirements' "$ROOT/docs/INSTALLATION.md" \
        && grep -Fq 'Model and effort are forwarded as caller-selected values.' "$ROOT/docs/INSTALLATION.md" \
        && grep -Fq 'Version text is diagnostic only' "$ROOT/docs/INSTALLATION.md" \
        && grep -Fq 'This agy-worker release accepts only the current dispatcher state and' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'Older records fail closed before partial projection, migration, or job mutation.' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'WORKTREE_SNAPSHOT_SEMANTIC_V1 = "semantic-v1"' "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        && grep -Fq 'CURRENT_WORKTREE_SNAPSHOT_ALGORITHM = WORKTREE_SNAPSHOT_SEMANTIC_V1' "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        && grep -Fq 'Every emitted action or stale-approval rerun command uses the caller-resolved' \
            "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'Current controller-private state also persists a sanitized' \
            "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq '`status`, `wait`, and `result` JSON intentionally omit it' \
            "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq '`runtime/scripts/agy_dispatch.py`) uses `dispatching`' \
            "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && grep -Fq '| `--allow-slash-commands` |' "$ROOT/docs/USAGE.md" \
        && grep -Fq 'Leave slash expansion disabled when any prompt content comes from a repository or' \
            "$ROOT/docs/USAGE.md" \
        && grep -Fq '| `cheap` | `gemini-3.6-flash-low` |' "$ROOT/docs/USAGE.md" \
        && grep -Fq '| `hardest` | `claude-opus-4-6-thinking` |' "$ROOT/docs/USAGE.md" \
        && grep -Fq './model-recommendation.sh --stage pre-dispatch' "$ROOT/docs/USAGE.md" \
        && grep -Fq './model-recommendation.sh --stage post-gate' "$ROOT/docs/USAGE.md" \
        && grep -Fq 'symbolic launcher `"$PIPELINE/agy-worker.sh"`; export `PIPELINE` before copying it.' \
            "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'deterministic state, worktree, and branch bindings under an owner-private' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'Keep `STATE_DIR` owner-private and outside both the repository and worktree.' \
            "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && grep -Fq 'Every emitted action or stale-approval rerun command uses' \
            "$ROOT/skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md" \
        && grep -Fq 'tests/test-agy-worker.sh' "$ROOT/docs/REPO_MAP.md" \
        && grep -Fq 'tests/test-agy-worker-remediation.py' "$ROOT/docs/REPO_MAP.md" \
        && grep -Fq 'tests/test-doctor.sh' "$ROOT/docs/REPO_MAP.md" \
        && grep -Fq 'export PYTHONDONTWRITEBYTECODE=1' "$ROOT/tests/test-agy-worker.sh" \
        && [[ ! -e "$ROOT/skills/agy-worker/runtime/scripts/legacy_dispatch_state.py" ]] \
        && ! grep -Fq 'resolution remains blocked until installed agy exactly matches' \
            "$ROOT/docs/INSTALLATION.md"; then
    ok "dispatcher docs describe mode-bound selection, source-owned lifecycle state, no-bytecode imports, and registered focused coverage"
else
    bad "dispatcher docs describe mode-bound selection, source-owned lifecycle state, no-bytecode imports, and registered focused coverage"
fi

if python3 -B - "$ROOT" <<'PYRETIRED'
from pathlib import Path
import sys
root = Path(sys.argv[1])
for path in (root / "compat", root / "skills/agy-worker/runtime/compat"):
    assert not path.exists() or not any(p.is_file() for p in path.rglob("*")), path
for pattern in ("scripts/version_*.py", "scripts/models_*.py", "tests/test-version-*.py", "tests/test-models-*.py"):
    assert not list(root.glob(pattern)), pattern
assert not (root / ".github/workflows/compatibility-watch.yml").exists()
assert (root / "skills/agy-worker/runtime/scripts/model_selection.py").is_file()
PYRETIRED
then ok "retired attestation assets are absent while the shared capability probe remains packaged"
else bad "retired attestation assets are absent while the shared capability probe remains packaged"
fi

if grep -Fq 'same-UID processes' "$ROOT/docs/CONFORMANCE.md" \
        && grep -Fq 'It never scans for or chases a moved directory.' \
            "$ROOT/docs/CONFORMANCE.md" \
        && grep -Fq 'may leave a private residual' "$ROOT/PRIVACY.md" \
        && grep -Fq 'not claim same-user tamper resistance; review the supplied gate and loaded code' \
            "$ROOT/docs/CONFORMANCE.md" \
        && grep -Fq 'targets. The final pathname removal is explicitly inside the same-UID TCB.' \
            "$ROOT/docs/CONFORMANCE.md"; then
    ok "conformance docs bind the same-UID TCB and fail-closed residual boundary"
else
    bad "conformance docs bind the same-UID TCB and fail-closed residual boundary"
fi

python3 "$ROOT/scripts/validate-brand-assets.py" "$ROOT/docs/assets/brand" \
    > "$TMP/brand-valid.out" 2> "$TMP/brand-valid.err"
brand_valid_rc=$?
if [[ "$brand_valid_rc" == "0" ]] \
        && grep -Fq '4 SVG, 7 PNG' "$TMP/brand-valid.out" \
        && grep -Fq 'https://cagdasyurekli.github.io/codex-agy-worker/' "$ROOT/docs/_config.yml" \
        && grep -Fq 'https://cagdasyurekli.github.io/codex-agy-worker/assets/brand/social-preview-1280x640.png' "$ROOT/docs/_config.yml" \
        && grep -Fq '{% assign resolved_canonical_url = page.canonical_url %}' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '{% assign resolved_canonical_url = page.url | absolute_url %}' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '<link rel="canonical" href="{{ resolved_canonical_url | escape }}">' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '<meta property="og:url" content="{{ resolved_canonical_url | escape }}">' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'property="og:image"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'name="google-site-verification" content="EwC8gQMZuIrAWw4ZLoyE_FjHZIHZGXNX7IeXOcvZHvs"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'name="twitter:card" content="summary_large_image"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'sizes="16x16"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'sizes="32x32"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '<picture aria-hidden="true">' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'code { overflow-wrap: anywhere; }' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'pre code { overflow-wrap: normal; }' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'table { border-collapse: collapse; display: block; max-width: 100%; overflow-x: auto; }' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '{% if page.url == "/" %}' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq 'type="application/ld+json"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '"@type": "SoftwareSourceCode"' "$ROOT/docs/_layouts/default.html" \
        && grep -Fq '"codeRepository": "https://github.com/cagdasyurekli/codex-agy-worker"' "$ROOT/docs/_layouts/default.html" \
        && [[ "$(grep -Fc '<h1>' "$ROOT/docs/index.md")" == "1" ]] \
        && grep -Fq 'Delegate coding work. Verify before you trust it.' "$ROOT/docs/index.md" \
        && grep -Fq 'href="https://github.com/cagdasyurekli/codex-agy-worker">View on GitHub</a>' "$ROOT/docs/index.md" \
        && grep -Fq 'must not create body-level horizontal overflow at a 390-pixel mobile' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '<loc>https://cagdasyurekli.github.io/codex-agy-worker/</loc>' "$ROOT/docs/sitemap.xml" \
        && grep -Fq '<loc>https://cagdasyurekli.github.io/codex-agy-worker/VERIFYING_AGENT_OUTPUT.html</loc>' "$ROOT/docs/sitemap.xml" \
        && [[ "$(grep -Fc '<url>' "$ROOT/docs/sitemap.xml")" == "2" ]] \
        && grep -Fq 'GitHub repository as the source of truth' "$ROOT/docs/index.md" \
        && grep -Fq 'VERIFYING_AGENT_OUTPUT.html' "$ROOT/docs/index.md" \
        && grep -Fq 'blob/main/docs/INSTALLATION.md' "$ROOT/docs/index.md" \
        && grep -Fq 'blob/main/docs/USAGE.md' "$ROOT/docs/index.md" \
        && grep -Fq 'canonical_url: "https://cagdasyurekli.github.io/codex-agy-worker/VERIFYING_AGENT_OUTPUT.html"' "$ROOT/docs/VERIFYING_AGENT_OUTPUT.md" \
        && grep -Fq 'An Agent Skill for bounded Antigravity CLI delegation' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq '## Quick start' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq 'codex plugin marketplace add cagdasyurekli/codex-agy-worker' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq 'codex plugin add agy-worker@agy-worker' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq 'git clone https://github.com/cagdasyurekli/codex-agy-worker.git' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq 'does not authorize a provider dispatch or repository transmission' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq './proof-demo.sh' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq 'Read [PRIVACY.md](PRIVACY.md).' < <(sed -n '1,120p' "$ROOT/README.md") \
        && grep -Fq '<picture>' "$ROOT/README.md" \
        && grep -Fq 'srcset="docs/assets/brand/logo-dark.svg"' "$ROOT/README.md" \
        && grep -Fq 'src="docs/assets/brand/logo-light.svg" alt=""' "$ROOT/README.md" \
        && [[ ! -e "$ROOT/docs/robots.txt" ]]; then
    ok "approved brand assets and GitHub Pages wiring pass the production contract"
else
    bad "approved brand assets and GitHub Pages wiring pass the production contract"
fi

if python3 - "$ROOT/docs/_layouts/default.html" <<'PY'
import json
from pathlib import Path
import re
import sys

layout = Path(sys.argv[1]).read_text(encoding="utf-8")
matches = re.findall(
    r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
    layout,
    flags=re.S,
)
assert len(matches) == 1
payload = json.loads(matches[0])
assert payload["@context"] == "https://schema.org"
assert payload["@type"] == "SoftwareSourceCode"
assert payload["codeRepository"] == "https://github.com/cagdasyurekli/codex-agy-worker"
assert payload["programmingLanguage"] == ["Python", "Shell"]
assert payload["license"].endswith("/blob/main/LICENSE")
assert '{% if page.url == "/" %}' in layout
PY
then
    ok "homepage SoftwareSourceCode structured data is valid JSON with truthful core fields"
else
    bad "homepage SoftwareSourceCode structured data is valid JSON with truthful core fields"
fi

python3 "$ROOT/scripts/validate-docs.py" "$ROOT" --readme-max-lines 250 \
    > "$TMP/docs-valid.out" 2> "$TMP/docs-valid.err"
docs_valid_rc=$?
python3 - "$ROOT/scripts/validate-docs.py" "$ROOT/README.md" "$ROOT" <<'PY'
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

script = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("validate_docs", script)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

readme_path = Path(sys.argv[2])
root_path = Path(sys.argv[3])
readme = readme_path.read_text(encoding="utf-8")
assert module.validate_onboarding(readme, 250) == []
max_lines = 250
padding = ["<!-- budget mutation -->"] * (max_lines + 1 - len(readme.splitlines()))
over_budget = "\n".join([*readme.splitlines(), *padding])
assert len(over_budget.splitlines()) == 251
assert any("maximum is 250" in error for error in module.validate_onboarding(over_budget, max_lines))
assert any("maximum is 250" in error for error in module.validate_onboarding(over_budget, 1000))
exact_limit = "\n".join([*readme.splitlines(), *(["padding"] * (250 - len(readme.splitlines())))])
assert module.validate_onboarding(exact_limit, 250) == []
assert any("maximum is 249" in error for error in module.validate_onboarding(exact_limit, 249))

# Exercise the public CLI on one otherwise-valid minimal documentation tree.
with tempfile.TemporaryDirectory(prefix="agy-doc-budgets-") as temporary:
    budget_root = Path(temporary)
    (budget_root / "docs").mkdir()
    markers = [marker + module.STANDALONE_ONBOARDING_SUFFIX.get(label, "")
               for label, marker in module.ONBOARDING_MARKERS]
    boundary_readme = "\n".join([*markers, *(["padding"] * (250 - len(markers)))]) + "\n"
    (budget_root / "README.md").write_text(boundary_readme, encoding="utf-8")
    (budget_root / "LICENSE").write_text("fixture", encoding="utf-8")
    for filename in ("index.md", "VERIFYING_AGENT_OUTPUT.md"):
        (budget_root / "docs" / filename).write_text("# Guide\n", encoding="utf-8")
    (budget_root / "docs/sitemap.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'
        + module.PAGES_BASE + '</loc></url></urlset>', encoding="utf-8",
    )
    limits = {"docs/ROADMAP.md": 600, "docs/lessons_learned.md": 1200, "docs/REPO_MAP.md": 1500}
    for relative, limit in limits.items():
        (budget_root / relative).write_text(" ".join(["word"] * limit) + "\n", encoding="utf-8")
    public_files = ["docs/public-files.allowlist", "docs/sitemap.xml", "docs/index.md",
                    "docs/VERIFYING_AGENT_OUTPUT.md", *limits]
    (budget_root / "docs/public-files.allowlist").write_text(
        "\n".join(sorted(public_files)) + "\n", encoding="utf-8",
    )

    def budget_cli(cap: int = 450) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(script), str(budget_root), "--readme-max-lines", str(cap)],
            capture_output=True, text=True, check=False,
        )

    assert budget_cli().returncode == 0
    (budget_root / "README.md").write_text(boundary_readme + "extra\n", encoding="utf-8")
    for requested in (250, 450, 1000):
        rejected = budget_cli(requested)
        assert rejected.returncode == 1 and "README has 251 lines; maximum is 250" in rejected.stderr
    (budget_root / "README.md").write_text(boundary_readme, encoding="utf-8")
    assert "maximum is 249" in budget_cli(249).stderr
    for requested in (0, -1):
        rejected = budget_cli(requested)
        assert rejected.returncode == 2 and "must be positive" in rejected.stderr
    for relative, limit in limits.items():
        path = budget_root / relative
        # Headings, tables, comments and fenced tokens all count as full-source words.
        prefix = "# Heading\n| table |\n<!-- comment -->\n```text\nfenced\n```\n"
        at_limit = prefix + "\t".join(["word"] * (limit - len(prefix.split()))) + "\n"
        path.write_text(at_limit, encoding="utf-8")
        assert budget_cli().returncode == 0, relative
        path.write_text(at_limit + "extra\n", encoding="utf-8")
        rejected = budget_cli()
        assert rejected.returncode == 1 and f"{relative} has {limit + 1} words; maximum is {limit}" in rejected.stderr
        path.unlink()
        assert f"{relative} must be a regular file" in budget_cli().stderr
        path.mkdir()
        assert f"{relative} must be a regular file" in budget_cli().stderr
        path.rmdir()
        path.symlink_to(budget_root / "docs/index.md")
        assert f"{relative} must be a regular file" in budget_cli().stderr
        path.unlink()
        path.write_text(at_limit, encoding="utf-8")
    assert budget_cli().returncode == 0

hidden_markers = "\n".join(
    f"<!-- {marker} -->" for _label, marker in module.ONBOARDING_MARKERS
)
assert module.validate_onboarding(hidden_markers, 250)
unclosed_comment = "<!--\n" + "\n".join(marker for _label, marker in module.ONBOARDING_MARKERS)
assert module.validate_onboarding(unclosed_comment, 250)
fenced_markers = "```text\n" + "\n".join(
    marker for _label, marker in module.ONBOARDING_MARKERS
) + "\n```"
assert module.validate_onboarding(fenced_markers, 250)
full_tutorial = module.ONBOARDING_MARKERS[-1][1]
broken_tutorial = readme.replace(full_tutorial, full_tutorial.split("](", 1)[0] + "]")
assert any("verification tutorial" in error for error in module.validate_onboarding(broken_tutorial, 250))
inline_code_tutorial = readme.replace(full_tutorial + ".", f"`{full_tutorial}`")
assert any("verification tutorial" in error for error in module.validate_onboarding(inline_code_tutorial, 250))

lines = readme.splitlines()
positioning = next(index for index, line in enumerate(lines) if module.ONBOARDING_MARKERS[0][1] in line)
workflow_badge = next(index for index, line in enumerate(lines) if module.ONBOARDING_MARKERS[1][1] in line)
lines[positioning], lines[workflow_badge] = lines[workflow_badge], lines[positioning]
assert any("out of order" in error for error in module.validate_onboarding("\n".join(lines), 250))

guide_links = {
    "INSTALLATION.md": "[Installation and compatibility](docs/INSTALLATION.md)",
    "USAGE.md": "[Usage](docs/USAGE.md)",
    "PROJECT_WORKFLOW.md": "[Project workflow](docs/PROJECT_WORKFLOW.md)",
    "OPERATIONS.md": "[Operations](docs/OPERATIONS.md)",
}
for filename, link in guide_links.items():
    guide = root_path / "docs" / filename
    assert guide.is_file() and not guide.is_symlink(), filename
    assert link in readme, link

migrated_literal = "The `--output` CLI path is deliberately process-owning"
assert migrated_literal not in readme
project_only_markers = (
    migrated_literal,
    '--format github-step-summary >> "${GITHUB_STEP_SUMMARY:?}"',
    "fork-controlled paths, repository content, tokens, or secrets",
)
for marker in project_only_markers:
    owners = [
        root_path / "docs" / filename
        for filename in guide_links
        if marker in (root_path / "docs" / filename).read_text(encoding="utf-8")
    ]
    assert owners == [root_path / "docs" / "PROJECT_WORKFLOW.md"], (marker, owners)

with tempfile.TemporaryDirectory() as directory:
    guide_root = Path(directory) / "repo"
    guide_docs = guide_root / "docs"
    guide_docs.mkdir(parents=True)
    exact_links = []
    for filename in guide_links:
        (guide_docs / filename).write_text(f"# {filename}\n", encoding="utf-8")
        exact_links.append(f"[{filename}](docs/{filename})")
    guide_readme = guide_root / "README.md"
    exact_readme = "\n".join(exact_links) + "\n"
    guide_readme.write_text(exact_readme, encoding="utf-8")
    assert module.validate_markdown_links(guide_root) == []
    for filename in guide_links:
        wrong_case = filename[0].lower() + filename[1:]
        guide_readme.write_text(
            exact_readme.replace(f"docs/{filename}", f"docs/{wrong_case}"),
            encoding="utf-8",
        )
        assert any(
            "non-exact path casing" in error
            for error in module.validate_markdown_links(guide_root)
        ), filename
    guide_readme.write_text(exact_readme, encoding="utf-8")
    allowlist = guide_docs / "public-files.allowlist"
    allowlist.write_text(
        "".join(f"docs/{filename}\n" for filename in sorted(guide_links))
        + "docs/public-files.allowlist\n",
        encoding="utf-8",
    )
    victim = guide_docs / "OPERATIONS.md"
    victim.unlink()
    victim.symlink_to("USAGE.md")
    assert any(
        "regular file" in error
        for error in module.validate_public_docs_inventory(guide_root)
    )

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory) / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("[missing](docs/no.md)\n", encoding="utf-8")
    assert any("missing local link target" in error for error in module.validate_markdown_links(root))
    (root / "docs" / "guide.md").write_text("# Present\n", encoding="utf-8")
    (root / "README.md").write_text("[bad anchor](docs/guide.md#missing)\n", encoding="utf-8")
    assert any("missing Markdown anchor" in error for error in module.validate_markdown_links(root))
    (root / "README.md").write_text("[case](docs/GUIDE.md#present)\n", encoding="utf-8")
    assert any("non-exact path casing" in error for error in module.validate_markdown_links(root))
    (root.parent / "outside.md").write_text("# Outside\n", encoding="utf-8")
    (root / "README.md").write_text("[escape](../outside.md#outside)\n", encoding="utf-8")
    assert any("escapes the repository" in error for error in module.validate_markdown_links(root))
    (root / "README.md").write_text("[root](/../outside.md#outside)\n", encoding="utf-8")
    assert any("root-relative" in error for error in module.validate_markdown_links(root))
    (root / "README.md").write_text("[encoded](/%2e%2e/outside.md#outside)\n", encoding="utf-8")
    assert any("root-relative" in error for error in module.validate_markdown_links(root))
    (root / "docs" / "name_(guide).md").write_text("# Parentheses\n", encoding="utf-8")
    (root / "README.md").write_text("[balanced](docs/name_(guide).md#parentheses)\n", encoding="utf-8")
    assert module.validate_markdown_links(root) == []
    allowlist = root / "docs" / "public-files.allowlist"
    allowlist.write_text(
        "docs/guide.md\ndocs/name_(guide).md\ndocs/public-files.allowlist\n",
        encoding="utf-8",
    )
    assert module.validate_public_docs_inventory(root) == []
    (root / "docs" / ".DS_Store").write_bytes(b"ignored OS noise")
    assert any("not public-allowlisted" in error for error in module.validate_public_docs_inventory(root))
    (root / "docs" / ".DS_Store").unlink()
    (root / "docs" / ".DS_Store").mkdir()
    (root / "docs" / ".DS_Store" / "private.md").write_text("# Hidden\n", encoding="utf-8")
    assert any("not public-allowlisted" in error for error in module.validate_public_docs_inventory(root))
    (root / "docs" / ".DS_Store" / "private.md").unlink()
    (root / "docs" / ".DS_Store").rmdir()
    (root / "README.md").write_text("[escaped](docs/name_\\(guide\\).md#parentheses)\n", encoding="utf-8")
    assert module.validate_markdown_links(root) == []
    (root / "docs" / "private-report.MD").write_text("# Private readout\n", encoding="utf-8")
    assert any("not public-allowlisted" in error for error in module.validate_public_docs_inventory(root))
    (root / "docs" / "private-report.markdown").write_text("# Private readout\n", encoding="utf-8")
    assert any("not public-allowlisted" in error for error in module.validate_public_docs_inventory(root))
    (root / "docs" / "guide.markdown").write_text("[missing](nope.md)\n", encoding="utf-8")
    assert any("missing local link target" in error for error in module.validate_markdown_links(root))
    campaign = root / "docs" / "campaign-report-2026-08-29.md"
    campaign.write_text("# Private readout\n", encoding="utf-8")
    allowlist.write_text(
        "docs/campaign-report-2026-08-29.md\ndocs/guide.md\ndocs/name_(guide).md\n"
        "docs/private-report.MD\ndocs/private-report.markdown\ndocs/public-files.allowlist\n",
        encoding="utf-8",
    )
    assert any("forbidden private/report/draft/dated" in error for error in module.validate_public_docs_inventory(root))

    sitemap = root / "docs" / "sitemap.xml"
    sitemap.write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n',
        encoding="utf-8",
    )
    assert any("at least one owned URL" in error for error in module.validate_pages_sitemap(root))
    sitemap.write_text("<urlset></urlset>\n", encoding="utf-8")
    assert any("sitemap urlset namespace" in error for error in module.validate_pages_sitemap(root))
    sitemap.write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'
        + module.PAGES_BASE
        + "GUIDE.html</loc></url></urlset>\n",
        encoding="utf-8",
    )
    assert any("non-exact path casing" in error for error in module.validate_pages_sitemap(root))
PY
docs_mutation_rc=$?
if tracked_evidence="$(git -C "$ROOT" ls-files -- 'evidence' 'evidence/**')"; then
    tracked_evidence_rc=0
else
    tracked_evidence_rc=$?
fi
mkdir "$TMP/evidence-pathspec-repo"
git -C "$TMP/evidence-pathspec-repo" init -q
ln -s private-target "$TMP/evidence-pathspec-repo/evidence"
git -C "$TMP/evidence-pathspec-repo" add -f evidence
if [[ "$(git -C "$TMP/evidence-pathspec-repo" ls-files -- 'evidence' 'evidence/**')" == "evidence" ]]; then
    evidence_pathspec_rc=0
else
    evidence_pathspec_rc=1
fi
if git -C "$ROOT" check-ignore -q --no-index \
        docs/agy-worker-campaign-quality-report-2026-08-27.md; then
    removed_report_ignore_rc=0
else
    removed_report_ignore_rc=$?
fi
if [[ "$docs_valid_rc" == "0" ]] \
        && [[ "$docs_mutation_rc" == "0" ]] \
        && [[ "$tracked_evidence_rc" == "0" ]] \
        && [[ "$evidence_pathspec_rc" == "0" ]] \
        && [[ "$removed_report_ignore_rc" == "0" ]] \
        && grep -Fq 'complete public docs inventory, README onboarding order and line budget' "$TMP/docs-valid.out" \
        && grep -Fq '[documentation policy](docs/DOCUMENTATION_POLICY.md)' "$ROOT/CONTRIBUTING.md" \
        && grep -Fq '`README.md` is the first-visit product page' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq 'one authoritative documentation owner' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq 'permanent hard ceiling of **250 physical lines**' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq 'Never raise it' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '`docs/ROADMAP.md` to **600 words**' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '`docs/lessons_learned.md` to **1,200 words**' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '`docs/REPO_MAP.md` to **1,500 words**' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq 'Packaging tests pin operational literals to their authoritative task guide' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '`docs/public-files.allowlist` is the complete set' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq 'Installation never authorizes provider dispatch or repository transmission' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fq '`bash tests/test-packaging.sh`' "$ROOT/docs/DOCUMENTATION_POLICY.md" \
        && grep -Fxq '/evidence' "$ROOT/.gitignore" \
        && grep -Fxq '/docs/private/' "$ROOT/.gitignore" \
        && grep -Fxq '/docs/reports/' "$ROOT/.gitignore" \
        && grep -Fxq '/docs/agy-worker-campaign-quality-report-*.md' "$ROOT/.gitignore" \
        && grep -Fxq '/docs/*campaign-report-20??-??-??*.md' "$ROOT/.gitignore" \
        && [[ -z "$tracked_evidence" ]] \
        && [[ ! -e "$ROOT/docs/agy-worker-campaign-quality-report-2026-08-27.md" ]]; then
    ok "documentation policy, public inventory, ordered onboarding, budget, links, anchors, and Pages mapping stay valid"
else
    bad "documentation policy, public inventory, ordered onboarding, budget, links, anchors, and Pages mapping stay valid"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-image"
python3 - "$TMP/reject-brand-image/logo-light.svg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace("</svg>", '<image href="https://invalid.example/logo.svg"/></svg>'),
    encoding="utf-8",
)
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-image" \
    > "$TMP/brand-image.out" 2> "$TMP/brand-image.err"
brand_image_rc=$?
if [[ "$brand_image_rc" == "1" ]] \
        && grep -Fq 'forbidden image element' "$TMP/brand-image.err"; then
    ok "brand validator rejects an external SVG image reference"
else
    bad "brand validator rejects an external SVG image reference"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-onload"
python3 - "$TMP/reject-brand-onload/logo-light.svg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("<svg ", '<svg onload="alert(1)" ', 1), encoding="utf-8")
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-onload" \
    > "$TMP/brand-onload.out" 2> "$TMP/brand-onload.err"
brand_onload_rc=$?
if [[ "$brand_onload_rc" == "1" ]] \
        && grep -Fq 'event attributes are forbidden' "$TMP/brand-onload.err"; then
    ok "brand validator rejects an SVG root event attribute"
else
    bad "brand validator rejects an SVG root event attribute"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-style"
python3 - "$TMP/reject-brand-style/logo-light.svg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace(
        "</svg>",
        '<style>@import url("https://invalid.example/brand.css");</style></svg>',
    ),
    encoding="utf-8",
)
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-style" \
    > "$TMP/brand-style.out" 2> "$TMP/brand-style.err"
brand_style_rc=$?
if [[ "$brand_style_rc" == "1" ]] \
        && grep -Fq 'forbidden style element' "$TMP/brand-style.err"; then
    ok "brand validator rejects SVG style imports and external CSS"
else
    bad "brand validator rejects SVG style imports and external CSS"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-truncated"
python3 - "$TMP/reject-brand-truncated/social-preview-1280x640.png" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = path.read_bytes()
path.write_bytes(data[:-5])
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-truncated" \
    > "$TMP/brand-truncated.out" 2> "$TMP/brand-truncated.err"
brand_truncated_rc=$?
if [[ "$brand_truncated_rc" == "1" ]] \
        && grep -Fq 'truncated PNG chunk' "$TMP/brand-truncated.err"; then
    ok "brand validator rejects a truncated social-preview PNG"
else
    bad "brand validator rejects a truncated social-preview PNG"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-geometry"
python3 - "$TMP/reject-brand-geometry/logo-dark.svg" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("M800 160", "M801 160", 1), encoding="utf-8")
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-geometry" \
    > "$TMP/brand-geometry.out" 2> "$TMP/brand-geometry.err"
brand_geometry_rc=$?
if [[ "$brand_geometry_rc" == "1" ]] \
        && grep -Fq 'ordered geometry diverged' "$TMP/brand-geometry.err"; then
    ok "brand validator rejects light and dark SVG geometry divergence"
else
    bad "brand validator rejects light and dark SVG geometry divergence"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-trns"
python3 - "$TMP/reject-brand-trns/social-preview-1280x640.png" <<'PY'
from pathlib import Path
import struct
import sys
import zlib

path = Path(sys.argv[1])
data = path.read_bytes()
output = bytearray(data[:8])
cursor = 8
inserted = False
while cursor < len(data):
    length = struct.unpack(">I", data[cursor : cursor + 4])[0]
    chunk_end = cursor + 12 + length
    chunk_type = data[cursor + 4 : cursor + 8]
    if chunk_type == b"IDAT" and not inserted:
        transparent_color = b"\x00\x00\x00\x00\x00\x00"
        trns_type = b"tRNS"
        output.extend(struct.pack(">I", len(transparent_color)))
        output.extend(trns_type)
        output.extend(transparent_color)
        output.extend(
            struct.pack(">I", zlib.crc32(trns_type + transparent_color) & 0xFFFFFFFF)
        )
        inserted = True
    output.extend(data[cursor:chunk_end])
    cursor = chunk_end
assert inserted
path.write_bytes(output)
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-trns" \
    > "$TMP/brand-trns.out" 2> "$TMP/brand-trns.err"
brand_trns_rc=$?
if [[ "$brand_trns_rc" == "1" ]] \
        && grep -Fq 'tRNS is forbidden' "$TMP/brand-trns.err"; then
    ok "brand validator rejects a valid-CRC tRNS transparency chunk"
else
    bad "brand validator rejects a valid-CRC tRNS transparency chunk"
fi

cp -R "$ROOT/docs/assets/brand" "$TMP/reject-brand-idat"
python3 - "$TMP/reject-brand-idat/social-preview-1280x640.png" <<'PY'
from pathlib import Path
import struct
import sys
import zlib

path = Path(sys.argv[1])
data = path.read_bytes()
output = bytearray(data[:8])
cursor = 8
replaced = False
while cursor < len(data):
    length = struct.unpack(">I", data[cursor : cursor + 4])[0]
    chunk_end = cursor + 12 + length
    chunk_type = data[cursor + 4 : cursor + 8]
    if chunk_type == b"IDAT" and not replaced:
        payload = b"\x00" * length
        output.extend(struct.pack(">I", length))
        output.extend(chunk_type)
        output.extend(payload)
        output.extend(struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF))
        replaced = True
    else:
        output.extend(data[cursor:chunk_end])
    cursor = chunk_end
assert replaced
path.write_bytes(output)
PY
python3 "$ROOT/scripts/validate-brand-assets.py" "$TMP/reject-brand-idat" \
    > "$TMP/brand-idat.out" 2> "$TMP/brand-idat.err"
brand_idat_rc=$?
if [[ "$brand_idat_rc" == "1" ]] \
        && grep -Fq 'invalid IDAT zlib stream' "$TMP/brand-idat.err"; then
    ok "brand validator rejects a re-CRCed invalid IDAT zlib stream"
else
    bad "brand validator rejects a re-CRCed invalid IDAT zlib stream"
fi

if [[ ! -e "$ROOT/codex-skill/SKILL.md" ]] \
        && [[ -f "$ROOT/skills/agy-worker/SKILL.md" ]]; then
    ok "repository has one canonical skill source"
else
    bad "repository has one canonical skill source"
fi

if grep -Fq 'There is no version-specific quota countdown or automatic retry.' \
        "$ROOT/skills/agy-worker/references/TROUBLESHOOTING.md" \
        && grep -Fq '| `completed` / `blocked` | The local controller is terminal. |' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'The separate driver dispositions are `verified`, `partially_verified`, `rejected`,' "$ROOT/docs/PROJECT_WORKFLOW.md" \
        && grep -Fq 'strict terminal' "$ROOT/skills/agy-worker/references/TROUBLESHOOTING.md" \
        && grep -Fq 'private `stderr_path`' "$ROOT/skills/agy-worker/references/TROUBLESHOOTING.md"; then
    ok "package documents version-independent failures and private preflight diagnostics"
else
    bad "package documents version-independent failures and private preflight diagnostics"
fi

echo
if (( fail )); then
    echo "FAILED: $fail failed, $pass passed"
    exit 1
fi
echo "PASSED: $pass tests"
