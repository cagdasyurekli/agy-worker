#!/usr/bin/env bash
# Offline dispatcher and installer tests using a fake agy executable.
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1

# The suite owns every dispatcher input it exercises. Ambient caller values would
# otherwise conflict with explicit selector cases or silently change default
# timeout/mode behavior before the fake worker is reached.
unset AGY_WORKER_TIER AGY_WORKER_MODEL AGY_WORKER_EFFORT AGY_WORKER_MODE
unset AGY_WORKER_IDLE_TIMEOUT AGY_WORKER_HARD_TIMEOUT AGY_WORKER_MAX_RUNTIME
unset AGY_WORKER_NOTICE_INTERVAL AGY_WORKER_TIMEOUT AGY_WORKER_SCHEMA
unset AGY_WORKER_MAX_ATTEMPTS AGY_WORKER_JOB_ID AGY_WORKER_LOG_DIR

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE/.."
WORKER="$ROOT/agy-worker.sh"
SELECTOR="$ROOT/model-selection.sh"
TMP="$(mktemp -d -t agyworker-dispatch.XXXXXX)"
tmp_identity() {
    python3 - "$1" <<'PY'
import os
import stat
import sys

try:
    info = os.lstat(sys.argv[1])
except OSError as exc:
    print(f"unavailable errno={exc.errno}")
else:
    print(
        f"exists dev={info.st_dev} ino={info.st_ino} "
        f"mode={stat.S_IMODE(info.st_mode):o} uid={info.st_uid} gid={info.st_gid}"
    )
PY
}
if [[ "${KEEP_AGY_WORKER_TEST_TMP:-0}" == "1" ]]; then
    TMP_START_IDENTITY="$(tmp_identity "$TMP")"
    printf 'test tmp identity at startup: %s; %s\n' "$TMP" "$TMP_START_IDENTITY" >&2
    trap 'TMP_EXIT_IDENTITY="$(tmp_identity "$TMP")"; if [[ "$TMP_EXIT_IDENTITY" == "$TMP_START_IDENTITY" ]]; then printf "test tmp identity at exit: unchanged; %s\n" "$TMP_EXIT_IDENTITY" >&2; else printf "test tmp identity at exit: changed-or-unavailable; startup=%s exit=%s\n" "$TMP_START_IDENTITY" "$TMP_EXIT_IDENTITY" >&2; fi; printf "kept test tmp: %s\n" "$TMP" >&2' EXIT
else
    trap 'rm -rf "$TMP"' EXIT
fi
pass=0; fail=0

ok() { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail+1)); }
expect_exit() {
    local name="$1" want="$2" got="$3"
    if [[ "$got" == "$want" ]]; then ok "$name (exit $got)"; else bad "$name (exit $got, wanted $want)"; fi
}
expect_print_last() {
    local name="$1" argv_file="$2"
    if python3 - "$argv_file" <<'PY'
import sys
parts = [part for part in open(sys.argv[1], "rb").read().split(b"\0") if part]
raise SystemExit(0 if len(parts) >= 2 and parts[-2] == b"--print" else 1)
PY
    then ok "$name"; else bad "$name"; fi
}
private_tree_is_private() {
    python3 - "$1" <<'PY'
import os
import stat
import sys

root = sys.argv[1]
paths = [root]
for current, directories, files in os.walk(root, followlinks=False):
    paths.extend(os.path.join(current, name) for name in directories + files)
for path in paths:
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    if mode & 0o077:
        print(f"non-private artifact: {path} mode={mode:04o}", file=sys.stderr)
        raise SystemExit(1)
PY
}
mode_is() {
    python3 - "$1" "$2" <<'PY'
import os
import stat
import sys

actual = stat.S_IMODE(os.lstat(sys.argv[1]).st_mode)
expected = int(sys.argv[2], 8)
raise SystemExit(0 if actual == expected else 1)
PY
}
log_root_is_acceptable() {
    python3 - "$1" <<'PY'
import os
import stat
import sys

metadata = os.lstat(sys.argv[1])
mode = stat.S_IMODE(metadata.st_mode)
valid = (
    not stat.S_ISLNK(metadata.st_mode)
    and stat.S_ISDIR(metadata.st_mode)
    and metadata.st_uid == os.geteuid()
    and (mode & 0o022) == 0
)
raise SystemExit(0 if valid else 1)
PY
}

process_group_is_gone() {
    python3 -B - "$1" <<'PY'
import os
import sys

try:
    os.killpg(int(sys.argv[1]), 0)
except ProcessLookupError:
    raise SystemExit(0)
except (PermissionError, ValueError):
    pass
raise SystemExit(1)
PY
}

wait_probe_cleanup() {
    local child_pid="$1" probe_pgid="$2" wait_index
    [[ "$child_pid" != "$probe_pgid" ]] || return 1
    for (( wait_index=0; wait_index<100; wait_index++ )); do
        if process_group_is_gone "$probe_pgid"; then
            return 0
        fi
        sleep 0.02
    done
    process_group_is_gone "$probe_pgid"
}

mkdir -p "$TMP/bin" "$TMP/source-repo" "$TMP/logs"
git -C "$TMP/source-repo" init -q
git -C "$TMP/source-repo" -c user.name='agy-worker test' -c user.email='test@example.invalid' \
    commit --allow-empty -q -m initial
git -C "$TMP/source-repo" worktree add -q -b dispatch-tests "$TMP/repo" HEAD
git -C "$TMP/source-repo" worktree add -q -b project-tests "$TMP/project-worktree" HEAD
git -C "$TMP/source-repo" worktree add --detach -q "$TMP/detached-worktree" HEAD
git -C "$TMP/source-repo" worktree add -q -b preview-boundary "$TMP/preview-worktree" HEAD
PREVIEW_WORKTREE="$(cd "$TMP/preview-worktree" && pwd -P)"
PRIMARY_WORKTREE="$(cd "$TMP/source-repo" && pwd -P)"
DETACHED_WORKTREE="$(cd "$TMP/detached-worktree" && pwd -P)"
chmod 0755 "$TMP/logs"
LOGS_REAL="$(cd "$TMP/logs" && pwd -P)"

whole_worktree_manifest_sha() {
    local worker_path="$1" worktree_path="$2" canonical_worktree
    canonical_worktree="$(cd "$worktree_path" && pwd -P)" || return 64
    "$worker_path" transmission-preview --task fixture --workdir "$canonical_worktree" --provider-isolation session \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["launch_approval_sha256"])'
}

echo "transmission preview boundary:"
if python3 -I -S -B - "$WORKER" "$ROOT" "$PRIMARY_WORKTREE" \
        "$PREVIEW_WORKTREE" "$DETACHED_WORKTREE" "$TMP" <<'PY'
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

worker, root_text, primary_text, worktree_text, detached_text, temp_text = sys.argv[1:]
root = Path(root_text)
primary = Path(primary_text)
worktree = Path(worktree_text)
temp = Path(temp_text)
(worktree / ".gitignore").write_text("ignored-path\n")
(worktree / "ignored-path").write_text("ignored")
(worktree / ".visible-dotfile").write_text("dot")
(worktree / "empty-directory").mkdir()
route = temp / "preview-route"
route.mkdir()
marker = temp / "preview-external-called"
for name in ("agy", "git", "curl", "ssh"):
    path = route / name
    path.write_text(f"#!/bin/sh\nprintf called >> '{marker}'\nexit 99\n")
    path.chmod(0o755)
state = temp / "preview-state-must-not-exist"
prompt = temp / "preview-prompt"
prompt.write_text("PROMPT-MUST-NOT-BE-CONSUMED")
environment = dict(os.environ)
environment["PATH"] = str(route) + os.pathsep + environment["PATH"]
environment["AGY_WORKER_LOG_DIR"] = str(state)

def preview() -> tuple[subprocess.CompletedProcess[bytes], dict]:
    with prompt.open("rb") as source:
        completed = subprocess.run(
            [worker, "transmission-preview", "--task", "fixture", "--workdir", str(worktree)],
            stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, check=False,
        )
        assert source.tell() == 0
    value = json.loads(completed.stdout) if completed.returncode == 0 else {}
    return completed, value

first_run, first = preview()
second_run, second = preview()
assert first_run.returncode == second_run.returncode == 0
assert first == second
assert first["provider_launched"] is False
assert first["network_used"] is False
assert first["contents_read"] is True
assert "authority_summary" in first
assert first["authority_summary"]["provider_launched"] is False
assert first["authority_summary"]["network_used"] is False
assert first["authority_summary"]["contents_read"] is True
assert first["authority_summary"]["provider_isolation"] == "session"
assert first["authority_summary"]["content_binding_kind"] == "whole-worktree-content-v1"
assert first["authority_summary"]["local_review_only"] is True
assert first["authority_summary"]["provider_review_authority"] is False
assert first["authority_summary"]["manifest_sha256"] == first["manifest_sha256"]
assert first["authority_summary"]["content_manifest_sha256"] == first["content_manifest_sha256"]
assert first["authority_summary"]["launch_approval_sha256"] == first["launch_approval_sha256"]
assert first["authority_summary"]["provider_authority"] == "normal same-user filesystem and network authority; selected scope is staging and reconciliation, not host confinement"
assert first["resolved_root"] == str(worktree)
assert first["manifest"]["entry_count"] == len(first["manifest"]["entries"])
assert first["content_manifest"]["entry_count"] == len(first["content_manifest"]["entries"])
manifest_bytes = json.dumps(
    first["manifest"], ensure_ascii=True, sort_keys=True, separators=(",", ":")
).encode()
assert hashlib.sha256(manifest_bytes).hexdigest() == first["manifest_sha256"]
content_bytes = json.dumps(
    first["content_manifest"], ensure_ascii=True, sort_keys=True, separators=(",", ":")
).encode()
assert hashlib.sha256(content_bytes).hexdigest() == first["content_manifest_sha256"]
assert "content_manifest" not in first["authority_summary"]
assert "entries" not in first["authority_summary"]
for entry in first["content_manifest"]["entries"]:
    assert set(entry) == ({"kind", "mode", "path"} if entry["kind"] == "directory" else (
        {"kind", "mode", "path", "sha256", "size"} if entry["kind"] == "file"
        else {"kind", "mode", "path", "target_sha256", "target_size"}
    ))
paths = [entry["path"] for entry in first["manifest"]["entries"]]
assert [path.encode() for path in paths] == sorted(path.encode() for path in paths)
for expected in (".gitignore", "ignored-path", ".visible-dotfile", "empty-directory"):
    assert expected in paths
assert not marker.exists() and not state.exists()
assert all(entry["path"] != ".git" for entry in first["manifest"]["entries"])

secret = worktree / "visible-secret-name.txt"
secret.write_text("SECRET-CONTENT-MUST-NOT-APPEAR")
content_one_run, content_one = preview()
secret.write_text("CHANGED-SECRET-CONTENT-MUST-NOT-APPEAR")
content_two_run, content_two = preview()
assert content_one_run.returncode == content_two_run.returncode == 0
assert content_one["manifest_sha256"] == content_two["manifest_sha256"]
assert content_one["content_manifest_sha256"] != content_two["content_manifest_sha256"]
assert b"visible-secret-name.txt" in content_one_run.stdout
assert b"SECRET-CONTENT-MUST-NOT-APPEAR" not in content_one_run.stdout
assert b"CHANGED-SECRET-CONTENT-MUST-NOT-APPEAR" not in content_two_run.stdout

secret.chmod(0o700)
mode_run, mode_preview = preview()
assert mode_run.returncode == 0
assert mode_preview["content_manifest_sha256"] != content_two["content_manifest_sha256"]
secret.chmod(0o644)

scope_path = temp / "preview-scope.json"
scope_path.write_text(json.dumps({
    "schema_version": 1,
    "kind": "agy-worker-provider-scope",
    "read": [{"path": "visible-secret-name.txt", "kind": "file"}],
    "write": [],
}))
scope_path.chmod(0o600)
scoped_run = subprocess.run(
    [
        worker, "transmission-preview", "--task", "fixture", "--workdir", str(worktree),
        "--provider-scope", str(scope_path), "--format", "json",
    ],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=environment, check=False,
)
scoped = json.loads(scoped_run.stdout) if scoped_run.returncode == 0 else {}
assert scoped_run.returncode == 0
assert scoped["contents_read"] is True
assert "content_manifest" not in scoped and "content_manifest_sha256" not in scoped
assert scoped["provider_launched"] is False
assert scoped["network_used"] is False
assert "authority_summary" in scoped
assert scoped["authority_summary"]["contents_read"] is True
assert scoped["authority_summary"]["provider_launched"] is False
assert scoped["authority_summary"]["network_used"] is False
assert scoped["authority_summary"]["provider_isolation"] == "session"
assert scoped["authority_summary"]["content_binding_kind"] == "scoped-selected-content"
assert scoped["authority_summary"]["manifest_sha256"] == scoped["manifest_sha256"]
assert scoped["authority_summary"]["launch_approval_sha256"] == scoped["launch_approval_sha256"]
assert scoped["authority_summary"]["policy_sha256"] == scoped["policy_sha256"]
assert scoped["authority_summary"]["selected_content_sha256"] == scoped["selected_content_sha256"]
assert scoped["authority_summary"]["transmission_sha256"] == scoped["transmission_sha256"]
assert scoped["authority_summary"]["provider_authority"] == "normal same-user filesystem and network authority; selected scope is staging and reconciliation, not host confinement"
assert b"CHANGED-SECRET-CONTENT-MUST-NOT-APPEAR" not in scoped_run.stdout

# An unrelated hardlink must fail whole-worktree V11 authority. The existing
# scoped validator independently rejects all hardlinks in its readable tree.
unrelated = worktree / "unrelated-hardlink-source"
unrelated.write_text("not selected")
os.link(unrelated, worktree / "unrelated-hardlink-alias")
whole_hardlink, _ = preview()
assert whole_hardlink.returncode == 20 and not whole_hardlink.stdout
(worktree / "unrelated-hardlink-alias").unlink(); unrelated.unlink()
scope_path.chmod(0o644)
invalid_scope_run = subprocess.run(
    [
        worker, "transmission-preview", "--task", "fixture", "--workdir", str(worktree),
        "--provider-scope", str(scope_path), "--format", "json",
    ],
    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=environment, check=False,
)
assert invalid_scope_run.returncode == 20 and not invalid_scope_run.stdout
assert invalid_scope_run.stderr == b"agy-worker.sh: transmission preview invalid: provider scope authority is invalid\n"
assert b"Traceback" not in invalid_scope_run.stderr
scope_path.chmod(0o600)

typed = worktree / "type-boundary"
typed.write_text("x")
_file_run, file_preview = preview()
typed.unlink(); typed.mkdir()
_dir_run, directory_preview = preview()
assert file_preview["manifest_sha256"] != directory_preview["manifest_sha256"]

contained_target = worktree / "contained-target"
contained_target.mkdir()
alternate_target = worktree / "alternate-target"
alternate_target.mkdir()
(worktree / "contained-alias").symlink_to("contained-target")
contained_run, contained = preview()
assert contained_run.returncode == 0
assert {"kind": "symlink", "path": "contained-alias"} in contained["manifest"]["entries"]
(worktree / "contained-alias").unlink()
(worktree / "contained-alias").symlink_to("alternate-target")
link_drift_run, link_drift = preview()
assert link_drift_run.returncode == 0
assert contained["manifest_sha256"] == link_drift["manifest_sha256"]
assert contained["content_manifest_sha256"] != link_drift["content_manifest_sha256"]
(worktree / "contained-alias").unlink()
alternate_target.rmdir()

outside = temp / "preview-outside"
outside.write_text("outside")
(worktree / "outward-alias").symlink_to(outside)
failed, _ = preview()
assert failed.returncode == 20 and not failed.stdout
assert failed.stderr == b"agy-worker.sh: transmission preview invalid: symlink boundary violation\n"
(worktree / "outward-alias").unlink()

nested = worktree / "nested-marker"
nested.mkdir(); (nested / ".GIT").write_text("marker")
failed, _ = preview()
assert failed.returncode == 20 and not failed.stdout
shutil.rmtree(nested)

primary_failure = subprocess.run(
    [worker, "transmission-preview", "--task", "fixture", "--workdir", str(primary)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
assert primary_failure.returncode == 20 and not primary_failure.stdout
detached_failure = subprocess.run(
    [worker, "transmission-preview", "--task", "fixture", "--workdir", detached_text],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
assert detached_failure.returncode == 20 and not detached_failure.stdout

fake_root = temp / "fake-worktree"
fake_admin = temp / "fake-worktree-admin"
fake_root.mkdir(); fake_admin.mkdir()
(fake_root / ".git").write_text(f"gitdir: {fake_admin}\n")
(fake_admin / "gitdir").write_text(f"{fake_root / '.git'}\n")
(fake_admin / "HEAD").write_text("ref: refs/heads/fake-preview\n")
fake_failure = subprocess.run(
    [worker, "transmission-preview", "--task", "fixture", "--workdir", str(fake_root)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
assert fake_failure.returncode == 20 and not fake_failure.stdout
assert fake_failure.stderr.startswith(b"agy-worker.sh: transmission preview invalid: ")
assert b"Traceback" not in fake_failure.stderr

alias = temp / "preview-root-alias"
alias.symlink_to(worktree, target_is_directory=True)
alias_failure = subprocess.run(
    [worker, "transmission-preview", "--task", "fixture", "--workdir", str(alias)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
assert alias_failure.returncode == 20 and not alias_failure.stdout

broken = worktree / "broken-alias"
broken.symlink_to("missing-target")
broken_failure, _ = preview()
assert broken_failure.returncode == 20 and not broken_failure.stdout
broken.unlink()

fifo = worktree / "special-node"
os.mkfifo(fifo)
special_failure, _ = preview()
assert special_failure.returncode == 20 and not special_failure.stdout
fifo.unlink()

# Physical NFD spellings normalize in the approved manifest, but a second NFC
# spelling collides and fails before any provider activity.
nfd_name = "caf\u0065\u0301.txt"
nfc_name = "caf\u00e9.txt"
(worktree / nfd_name).write_text("unicode")
unicode_run, unicode_preview = preview()
assert unicode_run.returncode == 0
assert nfc_name in [entry["path"] for entry in unicode_preview["content_manifest"]["entries"]]
(worktree / nfc_name).write_text("collision")
if (worktree / nfc_name).samefile(worktree / nfd_name):
    # APFS commonly canonicalizes these spellings to one physical entry.
    (worktree / nfd_name).unlink()
else:
    collision_run, _ = preview()
    assert collision_run.returncode == 20 and not collision_run.stdout
    (worktree / nfc_name).unlink(); (worktree / nfd_name).unlink()

unreadable = worktree / "unreadable-directory"
unreadable.mkdir(); unreadable.chmod(0)
unreadable_failure, _ = preview()
unreadable.chmod(0o700); unreadable.rmdir()
assert unreadable_failure.returncode == 20 and not unreadable_failure.stdout

helper_path = root / "skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py"
spec = importlib.util.spec_from_file_location("preview_helper", helper_path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
try:
    module._decode_manifest_path(b"non-utf8-\xff")
except module.ReadableManifestError:
    pass
else:
    raise AssertionError("non-UTF-8 manifest path was accepted")
git_calls = []
socket_called = False
real_popen = subprocess.Popen
real_socket = socket.socket
def guarded_popen(*args, **kwargs):
    command = args[0] if args else kwargs.get("args")
    assert isinstance(command, list) and command[0] == "/usr/bin/git"
    assert command[-6:] == ["-C", str(worktree), "worktree", "list", "--porcelain", "-z"]
    assert kwargs.get("stdin") is subprocess.DEVNULL
    assert kwargs.get("stderr") is subprocess.DEVNULL
    git_calls.append(tuple(command))
    return real_popen(*args, **kwargs)
def blocked_socket(*args, **kwargs):
    global socket_called
    socket_called = True
    raise AssertionError("preview opened a socket")
subprocess.Popen = guarded_popen
socket.socket = blocked_socket
try:
    direct = module.readable_path_manifest(str(worktree))
finally:
    subprocess.Popen = real_popen
    socket.socket = real_socket
assert direct["provider_launched"] is False and len(git_calls) == 2 and not socket_called

real_scandir = module.os.scandir
class FakeEntry:
    def __init__(self, name): self.name = name
class FakeIterator:
    def __init__(self, *, delay=0.0):
        self.delay = delay; self.index = 0; self.closed = False
    def __enter__(self): return self
    def __exit__(self, *_args): self.closed = True
    def __iter__(self): return self
    def __next__(self):
        self.index += 1
        if self.delay: time.sleep(self.delay)
        return FakeEntry(f"fake-{self.index:03d}")

oversized_iterator = FakeIterator()
original_entry_limit = module.READABLE_MANIFEST_MAX_ENTRIES
module.READABLE_MANIFEST_MAX_ENTRIES = 2
module.os.scandir = lambda _fd: oversized_iterator
try:
    try: module._scan_readable_paths(str(worktree))
    except module.ReadableManifestError: pass
    else: raise AssertionError("oversized iterator was accepted")
finally:
    module.os.scandir = real_scandir
    module.READABLE_MANIFEST_MAX_ENTRIES = original_entry_limit
assert oversized_iterator.index == 3 and oversized_iterator.closed

delayed_iterator = FakeIterator(delay=0.02)
original_scan_seconds = module.READABLE_MANIFEST_SCAN_SECONDS
module.READABLE_MANIFEST_SCAN_SECONDS = 0.001
module.os.scandir = lambda _fd: delayed_iterator
try:
    try: module._scan_readable_paths(str(worktree))
    except module.ReadableManifestError: pass
    else: raise AssertionError("delayed iterator exceeded no deadline")
finally:
    module.os.scandir = real_scandir
    module.READABLE_MANIFEST_SCAN_SECONDS = original_scan_seconds
assert delayed_iterator.index == 1 and delayed_iterator.closed

depth_parent = worktree / "depth-parent"
(depth_parent / "depth-child").mkdir(parents=True)
for attribute, constrained in (
    ("READABLE_MANIFEST_MAX_ENTRIES", 1),
    ("READABLE_MANIFEST_MAX_BYTES", 64),
    ("READABLE_MANIFEST_MAX_DEPTH", 1),
    ("READABLE_MANIFEST_SCAN_SECONDS", -1.0),
):
    original = getattr(module, attribute)
    setattr(module, attribute, constrained)
    try:
        try: module.readable_path_manifest(str(worktree))
        except module.ReadableManifestError: pass
        else: raise AssertionError(f"{attribute} bound was not enforced")
    finally:
        setattr(module, attribute, original)
shutil.rmtree(depth_parent)

original_content_limit = module.WHOLE_CONTENT_MAX_BYTES
module.WHOLE_CONTENT_MAX_BYTES = 1
try:
    try: module.whole_worktree_content_manifest(str(worktree))
    except module.ReadableManifestError: pass
    else: raise AssertionError("whole content byte bound was not enforced")
finally:
    module.WHOLE_CONTENT_MAX_BYTES = original_content_limit

original_scan = module._scan_readable_paths
scan_count = 0
drift = worktree / "between-scan-drift"
def drifting_scan(path):
    global scan_count
    result = original_scan(path)
    scan_count += 1
    if scan_count == 1:
        drift.write_text("drift")
    return result
module._scan_readable_paths = drifting_scan
try:
    try:
        module.readable_path_manifest(str(worktree))
    except module.ReadableManifestError:
        pass
    else:
        raise AssertionError("between-scan drift was accepted")
finally:
    module._scan_readable_paths = original_scan
    drift.unlink(missing_ok=True)

original_authority = module._preview_worktree_authority
authority_count = 0
def racing_authority(path):
    global authority_count
    result = original_authority(path)
    authority_count += 1
    return result if authority_count == 1 else result + (("raced",),)
module._preview_worktree_authority = racing_authority
try:
    try:
        module.readable_path_manifest(str(worktree))
    except module.ReadableManifestError:
        pass
    else:
        raise AssertionError("racing worktree registration was accepted")
finally:
    module._preview_worktree_authority = original_authority
PY
then
    ok "preview is stable, content-free, provider-free, bounded, and fail-closed"
else
    bad "preview is stable, content-free, provider-free, bounded, and fail-closed"
fi

if python3 -B - "$WORKER" "$ROOT" <<'PY'
from pathlib import Path
import json, subprocess, sys

worker = sys.argv[1]
root = Path(sys.argv[2])

helper_path = root / "skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py"
spec = __import__("importlib.util").util.spec_from_file_location("worktree_helper", helper_path)
module = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(module)

valid_scope = b'{"schema_version": 1, "kind": "agy-worker-provider-scope", "read": [{"path": "a.txt", "kind": "file"}], "write": [{"path": "a.txt", "kind": "file"}]}'
parsed = module._parse_provider_scope(valid_scope)
assert parsed["read"] == [{"path": "a.txt", "kind": "file"}]

for bad_scope in [
    b'{}',
    b'{"schema_version": 2, "kind": "agy-worker-provider-scope", "read": [], "write": []}',
    b'{"schema_version": 1, "kind": "wrong", "read": [], "write": []}',
    b'{"schema_version": 1, "kind": "agy-worker-provider-scope", "read": [{"path": "../a", "kind": "file"}], "write": []}',
    b'{"schema_version": 1, "kind": "agy-worker-provider-scope", "read": [{"path": ".git", "kind": "file"}], "write": []}',
    b'{"schema_version": 1, "kind": "agy-worker-provider-scope", "read": [{"path": "a.txt", "kind": "file"}], "write": [{"path": "b.txt", "kind": "file"}]}',
]:
    try:
        module._parse_provider_scope(bad_scope)
    except ValueError:
        pass
    else:
        raise AssertionError(f"bad scope accepted: {bad_scope}")
PY
then
    ok "provider scope parser validates schema, paths, and write-covered-by-read invariants"
else
    bad "provider scope parser validates schema, paths, and write-covered-by-read invariants"
fi

if python3 -B - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch_worktree.py" \
        "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" "$WORKER" <<'PY'
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
worktree_path, dispatch_path, worker_path = map(Path, sys.argv[1:])

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

worktree = load("scope_worktree", worktree_path)
dispatch = load("scope_dispatch", dispatch_path)
readers = (
    (worktree._read_provider_scope_file, worktree.ReadableManifestError),
    (dispatch._read_provider_scope_file, dispatch.DispatchError),
)

with tempfile.TemporaryDirectory(prefix="agy-provider-scope-") as temporary:
    root = Path(temporary).resolve(strict=True)
    root.chmod(0o700)
    scope = root / "scope.json"
    scope.write_bytes(b'{"schema_version":1}')
    scope.chmod(0o600)

    expected = None
    for reader, _error_type in readers:
        resolved, raw, info = reader(scope, 512 * 1024)
        binding = (resolved, raw, (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)))
        expected = binding if expected is None else expected
        assert binding == expected
        assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1

    for mode in (0o644, 0o400, 0o660):
        scope.chmod(mode)
        for reader, error_type in readers:
            try:
                reader(scope, 512 * 1024)
            except error_type:
                pass
            else:
                raise AssertionError(f"mode {mode:o} was accepted")
    scope.chmod(0o600)

    alias = root / "scope-alias.json"
    alias.symlink_to(scope)
    for reader, error_type in readers:
        try:
            reader(alias, 512 * 1024)
        except error_type:
            pass
        else:
            raise AssertionError("symlink was accepted")
    alias.unlink()

    hardlink = root / "scope-hardlink.json"
    os.link(scope, hardlink)
    for reader, error_type in readers:
        try:
            reader(scope, 512 * 1024)
        except error_type:
            pass
        else:
            raise AssertionError("hardlink was accepted")
    hardlink.unlink()

    fifo = root / "scope.fifo"
    os.mkfifo(fifo, 0o600)
    for reader, error_type in readers:
        try:
            reader(fifo, 512 * 1024)
        except error_type:
            pass
        else:
            raise AssertionError("FIFO was accepted")

    immediate_parent = root / "verification-parent"
    immediate_parent.mkdir(mode=0o755)
    immediate_parent.chmod(0o755)
    try:
        dispatch._verification_copy_destination(immediate_parent / "candidate", root)
    except dispatch.DispatchError as exc:
        assert str(exc) == "verification copy destination immediate parent must be current-user mode 0700"
    else:
        raise AssertionError("non-0700 immediate parent was accepted")

    for reader, error_type in readers:
        scope.write_bytes(b"before")
        scope.chmod(0o600)
        replacement = root / "replacement.json"
        replacement.write_bytes(b"after")
        replacement.chmod(0o600)
        original_read = os.read
        swapped = [False]
        def replace_after_read(descriptor, count):
            chunk = original_read(descriptor, count)
            if not swapped[0]:
                os.replace(replacement, scope)
                swapped[0] = True
            return chunk
        os.read = replace_after_read
        try:
            reader(scope, 512 * 1024)
        except error_type:
            pass
        else:
            raise AssertionError("replacement during read was accepted")
        finally:
            os.read = original_read

help_result = subprocess.run(
    [str(worker_path), "verification-copy", "--help"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
assert help_result.returncode == 0 and not help_result.stdout
assert b"NEW_DIRECTORY_IN_0700_PARENT" in help_result.stderr
PY
then
    ok "provider scope reads and verification-copy immediate-parent boundary are strict and explicit"
else
    bad "provider scope reads and verification-copy immediate-parent boundary are strict and explicit"
fi

# Help is an informational CLI surface, never a result-envelope path.  It must
# succeed before log/state setup for the top level and every public subcommand;
# malformed use remains a normal 64 with no stdout JSON.
help_ok=1
for help_command in '' run start status wait result extend cancel resume restart continue self-verify finalize; do
    help_out="$TMP/help-${help_command:-top}.out"
    help_err="$TMP/help-${help_command:-top}.err"
    if [[ -n "$help_command" ]]; then
        "$WORKER" "$help_command" --help > "$help_out" 2> "$help_err"
    else
        "$WORKER" --help > "$help_out" 2> "$help_err"
    fi
    help_rc=$?
    if [[ "$help_rc" != 0 || -s "$help_out" ]] || ! grep -Fq 'usage: agy-worker.sh' "$help_err"; then
        help_ok=0
    fi
done
"$WORKER" status --not-a-real-option > "$TMP/help-invalid.out" 2> "$TMP/help-invalid.err"
invalid_help_rc=$?
private_unknown='--not-a-real-option=/private/unknown-argument'
"$WORKER" "$private_unknown" > "$TMP/help-private-run.out" 2> "$TMP/help-private-run.err"
private_run_rc=$?
"$WORKER" status "$private_unknown" > "$TMP/help-private-control.out" 2> "$TMP/help-private-control.err"
private_control_rc=$?
if [[ "$help_ok" == 1 && "$invalid_help_rc" == 64 && ! -s "$TMP/help-invalid.out" ]] \
    && grep -Fxq 'Stdout contracts: run emits a worker result envelope; start and lifecycle controls emit' "$TMP/help-top.err" \
    && grep -Fxq 'control JSON, with status/wait/resume/restart/continue/finalize accepting --format text;' "$TMP/help-top.err" \
    && grep -Fxq 'result emits its bound worker envelope unless --format text. A non-zero run exit means' "$TMP/help-top.err" \
    && [[ "$private_run_rc" == 64 && "$private_control_rc" == 64 ]] \
    && [[ ! -s "$TMP/help-private-run.out" && ! -s "$TMP/help-private-control.out" ]] \
    && grep -Fq 'agy-worker.sh: invalid usage; run --help for usage' "$TMP/help-private-run.err" \
    && grep -Fq 'agy-worker.sh: invalid usage; run --help for usage' "$TMP/help-private-control.err" \
    && ! grep -Fq -- "$private_unknown" "$TMP/help-private-run.err" \
    && ! grep -Fq -- "$private_unknown" "$TMP/help-private-control.err"; then
    ok "top-level help distinguishes worker and lifecycle stdout; invalid usage is sanitized"
else
    bad "help stdout contract or sanitized invalid usage"
fi
cat > "$TMP/bin/agy" <<'FAKE'
#!/usr/bin/env bash
set -u
FAKE_EXECUTABLE_CONTENT_SENTINEL=round-two-binding-original
fake_helper_python=python3
if [[ "${OSTYPE:-}" == darwin* ]]; then
    fake_helper_python=/Library/Developer/CommandLineTools/usr/bin/python3
fi
FAKE_CALLS_FILE="${FAKE_CALLS_FILE:-/dev/null}"
FAKE_WORKER_CALLS_FILE="${FAKE_WORKER_CALLS_FILE:-/dev/null}"
if [[ -n "${FAKE_ENV_OBSERVED_FILE:-}" ]]; then
    if [[ -n "${AGY_WORKER_UNRELATED_SECRET+x}" ]]; then
        printf '%s:present\n' "${1:-worker}" >> "$FAKE_ENV_OBSERVED_FILE"
    else
        printf '%s:absent\n' "${1:-worker}" >> "$FAKE_ENV_OBSERVED_FILE"
    fi
fi
if [[ -n "${FAKE_HOME_OBSERVED_FILE:-}" ]]; then
    printf '%s\n' "$HOME" > "$FAKE_HOME_OBSERVED_FILE"
fi
if [[ "${1:-}" == "--version" && $# -eq 1 ]]; then
    printf 'version\n' >> "$FAKE_CALLS_FILE"
    case "${FAKE_VERSION_MODE:-ready}" in
        ready) printf '1.2.11\n' ;;
        quota113) printf '1.1.13\n' ;;
        prefixed) printf 'agy 1.2.11\n' ;;
        drift) printf '1.1.11\n' ;;
        drift117) printf '1.1.17\n' ;;
        drift999) printf '9.9.9\n' ;;
        canary) printf 'canary-build\n' ;;
        empty) : ;;
        malformed) printf 'version 1.2.11\n' ;;
        oversize) i=0; while [[ $i -lt 140 ]]; do printf x; i=$((i+1)); done; printf '\n' ;;
        stream) while :; do printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'; done ;;
        child-stream)
            cleanup_probe_child() {
                trap - TERM
                kill -KILL "$child_pid" 2>/dev/null || true
                wait "$child_pid" 2>/dev/null || true
                exit 143
            }
            trap cleanup_probe_child TERM
            (
                trap '' TERM
                while [[ ! -e "${FAKE_PROBE_RELEASE_FILE:?}" ]]; do
                    sleep 0.01
                done
                while :; do
                    printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
                done
            ) &
            child_pid=$!
            [[ -z "${FAKE_CHILD_PID_FILE:-}" ]] || printf '%s\n' "$child_pid" > "$FAKE_CHILD_PID_FILE"
            [[ -z "${FAKE_PROBE_PGID_FILE:-}" ]] || printf '%s\n' "$$" > "$FAKE_PROBE_PGID_FILE"
            [[ -z "${FAKE_PROBE_PARENT_PID_FILE:-}" ]] || printf '%s\n' "$PPID" > "$FAKE_PROBE_PARENT_PID_FILE"
            [[ -z "${FAKE_PROBE_READY_FILE:-}" ]] || : > "$FAKE_PROBE_READY_FILE"
            wait "$child_pid"
            ;;
        signal-wait)
            cleanup_probe_child() {
                trap - TERM
                kill -KILL "$child_pid" 2>/dev/null || true
                wait "$child_pid" 2>/dev/null || true
                exit 143
            }
            trap cleanup_probe_child TERM
            (
                trap '' HUP INT TERM
                while :; do sleep 1; done
            ) &
            child_pid=$!
            [[ -z "${FAKE_CHILD_PID_FILE:-}" ]] || printf '%s\n' "$child_pid" > "$FAKE_CHILD_PID_FILE"
            [[ -z "${FAKE_PROBE_PGID_FILE:-}" ]] || printf '%s\n' "$$" > "$FAKE_PROBE_PGID_FILE"
            [[ -z "${FAKE_PROBE_PARENT_PID_FILE:-}" ]] || printf '%s\n' "$PPID" > "$FAKE_PROBE_PARENT_PID_FILE"
            [[ -z "${FAKE_PROBE_READY_FILE:-}" ]] || : > "$FAKE_PROBE_READY_FILE"
            wait "$child_pid"
            ;;
        fail) exit 23 ;;
        hang) sleep 10 ;;
        *) exit 24 ;;
    esac
    exit 0
fi
if [[ "${1:-}" == "--help" && $# -eq 1 ]]; then
    printf 'help\n' >> "$FAKE_CALLS_FILE"
    case "${FAKE_HELP_MODE:-ready}" in
        ready|missing-*)
            sed "/^  ${FAKE_HELP_MODE#missing-}  /d" >&2 <<'HELP'
Usage of agy:
  --add-dir                       Add a directory to the workspace
  --conversation                  Resume a previous conversation by ID
  --disable-slash-commands        Disable slash command expansion
  --effort                        Reasoning effort (low|medium|high|max)
  --json-schema                   Optional JSON schema path
  --mode                          Set execution mode (accept-edits, plan)
  --model                         Select a model
  --output-format                 Output format (text, json, stream-json)
  --print                         Run a prompt
  --print-timeout                 Timeout for print mode
  --sandbox                       Run sandboxed
HELP
            ;;
        locale-sensitive)
            locale_label="inherited-${LC_ALL:-unset}"
            [[ "${LC_ALL:-}" == "C" ]] && locale_label="canonical-C"
            cat >&2 <<HELP
Usage of agy:
  --add-dir                       Add a directory to the workspace ($locale_label)
  --conversation                  Resume a previous conversation by ID
  --disable-slash-commands        Disable slash command expansion
  --effort                        Reasoning effort (low|medium|high|max)
  --json-schema                   Optional JSON schema path
  --mode                          Set execution mode (accept-edits, plan)
  --model                         Select a model
  --output-format                 Output format (text, json, stream-json)
  --print                         Run a prompt
  --print-timeout                 Timeout for print mode
  --sandbox                       Run sandboxed
HELP
            ;;
        missing) printf '%s\n' 'Usage of agy:' >&2 ;;
        duplicate) printf '%s\n' '  --model                         Duplicate model' >&2; cat >&2 <<'HELP'
  --add-dir                       Add a directory to the workspace
  --conversation                  Resume a previous conversation by ID
  --disable-slash-commands        Disable slash command expansion
  --effort                        Reasoning effort (low|medium|high|max)
  --json-schema                   Optional JSON schema path
  --mode                          Set execution mode (accept-edits, plan)
  --model                         Select a model
  --output-format                 Output format (text, json, stream-json)
  --print                         Run a prompt
  --print-timeout                 Timeout for print mode
  --sandbox                       Run sandboxed
HELP
            ;;
        malformed) printf '%s\n' ' --model                          Select a model' >&2 ;;
        semantic) cat >&2 <<'HELP'
Usage of agy:
  --add-dir                       Add a directory to the workspace
  --conversation                  Resume a previous conversation by ID
  --disable-slash-commands        Disable slash command expansion
  --effort                        Reasoning effort (low|medium|high|max)
  --json-schema                   Optional JSON schema path
  --mode                          Set execution mode (accept-edits, plan)
  --model                         Select a model (not available in this build)
  --output-format                 Output format (text, json, stream-json)
  --print                         Run a prompt
  --print-timeout                 Timeout for print mode
  --sandbox                       Run sandboxed
HELP
            ;;
        utf8) printf '\377\n' >&2 ;;
        nul) printf 'x\000\n' >&2 ;;
        oversize) i=0; while [[ $i -lt 70000 ]]; do printf x >&2; i=$((i+1)); done ;;
        fail) exit 23 ;;
        hang) sleep 10 ;;
        *) exit 24 ;;
    esac
    if [[ -n "${FAKE_MUTATE_EXECUTABLE:-}" ]]; then
        printf '#!/usr/bin/env bash\nexit 97\n' > "$FAKE_MUTATE_EXECUTABLE"
        chmod 0755 "$FAKE_MUTATE_EXECUTABLE"
    fi
    if [[ -n "${FAKE_MUTATE_EXECUTABLE_SAME_LENGTH:-}" ]]; then
        python3 -B - "$FAKE_MUTATE_EXECUTABLE_SAME_LENGTH" <<'PY'
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
before = path.stat()
raw = path.read_bytes()
old = b"FAKE_EXECUTABLE_CONTENT_SENTINEL=round-two-binding-" + b"original"
new = b"FAKE_EXECUTABLE_CONTENT_SENTINEL=round-two-binding-" + b"replaced"
if len(old) != len(new) or raw.count(old) != 1:
    raise SystemExit(97)
path.write_bytes(raw.replace(old, new))
os.chmod(path, 0o755)
os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
marker = os.environ.get("FAKE_MUTATION_MARKER")
if marker:
    Path(marker).touch()
PY
    [[ $? == 0 ]] || exit 97
    fi
    if [[ -n "${FAKE_REPLACE_EXECUTABLE_SYMLINK:-}" ]]; then
        replacement="${FAKE_REPLACE_EXECUTABLE_SYMLINK}.round-two-replacement"
        rm -f "$replacement"
        ln -s "${FAKE_EXECUTABLE_SYMLINK_TARGET:?}" "$replacement"
        mv -f "$replacement" "$FAKE_REPLACE_EXECUTABLE_SYMLINK"
    fi
    if [[ -n "${FAKE_MUTATE_EXECUTABLE_MODE:-}" ]]; then
        chmod 0775 "$FAKE_MUTATE_EXECUTABLE_MODE"
    fi
    if [[ -n "${FAKE_MUTATE_EXECUTABLE_PARENT:-}" ]]; then
        chmod 0775 "$FAKE_MUTATE_EXECUTABLE_PARENT"
    fi
    if [[ -n "${FAKE_MUTATE_WORKTREE_PATH:-}" ]]; then
        : > "$FAKE_MUTATE_WORKTREE_PATH"
    fi
    exit 0
fi
printf 'worker\n' >> "$FAKE_CALLS_FILE"
printf 'worker\n' >> "$FAKE_WORKER_CALLS_FILE"
: "${FAKE_MODEL_FILE:?}"
: "${FAKE_PROMPT_FILE:?}"
: "${FAKE_DIRS_FILE:?}"
: "${FAKE_ARGV_FILE:?}"
: "${FAKE_STAGE_RESULT_FILE:?}"
: > "$FAKE_MODEL_FILE"
: > "$FAKE_PROMPT_FILE"
: > "$FAKE_DIRS_FILE"
: > "$FAKE_STAGE_RESULT_FILE"
printf '%s\0' "$@" > "$FAKE_ARGV_FILE"
stage_dir=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) printf '%s' "$2" > "$FAKE_MODEL_FILE"; shift 2 ;;
        --add-dir)
            printf '%s\n' "$2" >> "$FAKE_DIRS_FILE"
            case "$2" in */staged) stage_dir="$2" ;; esac
            shift 2 ;;
        --print) printf '%s' "$2" > "$FAKE_PROMPT_FILE"; shift 2 ;;
        *) shift ;;
    esac
done
if [[ -n "${FAKE_EDIT_FROM_BOUND_ROOT:-}" ]]; then
    fake_helper_error="${TMPDIR:-/tmp}/agy-worker-fake-edit-$$.stderr"
    if ! "$fake_helper_python" -B - "$FAKE_PROMPT_FILE" "$FAKE_EDIT_FROM_BOUND_ROOT" \
        "${FAKE_EDIT_CONTENT:-provider changed}" 2>"$fake_helper_error" <<'PY'
import json
from pathlib import Path
import sys

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
marker = "The exact absolute workspace root for this attempt is the JSON string "
if marker in prompt:
    start = prompt.index(marker) + len(marker)
    root, _end = json.JSONDecoder().raw_decode(prompt[start:])
else:
    root = str(Path.cwd())
target = Path(root) / sys.argv[2]
target.write_text(sys.argv[3] + "\n", encoding="utf-8")
PY
    then
        printf '%s' 'fake agy: bound-root edit helper failed: ' >&2
        /usr/bin/head -c 4096 "$fake_helper_error" >&2 || :
        printf '\n' >&2
        rm -f "$fake_helper_error"
        exit 97
    fi
    rm -f "$fake_helper_error"
fi
if [[ -n "${FAKE_DELETE_FROM_BOUND_ROOT:-}" ]]; then
    python3 -B - "$FAKE_PROMPT_FILE" "$FAKE_DELETE_FROM_BOUND_ROOT" <<'PY'
import json
from pathlib import Path
import sys

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
marker = "The exact absolute workspace root for this attempt is the JSON string "
if marker in prompt:
    start = prompt.index(marker) + len(marker)
    root, _end = json.JSONDecoder().raw_decode(prompt[start:])
else:
    root = str(Path.cwd())
(Path(root) / sys.argv[2]).unlink()
PY
fi
if [[ "${FAKE_TRY_STAGE_WRITE:-0}" == "1" && -n "$stage_dir" ]]; then
    if printf 'tampered' 2>/dev/null > "$stage_dir/full-prompt.txt"; then
        printf 'wrote' > "$FAKE_STAGE_RESULT_FILE"
    else
        printf 'blocked' > "$FAKE_STAGE_RESULT_FILE"
    fi
fi
if [[ -n "${FAKE_CALLED_FILE:-}" ]]; then
    : > "$FAKE_CALLED_FILE"
fi
if [[ -n "${FAKE_MUTATE_PROJECT_MARKER:-}" ]]; then
    printf 'gitdir: tampered\n' > "$FAKE_MUTATE_PROJECT_MARKER"
fi
if [[ -n "${FAKE_SPARSE_PROJECT_MARKER:-}" ]]; then
    python3 -B - "$FAKE_SPARSE_PROJECT_MARKER" <<'PY'
import os
import sys
os.truncate(sys.argv[1], 1 << 20)
PY
fi
dispatch_count=1
if [[ -n "${FAKE_DISPATCH_COUNT_FILE:-}" ]]; then
    if [[ -f "$FAKE_DISPATCH_COUNT_FILE" ]]; then
        IFS= read -r dispatch_count < "$FAKE_DISPATCH_COUNT_FILE"
        dispatch_count=$((dispatch_count+1))
    fi
    printf '%s\n' "$dispatch_count" > "$FAKE_DISPATCH_COUNT_FILE"
fi
if [[ -n "${FAKE_PROVIDER_CREATE_PATH:-}" ]]; then
    : > "$FAKE_PROVIDER_CREATE_PATH"
fi
if [[ "${FAKE_FAIL_FIRST:-0}" == "1" && "$dispatch_count" == "1" ]]; then
    exit 23
fi
if [[ -n "${FAKE_SIGNAL_PARENT:-}" ]]; then
    kill -s "$FAKE_SIGNAL_PARENT" "$PPID"
    exit "${FAKE_EXIT_CODE:-23}"
fi
case "${FAKE_DISPATCH_MODE:-result}" in
    idle)
        sleep 10
        exit 0
        ;;
    malformed-heartbeat)
        while :; do
            printf '{not-valid-json}\n'
            sleep 0.10
        done
        ;;
    oversized-heartbeat)
        python3 -c 'import json; print(json.dumps({"event":"step_update", "blob":"x" * 1100000}))'
        sleep 10
        exit 0
        ;;
    empty-success)
        exit 0
        ;;
    heartbeat-forever)
        printf '{"event":"init","conversation_id":"fake-conversation-01","init":{}}\n'
        if [[ -n "${FAKE_HEARTBEAT_BARRIER_READY:-}" \
                && -n "${FAKE_HEARTBEAT_BARRIER_RELEASE:-}" ]]; then
            : > "$FAKE_HEARTBEAT_BARRIER_READY"
            while [[ ! -e "$FAKE_HEARTBEAT_BARRIER_RELEASE" ]]; do
                sleep 0.01
            done
        fi
        if [[ -n "${FAKE_SIDE_EFFECT_FILE:-}" ]]; then
            ( sleep 3; : > "$FAKE_SIDE_EFFECT_FILE" ) &
        fi
        while :; do
            printf '{"event":"step_update","step_update":{}}\n'
            sleep "${FAKE_HEARTBEAT_DELAY:-0.10}"
        done
        ;;
    heartbeat-success)
        printf '{"event":"init","conversation_id":"fake-conversation-01","init":{}}\n'
        if [[ -n "${FAKE_HEARTBEAT_BARRIER_READY:-}" \
                && -n "${FAKE_HEARTBEAT_BARRIER_RELEASE:-}" ]]; then
            : > "$FAKE_HEARTBEAT_BARRIER_READY"
            while [[ ! -e "$FAKE_HEARTBEAT_BARRIER_RELEASE" ]]; do
                sleep 0.01
            done
        fi
        heartbeat_count="${FAKE_HEARTBEAT_COUNT:-8}"
        heartbeat_delay="${FAKE_HEARTBEAT_DELAY:-0.10}"
        heartbeat_index=0
        while [[ "$heartbeat_index" -lt "$heartbeat_count" ]]; do
            printf '{"event":"step_update","step_update":{}}\n'
            if [[ "$heartbeat_index" == 0 \
                    && -n "${FAKE_HEARTBEAT_AFTER_FIRST_READY:-}" \
                    && -n "${FAKE_HEARTBEAT_AFTER_FIRST_RELEASE:-}" ]]; then
                : > "$FAKE_HEARTBEAT_AFTER_FIRST_READY"
                while [[ ! -e "$FAKE_HEARTBEAT_AFTER_FIRST_RELEASE" ]]; do
                    sleep 0.01
                done
            fi
            sleep "$heartbeat_delay"
            heartbeat_index=$((heartbeat_index+1))
        done
        ;;
    conversation-fail)
        printf '{"event":"init","conversation_id":"fake-conversation-01","init":{}}\n'
        exit 23
        ;;
    quota-error)
        quota_text="${FAKE_QUOTA_ERROR:-rpc error: Individual quota reached. Contact your administrator to enable overages. Resets in 4h51m54s.}"
        printf '{"event":"init","conversation_id":"fake-conversation-01","init":{}}\n'
        python3 -B - "$quota_text" <<'PY'
import json
import sys

print(json.dumps({
    "event": "result",
    "result": {
        "conversation_id": "fake-conversation-01",
        "status": "ERROR",
        "response": "",
        "error": sys.argv[1],
        "duration_seconds": 1.0,
        "num_turns": 3,
        "json_schema": {},
        "usage": {},
    },
}, separators=(",", ":")))
PY
        exit "${FAKE_EXIT_CODE:-23}"
        ;;
esac
if [[ "${FAKE_EXIT_CODE:-0}" != "0" ]]; then
    [[ -z "${FAKE_ERROR_LINE:-}" ]] || printf '%s\n' "$FAKE_ERROR_LINE" >&2
    exit "$FAKE_EXIT_CODE"
fi
[[ -z "${FAKE_WARNING_LINE:-}" ]] || printf '%s\n' "$FAKE_WARNING_LINE" >&2
status="${FAKE_AGY_STATUS:-SUCCESS}"
if [[ "${FAKE_DISPATCH_MODE:-result}" == "result" ]]; then
    printf '{"event":"init","conversation_id":"fake-conversation-01","init":{}}\n'
fi
if [[ "${FAKE_BAD_ENVELOPE:-0}" == "1" ]]; then
    envelope='{"status":"completed","summary":"done","files_changed":[],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":9,"requires_human":false}'
elif [[ -n "${FAKE_EDIT_FROM_BOUND_ROOT:-}" ]]; then
    fake_helper_error="${TMPDIR:-/tmp}/agy-worker-fake-envelope-$$.stderr"
    if ! envelope="$("$fake_helper_python" -B - "$FAKE_EDIT_FROM_BOUND_ROOT" \
        "" 2>"$fake_helper_error" <<'PY'
import json
import sys
print(json.dumps({
    "status": "completed",
    "summary": "done",
    "files_changed": [{"path": sys.argv[1], "change": sys.argv[2] or "modified"}],
    "commands_run": [],
    "tests_run": [],
    "risks": [],
    "open_questions": [],
    "confidence": 1,
    "requires_human": False,
}, separators=(",", ":")))
PY
)"; then
        printf '%s' 'fake agy: result envelope helper failed: ' >&2
        /usr/bin/head -c 4096 "$fake_helper_error" >&2 || :
        printf '\n' >&2
        rm -f "$fake_helper_error"
        exit 97
    fi
    rm -f "$fake_helper_error"
elif [[ -n "${FAKE_DELETE_FROM_BOUND_ROOT:-}" ]]; then
    envelope="$(python3 -B - "$FAKE_DELETE_FROM_BOUND_ROOT" deleted <<'PY'
import json
import sys
print(json.dumps({
    "status": "completed",
    "summary": "done",
    "files_changed": [{"path": sys.argv[1], "change": sys.argv[2]}],
    "commands_run": [],
    "tests_run": [],
    "risks": [],
    "open_questions": [],
    "confidence": 1,
    "requires_human": False,
}, separators=(",", ":")))
PY
)"
elif [[ "${FAKE_WORKER_VERIFIED:-0}" == "1" ]]; then
    envelope='{"status":"completed","summary":"Verified private-worker-prose-sentinel","files_changed":[],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":1,"requires_human":false}'
elif [[ "${FAKE_UTF8_SUMMARY:-0}" == "1" ]]; then
    envelope='{"status":"completed","summary":"café 😀","files_changed":[],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":1,"requires_human":false}'
else
    envelope='{"status":"completed","summary":"done","files_changed":[],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":1,"requires_human":false}'
fi
printf '{"event":"result","result":{"status":"%s","duration_seconds":0,"num_turns":1,"usage":{},"structured_output":%s}}\n' "$status" "$envelope"
FAKE
chmod +x "$TMP/bin/agy"
cp "$TMP/bin/agy" "$TMP/bin/agy.package-original"

run_worker() {
    local fake_provider_env_args=()
    local fake_provider_env_name
    for fake_provider_env_name in \
        FAKE_AGY_STATUS FAKE_ARGV_FILE FAKE_BAD_ENVELOPE FAKE_CALLED_FILE \
        FAKE_CALLS_FILE FAKE_CHILD_PID_FILE FAKE_DIRS_FILE FAKE_DISPATCH_COUNT_FILE \
        FAKE_DISPATCH_MODE FAKE_ENV_OBSERVED_FILE FAKE_HOME_OBSERVED_FILE FAKE_ERROR_LINE \
        FAKE_DELETE_FROM_BOUND_ROOT FAKE_EDIT_CONTENT FAKE_EDIT_FROM_BOUND_ROOT \
        FAKE_EXECUTABLE_SYMLINK_TARGET \
        FAKE_EXIT_CODE FAKE_FAIL_FIRST FAKE_HEARTBEAT_AFTER_FIRST_READY \
        FAKE_HEARTBEAT_AFTER_FIRST_RELEASE FAKE_HEARTBEAT_BARRIER_READY \
        FAKE_HEARTBEAT_BARRIER_RELEASE FAKE_HEARTBEAT_COUNT FAKE_HEARTBEAT_DELAY \
        FAKE_HELP_MODE FAKE_MODEL_FILE FAKE_MUTATE_EXECUTABLE \
        FAKE_MUTATE_EXECUTABLE_MODE FAKE_MUTATE_EXECUTABLE_PARENT \
        FAKE_MUTATE_EXECUTABLE_SAME_LENGTH \
        FAKE_MUTATE_PROJECT_MARKER FAKE_MUTATION_MARKER FAKE_PROBE_PARENT_PID_FILE \
        FAKE_PROBE_PGID_FILE FAKE_PROBE_READY_FILE FAKE_PROBE_RELEASE_FILE \
        FAKE_PROMPT_FILE FAKE_QUOTA_ERROR FAKE_REPLACE_EXECUTABLE_SYMLINK \
        FAKE_PROVIDER_CREATE_PATH \
        FAKE_SIDE_EFFECT_FILE FAKE_SIGNAL_PARENT FAKE_SPARSE_PROJECT_MARKER \
        FAKE_STAGE_RESULT_FILE FAKE_TRY_STAGE_WRITE FAKE_UTF8_SUMMARY \
        FAKE_MUTATE_WORKTREE_PATH \
        FAKE_VERSION_MODE FAKE_WARNING_LINE FAKE_WORKER_CALLS_FILE \
        FAKE_WORKER_VERIFIED; do
        fake_provider_env_args+=(--provider-env "$fake_provider_env_name")
    done
    local job="$1" workdir worker_path provider_scope_arg=0 option manifest_sha
    local transmission_approval_args=()
    shift
    workdir="${AGY_TEST_WORKDIR:-$TMP/repo}"
    worker_path="${AGY_TEST_WORKER:-$WORKER}"
    for option in "$@"; do
        [[ "$option" != "--provider-scope" ]] || provider_scope_arg=1
    done
    PATH="$TMP/bin:$PATH" \
    AGY_WORKER_MODE="${AGY_WORKER_MODE:-accept-edits}" \
    AGY_WORKER_LOG_DIR="${AGY_TEST_LOG_DIR:-$TMP/logs}" \
    AGY_WORKER_JOB_ID="$job" \
    FAKE_MODEL_FILE="${FAKE_MODEL_FILE:-$TMP/$job.model}" \
    FAKE_PROMPT_FILE="${FAKE_PROMPT_FILE:-$TMP/$job.prompt}" \
    FAKE_DIRS_FILE="${FAKE_DIRS_FILE:-$TMP/$job.dirs}" \
    FAKE_ARGV_FILE="${FAKE_ARGV_FILE:-$TMP/$job.argv}" \
    FAKE_STAGE_RESULT_FILE="${FAKE_STAGE_RESULT_FILE:-$TMP/$job.stage-result}" \
    FAKE_CALLS_FILE="${FAKE_CALLS_FILE:-$TMP/$job.calls}" \
    FAKE_WORKER_CALLS_FILE="${FAKE_WORKER_CALLS_FILE:-$TMP/$job.worker-calls}" \
    FAKE_VERSION_MODE="${FAKE_VERSION_MODE:-ready}" \
    FAKE_HELP_MODE="${FAKE_HELP_MODE:-ready}" \
    FAKE_MUTATE_EXECUTABLE="${FAKE_MUTATE_EXECUTABLE:-}" \
    FAKE_MUTATE_EXECUTABLE_SAME_LENGTH="${FAKE_MUTATE_EXECUTABLE_SAME_LENGTH:-}" \
    FAKE_REPLACE_EXECUTABLE_SYMLINK="${FAKE_REPLACE_EXECUTABLE_SYMLINK:-}" \
    FAKE_EXECUTABLE_SYMLINK_TARGET="${FAKE_EXECUTABLE_SYMLINK_TARGET:-}" \
    FAKE_MUTATE_EXECUTABLE_MODE="${FAKE_MUTATE_EXECUTABLE_MODE:-}" \
    FAKE_MUTATE_EXECUTABLE_PARENT="${FAKE_MUTATE_EXECUTABLE_PARENT:-}" \
    FAKE_MUTATION_MARKER="${FAKE_MUTATION_MARKER:-}" \
    FAKE_CHILD_PID_FILE="${FAKE_CHILD_PID_FILE:-}" \
    FAKE_PROBE_PGID_FILE="${FAKE_PROBE_PGID_FILE:-}" \
    FAKE_PROBE_PARENT_PID_FILE="${FAKE_PROBE_PARENT_PID_FILE:-}" \
    FAKE_PROBE_READY_FILE="${FAKE_PROBE_READY_FILE:-}" \
    FAKE_PROBE_RELEASE_FILE="${FAKE_PROBE_RELEASE_FILE:-}" \
    FAKE_MUTATE_WORKTREE_PATH="${FAKE_MUTATE_WORKTREE_PATH:-}" \
    FAKE_MUTATE_PROJECT_MARKER="${FAKE_MUTATE_PROJECT_MARKER:-}" \
    FAKE_SPARSE_PROJECT_MARKER="${FAKE_SPARSE_PROJECT_MARKER:-}" \
    FAKE_DISPATCH_COUNT_FILE="${FAKE_DISPATCH_COUNT_FILE:-}" \
    FAKE_FAIL_FIRST="${FAKE_FAIL_FIRST:-0}" \
    FAKE_TRY_STAGE_WRITE="${FAKE_TRY_STAGE_WRITE:-0}" \
    FAKE_DISPATCH_MODE="${FAKE_DISPATCH_MODE:-result}" \
    FAKE_DELETE_FROM_BOUND_ROOT="${FAKE_DELETE_FROM_BOUND_ROOT:-}" \
    FAKE_EDIT_FROM_BOUND_ROOT="${FAKE_EDIT_FROM_BOUND_ROOT:-}" \
    FAKE_EDIT_CONTENT="${FAKE_EDIT_CONTENT:-}" \
    FAKE_HEARTBEAT_COUNT="${FAKE_HEARTBEAT_COUNT:-8}" \
    FAKE_HEARTBEAT_DELAY="${FAKE_HEARTBEAT_DELAY:-0.10}" \
    FAKE_SIDE_EFFECT_FILE="${FAKE_SIDE_EFFECT_FILE:-}" \
    FAKE_ENV_OBSERVED_FILE="${FAKE_ENV_OBSERVED_FILE:-}" \
    FAKE_HOME_OBSERVED_FILE="${FAKE_HOME_OBSERVED_FILE:-}" \
    FAKE_ERROR_LINE="${FAKE_ERROR_LINE:-}" \
    FAKE_WARNING_LINE="${FAKE_WARNING_LINE:-}" \
    FAKE_QUOTA_ERROR="${FAKE_QUOTA_ERROR:-}" \
    FAKE_WORKER_VERIFIED="${FAKE_WORKER_VERIFIED:-0}" \
    FAKE_UTF8_SUMMARY="${FAKE_UTF8_SUMMARY:-0}" \
    FAKE_CALLED_FILE="${FAKE_CALLED_FILE:-$TMP/$job.called}" \
    FAKE_SIGNAL_PARENT="${FAKE_SIGNAL_PARENT:-}" \
    FAKE_EXIT_CODE="${FAKE_EXIT_CODE:-0}" \
    python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$worker_path" --workdir "$workdir" \
        "${fake_provider_env_args[@]}" \
        ${transmission_approval_args+"${transmission_approval_args[@]}"} "$@"
}

echo "agy-worker.sh offline test suite"
echo

"$WORKER" --help > "$TMP/help.out" 2> "$TMP/help.err"
help_rc=$?
if [[ "$help_rc" == 0 && ! -s "$TMP/help.out" ]] \
        && grep -Fqx 'Workflow cycle limits: explore/task 1..2 (default 2); project 1..5 (default 5).' \
            "$TMP/help.err" \
        && grep -Fqx -- '--max-cycles requires an explicit workflow; legacy raw mode remains one attempt.' \
            "$TMP/help.err"; then
    ok "help states workflow-specific cycle limits"
else
    bad "help workflow-specific cycle limits"
fi

printf 'must not dispatch without a transmission mode\n' | \
    AGY_TEST_SKIP_WHOLE_APPROVAL=1 run_worker missing-transmission-mode \
    > "$TMP/missing-transmission-mode.out" 2> "$TMP/missing-transmission-mode.err"
missing_transmission_rc=$?
if [[ "$missing_transmission_rc" == 64 \
        && ! -s "$TMP/missing-transmission-mode.out" \
        && ! -e "$TMP/missing-transmission-mode.called" \
        && ! -e "$TMP/logs/missing-transmission-mode" ]] \
        && grep -Fq 'choose provider scope, or explicitly approve whole-worktree transmission' \
            "$TMP/missing-transmission-mode.err" \
        && grep -Fq 'obtain a full transmission-preview' \
            "$TMP/missing-transmission-mode.err"; then
    ok "raw dispatch requires an explicit transmission mode before provider or job artifacts"
else
    bad "raw dispatch missing transmission mode boundary"
fi

printf 'must reject stale whole-worktree approval\n' | \
    AGY_TEST_SKIP_WHOLE_APPROVAL=1 run_worker stale-whole-worktree \
    --approve-whole-worktree "$(printf '0%.0s' {1..64})" \
    > "$TMP/stale-whole-worktree.out" 2> "$TMP/stale-whole-worktree.err"
stale_whole_rc=$?
if [[ "$stale_whole_rc" == 64 \
        && ! -s "$TMP/stale-whole-worktree.out" \
        && ! -e "$TMP/stale-whole-worktree.called" \
        && ! -e "$TMP/logs/stale-whole-worktree" ]] \
        && grep -Fq 'approval record does not match approved digest' \
            "$TMP/stale-whole-worktree.err"; then
    ok "raw whole-worktree approval is exact and stale-safe before provider launch"
else
    bad "raw whole-worktree stale approval boundary"
fi

# The provider-free preview can succeed, then the command-construction scan can
# still detect a bounded content failure.  That later boundary must give the
# caller a safe scope hint, without publishing a command or starting agy.
WHOLE_BINDING_FAILURE_FIXTURE="$TMP/whole-binding-failure"
cp -R "$ROOT/skills/agy-worker" "$WHOLE_BINDING_FAILURE_FIXTURE"
cat >> "$WHOLE_BINDING_FAILURE_FIXTURE/runtime/scripts/agy_dispatch.py" <<'PY'

def whole_worktree_content_manifest(_workdir):
    raise RuntimeError("injected bounded content scan failure")
PY
WHOLE_BINDING_FAILURE_MARKER="$TMP/whole-binding-failure.provider-called"
WHOLE_BINDING_FAILURE_LOGS="$TMP/whole-binding-failure-logs"
printf 'whole binding must fail closed\n' | \
    AGY_TEST_WORKER="$WHOLE_BINDING_FAILURE_FIXTURE/runtime/agy-worker.sh" \
    AGY_TEST_LOG_DIR="$WHOLE_BINDING_FAILURE_LOGS" \
    FAKE_CALLED_FILE="$WHOLE_BINDING_FAILURE_MARKER" \
    run_worker whole-binding-failure \
        > "$TMP/whole-binding-failure.out" 2> "$TMP/whole-binding-failure.err"
whole_binding_failure_rc=$?
if [[ "$whole_binding_failure_rc" == 20 && ! -s "$TMP/whole-binding-failure.out" \
        && ! -e "$WHOLE_BINDING_FAILURE_MARKER" \
        && ! -e "$WHOLE_BINDING_FAILURE_LOGS/whole-binding-failure/dispatch-command.json" \
        && ! -e "$WHOLE_BINDING_FAILURE_LOGS/whole-binding-failure/dispatch-state.json" ]] \
        && grep -Fqx \
            'agy-worker.sh: whole-worktree content binding failed its bounded local scan; use --provider-scope for selected content' \
            "$TMP/whole-binding-failure.err"; then
    ok "post-preview whole content binding failure is bounded and publishes no provider command"
else
    bad "post-preview whole content binding failure boundary"
fi

printf 'small task\n' | run_worker literal-smoke --model gemini-3.6-flash-low > "$TMP/literal-smoke.out" 2> "$TMP/literal-smoke.err"
rc=$?
if [[ "$rc" != "0" ]]; then
    # Keep the first synthetic dispatch actionable in remote CI.  This fixture
    # contains no provider prose or credentials; later cases intentionally keep
    # their captured diagnostics private.
    tail -n 5 "$TMP/literal-smoke.err" >&2
fi
expect_exit "literal model produces an envelope" 0 "$rc"
if [[ "$(<"$TMP/literal-smoke.model")" == "gemini-3.6-flash-low" ]] \
        && grep -Fq 'Use file tools to inspect and edit the approved workspace.' "$TMP/literal-smoke.prompt" \
        && ! grep -Fq 'BOOST WORKSPACE CONTRACT' "$TMP/literal-smoke.prompt"; then
    ok "literal model is forwarded after CLI parsing and keeps the ordinary writable preamble"
else
    bad "literal model forwarding or ordinary writable preamble"
fi
expect_print_last "small prompt keeps --print and its value last" "$TMP/literal-smoke.argv"

LEGACY_UNAPPROVED_JOB="$TMP/logs/legacy-unapproved-initial"
mkdir "$LEGACY_UNAPPROVED_JOB"
chmod 0700 "$LEGACY_UNAPPROVED_JOB"
LEGACY_UNAPPROVED_JOB="$(cd "$LEGACY_UNAPPROVED_JOB" && pwd -P)"
PYTHONDONTWRITEBYTECODE=1 python3 - \
        "$TMP/logs/literal-smoke/dispatch-command.json" \
        "$LEGACY_UNAPPROVED_JOB/dispatch-command.json" <<'PY'
import json
import os
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
value = json.loads(source.read_text(encoding="utf-8"))
value["schema_version"] = 6
value.pop("whole_worktree_content_sha256")
value.pop("native_grant_profile")
value.pop("provider_isolation")
value.pop("approved_whole_worktree_sha256")
value.pop("allow_scoped_repair")
value.pop("repair_authority_sha256")
value.pop("allow_self_verification")
value.pop("self_verification_manifest_path")
value.pop("self_verification_manifest_sha256")
value.pop("self_verification_manifest_identity")
target.write_text(
    json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
os.chmod(target, 0o600)
PY
PATH="$TMP/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    python3 "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        run --job-dir "$LEGACY_UNAPPROVED_JOB" \
        > "$TMP/legacy-unapproved-initial.out" \
        2> "$TMP/legacy-unapproved-initial.err"
legacy_unapproved_initial_rc=$?
if [[ "$legacy_unapproved_initial_rc" == 64 \
        && ! -s "$TMP/legacy-unapproved-initial.out" \
        && ! -e "$LEGACY_UNAPPROVED_JOB/dispatch-state.json" ]] \
        && grep -Fq 'dispatch command schema v6 is not supported' \
            "$TMP/legacy-unapproved-initial.err"; then
    ok "direct dispatcher rejects a fresh legacy broad command before provider launch"
else
    bad "direct dispatcher legacy broad initial boundary"
fi

printf 'scoped core target\n' > "$TMP/repo/scoped-target.txt"
CORE_SCOPE="$TMP/core.scope.json"
printf '%s\n' \
    '{"schema_version":1,"kind":"agy-worker-provider-scope","read":[{"path":"scoped-target.txt","kind":"file"}],"write":[{"path":"scoped-target.txt","kind":"file"}]}' \
    > "$CORE_SCOPE"
chmod 0600 "$CORE_SCOPE"
CORE_WORKDIR="$(cd "$TMP/repo" && pwd -P)"
CORE_TRANSMISSION_SHA="$(
    "$WORKER" transmission-preview --task fixture --workdir "$CORE_WORKDIR" \
        --provider-scope "$CORE_SCOPE" --format json \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["transmission_sha256"])'
)"
printf 'scoped repair authority test\n' | run_worker scoped-repair-authority \
    --workflow task --max-cycles 2 --allow-scoped-repair \
    --provider-scope "$CORE_SCOPE" --approve-transmission-sha "$CORE_TRANSMISSION_SHA" \
    > "$TMP/scoped-repair-authority.out" 2> "$TMP/scoped-repair-authority.err"
scoped_repair_authority_rc=$?
if [[ "$scoped_repair_authority_rc" == 0 ]] && python3 -I -S -B - \
        "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/logs/scoped-repair-authority" <<'PY'
import importlib.util
from pathlib import Path
import sys

source, job_text = sys.argv[1:]
spec = importlib.util.spec_from_file_location("scoped_repair_command", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)
command, _raw, _identity = module.load_command(Path(job_text).resolve())
assert command["schema_version"] == 16
assert command["provider_isolation"] == "session"
assert command["native_grant_profile"] == "baseline"
assert command["whole_worktree_content_sha256"] is None
assert command["allow_scoped_repair"] is True
assert command["allow_self_verification"] is False
assert command["repair_authority_sha256"] == module.scoped_repair_authority_sha256(
    command, verification_binding_sha256=None,
)
module.CONTAINMENT.NEW_NATIVE_GRANT_PROFILE = "AB"
assert module.load_command(Path(job_text).resolve())[0]["native_grant_profile"] == "baseline"
PY
then
    ok "scoped repair opt-in writes one immutable command authority"
else
    bad "scoped repair opt-in command authority"
fi

scoped_repair_constraint_failures=0
for repair_case in no-scope workflow cycles; do
    repair_args=(--workflow task --max-cycles 2 --allow-scoped-repair)
    case "$repair_case" in
        no-scope) ;;
        workflow) repair_args=(--workflow explore --max-cycles 2 --allow-scoped-repair --provider-scope "$CORE_SCOPE" --approve-transmission-sha "$CORE_TRANSMISSION_SHA") ;;
        cycles) repair_args=(--workflow task --max-cycles 1 --allow-scoped-repair --provider-scope "$CORE_SCOPE" --approve-transmission-sha "$CORE_TRANSMISSION_SHA") ;;
    esac
    printf 'invalid scoped repair profile\n' | run_worker "scoped-repair-invalid-$repair_case" "${repair_args[@]}" \
        > "$TMP/scoped-repair-invalid-$repair_case.out" 2> "$TMP/scoped-repair-invalid-$repair_case.err"
    repair_case_rc=$?
    if [[ "$repair_case_rc" != 64 || -e "$TMP/scoped-repair-invalid-$repair_case.called" ]]; then
        scoped_repair_constraint_failures=$((scoped_repair_constraint_failures + 1))
    fi
done
if (( scoped_repair_constraint_failures == 0 )); then
    ok "scoped repair rejects missing scope and unsupported workflow or cycle bounds"
else
    bad "scoped repair public constraints"
fi

SELF_VERIFY_MANIFEST="$TMP/self-verification-valid.json"
cat > "$SELF_VERIFY_MANIFEST" <<'JSON'
{"checks":[{"argv":["/usr/bin/true"],"id":"required_check","output_limit_bytes":1024,"required":true,"timeout_seconds":5},{"argv":["/bin/sh","checks/optional.sh"],"id":"optional_check","output_limit_bytes":512,"required":false,"timeout_seconds":5}],"kind":"agy-worker-self-verification","max_seconds":10,"schema_version":1}
JSON
chmod 0600 "$SELF_VERIFY_MANIFEST"
SELF_VERIFY_MANIFEST="$(cd "$(dirname "$SELF_VERIFY_MANIFEST")" && pwd -P)/$(basename "$SELF_VERIFY_MANIFEST")"

# The preamble must reach the actual prompt sent to agy in every workflow and
# transmission mode. Explore whole-worktree dispatch points at a staged prompt,
# so the assertion follows that pointer and inspects the staged bytes.
noninteractive_preamble_failures=0
for preamble_workflow in explore task project; do
    for preamble_mode in whole scoped; do
        preamble_job="noninteractive-$preamble_workflow-$preamble_mode"
        preamble_agy_mode=accept-edits
        [[ "$preamble_workflow" != explore ]] || preamble_agy_mode=plan
        preamble_mode_args=()
        if [[ "$preamble_mode" == scoped ]]; then
            preamble_mode_args=(
                --provider-scope "$CORE_SCOPE"
                --approve-transmission-sha "$CORE_TRANSMISSION_SHA"
            )
        fi
        preamble_self_verify_args=()
        preamble_self_verify=0
        if [[ "$preamble_workflow" == task && "$preamble_mode" == scoped ]]; then
            preamble_self_verify=1
            preamble_self_verify_args=(--self-verification-manifest "$SELF_VERIFY_MANIFEST")
        fi
        printf 'non-interactive preamble regression\n' | run_worker "$preamble_job" \
            --workflow "$preamble_workflow" --mode "$preamble_agy_mode" --max-cycles 1 \
            ${preamble_mode_args+"${preamble_mode_args[@]}"} \
            ${preamble_self_verify_args+"${preamble_self_verify_args[@]}"} \
            > "$TMP/$preamble_job.out" 2> "$TMP/$preamble_job.err"
        preamble_rc=$?
        if [[ "$preamble_rc" == 0 ]] && python3 -I -S -B - \
                "$TMP" "$preamble_job" "$preamble_workflow" "$preamble_mode" \
                "$preamble_self_verify" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
job, workflow, mode, self_verify = sys.argv[2:]
job_dir = root / "logs" / job
provider_prompt_path = root / f"{job}.prompt"
argv_path = root / f"{job}.argv"
state = json.loads((job_dir / "dispatch-state.json").read_text(encoding="utf-8"))
command = json.loads((job_dir / "dispatch-command.json").read_text(encoding="utf-8"))
assert state["status"] == "succeeded"
assert state["workflow"] == workflow
assert command["workflow"] == workflow
assert bool(command["provider_scope_path"]) == (mode == "scoped")

provider_prompt = provider_prompt_path.read_bytes()
argv = [part for part in argv_path.read_bytes().split(b"\0") if part]
assert len(argv) >= 2 and argv[-2] == b"--print"
assert argv[-1] == provider_prompt
assert argv[argv.index(b"--mode") + 1] == (b"plan" if workflow == "explore" else b"accept-edits")
effective_prompt = provider_prompt
pointer = re.search(rb"Read '([^']+)' as the complete prompt", provider_prompt)
recorded_prompt = (job_dir / "full-prompt.txt").read_bytes()
if pointer is not None:
    staged_path = Path(pointer.group(1).decode("utf-8"))
    assert staged_path == (job_dir / "staged" / "full-prompt.txt").resolve(strict=True)
    effective_prompt = staged_path.read_bytes()
    assert effective_prompt == recorded_prompt
else:
    assert recorded_prompt in provider_prompt

expected_block = (
    "NON-INTERACTIVE RUN:\n"
    "- Respect applicable user and repository instructions (for example GEMINI.md),\n"
    "  including security, privacy, permission, and scope constraints.\n"
    "- If those instructions conflict with this task or output contract, or require\n"
    "  clarification, report status=blocked and requires_human=true; explain the\n"
    "  conflict in open_questions. Do not bypass the constraint.\n"
    "- Nobody can answer questions during this run. Do not ask; put assumptions,\n"
    "  blockers, and questions in the result as the output contract requires.\n"
    "- Stay within the task's scope and allowed paths. Do not add CI, hooks, linters,\n"
    "  formatters, type checkers, dependencies, or refactors the task did not ask for.\n"
    "- Include compatible report requirements in the schema fields; report incompatible\n"
    "  requirements as a conflict rather than silently discarding them.\n"
).encode("utf-8")
assert effective_prompt.count(expected_block) == 1
output_contract = effective_prompt.index("OUTPUT CONTRACT — non-negotiable:".encode("utf-8"))
block_start = effective_prompt.index(expected_block)
shell_rule = effective_prompt.index(b"Do NOT run shell or terminal tools or tests.")
task_follows = effective_prompt.index(b"TASK FOLLOWS:")
assert block_start < output_contract < shell_rule < task_follows
if workflow in ("task", "project") and mode == "whole":
    base = command["base_commit"]
    assert f"immutable Git base commit {base}".encode() in provider_prompt
    assert b"cumulative net changes relative to that base commit" in provider_prompt
    assert b"state at provider launch" not in provider_prompt
elif mode == "scoped":
    assert b"net changes in this Gitless stage since this stage launched" in provider_prompt
if self_verify == "1":
    self_verify_request = b"Required check IDs, run automatically: required_check"
    assert self_verify_request in effective_prompt
    assert effective_prompt.index(self_verify_request) < block_start
else:
    assert b"Required check IDs, run automatically:" not in effective_prompt
PY
        then
            ok "$preamble_workflow/$preamble_mode provider-bound preamble and existing contract order"
        else
            noninteractive_preamble_failures=$((noninteractive_preamble_failures + 1))
            bad "$preamble_workflow/$preamble_mode provider-bound preamble and existing contract order"
        fi
    done
done
if (( noninteractive_preamble_failures == 0 )); then
    ok "non-interactive preamble reaches all six workflow/transmission combinations"
else
    bad "non-interactive preamble reaches all six workflow/transmission combinations"
fi

printf 'self-verification manifest CLI binding\n' | run_worker self-verification-valid \
    --workflow task --max-cycles 2 \
    --self-verification-manifest "$SELF_VERIFY_MANIFEST" \
    > "$TMP/self-verification-valid.out" 2> "$TMP/self-verification-valid.err"
self_verification_valid_rc=$?
if [[ "$self_verification_valid_rc" == 0 ]] && python3 -I -S -B - \
        "$SELF_VERIFY_MANIFEST" \
        "$LOGS_REAL/self-verification-valid/self-verification-manifest.json" \
        "$LOGS_REAL/self-verification-valid/dispatch-command.json" \
        "$TMP/self-verification-valid.prompt" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

source_path, copied_path, command_path, prompt_path = map(Path, sys.argv[1:])
source = source_path.read_bytes()
copied = copied_path.read_bytes()
command = json.loads(command_path.read_text(encoding="utf-8"))
prompt = prompt_path.read_text(encoding="utf-8")
info = copied_path.stat()

assert copied == source
assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
assert command["schema_version"] == 16
assert command["provider_isolation"] == "session"
assert command["allow_self_verification"] is True
assert command["self_verification_manifest_path"] == str(copied_path)
assert command["self_verification_manifest_sha256"] == hashlib.sha256(source).hexdigest()
assert command["self_verification_manifest_identity"] == [
    info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
]
assert "Required check IDs, run automatically: required_check" in prompt
assert "Optional check IDs, request only when useful: optional_check" in prompt
assert "requested_check_ids may contain each optional ID at most once" in prompt
for private_value in (
    "/usr/bin/true", "/bin/sh", "checks/optional.sh", str(source_path), str(copied_path),
):
    assert private_value not in prompt
PY
then
    ok "self-verification CLI copies and binds the private manifest with an ID-only prompt"
else
    bad "self-verification CLI manifest copy, command binding, or prompt boundary"
fi

cp "$SELF_VERIFY_MANIFEST" "$TMP/self-verification-mode.json"
chmod 0644 "$TMP/self-verification-mode.json"
ln -s "$SELF_VERIFY_MANIFEST" "$TMP/self-verification-symlink.json"
cp "$SELF_VERIFY_MANIFEST" "$TMP/self-verification-hardlink-anchor.json"
chmod 0600 "$TMP/self-verification-hardlink-anchor.json"
ln "$TMP/self-verification-hardlink-anchor.json" "$TMP/self-verification-hardlink.json"
TMP_REAL="$(cd "$TMP" && pwd -P)"
self_verification_unsafe_failures=0
for unsafe_case in mode symlink hardlink; do
    unsafe_manifest="$TMP_REAL/self-verification-$unsafe_case.json"
    printf 'unsafe self-verification manifest\n' | run_worker "self-verification-invalid-$unsafe_case" \
        --workflow task --max-cycles 2 --self-verification-manifest "$unsafe_manifest" \
        > "$TMP/self-verification-invalid-$unsafe_case.out" \
        2> "$TMP/self-verification-invalid-$unsafe_case.err"
    unsafe_rc=$?
    if [[ "$unsafe_rc" != 64 \
            || -e "$TMP/self-verification-invalid-$unsafe_case.called" \
            || -e "$LOGS_REAL/self-verification-invalid-$unsafe_case/self-verification-manifest.json" ]] \
            || ! grep -Fq 'self-verification manifest is invalid or unavailable' \
                "$TMP/self-verification-invalid-$unsafe_case.err"; then
        self_verification_unsafe_failures=$((self_verification_unsafe_failures + 1))
    fi
done
if (( self_verification_unsafe_failures == 0 )); then
    ok "self-verification CLI rejects non-private, symlinked, and hard-linked manifests before provider launch"
else
    bad "self-verification CLI unsafe manifest boundaries"
fi

printf 'unsupported explore verification\n' | AGY_WORKER_MODE=plan \
    run_worker self-verification-explore --workflow explore --max-cycles 1 \
    --self-verification-manifest "$SELF_VERIFY_MANIFEST" \
    > "$TMP/self-verification-explore.out" 2> "$TMP/self-verification-explore.err"
self_verification_explore_rc=$?
if [[ "$self_verification_explore_rc" == 64 && ! -e "$TMP/self-verification-explore.called" ]] \
        && grep -Fq 'requires task or project workflow' "$TMP/self-verification-explore.err"; then
    ok "self-verification CLI rejects explore before provider launch"
else
    bad "self-verification CLI workflow boundary"
fi

AGY_WORKER_LOG_DIR="$TMP/logs" "$WORKER" status --job-id self-verification-valid \
    --use-self-verification > "$TMP/self-verification-wrong-action.out" \
    2> "$TMP/self-verification-wrong-action.err"
self_verification_wrong_action_rc=$?
AGY_WORKER_LOG_DIR="$TMP/logs" "$WORKER" continue --job-id self-verification-valid \
    --approve-state-sha "$(printf '0%.0s' {1..64})" \
    --use-self-verification --use-self-verification \
    > "$TMP/self-verification-repeated.out" 2> "$TMP/self-verification-repeated.err"
self_verification_repeated_rc=$?
AGY_WORKER_LOG_DIR="$TMP/logs" "$WORKER" status --job-id self-verification-valid \
    --format json > "$TMP/self-verification-status.json" 2> "$TMP/self-verification-status.err"
self_verification_status_rc=$?
self_verification_state_sha="$(python3 -I -S -B -c \
    'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["state_sha256"])' \
    "$TMP/self-verification-status.json" 2>/dev/null)"
self_verification_worker_calls_before="$(wc -l < "$TMP/self-verification-valid.worker-calls")"
AGY_WORKER_LOG_DIR="$TMP/logs" "$WORKER" continue --job-id self-verification-valid \
    --approve-state-sha "$self_verification_state_sha" --use-self-verification \
    > "$TMP/self-verification-continue.out" 2> "$TMP/self-verification-continue.err"
self_verification_continue_rc=$?
self_verification_worker_calls_after="$(wc -l < "$TMP/self-verification-valid.worker-calls")"
if [[ "$self_verification_wrong_action_rc" == 64 \
        && "$self_verification_repeated_rc" == 64 \
        && "$self_verification_status_rc" == 0 \
        && "$self_verification_continue_rc" == 64 \
        && "$self_verification_worker_calls_after" == "$self_verification_worker_calls_before" ]] \
        && grep -Fq -- '--use-self-verification is valid only with continue' \
            "$TMP/self-verification-wrong-action.err" \
        && grep -Fq 'usage: agy-worker.sh' "$TMP/self-verification-repeated.err" \
        && grep -Fq 'self-verification feedback is unavailable' \
            "$TMP/self-verification-continue.err"; then
    ok "stored self-verification feedback is explicit, continue-only, and single-use"
else
    bad "stored self-verification continue routing boundary"
fi

printf 'normal scoped root target\n' > "$TMP/repo/normal-root-target.txt"
NORMAL_ROOT_SCOPE="$TMP/normal-root.scope.json"
NORMAL_ROOT_PROVIDER_HOME="$LOGS_REAL/normal-root-prompt/provider-home"
NORMAL_ROOT_CALLER_HOME="$TMP/native-caller-home"
mkdir -p "$NORMAL_ROOT_CALLER_HOME"
chmod 0700 "$NORMAL_ROOT_CALLER_HOME"
printf '%s\n' \
    '{"schema_version":1,"kind":"agy-worker-provider-scope","read":[{"path":"normal-root-target.txt","kind":"file"}],"write":[{"path":"normal-root-target.txt","kind":"file"}]}' \
    > "$NORMAL_ROOT_SCOPE"
chmod 0600 "$NORMAL_ROOT_SCOPE"
NORMAL_ROOT_TRANSMISSION_SHA="$(
    "$WORKER" transmission-preview --task fixture --workdir "$CORE_WORKDIR" \
        --provider-scope "$NORMAL_ROOT_SCOPE" --provider-isolation native --format json \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["transmission_sha256"])'
)"
NORMAL_ROOT_SESSION_TRANSMISSION_SHA="$(
    "$WORKER" transmission-preview --task fixture --workdir "$CORE_WORKDIR" \
        --provider-scope "$NORMAL_ROOT_SCOPE" --provider-isolation session --format json \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["transmission_sha256"])'
)"
printf 'mode-bound scoped approval mismatch\n' | \
    FAKE_CALLED_FILE="$TMP/normal-root-mode-mismatch.called" \
    run_worker normal-root-mode-mismatch --workflow task --max-cycles 1 --provider-isolation native \
    --provider-scope "$NORMAL_ROOT_SCOPE" --approve-transmission-sha "$NORMAL_ROOT_SESSION_TRANSMISSION_SHA" \
    > "$TMP/normal-root-mode-mismatch.out" 2> "$TMP/normal-root-mode-mismatch.err"
normal_root_mode_mismatch_rc=$?
if [[ "$normal_root_mode_mismatch_rc" == 64 && ! -e "$TMP/normal-root-mode-mismatch.called" ]]; then
    ok "scoped launch approval is bound to provider isolation"
else
    bad "scoped launch approval provider-isolation binding"
fi
printf 'normal scoped root prompt\n' | \
    FAKE_MODEL_FILE="$NORMAL_ROOT_PROVIDER_HOME/model" \
    FAKE_PROMPT_FILE="$NORMAL_ROOT_PROVIDER_HOME/prompt" \
    FAKE_DIRS_FILE="$NORMAL_ROOT_PROVIDER_HOME/dirs" \
    FAKE_ARGV_FILE="$NORMAL_ROOT_PROVIDER_HOME/argv" \
    FAKE_STAGE_RESULT_FILE="$NORMAL_ROOT_PROVIDER_HOME/stage-result" \
    FAKE_CALLS_FILE=/dev/null \
    FAKE_WORKER_CALLS_FILE="$NORMAL_ROOT_PROVIDER_HOME/worker-calls" \
    FAKE_CALLED_FILE="$NORMAL_ROOT_PROVIDER_HOME/called" \
    FAKE_HOME_OBSERVED_FILE="$NORMAL_ROOT_PROVIDER_HOME/home" \
    HOME="$NORMAL_ROOT_CALLER_HOME" \
    FAKE_EDIT_FROM_BOUND_ROOT=normal-root-target.txt FAKE_EDIT_CONTENT='normal scoped changed' \
    run_worker normal-root-prompt \
    --workflow task --max-cycles 1 --provider-isolation native \
    --provider-scope "$NORMAL_ROOT_SCOPE" --approve-transmission-sha "$NORMAL_ROOT_TRANSMISSION_SHA" \
    > "$TMP/normal-root-prompt.out" 2> "$TMP/normal-root-prompt.err"
normal_root_prompt_rc=$?
if [[ "$normal_root_prompt_rc" == 0 ]] && python3 -B - \
        "$NORMAL_ROOT_PROVIDER_HOME/argv" \
        "$TMP/logs/normal-root-prompt/dispatch-command.json" "$TMP/repo" \
        "$LOGS_REAL/normal-root-prompt/stage-001" "$NORMAL_ROOT_PROVIDER_HOME/home" \
        "$NORMAL_ROOT_CALLER_HOME" "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" <<'PY'
import json
import os
from pathlib import Path
import runpy
import sys

dispatch = runpy.run_path(sys.argv[7], run_name="agy_dispatch_prompt_test")
argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
command = json.load(open(sys.argv[2], encoding="utf-8"))
prompt = argv[argv.index(b"--print") + 1].decode("utf-8")
root_marker = "The exact absolute workspace root for this attempt is the JSON string "
root_start = prompt.index(root_marker) + len(root_marker)
decoded_root, root_end = json.JSONDecoder().raw_decode(prompt[root_start:])
assert command["schema_version"] == dispatch["CURRENT_COMMAND_SCHEMA"]
assert command["provider_isolation"] == "native"
assert argv.count(b"--sandbox") == 1
assert command["provider_scope_path"] is not None
assert Path(open(sys.argv[5], encoding="utf-8").read().strip()).is_absolute()
assert open(sys.argv[5], encoding="utf-8").read().strip() != sys.argv[6]
assert prompt.startswith("FILE-TOOL ROOT — non-negotiable:\n")
assert not prompt.startswith("BOOST FILE-TOOL ROOT")
assert decoded_root == os.path.realpath(sys.argv[4]) and Path(decoded_root).is_absolute()
assert prompt[root_start + root_end:].startswith(".\n")
assert "absolute child path beneath that root" in prompt
assert "never guess or search for another root" in prompt
assert "If you delegate" not in prompt
assert sys.argv[3] not in prompt
assert (Path(sys.argv[3]) / "normal-root-target.txt").read_text(encoding="utf-8") == "normal scoped changed\n"

weird_root = Path('/private/tmp/space "quote" \\ slash\nline/stage-001')
synthetic = ["agy", "--print", "ORIGINAL-PROMPT"]
dispatch["_bind_workspace_prompt"](
    synthetic, weird_root, scoped=True, provider_isolation="native",
)
assert synthetic[-2] == "--print" and synthetic[-1].endswith("ORIGINAL-PROMPT")
synthetic_start = synthetic[-1].index(root_marker) + len(root_marker)
synthetic_root, synthetic_end = json.JSONDecoder().raw_decode(synthetic[-1][synthetic_start:])
assert synthetic_root == str(weird_root)
assert "\nline" not in synthetic[-1][synthetic_start:synthetic_start + synthetic_end]
PY
then
    ok "normal scoped dispatch pins the final stage root in its file-tool prompt"
else
    if [[ -s "$LOGS_REAL/normal-root-prompt/stderr.txt" ]]; then
        printf '%s' 'normal scoped root provider stderr: ' >&2
        /usr/bin/head -c 4096 "$LOGS_REAL/normal-root-prompt/stderr.txt" >&2 || :
        printf '\n' >&2
    fi
    bad "normal scoped file-tool root binding"
fi
rm -f "$TMP/repo/normal-root-target.txt"

printf 'normal whole root target\n' > "$TMP/repo/normal-whole-root-target.txt"
NORMAL_WHOLE_CALLER_HOME="$TMP/session-caller-home"
mkdir -p "$NORMAL_WHOLE_CALLER_HOME"
chmod 0700 "$NORMAL_WHOLE_CALLER_HOME"
printf 'normal whole root prompt\n' | \
    FAKE_HOME_OBSERVED_FILE="$TMP/normal-whole-root-prompt.home" \
    HOME="$NORMAL_WHOLE_CALLER_HOME" \
    FAKE_EDIT_FROM_BOUND_ROOT=normal-whole-root-target.txt FAKE_EDIT_CONTENT='normal whole changed' \
    run_worker normal-whole-root-prompt --workflow task --max-cycles 1 \
    > "$TMP/normal-whole-root-prompt.out" 2> "$TMP/normal-whole-root-prompt.err"
normal_whole_root_prompt_rc=$?
if [[ "$normal_whole_root_prompt_rc" == 0 ]] && python3 -B - \
        "$TMP/normal-whole-root-prompt.argv" \
        "$TMP/logs/normal-whole-root-prompt/dispatch-command.json" "$TMP/repo" \
        "$TMP/normal-whole-root-prompt.home" "$NORMAL_WHOLE_CALLER_HOME" <<'PY'
import json
import os
from pathlib import Path
import sys

argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
command = json.load(open(sys.argv[2], encoding="utf-8"))
prompt = argv[argv.index(b"--print") + 1].decode("utf-8")
root_marker = "The exact absolute workspace root for this attempt is the JSON string "
root_start = prompt.index(root_marker) + len(root_marker)
decoded_root, root_end = json.JSONDecoder().raw_decode(prompt[root_start:])
assert command["schema_version"] == 16
assert command["provider_isolation"] == "session"
assert b"--sandbox" not in argv
assert command["provider_scope_path"] is None
assert open(sys.argv[4], encoding="utf-8").read().strip() == sys.argv[5]
assert isinstance(command["approved_whole_worktree_sha256"], str)
assert prompt.startswith("FILE-TOOL ROOT — non-negotiable:\n")
assert decoded_root == os.path.realpath(sys.argv[3]) and Path(decoded_root).is_absolute()
assert prompt[root_start + root_end:].startswith(".\n")
assert "complete explicitly approved whole worktree" in prompt
assert "never guess or search for another root" in prompt
assert (Path(sys.argv[3]) / "normal-whole-root-target.txt").read_text(encoding="utf-8") == "normal whole changed\n"
PY
then
    ok "normal whole-worktree dispatch pins its approved root in the file-tool prompt"
else
    bad "normal whole-worktree file-tool root binding"
fi
rm -f "$TMP/repo/normal-whole-root-target.txt"

rm -f "$TMP/repo/scoped-target.txt"

WHOLE_DRIFT_PATH="$TMP/repo/whole-worktree-drift"
printf 'manifest must remain bound through launch\n' | \
    FAKE_MUTATE_WORKTREE_PATH="$WHOLE_DRIFT_PATH" \
    run_worker whole-worktree-drift --model gemini-3.6-flash --effort high \
    > "$TMP/whole-worktree-drift.out" 2> "$TMP/whole-worktree-drift.err"
whole_drift_rc=$?
if [[ "$whole_drift_rc" == 64 \
        && ! -s "$TMP/whole-worktree-drift.out" \
        && ! -s "$TMP/whole-worktree-drift.worker-calls" ]] \
        && grep -Fq 'launch authority changed: content.content_manifest_sha256' \
            "$TMP/whole-worktree-drift.err"; then
    ok "whole-worktree drift is rejected by the supervisor before provider launch"
else
    bad "whole-worktree pre-provider drift boundary"
fi
rm -f "$WHOLE_DRIFT_PATH"

ambient_env_observed="$TMP/ambient-env-observed.txt"
printf 'ambient environment filter\n' | \
    AGY_WORKER_UNRELATED_SECRET=do-not-forward \
    FAKE_ENV_OBSERVED_FILE="$ambient_env_observed" \
    run_worker ambient-env-filter --model gemini-3.6-flash-low \
    > "$TMP/ambient-env-filter.out" 2> "$TMP/ambient-env-filter.err"
ambient_env_rc=$?
if [[ "$ambient_env_rc" == 0 && -s "$ambient_env_observed" ]] \
        && ! grep -Fq ':present' "$ambient_env_observed"; then
    ok "ambient secret is absent from agy probes and provider launch"
else
    bad "ambient secret is absent from agy probes and provider launch"
fi

explicit_env_observed="$TMP/explicit-env-observed.txt"
printf 'explicit environment opt-in\n' | \
    AGY_WORKER_UNRELATED_SECRET=approved-value \
    FAKE_ENV_OBSERVED_FILE="$explicit_env_observed" \
    run_worker explicit-env-opt-in --model gemini-3.6-flash-low \
        --provider-env AGY_WORKER_UNRELATED_SECRET \
    > "$TMP/explicit-env-opt-in.out" 2> "$TMP/explicit-env-opt-in.err"
explicit_env_rc=$?
if [[ "$explicit_env_rc" == 0 && -s "$explicit_env_observed" ]] \
        && ! grep -Fq ':absent' "$explicit_env_observed"; then
    ok "explicit provider environment name reaches agy children"
else
    bad "explicit provider environment name reaches agy children"
fi

printf 'unsafe provider environment\n' | run_worker unsafe-provider-env \
    --model gemini-3.6-flash-low --provider-env PYTHONPATH \
    > "$TMP/unsafe-provider-env.out" 2> "$TMP/unsafe-provider-env.err"
expect_exit "runtime-injection provider environment name is rejected" 64 "$?"

printf 'raw custom model\n' | run_worker raw-flash-high \
    --model gemini-3.6-flash-high > "$TMP/raw-flash-high.out" 2>/dev/null
rc=$?
if [[ "$rc" == "0" && "$(<"$TMP/raw-flash-high.model")" == "gemini-3.6-flash-high" ]] \
        && python3 - "$TMP/raw-flash-high.argv" "$TMP/raw-flash-high.calls" <<'PY'
import sys
parts = [part for part in open(sys.argv[1], "rb").read().split(b"\0") if part]
calls = open(sys.argv[2], encoding="ascii").read().splitlines()
raise SystemExit(0 if b"--effort" not in parts and calls == ["version", "help"] * 2 + ["worker"] else 1)
PY
then
    ok "raw flash-high stays exact pass-through with no effort argument"
else
    bad "raw flash-high stays exact pass-through with no effort argument"
fi

printf 'default model\n' | run_worker agy-default > "$TMP/agy-default.out" 2> "$TMP/agy-default.err"
rc=$?
if [[ "$rc" == 0 ]] && python3 -B - "$TMP/agy-default.argv" "$TMP/logs/agy-default/selection.json" "$TMP/agy-default.calls" <<'PYTHON'
import json,sys
parts=open(sys.argv[1],'rb').read().split(b'\0');record=json.load(open(sys.argv[2]))
assert record['selection_mode']=='agy-default' and record['resolved_agy_model'] is None
assert 'probed_executable' in record and 'installed_agy_version' in record
assert b'--model' not in parts and b'--effort' not in parts
assert open(sys.argv[3]).read().splitlines()==['version','help']*2+['worker']
PYTHON
then ok "bound agy default preserves executable checks and emits no model or effort"; else bad "bound agy default"; fi

printf 'literal model under malformed version output\n' | FAKE_VERSION_MODE=malformed \
    run_worker literal-version-independent --model future-model-1.2 \
    > "$TMP/literal-version-independent.out" 2> "$TMP/literal-version-independent.err"
rc=$?
if [[ "$rc" == 0 && "$(<"$TMP/literal-version-independent.model")" == "future-model-1.2" ]] \
        && python3 - "$TMP/literal-version-independent.argv" \
            "$TMP/logs/literal-version-independent/selection.json" \
            "$TMP/literal-version-independent.calls" <<'PY'
import json
import sys

argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
record = json.load(open(sys.argv[2], encoding="utf-8"))
calls = open(sys.argv[3], encoding="ascii").read().splitlines()
assert calls == ["version", "help"] * 2 + ["worker"]
assert argv.count(b"--model") == 1
assert argv[argv.index(b"--model") + 1] == b"future-model-1.2"
assert b"--effort" not in argv and b"--thinking-level" not in argv
assert record["schema_version"] == 5
assert record["selection_mode"] == "exact-model"
assert record["user_model"] == record["resolved_agy_model"] == "future-model-1.2"
assert record["user_model_source"] == "cli"
assert record["installed_agy_version"] == "version 1.2.11"
assert "probed_executable" in record
assert not any(key.startswith("matrix_") for key in record)
PY
then
    ok "literal model routing stays version-independent while version observation remains non-gating"
else
    bad "literal model version-independent contract (exit $rc)"
fi

assert_direct_result() {
    local name="$1" job="$2" expected="$3" user_model="$4" user_effort="$5"
    local model_source="${6:-cli}" effort_source="${7:-}"
    local expected_schema="${8:-5}"
    if [[ "$(<"$TMP/$job.model")" == "$expected" ]] \
            && [[ "$(wc -l < "$TMP/$job.worker-calls" | tr -d ' ')" == "1" ]] \
            && python3 - "$TMP/$job.argv" "$TMP/logs/$job/selection.json" \
                "$TMP/$job.calls" "$expected" "$user_model" "$user_effort" "$model_source" "$effort_source" "$expected_schema" <<'PY'
import json
import os
import stat
import sys

argv_path, selection_path, calls_path, expected, user_model, user_effort, model_source, effort_source, expected_schema = sys.argv[1:]
parts = [part for part in open(argv_path, "rb").read().split(b"\0") if part]
assert open(calls_path, encoding="ascii").read().splitlines() == ["version", "help", "version", "help", "worker"]
assert parts.count(b"--model") == 1
index = parts.index(b"--model")
assert parts[index + 1].decode() == expected
if user_effort:
    assert parts.count(b"--effort") == 1
    assert parts[parts.index(b"--effort") + 1].decode() == user_effort
else:
    assert b"--effort" not in parts
assert b"--thinking-level" not in parts
record = json.load(open(selection_path, encoding="utf-8"))
assert record["schema_version"] == int(expected_schema)
assert record["kind"] == "agy-worker-selection"
assert record["user_model"] == user_model
assert record.get("user_effort", "") == user_effort
assert record["user_model_source"] == model_source
assert record.get("user_effort_source", "") == effort_source
assert record["resolved_agy_model"] == expected
assert record["installed_agy_version"] in {"1.2.11", "agy 1.2.11"}
assert not any(key.startswith("matrix_") for key in record)
binding = record["probed_executable"]
assert set(binding) == {"path_sha256", "target_lstat", "content_sha256", "symlink_chain", "components"}
assert len(binding["path_sha256"]) == 64
assert len(binding["content_sha256"]) == 64
assert binding["target_lstat"]["inode"] > 0
assert binding["target_lstat"]["ctime_ns"] > 0
assert all("path" not in key or key == "path_sha256" for item in [binding, *binding["symlink_chain"], *binding["components"]] for key in item)
assert stat.S_IMODE(os.stat(selection_path).st_mode) & 0o077 == 0
PY
    then ok "$name"; else bad "$name"; fi
}

# Advertised capabilities and literal caller choices authorize the interface.
printf 'exact-version structural help may dispatch\n' | \
    AGY_TEST_WORKER="$WORKER" run_worker exact-version-unseen-help --model gemini-3.6-flash --effort high \
    > "$TMP/exact-version-unseen-help.out" 2> "$TMP/exact-version-unseen-help.err"
rc=$?
if [[ "$rc" == 0 ]]; then
    assert_direct_result "complete structural probe proceeds without version approval" \
        exact-version-unseen-help gemini-3.6-flash gemini-3.6-flash high cli cli 5
else
    bad "exact-version structural probe boundary (exit $rc)"
fi
# An option help line may explicitly negate --model.  It must be an
# option-local structural match; the controller does not infer availability
# from provider prose.
printf 'help prose requires Codex, not controller, semantic interpretation\n' | \
    AGY_TEST_WORKER="$WORKER" FAKE_VERSION_MODE=ready FAKE_HELP_MODE=semantic \
    run_worker help-option-negation --model gemini-3.6-flash --effort high \
    > "$TMP/help-option-negation.out" 2> "$TMP/help-option-negation.err"
rc=$?
if [[ "$rc" == 0 ]]; then
    assert_direct_result "option prose does not override the structural capability check" \
        help-option-negation gemini-3.6-flash gemini-3.6-flash high cli cli 5
else
    bad "exact-version option prose structural boundary (exit $rc)"
fi
LC_ALL=POSIX FAKE_VERSION_MODE=drift117 FAKE_HELP_MODE=locale-sensitive PATH="$TMP/bin:$PATH" \
    "$SELECTOR" --model gemini-3.6-flash --effort high \
    --child-env FAKE_VERSION_MODE --child-env FAKE_HELP_MODE \
    > "$TMP/direct-selector-public.json" 2> "$TMP/direct-selector-public.err"
rc=$?
if [[ "$rc" == 0 ]] && python3 - "$TMP/direct-selector-public.json" "$TMP/bin/agy" <<'PYTHON'
import json, sys
payload = open(sys.argv[1], "rb").read()
record = json.loads(payload)
assert sys.argv[2].encode() not in payload
assert record["schema_version"] == 5
assert record["installed_agy_version"] == "1.1.17"
assert record["user_model"] == record["resolved_agy_model"] == "gemini-3.6-flash"
assert record["user_effort"] == "high"
assert "path" not in record["probed_executable"]
assert set(record["probed_executable"]) == {"path_sha256", "target_lstat", "content_sha256", "symlink_chain", "components"}
PYTHON
then ok "direct selector accepts diagnostic version and exposes no executable path"
else bad "direct selector diagnostic/executable binding"; fi

# BEGIN model-selection coverage
# BEGIN exhaustive pure-policy model-selection coverage
if PYTHONDONTWRITEBYTECODE=1 python3 -B - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "skills" / "agy-worker" / "runtime" / "scripts"))
import model_selection

original_platform = model_selection.sys.platform
try:
    model_selection.sys.platform = "darwin"
    assert model_selection._path_sha256("/var/run/agy") == model_selection._path_sha256("/private/var/run/agy")
    assert model_selection._path_sha256("/variety/run/agy") != model_selection._path_sha256("/private/variety/run/agy")
finally:
    model_selection.sys.platform = original_platform
PY
then
    ok "only the documented macOS /var alias has a normalized executable path digest"
else
    bad "macOS executable path alias normalization boundary"
fi

if PYTHONDONTWRITEBYTECODE=1 python3 -B - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "skills" / "agy-worker" / "runtime" / "scripts"))
import model_selection

# Model and effort catalogs belong to AGY. Only transport/provenance is validated.
for model in ("gemini-3.1-pro", "claude-sonnet-4-6", "vendor/Future-Model", "gemini-3.6-flash-high"):
    for effort in (None, "medium", "thinking-high", "Future-Level"):
        record = model_selection.resolve_selection(model, effort, "cli", "cli" if effort else None, probe_version=False)
        assert record["resolved_agy_model"] == model
        assert record.get("user_effort") == effort
        model_selection.validate_selection_record(record)
for model, effort in (("", None), (" padded", None), ("model", "bad effort"), ("model", "-flag")):
    try:
        model_selection.resolve_selection(model, effort, "cli", "cli" if effort else None, probe_version=False)
    except model_selection.CallerError:
        pass
    else:
        raise AssertionError("unsafe transport accepted")
PY
then
    ok "literal caller values and transport boundaries without a model catalog"
else
    bad "literal caller values and transport boundaries without a model catalog"
fi
# END exhaustive pure-policy model-selection coverage

# BEGIN representative model-selection worker dispatches
# Representative end-to-end direct pair worker dispatches
printf 'representative direct pair cli-cli\n' | \
    run_worker direct-pair-rep-cli-cli --model gemini-3.7-flash --effort high \
    > "$TMP/direct-pair-rep-cli-cli.out" 2> "$TMP/direct-pair-rep-cli-cli.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative pair gemini-3.7-flash/high accepts cli-cli" \
        "direct-pair-rep-cli-cli" "gemini-3.7-flash" "gemini-3.7-flash" "high" \
        "cli" "cli"
else
    bad "representative pair gemini-3.7-flash/high accepts cli-cli"
fi

printf 'representative direct pair cli-env\n' | \
    AGY_WORKER_EFFORT="medium" run_worker direct-pair-rep-cli-env --model gemini-3.6-flash \
    > "$TMP/direct-pair-rep-cli-env.out" 2> "$TMP/direct-pair-rep-cli-env.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative pair gemini-3.6-flash/medium accepts cli-env" \
        "direct-pair-rep-cli-env" "gemini-3.6-flash" "gemini-3.6-flash" "medium" \
        "cli" "environment"
else
    bad "representative pair gemini-3.6-flash/medium accepts cli-env"
fi

printf 'representative direct pair env-cli\n' | \
    AGY_WORKER_MODEL="gemini-3.8-flash" run_worker direct-pair-rep-env-cli --effort low \
    > "$TMP/direct-pair-rep-env-cli.out" 2> "$TMP/direct-pair-rep-env-cli.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative pair gemini-3.8-flash/low accepts env-cli" \
        "direct-pair-rep-env-cli" "gemini-3.8-flash" "gemini-3.8-flash" "low" \
        "environment" "cli"
else
    bad "representative pair gemini-3.8-flash/low accepts env-cli"
fi

printf 'representative direct pair env-env\n' | \
    AGY_WORKER_MODEL="gemini-3.1-pro" AGY_WORKER_EFFORT="high" \
    run_worker direct-pair-rep-env-env \
    > "$TMP/direct-pair-rep-env-env.out" 2> "$TMP/direct-pair-rep-env-env.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative pair gemini-3.1-pro/high accepts env-env" \
        "direct-pair-rep-env-env" "gemini-3.1-pro" "gemini-3.1-pro" "high" \
        "environment" "environment"
else
    bad "representative pair gemini-3.1-pro/high accepts env-env"
fi

# Representative end-to-end exact and fixed model worker dispatches
printf 'representative exact cli\n' | run_worker direct-exact-rep-cli \
    --model gemini-3.7-flash-high > "$TMP/direct-exact-rep-cli.out" 2> "$TMP/direct-exact-rep-cli.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative exact model gemini-3.7-flash-high accepts cli" \
        "direct-exact-rep-cli" "gemini-3.7-flash-high" "gemini-3.7-flash-high" "" \
        "cli" ""
else
    bad "representative exact model gemini-3.7-flash-high accepts cli"
fi

printf 'representative exact env\n' | \
    AGY_WORKER_MODEL="gemini-3.6-flash-low" run_worker direct-exact-rep-env \
    > "$TMP/direct-exact-rep-env.out" 2> "$TMP/direct-exact-rep-env.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative exact model gemini-3.6-flash-low accepts env" \
        "direct-exact-rep-env" "gemini-3.6-flash-low" "gemini-3.6-flash-low" "" \
        "environment" ""
else
    bad "representative exact model gemini-3.6-flash-low accepts env"
fi

printf 'representative fixed cli\n' | run_worker direct-fixed-rep-cli \
    --model claude-sonnet-4-6 > "$TMP/direct-fixed-rep-cli.out" 2> "$TMP/direct-fixed-rep-cli.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative fixed model claude-sonnet-4-6 accepts cli" \
        "direct-fixed-rep-cli" "claude-sonnet-4-6" "claude-sonnet-4-6" "" \
        "cli" ""
else
    bad "representative fixed model claude-sonnet-4-6 accepts cli"
fi

printf 'representative fixed env\n' | \
    AGY_WORKER_MODEL="gpt-oss-120b-medium" run_worker direct-fixed-rep-env \
    > "$TMP/direct-fixed-rep-env.out" 2> "$TMP/direct-fixed-rep-env.err"
if [[ $? == 0 ]]; then
    assert_direct_result "representative fixed model gpt-oss-120b-medium accepts env" \
        "direct-fixed-rep-env" "gpt-oss-120b-medium" "gpt-oss-120b-medium" "" \
        "environment" ""
else
    bad "representative fixed model gpt-oss-120b-medium accepts env"
fi
# END representative model-selection worker dispatches

# END model-selection coverage

expect_selector_reject() {
    local name="$1" job="$2"; shift 2
    printf 'must reject before task read\n' | run_worker "$job" "$@" \
        > "$TMP/$job.out" 2> "$TMP/$job.err"
    local got=$?
    if [[ "$got" == 64 && ! -s "$TMP/$job.out" \
            && ! -s "$TMP/$job.calls" \
            && ! -e "$TMP/logs/$job/task.txt" ]]; then
        ok "$name (exit 64, zero agy calls)"
    else
        bad "$name (exit $got, wanted 64 before task read and agy)"
    fi
}

expect_selector_reject "repeated model is ambiguous" repeated-model \
    --model gemini-3.6-flash --model gemini-3.6-flash --effort high
expect_selector_reject "repeated effort is ambiguous" repeated-effort \
    --model gemini-3.6-flash --effort high --effort high
expect_selector_reject "removed tier is unknown" repeated-tier --tier bulk --tier bulk
expect_selector_reject "retired literal alias rejects before task or provider" retired-literal \
    --literal-model future-model-1.2
model_too_long="$(python3 -c 'print("a-" + "b" * 127)')"
expect_selector_reject "overlong model is rejected" model-too-long --model "$model_too_long"
expect_selector_reject "empty CLI model is rejected" empty-cli-model --model ''
expect_selector_reject "empty CLI effort is rejected" empty-cli-effort \
    --model gemini-3.6-flash --effort ''
expect_selector_reject "effort without model is rejected" effort-without-model --effort high
expect_selector_reject "padded direct model is rejected" padded-direct \
    --model ' gemini-3.6-flash' --effort high
expect_selector_reject "invented thinking-level flag is rejected" thinking-flag \
    --model gemini-3.6-flash --thinking-level high

expect_selector_reject "retired disposition flag is actionable rejection" retired-disposition \
    --model future-model --compatibility-disposition proceed
expect_selector_reject "retired help approval flag is actionable rejection" retired-help-approval \
    --model future-model --approve-help-sha "$(printf 'a%.0s' {1..64})"

assert_env_reject() {
    local name="$1" job="$2" got="$3"
    if [[ "$got" == 64 && ! -s "$TMP/$job.out" && ! -s "$TMP/$job.calls" \
            && ! -e "$TMP/logs/$job/task.txt" ]]; then
        ok "$name (exit 64, zero agy calls)"
    else
        bad "$name (exit $got, wanted 64 before task read and agy)"
    fi
}

printf 'same model conflict\n' | AGY_WORKER_MODEL=gemini-3.6-flash \
    run_worker same-model-conflict --model gemini-3.6-flash --effort high \
    > "$TMP/same-model-conflict.out" 2> "$TMP/same-model-conflict.err"
assert_env_reject "same model in CLI and environment conflicts" same-model-conflict "$?"
printf 'same effort conflict\n' | AGY_WORKER_EFFORT=high \
    run_worker same-effort-conflict --model gemini-3.6-flash --effort high \
    > "$TMP/same-effort-conflict.out" 2> "$TMP/same-effort-conflict.err"
assert_env_reject "same effort in CLI and environment conflicts" same-effort-conflict "$?"
printf 'same tier conflict\n' | AGY_WORKER_TIER=bulk \
    run_worker same-tier-conflict --tier bulk \
    > "$TMP/same-tier-conflict.out" 2> "$TMP/same-tier-conflict.err"
assert_env_reject "retired environment is rejected" same-tier-conflict "$?"
printf 'empty env model\n' | AGY_WORKER_MODEL= run_worker empty-env-model \
    > "$TMP/empty-env-model.out" 2> "$TMP/empty-env-model.err"
assert_env_reject "explicit empty environment model is rejected" empty-env-model "$?"
printf 'empty env effort\n' | AGY_WORKER_MODEL=gemini-3.6-flash AGY_WORKER_EFFORT= \
    run_worker empty-env-effort > "$TMP/empty-env-effort.out" 2> "$TMP/empty-env-effort.err"
assert_env_reject "explicit empty environment effort is rejected" empty-env-effort "$?"

selector_fixture_has_no_bytecode() {
    ! find "$1/runtime/scripts" -type f -name '*.pyc' -print -quit | grep -q . \
        && [[ ! -d "$1/runtime/scripts/__pycache__" ]]
}

make_selector_fixture() {
    local destination="$1" mode="$2" source="${3:-$ROOT/skills/agy-worker}"
    cp -R "$source" "$destination"
    # Test fixtures must start from source bytes, not an ambient interpreter cache.
    # This is deliberately fixture-local; it never deletes checkout/cache inputs.
    rm -rf "$destination/runtime/scripts/__pycache__"
    [[ "$mode" == clean ]] || return 64

}

fixture_cache_source="$TMP/selector-fixture-cache-source"
fixture_cache_destination="$TMP/selector-fixture-cache-destination"
cp -R "$ROOT/skills/agy-worker" "$fixture_cache_source"
mkdir -p "$fixture_cache_source/runtime/scripts/__pycache__"
python3 -I -S -B - "$fixture_cache_source/runtime/scripts/model_selection.py" \
        "$fixture_cache_source/runtime/scripts/__pycache__/model_selection.fixture.pyc" <<'PY'
import py_compile
import sys

py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)
PY
make_selector_fixture "$fixture_cache_destination" clean "$fixture_cache_source"
fixture_cache_baseline=1
selector_fixture_has_no_bytecode "$fixture_cache_destination" || fixture_cache_baseline=0
mkdir -p "$fixture_cache_destination/runtime/scripts/__pycache__"
python3 -I -S -B - "$fixture_cache_destination/runtime/scripts/model_selection.py" \
        "$fixture_cache_destination/runtime/scripts/__pycache__/model_selection.fixture.pyc" <<'PY'
import py_compile
import sys

py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)
PY
fixture_cache_generated=1
selector_fixture_has_no_bytecode "$fixture_cache_destination" && fixture_cache_generated=0
if [[ "$fixture_cache_baseline" == 1 && "$fixture_cache_generated" == 1 ]]; then
    ok "selector fixtures exclude ambient bytecode but detect fixture-generated bytecode"
else
    bad "selector fixture bytecode baseline or generated-bytecode detection"
fi

expect_compat_reject() {
    local name="$1" fixture="$2" job="$3" want="$4" version_mode="$5" calls_want="$6"
    printf 'compatibility rejection\n' | AGY_TEST_WORKER="$fixture/runtime/agy-worker.sh" \
        FAKE_VERSION_MODE="$version_mode" run_worker "$job" \
        --model gemini-3.6-flash --effort high \
        > "$TMP/$job.out" 2> "$TMP/$job.err"
    local got=$? calls=0
    [[ ! -f "$TMP/$job.calls" ]] || calls="$(wc -l < "$TMP/$job.calls" | tr -d ' ')"
    if [[ "$got" == "$want" && "$calls" == "$calls_want" \
            && ! -s "$TMP/$job.worker-calls" \
            && ! -e "$TMP/logs/$job/task.txt" ]]; then
        ok "$name (exit $got, calls $calls, zero worker dispatch)"
    else
        bad "$name (exit $got/calls $calls, wanted $want/$calls_want and zero worker)"
    fi
}

VERSION_FIXTURE="$TMP/selector-version-probes"
make_selector_fixture "$VERSION_FIXTURE" clean
# Every base option must be advertised even on default routes.
for missing in add-dir disable-slash-commands json-schema mode model output-format print print-timeout; do
    for route in default direct; do
        selector_args=()
        case "$route" in
            direct) selector_args=(--model vendor/Future-Model --effort Future-Level) ;;
        esac
        job="missing-$route-$missing"
        printf 'must remain unread\n' | FAKE_HELP_MODE="missing---$missing" \
            run_worker "$job" ${selector_args+"${selector_args[@]}"} > "$TMP/$job.out" 2> "$TMP/$job.err"
        rc=$?
        if [[ "$rc" == 8 && ! -s "$TMP/$job.worker-calls" && ! -e "$TMP/logs/$job" ]] \
                && grep -Fq -- "--$missing" "$TMP/$job.err"; then
            ok "$route missing --$missing rejects before provider, job and lock mutation"
        else bad "$route missing --$missing capability boundary (exit $rc)"; fi
    done
done
# Conditional capabilities: initial session exploration needs neither native nor recovery flags.
for missing in sandbox conversation effort; do
    for route in default model; do
        selector_args=()
        case "$route" in
            model) selector_args=(--model vendor/Future-Model) ;;
        esac
        job="optional-$route-$missing"
        printf 'initial session exploration\n' | AGY_WORKER_MODE=plan FAKE_HELP_MODE="missing---$missing" \
            run_worker "$job" --workflow explore ${selector_args+"${selector_args[@]}"} \
            > "$TMP/$job.out" 2> "$TMP/$job.err"
        rc=$?
        if [[ "$rc" == 0 ]] && python3 -B - "$TMP/$job.calls" "$TMP/$job.argv" <<'PY'
from pathlib import Path
import sys
assert Path(sys.argv[1]).read_text().splitlines() == ['version', 'help'] * 2 + ['worker']
argv = Path(sys.argv[2]).read_bytes().split(b'\0')
assert b'--sandbox' not in argv and b'--conversation' not in argv and b'--effort' not in argv
PY
        then ok "$route session explore ignores unused --$missing with fresh launch probes"
        else bad "$route session explore unused --$missing (exit $rc)"; fi
    done
done
for effort_source in cli environment; do
    job="required-effort-$effort_source"
    if [[ "$effort_source" == cli ]]; then
        printf 'must remain unread\n' | FAKE_HELP_MODE=missing---effort \
            run_worker "$job" --model vendor/Future --effort Caller-Level > "$TMP/$job.out" 2> "$TMP/$job.err"
    else
        printf 'must remain unread\n' | AGY_WORKER_EFFORT=Caller-Level FAKE_HELP_MODE=missing---effort \
            run_worker "$job" --model vendor/Future > "$TMP/$job.out" 2> "$TMP/$job.err"
    fi
    rc=$?
    if [[ "$rc" == 8 && ! -e "$TMP/logs/$job" && ! -s "$TMP/$job.worker-calls" ]] \
            && grep -Fq -- '--effort' "$TMP/$job.err"; then
        ok "$effort_source effort requires its capability before task consumption"
    else bad "$effort_source effort capability boundary (exit $rc)"; fi
done
native_capability_root="$(cd "$TMP" && pwd -P)"
native_capability_target="$CORE_WORKDIR/native-capability-target.txt"
native_capability_scope="$native_capability_root/native-capability.scope.json"
printf 'native capability fixture\n' > "$native_capability_target"
printf '%s\n' '{"schema_version":1,"kind":"agy-worker-provider-scope","read":[{"path":"native-capability-target.txt","kind":"file"}],"write":[{"path":"native-capability-target.txt","kind":"file"}]}' > "$native_capability_scope"
chmod 0600 "$native_capability_scope"
native_capability_sha="$("$WORKER" transmission-preview --task fixture --workdir "$CORE_WORKDIR" \
    --provider-scope "$native_capability_scope" --provider-isolation native --format json \
    | python3 -B -c 'import json,sys; print(json.load(sys.stdin)["transmission_sha256"])')"
printf 'must remain unread\n' | AGY_TEST_WORKDIR="$CORE_WORKDIR" FAKE_HELP_MODE=missing---sandbox \
    run_worker required-native --workflow task --provider-isolation native \
    --provider-scope "$native_capability_scope" --approve-transmission-sha "$native_capability_sha" \
    > "$TMP/required-native.out" 2> "$TMP/required-native.err"
rc=$?
if [[ "$rc" == 8 && ! -e "$TMP/logs/required-native" && ! -s "$TMP/required-native.worker-calls" ]] \
        && grep -Fq -- '--sandbox' "$TMP/required-native.err"; then
    ok "native requires sandbox capability before task consumption or containment"
else bad "native capability boundary (exit $rc)"; fi
rm -f "$native_capability_target" "$native_capability_scope"

for route in default direct; do
    selector_args=()
    case "$route" in
        direct) selector_args=(--model vendor/Future-Model --effort Future-Level) ;;
    esac
    job="arbitrary-version-$route"
    printf 'arbitrary diagnostic version\n' | FAKE_VERSION_MODE=canary \
        run_worker "$job" ${selector_args+"${selector_args[@]}"} \
        > "$TMP/$job.out" 2> "$TMP/$job.err"
    if [[ $? == 0 ]] && python3 - "$TMP/$job.argv" "$TMP/logs/$job/selection.json" \
            "$TMP/$job.calls" "$route" <<'PYTHON'
import json,sys
argv=open(sys.argv[1],'rb').read().split(b'\0')
record=json.load(open(sys.argv[2]))
assert record['installed_agy_version']=='canary-build'
assert open(sys.argv[3]).read().splitlines() == ['version','help'] * 2 + ['worker']
if sys.argv[4] == 'direct':
    assert argv[argv.index(b'--model')+1] == b'vendor/Future-Model'
    assert argv[argv.index(b'--effort')+1] == b'Future-Level'
else:
    assert b'--model' not in argv and b'--effort' not in argv
PYTHON
    then ok "non-semver diagnostic permits $route launch with literal caller choices"
    else bad "non-semver diagnostic $route launch boundary"; fi
done

# Standalone observation is base-only; record verification retains recorded effort.
selection_helper="$ROOT/skills/agy-worker/runtime/scripts/model_selection.py"
for action in base record; do
    action_args=(--probe-interface)
    [[ "$action" != record ]] || action_args=(--verify-record-executable "$TMP/logs/arbitrary-version-direct/selection.json")
    FAKE_HELP_MODE=missing---effort FAKE_CALLS_FILE="$TMP/standalone-$action.calls" \
        PATH="$TMP/bin:$PATH" python3 -B "$selection_helper" "${action_args[@]}" \
        --child-env FAKE_HELP_MODE --child-env FAKE_CALLS_FILE \
        > "$TMP/standalone-$action.out" 2> "$TMP/standalone-$action.err"
    rc=$?
    if { [[ "$action" == base && "$rc" == 0 ]] \
            || { [[ "$action" == record && "$rc" == 8 ]] && grep -Fq -- '--effort' "$TMP/standalone-$action.err"; }; }; then
        ok "standalone $action probe uses its own effort context"
    else bad "standalone $action effort context (exit $rc)"; fi
    PATH="$TMP/bin:$PATH" python3 -B "$selection_helper" "${action_args[@]}" \
        --provider-isolation native > "$TMP/standalone-$action-exclusive.out" 2> "$TMP/standalone-$action-exclusive.err"
    expect_exit "standalone $action rejects selection-only isolation context" 64 "$?"
done

for version_mode in fail empty oversize hang; do
    expect_compat_reject "$version_mode version evidence is unavailable" \
        "$VERSION_FIXTURE" "version-$version_mode" 8 "$version_mode" 1
done

for help_mode in missing duplicate malformed utf8 nul oversize fail hang; do
    help_job="help-$help_mode"
    help_version_mode=ready
    printf 'help interface failure must not read this task\n' | \
        AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
        FAKE_VERSION_MODE="$help_version_mode" FAKE_HELP_MODE="$help_mode" \
        run_worker "$help_job" --model gemini-3.6-flash --effort high \
        > "$TMP/$help_job.out" 2> "$TMP/$help_job.err"
    rc=$?
    help_calls=0
    [[ ! -f "$TMP/$help_job.calls" ]] || help_calls="$(wc -l < "$TMP/$help_job.calls" | tr -d ' ')"
    help_expected=8
    if [[ "$rc" == "$help_expected" && "$help_calls" == 2 && ! -s "$TMP/$help_job.worker-calls" \
            && ! -e "$TMP/logs/$help_job/task.txt" ]]; then
        ok "$help_mode help preflight is pre-provider and task-unread"
    else
        bad "$help_mode help preflight (exit $rc/calls $help_calls, wanted $help_expected/2)"
    fi
done

cp "$TMP/bin/agy" "$TMP/bin/agy.binding-original"
printf 'executable binding drift must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_MUTATE_EXECUTABLE="$TMP/bin/agy" \
    run_worker executable-binding-drift --model gemini-3.6-flash --effort high \
    > "$TMP/executable-binding-drift.out" 2> "$TMP/executable-binding-drift.err"
rc=$?
if [[ "$rc" == 8 \
        && "$(cat "$TMP/executable-binding-drift.calls")" == $'version\nhelp' \
        && ! -s "$TMP/executable-binding-drift.worker-calls" \
        && ! -e "$TMP/logs/executable-binding-drift/task.txt" ]]; then
    ok "executable binding drift stops before task read or provider dispatch"
else
    bad "executable binding drift pre-provider boundary"
fi
mv "$TMP/bin/agy.binding-original" "$TMP/bin/agy"
chmod 0755 "$TMP/bin/agy"

# The first `--help` probe mutates the executable in-place without changing its
# inode, byte length, mode, uid/gid, or mtime.  Every lifecycle origin reaches
# the one controller launch routine below, so this initial dispatch proves the
# shared direct-selection launch binding fails before task intake or provider IO.
cp "$TMP/bin/agy" "$TMP/bin/agy.content-original"
CONTENT_MUTATION_MARKER="$TMP/executable-content-binding-drift.mutated"
printf 'same-length executable mutation must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_MUTATE_EXECUTABLE_SAME_LENGTH="$TMP/bin/agy" \
    FAKE_MUTATION_MARKER="$CONTENT_MUTATION_MARKER" \
    run_worker executable-content-binding-drift --model gemini-3.6-flash --effort high \
    > "$TMP/executable-content-binding-drift.out" 2> "$TMP/executable-content-binding-drift.err"
rc=$?
if [[ "$rc" == 8 && -f "$CONTENT_MUTATION_MARKER" \
        && ! -s "$TMP/executable-content-binding-drift.worker-calls" \
        && ! -e "$TMP/logs/executable-content-binding-drift/task.txt" ]]; then
    ok "same-length restored-mtime executable mutation stops before task or provider"
else
    bad "same-length restored-mtime executable mutation boundary"
fi
mv "$TMP/bin/agy.content-original" "$TMP/bin/agy"
chmod 0755 "$TMP/bin/agy"

# A replaced final symlink can resolve to exactly the same executable object.
# Target-only comparison accepted that topology change; the frozen binding must
# retain the symlink entry and every checked component as well.
cp "$TMP/bin/agy" "$TMP/bin/agy.real"
cp "$TMP/bin/agy" "$TMP/bin/agy.other"
chmod 0755 "$TMP/bin/agy.real" "$TMP/bin/agy.other"
rm "$TMP/bin/agy"
ln -s "agy.real" "$TMP/bin/agy"
printf 'same-target symlink replacement must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_REPLACE_EXECUTABLE_SYMLINK="$TMP/bin/agy" \
    FAKE_EXECUTABLE_SYMLINK_TARGET="$TMP/bin/agy.real" \
    run_worker executable-symlink-same-target-drift --model gemini-3.6-flash --effort high \
    > "$TMP/executable-symlink-same-target-drift.out" 2> "$TMP/executable-symlink-same-target-drift.err"
rc=$?
symlink_drift_calls="$(cat "$TMP/executable-symlink-same-target-drift.calls")"
# Either the first selector or the wrapper's repeated binding check may reject
# the changed entry. Both must stop before task intake and provider launch.
if [[ "$rc" == 8 \
        && ( "$symlink_drift_calls" == $'version\nhelp' \
             || "$symlink_drift_calls" == $'version\nhelp\nversion\nhelp' ) \
        && ! -s "$TMP/executable-symlink-same-target-drift.worker-calls" \
        && ! -e "$TMP/logs/executable-symlink-same-target-drift/task.txt" ]]; then
    ok "atomic same-target executable symlink replacement stops before task or provider"
else
    bad "atomic same-target executable symlink replacement boundary"
    printf '    rc=%s calls=%q worker_calls=%s task_present=%s\n' "$rc" \
        "$(cat "$TMP/executable-symlink-same-target-drift.calls" 2>/dev/null)" \
        "$([[ -s "$TMP/executable-symlink-same-target-drift.worker-calls" ]] && echo yes || echo no)" \
        "$([[ -e "$TMP/logs/executable-symlink-same-target-drift/task.txt" ]] && echo yes || echo no)"
fi

printf 'different executable target must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_REPLACE_EXECUTABLE_SYMLINK="$TMP/bin/agy" \
    FAKE_EXECUTABLE_SYMLINK_TARGET="$TMP/bin/agy.other" \
    run_worker executable-symlink-different-target --model gemini-3.6-flash --effort high \
    > "$TMP/executable-symlink-different-target.out" 2> "$TMP/executable-symlink-different-target.err"
rc=$?
if [[ "$rc" == 8 && ! -s "$TMP/executable-symlink-different-target.worker-calls" \
        && ! -e "$TMP/logs/executable-symlink-different-target/task.txt" ]]; then
    ok "different executable symlink target stops before task or provider"
else
    bad "different executable symlink target boundary"
fi

printf 'unsafe executable mode must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_MUTATE_EXECUTABLE_MODE="$TMP/bin/agy.other" \
    run_worker executable-unsafe-mode --model gemini-3.6-flash --effort high \
    > "$TMP/executable-unsafe-mode.out" 2> "$TMP/executable-unsafe-mode.err"
rc=$?
if [[ "$rc" == 8 && ! -s "$TMP/executable-unsafe-mode.worker-calls" \
        && ! -e "$TMP/logs/executable-unsafe-mode/task.txt" ]]; then
    ok "unsafe executable mode stops before task or provider"
else
    bad "unsafe executable mode boundary"
fi
chmod 0755 "$TMP/bin/agy.other"

printf 'unsafe executable parent must not read this task\n' | \
    AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_MUTATE_EXECUTABLE_PARENT="$TMP/bin" \
    run_worker executable-parent-authority-drift --model gemini-3.6-flash --effort high \
    > "$TMP/executable-parent-authority-drift.out" 2> "$TMP/executable-parent-authority-drift.err"
rc=$?
if [[ "$rc" == 8 && ! -s "$TMP/executable-parent-authority-drift.worker-calls" \
        && ! -e "$TMP/logs/executable-parent-authority-drift/task.txt" ]]; then
    ok "unsafe executable parent authority stops before task or provider"
else
    bad "unsafe executable parent authority boundary"
fi
chmod 0755 "$TMP/bin"
# The path-chain negatives intentionally leave a symlink fixture behind.  The
# remaining legacy probe tests need the original regular fake executable, not
# that adversarial fixture's selected target.
rm "$TMP/bin/agy"
cp "$TMP/bin/agy.real" "$TMP/bin/agy"
chmod 0755 "$TMP/bin/agy"

SECONDS=0
expect_compat_reject "continuous-stream version evidence is bounded" \
    "$VERSION_FIXTURE" version-stream 8 stream 1
stream_elapsed=$SECONDS
if (( stream_elapsed < 3 )); then
    ok "continuous-stream probe fails promptly without reading the task"
else
    bad "continuous-stream probe exceeded the byte-bound deadline (${stream_elapsed}s)"
fi

run_child_stream_probe() {
    local job="$1" child_file="$TMP/$1.pid" pgid_file="$TMP/$1.pgid"
    local parent_file="$TMP/$1.parent" ready_file="$TMP/$1.ready"
    local release_file="$TMP/$1.release" task_file="$TMP/$1.task-input"
    local worker_pid ready=1 rc calls=0 cleanup=1 artifacts=0 elapsed
    local child_pid="" probe_pgid="" probe_parent=""
    printf 'stream probe must not read this task\n' > "$task_file"
    SECONDS=0
    FAKE_CHILD_PID_FILE="$child_file" \
        FAKE_PROBE_PGID_FILE="$pgid_file" \
        FAKE_PROBE_PARENT_PID_FILE="$parent_file" \
        FAKE_PROBE_READY_FILE="$ready_file" \
        FAKE_PROBE_RELEASE_FILE="$release_file" \
        AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
        FAKE_VERSION_MODE=child-stream run_worker "$job" \
        --model gemini-3.6-flash --effort high \
        < "$task_file" > "$TMP/$job.out" 2> "$TMP/$job.err" &
    worker_pid=$!
    for (( child_wait=0; child_wait<200; child_wait++ )); do
        if [[ -e "$ready_file" && -s "$parent_file" \
                && -s "$child_file" && -s "$pgid_file" ]]; then
            ready=0
            break
        fi
        if ! kill -0 "$worker_pid" 2>/dev/null; then
            break
        fi
        sleep 0.01
    done
    if (( ready == 0 )); then
        child_pid="$(<"$child_file")"
        probe_pgid="$(<"$pgid_file")"
        probe_parent="$(<"$parent_file")"
    fi
    : > "$release_file"
    wait "$worker_pid"
    rc=$?
    elapsed=$SECONDS
    [[ ! -f "$TMP/$job.calls" ]] \
        || calls="$(wc -l < "$TMP/$job.calls" | tr -d ' ')"
    if (( ready == 0 )); then
        wait_probe_cleanup "$child_pid" "$probe_pgid"
        cleanup=$?
    fi
    if [[ -d "$TMP/logs/$job" ]]; then
        artifacts="$(find "$TMP/logs/$job" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d ' ')"
    fi
    case "$probe_parent:$probe_pgid:$child_pid" in
        *[!0-9:]*|:*|*::*) return 1 ;;
    esac
    [[ "$ready" == 0 && "$rc" == 8 && "$calls" == 1 \
        && "$elapsed" -lt 3 && "$probe_parent" != "$probe_pgid" \
        && "$probe_parent" != "$child_pid" && "$probe_pgid" != "$child_pid" \
        && "$cleanup" == 0 && "$artifacts" == 0 \
        && ! -s "$TMP/$job.out" && ! -s "$TMP/$job.worker-calls" \
        && "$(<"$TMP/$job.err")" == "model-selection: evidence-unavailable - agy version probe failed or was oversized" \
        && ! -e "$TMP/logs/$job/task.txt" \
        && ! -e "$TMP/logs/$job/selection.json" ]] \
        && selector_fixture_has_no_bytecode "$VERSION_FIXTURE"
}

if run_child_stream_probe version-child-stream; then
    ok "oversized child stream is handshake-bound, prompt, and group-clean"
else
    bad "oversized child stream handshake, bound, prompt, or group cleanup"
fi

child_stream_stress=0
for (( child_repeat=1; child_repeat<=20; child_repeat++ )); do
    if ! run_child_stream_probe "version-child-stream-stress-$child_repeat"; then
        child_stream_stress=1
        break
    fi
done
if (( child_stream_stress == 0 )); then
    ok "child-stream handshake and process-group cleanup are stable across 20 runs"
else
    bad "child-stream handshake or process-group cleanup flaked during 20 runs"
fi

for signal_case in HUP INT TERM; do
    case "$signal_case" in
        HUP) signal_exit=129; signal_slug=hup ;;
        INT) signal_exit=130; signal_slug=int ;;
        TERM) signal_exit=143; signal_slug=term ;;
    esac
    signal_job="version-signal-$signal_slug"
    signal_pid_file="$TMP/$signal_job.pid"
    signal_pgid_file="$TMP/$signal_job.pgid"
    signal_parent_file="$TMP/$signal_job.parent"
    signal_ready_file="$TMP/$signal_job.ready"
    signal_task_file="$TMP/$signal_job.task-input"
    printf 'probe signal must not read this task\n' > "$signal_task_file"
    FAKE_CHILD_PID_FILE="$signal_pid_file" \
        FAKE_PROBE_PGID_FILE="$signal_pgid_file" \
        FAKE_PROBE_PARENT_PID_FILE="$signal_parent_file" \
        FAKE_PROBE_READY_FILE="$signal_ready_file" \
        AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
        FAKE_VERSION_MODE=signal-wait run_worker "$signal_job" \
        --model gemini-3.6-flash --effort high \
        < "$signal_task_file" > "$TMP/$signal_job.out" 2> "$TMP/$signal_job.err" &
    signal_worker_pid=$!
    signal_ready=1
    for (( signal_wait=0; signal_wait<200; signal_wait++ )); do
        if [[ -e "$signal_ready_file" && -s "$signal_parent_file" \
                && -s "$signal_pid_file" && -s "$signal_pgid_file" ]]; then
            signal_ready=0
            break
        fi
        if ! kill -0 "$signal_worker_pid" 2>/dev/null; then
            break
        fi
        sleep 0.01
    done
    if (( signal_ready == 0 )); then
        signal_probe_parent="$(<"$signal_parent_file")"
        kill -s "$signal_case" "$signal_probe_parent" 2>/dev/null || true
    fi
    wait "$signal_worker_pid"
    rc=$?
    signal_calls=0
    [[ ! -f "$TMP/$signal_job.calls" ]] \
        || signal_calls="$(wc -l < "$TMP/$signal_job.calls" | tr -d ' ')"
    signal_cleanup=1
    if [[ -s "$signal_pid_file" && -s "$signal_pgid_file" ]]; then
        signal_child_pid="$(<"$signal_pid_file")"
        signal_probe_pgid="$(<"$signal_pgid_file")"
        wait_probe_cleanup "$signal_child_pid" "$signal_probe_pgid"
        signal_cleanup=$?
    fi
    signal_artifacts=0
    if [[ -d "$TMP/logs/$signal_job" ]]; then
        signal_artifacts="$(find "$TMP/logs/$signal_job" -mindepth 1 -maxdepth 1 -print | wc -l | tr -d ' ')"
    fi
    if [[ "$signal_ready" == 0 && "$rc" == "$signal_exit" && "$signal_calls" == 1 \
            && ! -s "$TMP/$signal_job.worker-calls" \
            && ! -s "$TMP/$signal_job.out" && ! -s "$TMP/$signal_job.err" \
            && ! -e "$TMP/logs/$signal_job/task.txt" \
            && ! -e "$TMP/logs/$signal_job/selection.json" \
            && "$signal_artifacts" == 0 \
            && "$signal_cleanup" == 0 ]] \
            && selector_fixture_has_no_bytecode "$VERSION_FIXTURE"; then
        ok "$signal_case interrupts the version probe with exit $signal_exit, no group, and no artifacts"
    else
        bad "$signal_case version-probe cleanup (ready $signal_ready/exit $rc/calls $signal_calls/artifacts $signal_artifacts/cleanup $signal_cleanup)"
    fi
done

NO_AGY_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
run_without_fake_agy() {
    local job="$1" path_value="$2" approval_sha; shift 2
    approval_sha="$(whole_worktree_manifest_sha "$WORKER" "$TMP/repo")" || return 64
    PATH="$path_value" \
    AGY_WORKER_MODE=accept-edits \
    AGY_WORKER_LOG_DIR="$TMP/no-agy-logs" \
    AGY_WORKER_JOB_ID="$job" \
    AGY_WORKER_MAX_ATTEMPTS=1 \
    python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WORKER" --workdir "$TMP/repo" --approve-whole-worktree "$approval_sha" "$@"
}
mkdir -p "$TMP/no-agy-logs"
chmod 0755 "$TMP/no-agy-logs"

printf 'direct PATH missing must not be read\n' | run_without_fake_agy direct-path-missing \
    "$NO_AGY_PATH" --model gemini-3.6-flash --effort high \
    > "$TMP/direct-path-missing.out" 2> "$TMP/direct-path-missing.err"
rc=$?
if [[ "$rc" == 8 && ! -s "$TMP/direct-path-missing.out" \
        && ! -e "$TMP/no-agy-logs/direct-path-missing/task.txt" ]]; then
    ok "direct selector reports missing agy as unavailable before task read"
else
    bad "direct selector missing-agy boundary (exit $rc)"
fi

mkdir -p "$TMP/nonexec-agy-bin"
printf '#!/usr/bin/env bash\n: > %q\n' "$TMP/nonexec-agy-ran" \
    > "$TMP/nonexec-agy-bin/agy"
chmod 0644 "$TMP/nonexec-agy-bin/agy"
printf 'direct nonexec must not be read\n' | run_without_fake_agy direct-path-nonexec \
    "$TMP/nonexec-agy-bin:$NO_AGY_PATH" --model gemini-3.6-flash --effort high \
    > "$TMP/direct-path-nonexec.out" 2> "$TMP/direct-path-nonexec.err"
rc=$?
if [[ "$rc" == 8 && ! -e "$TMP/nonexec-agy-ran" \
        && ! -e "$TMP/no-agy-logs/direct-path-nonexec/task.txt" ]]; then
    ok "direct selector reports non-executable agy as unavailable before task read"
else
    bad "direct selector non-executable-agy boundary (exit $rc)"
fi

mkdir -p "$TMP/broken-agy-bin"
printf '#!/definitely/missing/agy-interpreter\n' > "$TMP/broken-agy-bin/agy"
chmod +x "$TMP/broken-agy-bin/agy"
printf 'direct broken launch must not be read\n' | run_without_fake_agy direct-start-fail \
    "$TMP/broken-agy-bin:$NO_AGY_PATH" --model gemini-3.6-flash --effort high \
    > "$TMP/direct-start-fail.out" 2> "$TMP/direct-start-fail.err"
rc=$?
if [[ "$rc" == 8 && ! -e "$TMP/no-agy-logs/direct-start-fail/task.txt" ]]; then
    ok "direct selector sanitizes an agy launch failure before task read"
else
    bad "direct selector launch-failure boundary (exit $rc)"
fi

printf 'model missing agy must not read the task\n' | \
    run_without_fake_agy legacy-path-missing "$NO_AGY_PATH" --model gemini-3.6-flash-low \
    > "$TMP/legacy-path-missing.out" 2> "$TMP/legacy-path-missing.err"
rc=$?
if [[ "$rc" == 8 && ! -e "$TMP/no-agy-logs/legacy-path-missing/task.txt" \
        && ! -e "$TMP/no-agy-logs/legacy-path-missing/selection.json" ]]; then
    ok "model missing-agy fails before task intake"
else
    bad "model missing-agy preflight (exit $rc)"
fi

printf 'prefixed semantic version\n' | AGY_TEST_WORKER="$VERSION_FIXTURE/runtime/agy-worker.sh" \
    FAKE_VERSION_MODE=prefixed run_worker version-prefixed \
    --model gemini-3.6-flash --effort high \
    > "$TMP/version-prefixed.out" 2> "$TMP/version-prefixed.err"
rc=$?
if [[ "$rc" == 0 ]]; then
    assert_direct_result "documented prefixed agy version is accepted" version-prefixed \
        gemini-3.6-flash gemini-3.6-flash high cli cli 5
else
    bad "documented prefixed agy version is accepted (exit $rc)"
fi

VALID_DIRECT_RECORD="$TMP/logs/version-prefixed/selection.json"
VALID_DEFAULT_RECORD="$TMP/logs/agy-default/selection.json"
ARTIFACT_CASES="$TMP/selection-artifacts"
mkdir -p "$ARTIFACT_CASES"
python3 -B - "$VALID_DIRECT_RECORD" "$VALID_DEFAULT_RECORD" "$ARTIFACT_CASES" <<'PY'
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
PY

expect_valid_selection_record() {
    local name="$1" path="$2"
    "$SELECTOR" --validate-record "$path" > "$path.valid.out" 2> "$path.valid.err"
    local got=$?
    if [[ "$got" == 0 && ! -s "$path.valid.out" ]]; then ok "$name"; else bad "$name (exit $got)"; fi
}
expect_invalid_selection_record() {
    local name="$1" path="$2"
    "$SELECTOR" --validate-record "$path" > "$path.invalid.out" 2> "$path.invalid.err"
    local got=$?
    if [[ "$got" == 64 && ! -s "$path.invalid.out" ]]; then ok "$name"; else bad "$name (exit $got)"; fi
}
expect_valid_selection_record "runtime validator accepts a complete direct artifact" "$VALID_DIRECT_RECORD"
expect_valid_selection_record "runtime validator accepts a complete default artifact" "$VALID_DEFAULT_RECORD"
for record in "$ARTIFACT_CASES"/*.json; do
    expect_invalid_selection_record "runtime validator rejects $(basename "$record")" "$record"
done
for schema in 1 2 3 4; do
    record="$ARTIFACT_CASES/retired-$schema.json"
    before="$(shasum -a 256 "$record")"
    "$SELECTOR" --verify-record-executable "$record" > "$record.verify.out" 2> "$record.verify.err"
    if [[ $? == 64 && ! -s "$record.verify.out" && "$before" == "$(shasum -a 256 "$record")" ]] \
            && grep -Fq 'release that created it' "$record.verify.err"; then
        ok "retired selection $schema rejects launch authorization without rewriting history"
    else bad "retired selection $schema launch boundary"; fi
done

RETRY_FIXTURE="$TMP/selector-retry-freeze"
make_selector_fixture "$RETRY_FIXTURE" clean
printf 'automatic retry is forbidden\n' | \
    FAKE_DISPATCH_COUNT_FILE="$TMP/retry-freeze.dispatch-count" \
    FAKE_FAIL_FIRST=1 \
    AGY_TEST_WORKER="$RETRY_FIXTURE/runtime/agy-worker.sh" \
    run_worker retry-freeze \
        --model gemini-3.6-flash --effort high \
        > "$TMP/retry-freeze.out" 2> "$TMP/retry-freeze.err"
rc=$?
if [[ "$rc" == 5 ]] && python3 - \
        "$TMP/logs/retry-freeze/selection.json" \
        "$TMP/retry-freeze.calls" "$TMP/retry-freeze.worker-calls" <<'PY'
import hashlib
import json
import sys

selection_path, calls_path, workers_path = sys.argv[1:]
selection = json.load(open(selection_path, encoding="utf-8"))
assert selection["resolved_agy_model"] == "gemini-3.6-flash"
assert selection["user_effort"] == "high"
calls = open(calls_path).read().splitlines()
assert calls == ["version", "help", "version", "help", "worker"]
assert calls.count("worker") == 1
assert open(workers_path).read().splitlines() == ["worker"]
PY
then
    ok "failure never starts an automatic fresh retry and preserves frozen selection"
else
    bad "failure must not start an automatic fresh retry"
fi

WRAPPER_FIXTURE="$TMP/root-wrapper"
mkdir -p "$WRAPPER_FIXTURE/skills"
cp "$ROOT/agy-worker.sh" "$WRAPPER_FIXTURE/agy-worker.sh"
cp -R "$ROOT/skills/agy-worker" "$WRAPPER_FIXTURE/skills/agy-worker"
chmod +x "$WRAPPER_FIXTURE/agy-worker.sh"
WRAPPER_REAL="$(cd "$WRAPPER_FIXTURE" && pwd -P)"
EXPECTED_CHECKOUT_SHA="$(python3 -I -S -B -c 'import hashlib, sys; print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())' "$WRAPPER_REAL")"
WRAPPER_APPROVAL_SHA="$(whole_worktree_manifest_sha "$WRAPPER_FIXTURE/agy-worker.sh" "$TMP/repo")"

TEST_XDG="$TMP/isolated-xdg-state"
TEST_HOME="$TMP/isolated-home"
mkdir -p "$TEST_XDG" "$TEST_HOME"

wrapper_pass=1

# 1. Unset AGY_WORKER_LOG_DIR uses XDG_STATE_HOME
(
    unset AGY_WORKER_LOG_DIR
    printf 'unset log dir\n' | PATH="$TMP/bin:$PATH" \
        XDG_STATE_HOME="$TEST_XDG" HOME="$TEST_HOME" \
        AGY_WORKER_JOB_ID=unset-log AGY_WORKER_MODE=accept-edits \
        FAKE_MODEL_FILE="$TMP/unset-log.model" \
        FAKE_PROMPT_FILE="$TMP/unset-log.prompt" \
        FAKE_DIRS_FILE="$TMP/unset-log.dirs" \
        FAKE_ARGV_FILE="$TMP/unset-log.argv" \
        FAKE_STAGE_RESULT_FILE="$TMP/unset-log.stage-result" \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WRAPPER_FIXTURE/agy-worker.sh" --workdir "$TMP/repo" \
        --approve-whole-worktree "$WRAPPER_APPROVAL_SHA" \
        --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        > "$TMP/unset-log.out" 2> "$TMP/unset-log.err"
)
rc=$?
if [[ "$rc" != "0" ]] \
        || [[ ! -f "$TEST_XDG/agy-worker/checkouts/$EXPECTED_CHECKOUT_SHA/logs/unset-log/task.txt" ]] \
        || [[ -e "$WRAPPER_FIXTURE/logs" ]] \
        || [[ -e "$WRAPPER_FIXTURE/skills/agy-worker/runtime/logs/unset-log" ]]; then
    wrapper_pass=0
fi

# 2. Empty AGY_WORKER_LOG_DIR with unset XDG_STATE_HOME falls back to HOME/.local/state
(
    unset XDG_STATE_HOME
    printf 'empty log override\n' | PATH="$TMP/bin:$PATH" \
        HOME="$TEST_HOME" AGY_WORKER_LOG_DIR= \
        AGY_WORKER_JOB_ID=empty-log-override AGY_WORKER_MODE=accept-edits \
        FAKE_MODEL_FILE="$TMP/empty-log.model" \
        FAKE_PROMPT_FILE="$TMP/empty-log.prompt" \
        FAKE_DIRS_FILE="$TMP/empty-log.dirs" \
        FAKE_ARGV_FILE="$TMP/empty-log.argv" \
        FAKE_STAGE_RESULT_FILE="$TMP/empty-log.stage-result" \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WRAPPER_FIXTURE/agy-worker.sh" --workdir "$TMP/repo" \
        --approve-whole-worktree "$WRAPPER_APPROVAL_SHA" \
        --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        > "$TMP/empty-log.out" 2> "$TMP/empty-log.err"
)
rc=$?
if [[ "$rc" != "0" ]] \
        || [[ ! -f "$TEST_HOME/.local/state/agy-worker/checkouts/$EXPECTED_CHECKOUT_SHA/logs/empty-log-override/task.txt" ]]; then
    wrapper_pass=0
fi

# 3. Deterministic lifecycle reuse across commands (status uses same derived log root)
(
    unset XDG_STATE_HOME
    PATH="$TMP/bin:$PATH" HOME="$TEST_HOME" AGY_WORKER_LOG_DIR= \
        "$WRAPPER_FIXTURE/agy-worker.sh" status --job-id empty-log-override --format json \
        > "$TMP/empty-log-status.out" 2> "$TMP/empty-log-status.err"
)
rc=$?
if [[ "$rc" != "0" ]] || ! grep -Fq '"job_id":"empty-log-override"' "$TMP/empty-log-status.out"; then
    wrapper_pass=0
fi

# 4. Actionable error when neither XDG_STATE_HOME nor HOME is safe
(
    unset AGY_WORKER_LOG_DIR
    printf 'unsafe root\n' | PATH="$TMP/bin:$PATH" \
        XDG_STATE_HOME="relative/path" HOME="" \
        AGY_WORKER_JOB_ID=unsafe-root AGY_WORKER_MODE=accept-edits \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WRAPPER_FIXTURE/agy-worker.sh" --workdir "$TMP/repo" \
        --approve-whole-worktree "$WRAPPER_APPROVAL_SHA" \
        --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        > "$TMP/unsafe-root.out" 2> "$TMP/unsafe-root.err"
)
rc=$?
if [[ "$rc" != "64" ]] \
        || ! grep -Fq 'unable to derive a safe state root; set an explicit external AGY_WORKER_LOG_DIR' "$TMP/unsafe-root.err" \
        || [[ -e "$WRAPPER_FIXTURE/logs/unsafe-root" ]]; then
    wrapper_pass=0
fi

# 5. Explicit external AGY_WORKER_LOG_DIR remains unchanged
EXPLICIT_EXTERNAL="$TMP/explicit-external-logs"
mkdir -p "$EXPLICIT_EXTERNAL"
(
    printf 'explicit log override\n' | PATH="$TMP/bin:$PATH" \
        AGY_WORKER_LOG_DIR="$EXPLICIT_EXTERNAL" AGY_WORKER_JOB_ID=explicit-log AGY_WORKER_MODE=accept-edits \
        FAKE_MODEL_FILE="$TMP/explicit-log.model" \
        FAKE_PROMPT_FILE="$TMP/explicit-log.prompt" \
        FAKE_DIRS_FILE="$TMP/explicit-log.dirs" \
        FAKE_ARGV_FILE="$TMP/explicit-log.argv" \
        FAKE_STAGE_RESULT_FILE="$TMP/explicit-log.stage-result" \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WRAPPER_FIXTURE/agy-worker.sh" --workdir "$TMP/repo" \
        --approve-whole-worktree "$WRAPPER_APPROVAL_SHA" \
        --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        > "$TMP/explicit-log.out" 2> "$TMP/explicit-log.err"
)
rc=$?
if [[ "$rc" != "0" ]] || [[ ! -f "$EXPLICIT_EXTERNAL/explicit-log/task.txt" ]]; then
    wrapper_pass=0
fi

# 6. Project workflow rejects existing and prospective log roots equal to or inside workdir.
PROJECT_DIR="$TMP/project-test-worktree"
mkdir -p "$PROJECT_DIR/.git" "$PROJECT_DIR/logs"
touch "$PROJECT_DIR/.git/HEAD"

for test_case in equal child relative missing-child symlink-log symlink-worktree; do
    missing_root=""
    case "$test_case" in
        equal)
            test_log="$PROJECT_DIR"; test_work="$PROJECT_DIR"
            expected_job="$PROJECT_DIR/proj-equal" ;;
        child)
            test_log="$PROJECT_DIR/logs"; test_work="$PROJECT_DIR"
            expected_job="$PROJECT_DIR/logs/proj-child" ;;
        relative)
            test_log="./logs"; test_work="$PROJECT_DIR"
            expected_job="$PROJECT_DIR/logs/proj-relative" ;;
        missing-child)
            test_log="$PROJECT_DIR/new/logs"; test_work="$PROJECT_DIR"
            expected_job="$PROJECT_DIR/new/logs/proj-missing-child"
            missing_root="$PROJECT_DIR/new" ;;
        symlink-log)
            ln -s "$PROJECT_DIR/logs" "$TMP/symlink-proj-log"
            test_log="$TMP/symlink-proj-log"; test_work="$PROJECT_DIR"
            expected_job="$PROJECT_DIR/logs/proj-symlink-log" ;;
        symlink-worktree)
            ln -s "$PROJECT_DIR" "$TMP/symlink-proj-work"
            test_log="$PROJECT_DIR/logs"; test_work="$TMP/symlink-proj-work"
            expected_job="$PROJECT_DIR/logs/proj-symlink-worktree" ;;
    esac
    (
        cd "$PROJECT_DIR"
        printf 'project reject\n' | PATH="$TMP/bin:$PATH" \
            AGY_WORKER_LOG_DIR="$test_log" AGY_WORKER_JOB_ID="proj-$test_case" \
            FAKE_MODEL_FILE="$TMP/proj-$test_case.model" \
            FAKE_PROMPT_FILE="$TMP/proj-$test_case.prompt" \
            FAKE_DIRS_FILE="$TMP/proj-$test_case.dirs" \
            FAKE_ARGV_FILE="$TMP/proj-$test_case.argv" \
            FAKE_STAGE_RESULT_FILE="$TMP/proj-$test_case.stage-result" \
            FAKE_CALLED_FILE="$TMP/proj-$test_case.called" \
            "$WRAPPER_FIXTURE/agy-worker.sh" --workflow project --workdir "$test_work" \
            > "$TMP/proj-$test_case.out" 2> "$TMP/proj-$test_case.err"
    )
    rc=$?
    expected_msg="project log root cannot be inside the target workdir"
    if [[ "$rc" != "64" ]] \
            || ! grep -Fq "$expected_msg" "$TMP/proj-$test_case.err" \
            || [[ -e "$TMP/proj-$test_case.model" ]] \
            || [[ -e "$TMP/proj-$test_case.prompt" ]] \
            || [[ -e "$TMP/proj-$test_case.dirs" ]] \
            || [[ -e "$TMP/proj-$test_case.argv" ]] \
            || [[ -e "$TMP/proj-$test_case.stage-result" ]] \
            || [[ -e "$expected_job" ]] \
            || [[ -e "$expected_job/task.txt" ]] \
            || [[ -e "$expected_job/dispatch-state.json" ]] \
            || [[ -n "$missing_root" && -e "$missing_root" ]] \
            || [[ -e "$TMP/proj-$test_case.called" ]]; then
        wrapper_pass=0
    fi
done

if (( wrapper_pass )); then
    ok "root wrapper derives deterministic external state root and rejects project log root in worktree"
else
    bad "root wrapper derives deterministic external state root and rejects project log root in worktree"
fi

PRIVATE_LOG_022="$TMP/existing-log-022"
mkdir -p "$PRIVATE_LOG_022"
chmod 0755 "$PRIVATE_LOG_022"
(
    umask 022
    printf 'private artifacts under umask 022\n' | \
        AGY_TEST_LOG_DIR="$PRIVATE_LOG_022" run_worker private-022
) > "$TMP/private-022.out" 2>/dev/null
rc=$?
if [[ "$rc" == "0" ]] \
        && mode_is "$PRIVATE_LOG_022" 0755 \
        && log_root_is_acceptable "$PRIVATE_LOG_022" \
        && private_tree_is_private "$PRIVATE_LOG_022/private-022"; then
    ok "dispatcher keeps a new job private under umask 022 and a traversable custom log root"
else
    bad "dispatcher keeps a new job private under umask 022 and a traversable custom log root"
fi

PRIVATE_LOG_000="$TMP/existing-log-000"
mkdir -p "$PRIVATE_LOG_000"
chmod 0755 "$PRIVATE_LOG_000"
(
    umask 000
    printf 'private artifacts under umask 000\n' | \
        AGY_TEST_LOG_DIR="$PRIVATE_LOG_000" run_worker private-000
) > "$TMP/private-000.out" 2>/dev/null
rc=$?
if [[ "$rc" == "0" ]] \
        && mode_is "$PRIVATE_LOG_000" 0755 \
        && log_root_is_acceptable "$PRIVATE_LOG_000" \
        && mode_is "$TMP/private-000.model" 0666 \
        && private_tree_is_private "$PRIVATE_LOG_000/private-000"; then
    ok "dispatcher keeps artifacts private under umask 000 without changing the agy child umask"
else
    bad "dispatcher keeps artifacts private under umask 000 without changing the agy child umask"
fi

MISSING_LOG_ROOT="$TMP/missing-log-root"
(
    umask 000
    printf 'create a private log root\n' | \
        AGY_TEST_LOG_DIR="$MISSING_LOG_ROOT" run_worker missing-log-root
) > "$TMP/missing-log-root.out" 2>/dev/null
rc=$?
if [[ "$rc" == "0" ]] \
        && mode_is "$MISSING_LOG_ROOT" 0700 \
        && log_root_is_acceptable "$MISSING_LOG_ROOT" \
        && private_tree_is_private "$MISSING_LOG_ROOT/missing-log-root"; then
    ok "a missing custom log root is created owner-only under caller umask 000"
else
    bad "a missing custom log root is created owner-only under caller umask 000"
fi

invalid_root_index=0
for invalid_root_mode in 0777 0775; do
    invalid_root_index=$((invalid_root_index+1))
    invalid_root="$TMP/invalid-root-$invalid_root_index"
    invalid_job="invalid-root-$invalid_root_index"
    mkdir -p "$invalid_root"
    chmod "$invalid_root_mode" "$invalid_root"
    printf 'root sentinel %s\n' "$invalid_root_mode" > "$invalid_root/sentinel"
    printf 'must reject writable log root\n' | \
        AGY_TEST_LOG_DIR="$invalid_root" run_worker "$invalid_job" \
        > "$TMP/$invalid_job.out" 2>/dev/null
    rc=$?
    if [[ "$rc" == "64" ]] \
            && [[ "$(<"$invalid_root/sentinel")" == "root sentinel $invalid_root_mode" ]] \
            && [[ ! -e "$invalid_root/$invalid_job" ]] \
            && [[ ! -e "$TMP/$invalid_job.called" ]]; then
        ok "mode $invalid_root_mode log root is rejected before prompt staging or agy"
    else
        bad "mode $invalid_root_mode log root is rejected before prompt staging or agy"
    fi
done

SYMLINK_LOG_TARGET="$TMP/symlink-log-target"
SYMLINK_LOG_ROOT="$TMP/symlink-log-root"
mkdir -p "$SYMLINK_LOG_TARGET"
chmod 0755 "$SYMLINK_LOG_TARGET"
printf 'symlink root sentinel\n' > "$SYMLINK_LOG_TARGET/sentinel"
ln -s "$SYMLINK_LOG_TARGET" "$SYMLINK_LOG_ROOT"
printf 'must reject symlink log root\n' | \
    AGY_TEST_LOG_DIR="$SYMLINK_LOG_ROOT" run_worker symlink-log-root \
    > "$TMP/symlink-log-root.out" 2>/dev/null
rc=$?
if [[ "$rc" == "64" ]] \
        && [[ "$(<"$SYMLINK_LOG_TARGET/sentinel")" == "symlink root sentinel" ]] \
        && [[ ! -e "$SYMLINK_LOG_TARGET/symlink-log-root" ]] \
        && [[ ! -e "$TMP/symlink-log-root.called" ]]; then
    ok "symlink log root is rejected before prompt staging or agy"
else
    bad "symlink log root is rejected before prompt staging or agy"
fi

WEAK_ROOT_POLICY="$TMP/weak-root-policy"
mkdir -p "$WEAK_ROOT_POLICY"
cp -R "$ROOT/skills/agy-worker" "$WEAK_ROOT_POLICY/agy-worker"
python3 - "$WEAK_ROOT_POLICY/agy-worker/runtime/agy-worker.sh" <<'PY'
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    source = handle.read()
old = 'if ! validate_log_root "$LOG_DIR"; then'
new = 'if ! true; then  # TEST MUTATION: final log-root policy bypassed'
if source.count(old) != 1:
    raise SystemExit("expected exactly one final log-root policy call")
with open(path, "w", encoding="utf-8") as handle:
    handle.write(source.replace(old, new, 1))
PY
WEAK_ROOT_POLICY_LOG="$TMP/weak-root-policy-log"
mkdir -p "$WEAK_ROOT_POLICY_LOG"
chmod 0777 "$WEAK_ROOT_POLICY_LOG"
printf 'mutation must be caught\n' | \
    AGY_TEST_WORKER="$WEAK_ROOT_POLICY/agy-worker/runtime/agy-worker.sh" \
    AGY_TEST_LOG_DIR="$WEAK_ROOT_POLICY_LOG" run_worker weak-root-policy \
    > "$TMP/weak-root-policy.out" 2>/dev/null
rc=$?
if [[ "$rc" == "0" ]] \
        && [[ -e "$TMP/weak-root-policy.called" ]] \
        && private_tree_is_private "$WEAK_ROOT_POLICY_LOG/weak-root-policy" \
        && ! log_root_is_acceptable "$WEAK_ROOT_POLICY_LOG" 2>/dev/null; then
    ok "log-root acceptance rejects a runtime with final-root validation bypassed"
else
    bad "log-root acceptance rejects a runtime with final-root validation bypassed"
fi

WEAK_UMASK_ROOT="$TMP/weak-umask"
mkdir -p "$WEAK_UMASK_ROOT"
cp -R "$ROOT/skills/agy-worker" "$WEAK_UMASK_ROOT/agy-worker"
python3 - "$WEAK_UMASK_ROOT/agy-worker/runtime/scripts/agy_dispatch.py" <<'PY'
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    source = handle.read()
old = 'def _ensure_new_private(path: Path) -> int:\n    return os.open(\n'
new = 'def _ensure_new_private(path: Path) -> int:\n    os.umask(0)  # TEST MUTATION: private artifact creation weakened.\n    return os.open(\n'
if source.count(old) != 1:
    raise SystemExit("expected exactly one supervisor private-artifact block")
source = source.replace(old, new, 1)
old = '        0o600,\n    )\n\n\ndef _stage('
new = '        0o666,\n    )\n\n\ndef _stage('
if source.count(old) != 1:
    raise SystemExit("expected exactly one supervisor artifact mode")
with open(path, "w", encoding="utf-8") as handle:
    handle.write(source.replace(old, new, 1))
PY
WEAK_UMASK_LOG="$TMP/weak-umask-log"
mkdir -p "$WEAK_UMASK_LOG"
chmod 0755 "$WEAK_UMASK_LOG"
(
    umask 000
    printf 'mutation must be caught\n' | \
        AGY_TEST_WORKER="$WEAK_UMASK_ROOT/agy-worker/runtime/agy-worker.sh" \
        AGY_TEST_LOG_DIR="$WEAK_UMASK_LOG" run_worker weak-umask
) > "$TMP/weak-umask.out" 2>/dev/null
rc=$?
if [[ "$rc" != "0" && ! -s "$TMP/weak-umask.out" ]] \
        && ! private_tree_is_private "$WEAK_UMASK_LOG/weak-umask" 2>/dev/null; then
    ok "supervisor fails closed when a mutation weakens private creation"
else
    bad "privacy acceptance rejects a runtime with the private creation mask removed"
fi

COLLISION_LOG="$TMP/collision-log"
mkdir -p "$COLLISION_LOG/existing-dir" "$TMP/symlink-target"
chmod 0755 "$COLLISION_LOG"
printf 'directory sentinel\n' > "$COLLISION_LOG/existing-dir/sentinel"
printf 'file sentinel\n' > "$COLLISION_LOG/existing-file"
printf 'symlink sentinel\n' > "$TMP/symlink-target/sentinel"
ln -s "$TMP/symlink-target" "$COLLISION_LOG/existing-link"

printf 'must reject existing directory\n' | \
    AGY_TEST_LOG_DIR="$COLLISION_LOG" run_worker existing-dir \
    > "$TMP/existing-dir.out" 2>/dev/null
rc=$?
if [[ "$rc" == "64" ]] \
        && [[ "$(<"$COLLISION_LOG/existing-dir/sentinel")" == "directory sentinel" ]] \
        && [[ ! -e "$TMP/existing-dir.called" ]]; then
    ok "pre-existing job directory is rejected before invoking agy or touching its sentinel"
else
    bad "pre-existing job directory is rejected before invoking agy or touching its sentinel"
fi

printf 'must reject existing file\n' | \
    AGY_TEST_LOG_DIR="$COLLISION_LOG" run_worker existing-file \
    > "$TMP/existing-file.out" 2>/dev/null
rc=$?
if [[ "$rc" == "64" ]] \
        && [[ "$(<"$COLLISION_LOG/existing-file")" == "file sentinel" ]] \
        && [[ ! -e "$TMP/existing-file.called" ]]; then
    ok "pre-existing job file is rejected before invoking agy or touching its sentinel"
else
    bad "pre-existing job file is rejected before invoking agy or touching its sentinel"
fi

printf 'must reject existing symlink\n' | \
    AGY_TEST_LOG_DIR="$COLLISION_LOG" run_worker existing-link \
    > "$TMP/existing-link.out" 2>/dev/null
rc=$?
if [[ "$rc" == "64" ]] \
        && [[ "$(<"$TMP/symlink-target/sentinel")" == "symlink sentinel" ]] \
        && [[ ! -e "$TMP/existing-link.called" ]]; then
    ok "pre-existing job symlink is rejected before invoking agy or touching its target"
else
    bad "pre-existing job symlink is rejected before invoking agy or touching its target"
fi

printf 'broad audit is a usable default plan\n' | (
    unset AGY_WORKER_MODE
    PATH="$TMP/bin:$PATH" AGY_WORKER_LOG_DIR="$TMP/logs" \
        AGY_WORKER_JOB_ID=generic-plan \
        FAKE_MODEL_FILE="$TMP/generic-plan.model" \
        FAKE_PROMPT_FILE="$TMP/generic-plan.prompt" \
        FAKE_DIRS_FILE="$TMP/generic-plan.dirs" \
        FAKE_ARGV_FILE="$TMP/generic-plan.argv" \
        FAKE_STAGE_RESULT_FILE="$TMP/generic-plan.stage-result" \
        FAKE_CALLED_FILE="$TMP/generic-plan.called" \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WORKER" --workdir "$TMP/repo" \
            --approve-whole-worktree "$(whole_worktree_manifest_sha "$WORKER" "$TMP/repo")" \
            --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE --provider-env FAKE_CALLED_FILE
) > "$TMP/generic-plan.out" 2> "$TMP/generic-plan.err"
rc=$?
generic_plan_root_prompt="$TMP/generic-plan.prompt"
generic_plan_prompt="$generic_plan_root_prompt"
if [[ -f "$TMP/logs/generic-plan/staged/full-prompt.txt" ]]; then
    generic_plan_prompt="$TMP/logs/generic-plan/staged/full-prompt.txt"
fi
generic_plan_root="$(cd "$TMP/repo" && pwd -P)"
if [[ "$rc" == "0" ]] \
        && [[ -s "$TMP/generic-plan.out" ]] \
        && [[ -e "$TMP/generic-plan.called" ]] \
        && [[ -d "$TMP/logs/generic-plan" ]] \
        && grep -Fq 'Use file tools to inspect the approved workspace only; do not edit files.' \
            "$generic_plan_prompt" \
        && ! grep -Fq 'Use file tools to inspect and edit the approved workspace.' \
            "$generic_plan_prompt" \
        && grep -Fq 'This job runs in a normal AGY session with same-user filesystem and network authority' \
            "$generic_plan_prompt" \
        && grep -Fq "$generic_plan_root" "$generic_plan_root_prompt"; then
    ok "generic plan dispatches and receives the read-only file-tool preamble"
else
    bad "generic plan should remain usable"
fi

mkdir -p "$TMP/outside"
printf 'outside root\n' | run_worker outside --add-dir "$TMP/outside" > "$TMP/outside.out" 2>/dev/null
rc=$?
expect_exit "--add-dir outside audited workdir is rejected" 64 "$rc"

operand_index=0
for option in --workdir --mode --model --add-dir; do
    operand_index=$((operand_index+1))
    printf 'missing operand\n' | run_worker "missing-$operand_index" "$option" > "$TMP/missing-$operand_index.out" 2>/dev/null
    rc=$?
    expect_exit "$option missing operand is controlled" 64 "$rc"
done

python3 -c 'print("OVERSIZED_TASK_MARKER" + "x" * 100500)' > "$TMP/large-task.txt"
FAKE_TRY_STAGE_WRITE=1 run_worker oversized --mode accept-edits \
    --add-dir "$TMP/repo" < "$TMP/large-task.txt" > "$TMP/oversized.out" 2>/dev/null
rc=$?
expect_exit "oversized job produces an envelope" 0 "$rc"
if grep -q 'OVERSIZED_TASK_MARKER' "$TMP/logs/oversized/full-prompt.txt" \
        && grep -q 'OUTPUT CONTRACT — non-negotiable:' "$TMP/logs/oversized/full-prompt.txt"; then
    ok "oversized staged prompt preserves task and output contract"
else
    bad "oversized staged prompt preserves task and output contract"
fi
if grep -Fxq "$LOGS_REAL/oversized/staged" "$TMP/oversized.dirs" \
        && ! grep -Fxq "$LOGS_REAL" "$TMP/oversized.dirs"; then
    ok "oversized job grants only its staged prompt directory"
else
    bad "oversized job grants only its staged prompt directory"
fi
if grep -Fq "$LOGS_REAL/oversized/staged/full-prompt.txt" "$TMP/oversized.prompt"; then
    ok "oversized dispatch points agy at the complete staged prompt"
else
    bad "oversized dispatch points agy at the complete staged prompt"
fi
if [[ "$(<"$TMP/oversized.stage-result")" == "blocked" ]]; then
    ok "oversized staged prompt is read-only during agy execution"
else
    bad "oversized staged prompt is read-only during agy execution"
fi
if private_tree_is_private "$TMP/logs/oversized"; then
    ok "oversized staged prompt is private again after agy returns"
else
    bad "oversized staged prompt is private again after agy returns"
fi
expect_print_last "oversized prompt keeps --print and its value last" "$TMP/oversized.argv"

WEAK_RESTORE_ROOT="$TMP/weak-restore"
mkdir -p "$WEAK_RESTORE_ROOT"
cp -R "$ROOT/skills/agy-worker" "$WEAK_RESTORE_ROOT/agy-worker"
python3 - "$WEAK_RESTORE_ROOT/agy-worker/runtime/scripts/agy_dispatch.py" <<'PY'
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    source = handle.read()
replacements = (
    (
        'directory.chmod(0o555 if readonly else 0o700)',
        'directory.chmod(0o555 if readonly else 0o755)',
    ),
    (
        'source.chmod(0o444 if readonly else 0o600)',
        'source.chmod(0o444 if readonly else 0o644)',
    ),
)
for old, new in replacements:
    if source.count(old) != 1:
        raise SystemExit(f"expected exactly one restore statement: {old}")
    source = source.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as handle:
    handle.write(source)
PY
WEAK_RESTORE_LOG="$TMP/weak-restore-log"
mkdir -p "$WEAK_RESTORE_LOG"
chmod 0755 "$WEAK_RESTORE_LOG"
AGY_TEST_WORKER="$WEAK_RESTORE_ROOT/agy-worker/runtime/agy-worker.sh" \
    AGY_TEST_LOG_DIR="$WEAK_RESTORE_LOG" \
    run_worker weak-restore < "$TMP/large-task.txt" \
    > "$TMP/weak-restore.out" 2>/dev/null
rc=$?
if [[ "$rc" == "20" && ! -s "$TMP/weak-restore.out" ]] \
        && ! private_tree_is_private "$WEAK_RESTORE_LOG/weak-restore" 2>/dev/null; then
    ok "supervisor fails closed when a mutation restores staged artifacts publicly"
else
    bad "privacy acceptance rejects a runtime that restores staged artifacts publicly"
fi

FAKE_EXIT_CODE=23 AGY_WORKER_MAX_ATTEMPTS=1 \
    run_worker staged-early-exit < "$TMP/large-task.txt" \
    > "$TMP/staged-early-exit.out" 2>/dev/null
rc=$?
if [[ "$rc" == "5" ]] && private_tree_is_private "$TMP/logs/staged-early-exit"; then
    ok "failed oversized child restores staged artifacts before the wrapper exits"
else
    bad "failed oversized child restores staged artifacts before the wrapper exits"
fi

signal_index=0
for signal_name in HUP INT TERM; do
    signal_index=$((signal_index+1))
    case "$signal_name" in
        HUP) expected_signal_rc=129 ;;
        INT) expected_signal_rc=130 ;;
        TERM) expected_signal_rc=143 ;;
    esac
    signal_job="staged-signal-$signal_index"
    FAKE_SIGNAL_PARENT="$signal_name" FAKE_EXIT_CODE=23 AGY_WORKER_MAX_ATTEMPTS=1 \
        run_worker "$signal_job" < "$TMP/large-task.txt" \
        > "$TMP/$signal_job.out" 2>/dev/null
    rc=$?
    if [[ "$rc" == "$expected_signal_rc" ]] \
            && private_tree_is_private "$TMP/logs/$signal_job"; then
        ok "$signal_name restores staged artifacts and preserves signal exit semantics"
    else
        bad "$signal_name restores staged artifacts and preserves signal exit semantics"
    fi
done

printf 'terminal failure\n' | PATH="$TMP/bin:$PATH" \
    AGY_WORKER_LOG_DIR="$TMP/logs" AGY_WORKER_JOB_ID=terminal \
    AGY_WORKER_MODE=accept-edits AGY_WORKER_MAX_ATTEMPTS=1 FAKE_AGY_STATUS=FAILED \
    FAKE_MODEL_FILE="$TMP/terminal.model" FAKE_PROMPT_FILE="$TMP/terminal.prompt" \
    FAKE_DIRS_FILE="$TMP/terminal.dirs" \
    FAKE_ARGV_FILE="$TMP/terminal.argv" FAKE_STAGE_RESULT_FILE="$TMP/terminal.stage-result" \
    python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WORKER" --workdir "$TMP/repo" --approve-whole-worktree "$(whole_worktree_manifest_sha "$WORKER" "$TMP/repo")" --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        --provider-env FAKE_AGY_STATUS > "$TMP/terminal.out" 2>/dev/null
rc=$?
expect_exit "non-success terminal status fails closed" 4 "$rc"

printf 'bad envelope\n' | PATH="$TMP/bin:$PATH" \
    AGY_WORKER_LOG_DIR="$TMP/logs" AGY_WORKER_JOB_ID=bad-envelope \
    AGY_WORKER_MODE=accept-edits AGY_WORKER_MAX_ATTEMPTS=1 FAKE_BAD_ENVELOPE=1 \
    FAKE_MODEL_FILE="$TMP/bad.model" FAKE_PROMPT_FILE="$TMP/bad.prompt" \
    FAKE_DIRS_FILE="$TMP/bad.dirs" \
    FAKE_ARGV_FILE="$TMP/bad.argv" FAKE_STAGE_RESULT_FILE="$TMP/bad.stage-result" \
    python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WORKER" --workdir "$TMP/repo" --approve-whole-worktree "$(whole_worktree_manifest_sha "$WORKER" "$TMP/repo")" --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE --provider-env FAKE_STAGE_RESULT_FILE \
        --provider-env FAKE_BAD_ENVELOPE > "$TMP/bad.out" 2>/dev/null
rc=$?
expect_exit "dispatcher independently rejects schema-invalid output" 4 "$rc"

echo
echo "progress-aware local dispatch lifecycle tests:"

status_sha() {
    python3 - "$1" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["state_sha256"])
PY
}
status_field() {
    python3 - "$1" "$2" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])
PY
}
wait_terminal() {
    local job="$1" state_file="$2" next_file index sha status
    next_file="$state_file.next"
    for (( index=0; index<40; index++ )); do
        status="$(status_field "$state_file" status)"
        case "$status" in succeeded|failed|cancelled|orphaned) return 0 ;; esac
        sha="$(status_sha "$state_file")"
        control_worker wait "$job" --after-state-sha "$sha" --timeout 1s > "$next_file" || return 1
        mv "$next_file" "$state_file"
    done
    return 1
}
control_worker() {
    local action="$1" job="$2"; shift 2
    PATH="$TMP/bin:$PATH" AGY_WORKER_LOG_DIR="$TMP/logs" \
        FAKE_MODEL_FILE="$TMP/$job.model" FAKE_PROMPT_FILE="$TMP/$job.prompt" \
        FAKE_DIRS_FILE="$TMP/$job.dirs" FAKE_ARGV_FILE="$TMP/$job.argv" \
        FAKE_STAGE_RESULT_FILE="$TMP/$job.stage-result" \
        FAKE_CALLS_FILE="$TMP/$job.calls" FAKE_WORKER_CALLS_FILE="$TMP/$job.worker-calls" \
    FAKE_DISPATCH_MODE="${FAKE_DISPATCH_MODE:-result}" \
        FAKE_HEARTBEAT_COUNT="${FAKE_HEARTBEAT_COUNT:-8}" \
        FAKE_HEARTBEAT_DELAY="${FAKE_HEARTBEAT_DELAY:-0.10}" \
        FAKE_HEARTBEAT_BARRIER_READY="${FAKE_HEARTBEAT_BARRIER_READY:-}" \
        FAKE_HEARTBEAT_BARRIER_RELEASE="${FAKE_HEARTBEAT_BARRIER_RELEASE:-}" \
        FAKE_HEARTBEAT_AFTER_FIRST_READY="${FAKE_HEARTBEAT_AFTER_FIRST_READY:-}" \
        FAKE_HEARTBEAT_AFTER_FIRST_RELEASE="${FAKE_HEARTBEAT_AFTER_FIRST_RELEASE:-}" \
        FAKE_WORKER_VERIFIED="${FAKE_WORKER_VERIFIED:-0}" \
        "$WORKER" "$action" --job-id "$job" "$@"
}
start_worker() {
    local fake_provider_env_args=()
    local fake_provider_env_name
    for fake_provider_env_name in \
        FAKE_AGY_STATUS FAKE_ARGV_FILE FAKE_BAD_ENVELOPE FAKE_CALLED_FILE \
        FAKE_CALLS_FILE FAKE_CHILD_PID_FILE FAKE_DIRS_FILE FAKE_DISPATCH_COUNT_FILE \
        FAKE_DISPATCH_MODE FAKE_ENV_OBSERVED_FILE FAKE_HOME_OBSERVED_FILE FAKE_ERROR_LINE \
        FAKE_DELETE_FROM_BOUND_ROOT FAKE_EDIT_CONTENT FAKE_EDIT_FROM_BOUND_ROOT \
        FAKE_EXECUTABLE_SYMLINK_TARGET FAKE_EXIT_CODE FAKE_FAIL_FIRST \
        FAKE_HEARTBEAT_AFTER_FIRST_READY FAKE_HEARTBEAT_AFTER_FIRST_RELEASE \
        FAKE_HEARTBEAT_BARRIER_READY FAKE_HEARTBEAT_BARRIER_RELEASE \
        FAKE_HEARTBEAT_COUNT FAKE_HEARTBEAT_DELAY FAKE_HELP_MODE FAKE_MODEL_FILE \
        FAKE_MUTATE_EXECUTABLE FAKE_MUTATE_EXECUTABLE_MODE \
        FAKE_MUTATE_EXECUTABLE_PARENT FAKE_MUTATE_EXECUTABLE_SAME_LENGTH \
        FAKE_MUTATE_PROJECT_MARKER FAKE_MUTATION_MARKER \
        FAKE_MUTATE_WORKTREE_PATH \
        FAKE_PROBE_PARENT_PID_FILE FAKE_PROBE_PGID_FILE FAKE_PROBE_READY_FILE \
        FAKE_PROBE_RELEASE_FILE FAKE_PROMPT_FILE FAKE_QUOTA_ERROR \
        FAKE_PROVIDER_CREATE_PATH \
        FAKE_REPLACE_EXECUTABLE_SYMLINK FAKE_SIDE_EFFECT_FILE FAKE_SIGNAL_PARENT \
        FAKE_SPARSE_PROJECT_MARKER FAKE_STAGE_RESULT_FILE FAKE_TRY_STAGE_WRITE \
        FAKE_UTF8_SUMMARY FAKE_VERSION_MODE FAKE_WARNING_LINE \
        FAKE_WORKER_CALLS_FILE FAKE_WORKER_VERIFIED; do
        fake_provider_env_args+=(--provider-env "$fake_provider_env_name")
    done
    local job="$1" workdir worker_path provider_scope_arg=0 option manifest_sha
    local transmission_approval_args=()
    shift
    workdir="${AGY_TEST_WORKDIR:-$TMP/repo}"
    worker_path="${AGY_TEST_WORKER:-$WORKER}"
    for option in "$@"; do
        [[ "$option" != "--provider-scope" ]] || provider_scope_arg=1
    done
    PATH="$TMP/bin:$PATH" AGY_WORKER_LOG_DIR="$TMP/logs" AGY_WORKER_JOB_ID="$job" \
        AGY_WORKER_MODE="${AGY_WORKER_MODE:-accept-edits}" \
        FAKE_MODEL_FILE="${FAKE_MODEL_FILE:-$TMP/$job.model}" FAKE_PROMPT_FILE="${FAKE_PROMPT_FILE:-$TMP/$job.prompt}" \
        FAKE_DIRS_FILE="${FAKE_DIRS_FILE:-$TMP/$job.dirs}" FAKE_ARGV_FILE="${FAKE_ARGV_FILE:-$TMP/$job.argv}" \
        FAKE_STAGE_RESULT_FILE="${FAKE_STAGE_RESULT_FILE:-$TMP/$job.stage-result}" \
        FAKE_CALLS_FILE="${FAKE_CALLS_FILE:-$TMP/$job.calls}" FAKE_WORKER_CALLS_FILE="${FAKE_WORKER_CALLS_FILE:-$TMP/$job.worker-calls}" \
        FAKE_DISPATCH_MODE="${FAKE_DISPATCH_MODE:-result}" \
        FAKE_HEARTBEAT_COUNT="${FAKE_HEARTBEAT_COUNT:-8}" \
        FAKE_HEARTBEAT_DELAY="${FAKE_HEARTBEAT_DELAY:-0.10}" \
        FAKE_HEARTBEAT_BARRIER_READY="${FAKE_HEARTBEAT_BARRIER_READY:-}" \
        FAKE_HEARTBEAT_BARRIER_RELEASE="${FAKE_HEARTBEAT_BARRIER_RELEASE:-}" \
        FAKE_HEARTBEAT_AFTER_FIRST_READY="${FAKE_HEARTBEAT_AFTER_FIRST_READY:-}" \
        FAKE_HEARTBEAT_AFTER_FIRST_RELEASE="${FAKE_HEARTBEAT_AFTER_FIRST_RELEASE:-}" \
        FAKE_DELETE_FROM_BOUND_ROOT="${FAKE_DELETE_FROM_BOUND_ROOT:-}" \
        FAKE_EDIT_FROM_BOUND_ROOT="${FAKE_EDIT_FROM_BOUND_ROOT:-}" \
        FAKE_EDIT_CONTENT="${FAKE_EDIT_CONTENT:-}" \
        FAKE_WORKER_VERIFIED="${FAKE_WORKER_VERIFIED:-0}" \
        python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$worker_path" start --workdir "$workdir" \
        "${fake_provider_env_args[@]}" \
        ${transmission_approval_args+"${transmission_approval_args[@]}"} "$@"
}

printf 'start must not dispatch without a transmission mode\n' | \
    AGY_TEST_SKIP_WHOLE_APPROVAL=1 start_worker missing-transmission-start \
        --workflow task > "$TMP/missing-transmission-start.out" \
        2> "$TMP/missing-transmission-start.err"
missing_transmission_start_rc=$?
if [[ "$missing_transmission_start_rc" == 64 \
        && ! -s "$TMP/missing-transmission-start.out" \
        && ! -e "$TMP/missing-transmission-start.called" \
        && ! -e "$TMP/logs/missing-transmission-start" ]] \
        && grep -Fq 'choose provider scope, or explicitly approve whole-worktree transmission' \
            "$TMP/missing-transmission-start.err"; then
    ok "raw start requires an explicit transmission mode before queueing or provider launch"
else
    bad "raw start missing transmission mode boundary"
fi

partial_clone_source="$TMP/partial-clone-source"
partial_clone_repo="$TMP/partial-clone-repo"
git init -q "$partial_clone_source"
git -C "$partial_clone_source" -c user.name='agy-worker test' -c user.email='test@example.invalid' \
    commit --allow-empty -q -m initial
git -C "$partial_clone_source" worktree add -q -b partial-clone-test "$partial_clone_repo" HEAD
git -C "$partial_clone_source" config extensions.partialclone origin
git -C "$partial_clone_source" config remote.origin.promisor true
printf 'partial clone must fail before queueing\n' | \
    AGY_TEST_WORKDIR="$partial_clone_repo" start_worker partial-clone-preflight \
        --workflow task > "$TMP/partial-clone-preflight.out" \
        2> "$TMP/partial-clone-preflight.err"
partial_clone_rc=$?
if [[ "$partial_clone_rc" == 64 \
        && ! -e "$TMP/logs/partial-clone-preflight/dispatch-state.json" \
        && ! -s "$TMP/partial-clone-preflight.worker-calls" ]] \
        && grep -Fqx \
            'agy-dispatch: partial/promisor Git clones are unsupported; use a full clone' \
            "$TMP/partial-clone-preflight.err"; then
    ok "partial/promisor clones fail synchronously before queueing or provider launch"
else
    bad "partial/promisor clone synchronous preflight"
fi

printf 'plan staged prompt marker\n' | run_worker plan-staged --mode plan \
    > "$TMP/plan-staged.out" 2> "$TMP/plan-staged.err"
rc=$?
if [[ "$rc" == 0 ]] && python3 - "$TMP/plan-staged.argv" \
        "$TMP/logs/plan-staged/staged/full-prompt.txt" <<'PY'
import sys
argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
staged = open(sys.argv[2], encoding="utf-8").read()
assert b"--mode" in argv and argv[argv.index(b"--mode") + 1] == b"plan"
assert b"--disable-slash-commands" not in argv
assert b"Read '" in argv[-1]
assert "plan staged prompt marker" in staged
assert "Use file tools to inspect the approved workspace only; do not edit files." in staged
PY
then
    ok "plan stages the complete prompt and leaves slash expansion available only for its fixed driver prompt"
else
    bad "plan staging/slash contract"
fi

printf 'heartbeat completes\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_HEARTBEAT_COUNT=8 FAKE_HEARTBEAT_DELAY=0.10 \
    run_worker heartbeat-success --idle-timeout 1s --hard-timeout 3s --max-runtime 4s \
    > "$TMP/heartbeat-success.out" 2> "$TMP/heartbeat-success.err"
rc=$?
if [[ "$rc" == 0 ]] && python3 - "$TMP/logs/heartbeat-success/dispatch-state.json" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "succeeded"
assert state["progress_count"] >= 2
assert state["conversation_id"] == "fake-conversation-01"
PY
then
    ok "valid init and step updates renew the idle lease without changing hard limits"
else
    bad "valid stream heartbeats must complete below the hard deadline"
fi

printf 'idle must fail\n' | FAKE_DISPATCH_MODE=idle \
    run_worker idle-timeout --idle-timeout 1s --hard-timeout 3s --max-runtime 4s \
    > "$TMP/idle-timeout.out" 2> "$TMP/idle-timeout.err"
rc=$?
if [[ "$rc" == 9 ]] && [[ "$(status_field "$TMP/idle-timeout.err" reason)" == idle_timeout ]]; then
    ok "silent worker terminates at the independent idle deadline"
else
    bad "silent worker idle timeout classification"
fi

printf 'malformed heartbeat must not count\n' | FAKE_DISPATCH_MODE=malformed-heartbeat \
    run_worker malformed-heartbeat --idle-timeout 1s --hard-timeout 3s --max-runtime 4s \
    > "$TMP/malformed-heartbeat.out" 2> "$TMP/malformed-heartbeat.err"
rc=$?
if [[ "$rc" == 9 ]] && python3 - "$TMP/malformed-heartbeat.err" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["reason"] == "idle_timeout"
assert state["progress_count"] == 0
PY
then
    ok "malformed events never renew the idle lease"
else
    bad "malformed event heartbeat boundary"
fi

printf 'oversized heartbeat must not count\n' | FAKE_DISPATCH_MODE=oversized-heartbeat \
    run_worker oversized-heartbeat --idle-timeout 1s --hard-timeout 2s --max-runtime 3s \
    > "$TMP/oversized-heartbeat.out" 2> "$TMP/oversized-heartbeat.err"
rc=$?
if [[ "$rc" == 23 ]] && python3 - "$TMP/oversized-heartbeat.err" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["reason"] == "output_oversized"
assert state["progress_count"] == 0
PY
then
    ok "oversized stream events fail closed and never renew the idle lease"
else
    bad "oversized event heartbeat boundary"
fi

printf 'exit-zero empty output\n' | FAKE_DISPATCH_MODE=empty-success \
    run_worker empty-success > "$TMP/empty-success.out" 2> "$TMP/empty-success.err"
rc=$?
if [[ "$rc" == 3 && ! -s "$TMP/empty-success.out" \
        && "$(status_field "$TMP/empty-success.err" reason)" == empty_output ]]; then
    ok "worker rejects exit-zero empty provider output"
else
    bad "worker exit-zero empty-output classification"
fi

bound_state="$(CDPATH= cd -- "$TMP" && pwd -P)/workflow-bound-state.json"
python3 - "$ROOT" "$TMP/logs/empty-success" "$bound_state" <<'PY'
import json
import os
from pathlib import Path
import sys

repo = Path(sys.argv[1]).resolve()
dispatch = Path(sys.argv[2]).resolve()
path = Path(sys.argv[3])
st = repo.stat()
ident = {"dev": st.st_dev, "ino": st.st_ino, "mode": st.st_mode, "uid": st.st_uid, "gid": st.st_gid}
value = {
    "schema_version": 9, "kind": "agy-worker-workflow-state", "job_id": "empty-success",
    "repo_path": str(repo), "repo_identity": ident,
    "worktree_path": str(repo), "worktree_identity": ident,
    "branch": "test", "branch_ref": "refs/heads/test", "base": "0" * 40,
    "provider_isolation": "session", "provider_execution": None,
    "preview_manifest_sha256": "0" * 64, "preview_content_sha256": "0" * 64,
    "preview_launch_approval_sha256": json.loads((dispatch / "dispatch-command.json").read_bytes())["launch_approval_sha256"],
    "preview_launch_authority": json.loads((dispatch / "dispatch-command.json").read_bytes())["launch_authority"], "native_grant_profile": "baseline",
    "dispatch_job_dir": str(dispatch), "job_state_path": None, "receipt_path": None,
}
path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
"$WORKER" status --job-id empty-success --state "$bound_state" --format json \
    > "$TMP/advanced-state.out" 2> "$TMP/advanced-state.err"
bound_status=$?
"$WORKER" status --job-id wrong-job --state "$bound_state" --format json \
    > "$TMP/advanced-state-wrong.out" 2> "$TMP/advanced-state-wrong.err"
wrong_status=$?
if [[ "$bound_status" == 0 && "$wrong_status" != 0 ]] \
    && [[ "$(status_field "$TMP/advanced-state.out" job_id)" == empty-success ]]; then
    ok "advanced controls resolve only a job-bound workflow log root without environment"
else
    bad "advanced control workflow state log-root binding"
fi
"$WORKER" verification-copy --job-id empty-success --state "$bound_state" \
    --destination "$TMP/candidate-copy" --format json \
    > "$TMP/advanced-copy.out" 2> "$TMP/advanced-copy.err"
copy_status=$?
"$WORKER" restart --job-id empty-success --state "$bound_state" \
    --approve-state-sha "$(printf '%064d' 0)" --format text \
    > "$TMP/advanced-restart.out" 2> "$TMP/advanced-restart.err"
restart_status=$?
if [[ "$copy_status" != 0 && "$restart_status" != 0 ]] \
    && ! grep -Eq 'log root is unavailable|invalid usage' "$TMP/advanced-copy.err" "$TMP/advanced-restart.err"; then
    ok "verification-copy and restart accept bound --state before eligibility checks"
else
    bad "verification-copy and restart state-derived log root"
fi

printf 'benign print-mode diagnostics\n' | \
    FAKE_WARNING_LINE='permission that headless mode cannot prompt for; file write reported failure after content was already written' \
    FAKE_UTF8_SUMMARY=1 run_worker benign-print-diagnostics \
    > "$TMP/benign-print-diagnostics.out" 2> "$TMP/benign-print-diagnostics.err"
rc=$?
if [[ "$rc" == 0 ]] && python3 - "$TMP/benign-print-diagnostics.out" \
        "$TMP/logs/benign-print-diagnostics/dispatch-state.json" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
state = json.load(open(sys.argv[2], encoding="utf-8"))
assert result["status"] == "completed"
assert result["summary"] == "café 😀"
assert state["status"] == "succeeded"
assert state["reason"] is None
PY
then
    ok "successful structured output ignores stderr diagnostics and preserves UTF-8"
else
    bad "structured-output diagnostic and UTF-8 boundary"
fi

for classified_case in authentication_text provider_text unknown_text; do
    case "$classified_case" in
        authentication_text) classified_line='authentication failed' ;;
        provider_text) classified_line='provider unavailable' ;;
        *) classified_line='unrecognized provider diagnostic' ;;
    esac
    printf 'classification %s\n' "$classified_case" | FAKE_EXIT_CODE=23 \
        FAKE_ERROR_LINE="$classified_line" run_worker "classification-$classified_case" \
        --idle-timeout 1s --hard-timeout 2s --max-runtime 3s \
        > "$TMP/classification-$classified_case.out" \
        2> "$TMP/classification-$classified_case.err"
    rc=$?
    if [[ "$rc" == 5 ]] \
            && [[ "$(status_field "$TMP/classification-$classified_case.err" reason)" == agy_failed_unclassified ]]; then
        ok "unproven $classified_case remains unclassified without free-form guessing"
    else
        bad "closed error classification for $classified_case"
    fi
done

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" "$TMP" <<'PY'
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("dispatch_step16", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
stderr = Path(sys.argv[2]) / "native-host.err"
for line in ("sandbox_apply: Operation not permitted", "sandbox-exec: sandbox_apply: Operation not permitted"):
    stderr.write_text(line + "\n", encoding="utf-8")
    assert module._classify_stderr(stderr, "1.2.12", 1, native=True) == "native_host_sandbox_unavailable"
    assert module._classify_stderr(stderr, "1.2.12", 1, native=False) == "agy_failed_unclassified"
assert "native_host_sandbox_unavailable" in module.REASONS
assert module._cycle_budget_explanation({"status": "cancelled", "reason": "interrupted", "candidate_recognized": False, "attempt": 1, "max_cycles": 2})
PY
if [[ $? -eq 0 ]]; then
    ok "native nested-sandbox denial is actionable and interrupted candidate-free budget is explained"
else
    bad "native host and interrupted budget status explanations"
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/logs/literal-smoke/dispatch-command.json" "$TMP/diagnostic-command" <<'PY'
import copy
import importlib.util
import json
from pathlib import Path
import sys

source, template, destination = sys.argv[1:]
spec = importlib.util.spec_from_file_location("agy_dispatch_diagnostic_command", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
command = json.loads(Path(template).read_text(encoding="utf-8"))
job = Path(destination)
job.mkdir(mode=0o700)
for invalid in (None, [], {}, 123, "", "bad\nversion", "bad\x00version", "bad\x7fversion", "é" * 65):
    changed = copy.deepcopy(command)
    changed["agy_version"] = invalid
    module.write_atomic(job, module.COMMAND_NAME, changed)
    try:
        module.load_command(job)
    except module.DispatchError as exc:
        assert str(exc) == "dispatch agy diagnostic version is invalid", str(exc)
    else:
        raise AssertionError(f"invalid diagnostic version accepted: {invalid!r}")
for diagnostic in ("future vendor build", "9.9.9-preview", "é" * 64):
    changed = copy.deepcopy(command)
    changed["agy_version"] = diagnostic
    module.write_atomic(job, module.COMMAND_NAME, changed)
    validated, _, _ = module.load_command(job)
    assert validated["agy_version"] == diagnostic
PY
if [[ $? == 0 ]]; then
    ok "command diagnostic version is bounded text without a semantic-version gate"
else
    bad "command diagnostic version type, control, byte-bound or free-text validation"
fi

for version_mode in ready quota113 drift999; do
    printf 'quota prose does not establish a report\n' | FAKE_VERSION_MODE="$version_mode" \
        FAKE_DISPATCH_MODE=quota-error FAKE_EXIT_CODE=23 run_worker "quota-$version_mode" \
        > "$TMP/quota-$version_mode.out" 2> "$TMP/quota-$version_mode.err"
    rc=$?
    if [[ "$rc" == 4 && ! -s "$TMP/quota-$version_mode.out" \
            && "$(status_field "$TMP/quota-$version_mode.err" reason)" == invalid_envelope \
            && "$(wc -l < "$TMP/quota-$version_mode.worker-calls" | tr -d ' ')" == 1 ]]; then
        ok "quota prose without report fails across $version_mode without retry"
    else bad "quota prose must not invent report or retry authority ($version_mode)"; fi
done

HARD_SIDE_EFFECT="$TMP/hard-side-effect"
printf 'hard limit must win\n' | FAKE_DISPATCH_MODE=heartbeat-forever \
    FAKE_SIDE_EFFECT_FILE="$HARD_SIDE_EFFECT" \
    run_worker hard-timeout --idle-timeout 1s --hard-timeout 3s --max-runtime 5s \
    > "$TMP/hard-timeout.out" 2> "$TMP/hard-timeout.err"
rc=$?
sleep 1
if [[ "$rc" == 16 && ! -e "$HARD_SIDE_EFFECT" ]] && python3 - "$TMP/hard-timeout.err" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["reason"] == "hard_deadline_exceeded"
assert state["limit_kind"] == "hard"
assert state["progress_count"] >= 2
PY
then
    ok "fresh heartbeats cannot exceed hard deadline and process-group descendants are reaped"
else
    bad "hard deadline/process-group boundary"
fi

FOREGROUND_SIGNAL_SIDE_EFFECT="$TMP/foreground-signal-side-effect"
printf 'foreground signal ownership\n' > "$TMP/foreground-signal.task"
PATH="$TMP/bin:$PATH" AGY_WORKER_LOG_DIR="$TMP/logs" AGY_WORKER_JOB_ID=foreground-signal \
    AGY_WORKER_MODE=accept-edits \
    FAKE_MODEL_FILE="$TMP/foreground-signal.model" \
    FAKE_PROMPT_FILE="$TMP/foreground-signal.prompt" \
    FAKE_DIRS_FILE="$TMP/foreground-signal.dirs" \
    FAKE_ARGV_FILE="$TMP/foreground-signal.argv" \
    FAKE_STAGE_RESULT_FILE="$TMP/foreground-signal.stage-result" \
    FAKE_CALLS_FILE="$TMP/foreground-signal.calls" \
    FAKE_WORKER_CALLS_FILE="$TMP/foreground-signal.worker-calls" \
    FAKE_VERSION_MODE=ready FAKE_DISPATCH_MODE=heartbeat-forever \
    FAKE_SIDE_EFFECT_FILE="$FOREGROUND_SIGNAL_SIDE_EFFECT" \
    python3 -I -S -B "$ROOT/tests/launch_fixture.py" "$WORKER" --workdir "$TMP/repo" \
    --approve-whole-worktree "$(whole_worktree_manifest_sha "$WORKER" "$TMP/repo")" \
    --idle-timeout 2s --hard-timeout 4s --max-runtime 4s \
    --provider-env FAKE_MODEL_FILE --provider-env FAKE_PROMPT_FILE \
    --provider-env FAKE_DIRS_FILE --provider-env FAKE_ARGV_FILE \
    --provider-env FAKE_STAGE_RESULT_FILE --provider-env FAKE_CALLS_FILE \
    --provider-env FAKE_WORKER_CALLS_FILE --provider-env FAKE_VERSION_MODE \
    --provider-env FAKE_DISPATCH_MODE --provider-env FAKE_SIDE_EFFECT_FILE \
    < "$TMP/foreground-signal.task" > "$TMP/foreground-signal.out" \
    2> "$TMP/foreground-signal.err" &
foreground_wrapper=$!
for (( foreground_wait=0; foreground_wait<200; foreground_wait++ )); do
    [[ -s "$TMP/foreground-signal.worker-calls" ]] && break
    kill -0 "$foreground_wrapper" 2>/dev/null || break
    sleep 0.01
done
kill -TERM "$foreground_wrapper" 2>/dev/null || true
wait "$foreground_wrapper"
foreground_rc=$?
sleep 1
if [[ "$foreground_rc" == 143 && ! -e "$FOREGROUND_SIGNAL_SIDE_EFFECT" ]] \
        && python3 - "$TMP/logs/foreground-signal/dispatch-state.json" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "cancelled"
assert state["reason"] == "interrupted"
assert state["exit_code"] == 143
PY
then
    ok "foreground TERM is forwarded through the controller and leaves no late process-group side effect"
else
    bad "foreground signal ownership/process-group cleanup"
fi

printf 'private-task-prompt-sentinel\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_WORKER_VERIFIED=1 \
    FAKE_HEARTBEAT_COUNT=12 FAKE_HEARTBEAT_DELAY=0.10 \
    start_worker async-success --idle-timeout 1s --hard-timeout 3s --max-runtime 3s \
    > "$TMP/async-success.start" 2> "$TMP/async-success.start.err"
rc=$?
control_worker status async-success > "$TMP/async-success.status"
status_rc=$?
async_sha="$(status_sha "$TMP/async-success.status")"
control_worker wait async-success --after-state-sha "$async_sha" --timeout 1s \
    > "$TMP/async-success.wait"
wait_rc=$?
terminal_wait_rc=64
result_rc=64
result_json_rc=64
result_text_rc=64
status_text_rc=64
wait_text_rc=64
if [[ "$wait_rc" == 0 ]] && wait_terminal async-success "$TMP/async-success.wait"; then
    terminal_wait_rc=0
    control_worker result async-success > "$TMP/async-success.result"
    result_rc=$?
    control_worker result async-success --format json > "$TMP/async-success.result-json"
    result_json_rc=$?
    control_worker result async-success --format text > "$TMP/async-success.result-text"
    result_text_rc=$?
    control_worker status async-success --format text > "$TMP/async-success.status-text"
    status_text_rc=$?
    async_terminal_sha="$(status_sha "$TMP/async-success.wait")"
    control_worker wait async-success --after-state-sha "$async_terminal_sha" \
        --timeout 1s --format text > "$TMP/async-success.wait-text"
    wait_text_rc=$?
fi
if [[ "$rc" == 0 && "$status_rc" == 0 && "$wait_rc" == 0 \
        && "$terminal_wait_rc" == 0 && "$result_rc" == 0 \
        && "$result_json_rc" == 0 && "$result_text_rc" == 0 \
        && "$status_text_rc" == 0 && "$wait_text_rc" == 0 ]] \
        && cmp -s "$TMP/async-success.result" "$TMP/async-success.result-json" \
        && python3 - "$TMP/async-success.status" "$TMP/async-success.wait" \
            "$TMP/async-success.result" "$TMP/async-success.result-text" \
            "$TMP/async-success.status-text" "$TMP/async-success.wait-text" "$TMP" <<'PY'
import json
import sys
first = json.load(open(sys.argv[1], encoding="utf-8"))
changed = json.load(open(sys.argv[2], encoding="utf-8"))
result = json.load(open(sys.argv[3], encoding="utf-8"))
assert first["status"] in {"queued", "running"}
assert first["next_action"] == "wait"
assert first["next_action_command"] == (
    '"$PIPELINE/agy-worker.sh" wait --job-id async-success --after-state-sha '
    + first["state_sha256"] + " --format text"
)
assert changed["state_sha256"] != first["state_sha256"] or changed["status"] == "succeeded"
assert changed["next_action"] == "result"
assert changed["next_action_command"] == '"$PIPELINE/agy-worker.sh" result --job-id async-success --format json'
assert result["status"] == "completed"
for path in sys.argv[4:7]:
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 3
    assert lines[0] == "Provider attempt: succeeded; reason: none; failure stage: none; bound result available: yes; driver disposition: unreviewed."
    assert lines[1] == f"Driver evidence: 0 passed, 0 failed, 0 advisory, 0 missing; cycle: {changed['cycle']}/{changed['max_cycles']}."
    assert lines[2] == 'Next safe action: retrieve current bound result JSON with "$PIPELINE/agy-worker.sh" result --job-id async-success --format json; review it and run driver checks, construct Verification v2, then no further driver decision is currently listed.'
    text = "\n".join(lines)
    for sentinel in (
        "private-task-prompt-sentinel", "Verified private-worker-prose-sentinel",
        "fake-conversation-01", sys.argv[7],
    ):
        assert sentinel not in text
PY
then
    ok "status/wait/result formats preserve JSON and expose three sanitized driver-owned text lines"
else
    bad "async status/wait/result format and privacy lifecycle"
fi

startup_stress=0
for (( startup_index=1; startup_index<=12; startup_index++ )); do
    startup_job="startup-race-$startup_index"
    printf 'fast startup race\n' | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=1 \
        FAKE_HEARTBEAT_DELAY=0.01 start_worker "$startup_job" --idle-timeout 1s \
        --hard-timeout 3s --max-runtime 4s > "$TMP/$startup_job.start" \
        2> "$TMP/$startup_job.err" || { startup_stress=1; break; }
    wait_terminal "$startup_job" "$TMP/$startup_job.start" || { startup_stress=1; break; }
    if ! python3 - "$TMP/$startup_job.start" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "succeeded"
PY
    then startup_stress=1; break; fi
done
if [[ "$startup_stress" == 0 ]]; then
    ok "fast controller ownership handoff is stable without a competing parent PID transition"
else
    bad "fast controller ownership handoff race"
fi

# Budgets are wide on purpose: this case proves extend gating and arithmetic, and the
# job ends at the barrier release. Deadline expiry is covered by the max-runtime case.
extend_after_first_ready="$TMP/extend-active.after-first-ready"
extend_after_first_release="$TMP/extend-active.after-first-release"
printf 'extend active deadline\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_HEARTBEAT_COUNT=2 FAKE_HEARTBEAT_DELAY=1.00 \
    FAKE_HEARTBEAT_AFTER_FIRST_READY="$extend_after_first_ready" \
    FAKE_HEARTBEAT_AFTER_FIRST_RELEASE="$extend_after_first_release" \
    start_worker extend-active --idle-timeout 20s --hard-timeout 30s --max-runtime 60s \
    > "$TMP/extend-active.start" 2> "$TMP/extend-active.start.err"
extend_ready=0
for (( extend_index=0; extend_index<200; extend_index++ )); do
    control_worker status extend-active > "$TMP/extend-active.status"
    if [[ -e "$extend_after_first_ready" \
            && "$(status_field "$TMP/extend-active.status" status)" == "running" \
            && "$(status_field "$TMP/extend-active.status" progress_count)" -ge 1 ]]; then
        extend_ready=1
        break
    fi
    sleep 0.01
done
extend_sha="$(status_sha "$TMP/extend-active.status")"
control_worker extend extend-active --approve-state-sha "$(printf '0%.0s' {1..64})" --by 1s \
    > "$TMP/extend-active.stale" 2>&1
stale_extend_rc=$?
control_worker extend extend-active --approve-state-sha "$extend_sha" --by 31s \
    > "$TMP/extend-active.over-max" 2>&1
over_max_rc=$?
control_worker extend extend-active --approve-state-sha "$extend_sha" --by 1s \
    > "$TMP/extend-active.extend"
extend_rc=$?
: > "$extend_after_first_release"
wait_terminal extend-active "$TMP/extend-active.extend"
extend_terminal_rc=$?
control_worker result extend-active > "$TMP/extend-active.result"
result_rc=$?
if [[ "$extend_ready" == 1 && "$stale_extend_rc" == 64 \
        && "$over_max_rc" == 64 && "$extend_rc" == 0 \
        && "$extend_terminal_rc" == 0 && "$result_rc" == 0 ]] \
        && grep -Fqx 'agy-dispatch: deadline extension exceeds max runtime' "$TMP/extend-active.over-max" \
        && python3 - \
        "$TMP/extend-active.extend" "$TMP/extend-active.result" <<'PY'
import json
import sys
extended = json.load(open(sys.argv[1], encoding="utf-8"))
result = json.load(open(sys.argv[2], encoding="utf-8"))
assert extended["hard_seconds"] == 31.0
assert extended["max_seconds"] == 60.0
assert result["status"] == "completed"
PY
then
    ok "stale/over-max extend is rejected; fresh state-SHA extend changes only the local hard deadline"
else
    bad "extend control lifecycle"
fi

max_barrier_ready="$TMP/max-runtime.barrier-ready"
max_barrier_release="$TMP/max-runtime.barrier-release"
printf 'max runtime wins after extension\n' | FAKE_DISPATCH_MODE=heartbeat-forever \
    FAKE_HEARTBEAT_DELAY=0.60 \
    FAKE_HEARTBEAT_BARRIER_READY="$max_barrier_ready" \
    FAKE_HEARTBEAT_BARRIER_RELEASE="$max_barrier_release" \
    start_worker max-runtime --idle-timeout 3s --hard-timeout 3s --max-runtime 4s \
    > "$TMP/max-runtime.start" 2> "$TMP/max-runtime.start.err"
max_barrier_observed=0
for (( max_barrier_index=0; max_barrier_index<200; max_barrier_index++ )); do
    if [[ -e "$max_barrier_ready" ]]; then
        control_worker status max-runtime > "$TMP/max-runtime.status"
        if [[ "$(status_field "$TMP/max-runtime.status" progress_count)" -ge 1 ]]; then
            max_barrier_observed=1
            break
        fi
    fi
    sleep 0.01
done
max_extend_rc=64
max_wait_rc=64
if [[ "$max_barrier_observed" == 1 ]]; then
    max_sha="$(status_sha "$TMP/max-runtime.status")"
    control_worker extend max-runtime --approve-state-sha "$max_sha" --by 1s \
        > "$TMP/max-runtime.extend"
    max_extend_rc=$?
fi
: > "$max_barrier_release"
if [[ "$max_extend_rc" == 0 ]]; then
    max_after="$(status_sha "$TMP/max-runtime.extend")"
    control_worker wait max-runtime --after-state-sha "$max_after" --timeout 5s \
        > "$TMP/max-runtime.wait"
    max_wait_rc=$?
fi
for (( max_wait_index=0; max_wait_index<20; max_wait_index++ )); do
    [[ "$max_wait_rc" == 0 ]] || break
    max_status="$(status_field "$TMP/max-runtime.wait" status)"
    [[ "$max_status" == "running" || "$max_status" == "cancel-requested" ]] || break
    max_after="$(status_sha "$TMP/max-runtime.wait")"
    control_worker wait max-runtime --after-state-sha "$max_after" --timeout 1s \
        > "$TMP/max-runtime.wait.next"
    max_wait_rc=$?
    mv "$TMP/max-runtime.wait.next" "$TMP/max-runtime.wait"
done
if [[ "$max_extend_rc" == 0 && "$max_wait_rc" == 0 ]] && python3 - "$TMP/max-runtime.wait" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "failed"
assert state["reason"] == "hard_deadline_exceeded"
assert state["limit_kind"] == "max-runtime"
assert state["hard_seconds"] == 4.0 == state["max_seconds"]
PY
then
    ok "max runtime remains an absolute cap even after an approved hard-deadline extension"
else
    bad "max runtime cap after extension"
fi

cancel_barrier_ready="$TMP/cancel-active.barrier-ready"
cancel_barrier_release="$TMP/cancel-active.barrier-release"
printf 'cancel active job\n' | FAKE_DISPATCH_MODE=heartbeat-forever \
    FAKE_HEARTBEAT_DELAY=0.40 \
    FAKE_HEARTBEAT_BARRIER_READY="$cancel_barrier_ready" \
    FAKE_HEARTBEAT_BARRIER_RELEASE="$cancel_barrier_release" \
    start_worker cancel-active --idle-timeout 1s --hard-timeout 3s --max-runtime 3s \
    > "$TMP/cancel-active.start" 2> "$TMP/cancel-active.start.err"
cancel_barrier_observed=0
for (( cancel_barrier_index=0; cancel_barrier_index<200; cancel_barrier_index++ )); do
    if [[ -e "$cancel_barrier_ready" ]]; then
        control_worker status cancel-active > "$TMP/cancel-active.status"
        if [[ "$(status_field "$TMP/cancel-active.status" progress_count)" -ge 1 ]]; then
            cancel_barrier_observed=1
            break
        fi
    fi
    sleep 0.01
done
cancel_a_rc=64
cancel_b_rc=64
if [[ "$cancel_barrier_observed" == 1 ]]; then
    cancel_sha="$(status_sha "$TMP/cancel-active.status")"
    control_worker cancel cancel-active --approve-state-sha "$cancel_sha" \
        > "$TMP/cancel-active.cancel-a" 2> "$TMP/cancel-active.cancel-a.err" &
    cancel_a_pid=$!
    control_worker cancel cancel-active --approve-state-sha "$cancel_sha" \
        > "$TMP/cancel-active.cancel-b" 2> "$TMP/cancel-active.cancel-b.err" &
    cancel_b_pid=$!
    wait "$cancel_a_pid"; cancel_a_rc=$?
    wait "$cancel_b_pid"; cancel_b_rc=$?
fi
: > "$cancel_barrier_release"
cancel_rc=64
cancel_file="$TMP/cancel-active.cancel-a"
if [[ "$cancel_a_rc" == 0 && "$cancel_b_rc" == 64 ]]; then
    cancel_rc=0
elif [[ "$cancel_b_rc" == 0 && "$cancel_a_rc" == 64 ]]; then
    cancel_rc=0
    cancel_file="$TMP/cancel-active.cancel-b"
fi
wait_rc=64
if [[ "$cancel_rc" == 0 ]]; then
    cancel_after="$(status_sha "$cancel_file")"
    control_worker wait cancel-active --after-state-sha "$cancel_after" --timeout 2s \
        > "$TMP/cancel-active.wait"
    wait_rc=$?
    # A successful wait may observe the approved cancel-requested transition
    # before the controller reaps its local process group and terminalizes.
    # Follow the current SHA through the existing fixed bound; do not accept a
    # non-terminal state if that terminal transition never arrives.
    if [[ "$wait_rc" == 0 ]]; then
        wait_terminal cancel-active "$TMP/cancel-active.wait"
        wait_rc=$?
    fi
fi
if [[ "$cancel_rc" == 0 && "$wait_rc" == 0 ]] && python3 - "$TMP/cancel-active.wait" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "cancelled"
assert state["reason"] == "cancelled"
assert state["remote_cancel_unverified"] is True
assert state["candidate_recognized"] is False
assert state["result_available"] is False
assert state["driver_disposition"] == "not_applicable"
# A no-candidate local cancel must terminalize without the potentially slow
# repository reconciliation that follows a report-bearing completion.
assert state["worktree_reconciliation"] == "unavailable"
assert state["worktree_changes_present"] is None
assert state["worktree_changed_since_dispatch"] is None
PY
then
    ok "concurrent cancel is state-SHA-gated, reaps the local process group, and does not claim remote cancellation"
else
    bad "cancel control lifecycle"
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/queued-cancel-job" "$TMP/repo" \
        "$TMP/logs/literal-smoke/dispatch-command.json" <<'PY'
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

source, job_text, workdir, command_template = sys.argv[1:]
workdir = str(Path(workdir).resolve())
spec = importlib.util.spec_from_file_location("agy_dispatch_queued_cancel", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)
job = Path(job_text).resolve()
job.mkdir(mode=0o700)
command = json.loads(Path(command_template).read_text(encoding="utf-8"))
command.update({
    "job_id": "queued-cancel", "workdir": workdir,
    "idle_seconds": 1, "hard_seconds": 2, "max_seconds": 4,
    "notice_seconds": 3,
})
module.write_atomic(job, module.COMMAND_NAME, command)
lock_path = job / module.LOCK_NAME
lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
os.fchmod(lock_fd, 0o600)
fcntl.flock(lock_fd, fcntl.LOCK_EX)
state, sha = module.create_state(job, "initial", resume=False)
module.command_control(job, "cancel", sha, None)
child = subprocess.Popen(
    [sys.executable, "-I", "-S", "-B", source, "controller", "--job-dir", str(job),
     "--ownership-fd", str(lock_fd)], pass_fds=(lock_fd,), stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
os.close(lock_fd)
assert child.wait(timeout=5) == module.EXIT_BY_REASON["cancelled"]
terminal, _, _ = module.load_state(job)
assert terminal["status"] == "cancelled"
assert terminal["reason"] == "cancelled"
assert terminal["remote_cancel_unverified"] is False
assert not (job / "stream.ndjson").exists()
PY
queued_cancel_rc=$?
if [[ "$queued_cancel_rc" == 0 ]]; then
    ok "queued cancel is consumed by inherited controller ownership without starting agy"
else
    bad "queued cancel/start ownership handoff"
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/state-snapshot-job" <<'PY'
import contextlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

source, job_text = sys.argv[1:]
spec = importlib.util.spec_from_file_location("agy_dispatch_state_snapshot", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)
job = Path(job_text).resolve()
job.mkdir(mode=0o700)
workdir = job.parent / "state-snapshot-workdir"
workdir.mkdir(mode=0o700)
subprocess.run(["git", "init", "-q", str(workdir)], check=True)
command = {
    "schema_version": module.CURRENT_COMMAND_SCHEMA, "provider_isolation": "session",
    "job_id": "state-snapshot", "workdir": str(workdir),
    "idle_seconds": 1.0, "hard_seconds": 2.0, "max_seconds": 3.0,
    "workflow": "legacy", "max_cycles": 1,
}
state = module.initial_state(
    command, "initial", 1, command_sha="0" * 64,
    command_identity=(1, 1, os.getuid(), os.getgid(), 0o600),
    stage_sha=None, stage_identity=None,
)
assert state["schema_version"] == module.CURRENT_STATE_SCHEMA == 18
assert state["worktree_root_identity"] is not None
assert state["worktree_baseline"] is not None
assert state["worktree_snapshot_algorithm"] == module.WORKTREE_SNAPSHOT_SEMANTIC_V1
module.write_atomic(job, module.STATE_NAME, state)
done = job / "writer.done"
blocked = job / "writer.blocked"
acquired = job / "writer.acquired"
writer_source = r'''
import fcntl
import importlib.util
import os
from pathlib import Path
import sys

source, job_text, done_text, blocked_text, acquired_text = sys.argv[1:]
spec = importlib.util.spec_from_file_location("agy_dispatch_state_writer", source)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)
job = Path(job_text)
lock_fd = os.open(
    job / module.STATE_LOCK_NAME,
    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
os.fchmod(lock_fd, 0o600)
try:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        Path(blocked_text).touch(mode=0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    else:
        Path(acquired_text).touch(mode=0o600)
    state, raw, _sha = module.load_state(job)
    module._transition_locked(job, state, raw, {
        "notice_count": state["notice_count"] + 1,
    })
finally:
    os.close(lock_fd)
Path(done_text).touch(mode=0o600)
'''
original_lstat = Path.lstat
original_state_lock = module.state_lock
child = None
writer_was_blocked = False
locked_read = False

@contextlib.contextmanager
def observe_state_lock(job_path):
    global locked_read
    with original_state_lock(job_path) as descriptor:
        locked_read = True
        try:
            yield descriptor
        finally:
            locked_read = False

def replace_during_identity_check(path: Path):
    global child, writer_was_blocked
    if locked_read and path == job / module.STATE_NAME and child is None:
        child = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-c", writer_source,
             source, str(job), str(done), str(blocked), str(acquired)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 2.0
        while not blocked.exists() and not acquired.exists() \
                and time.monotonic() < deadline:
            time.sleep(0.005)
        assert blocked.exists() != acquired.exists()
        writer_was_blocked = blocked.exists()
        if not writer_was_blocked:
            child.wait(timeout=3)
            assert done.exists()
    return original_lstat(path)

Path.lstat = replace_during_identity_check
module.state_lock = observe_state_lock
try:
    snapshot, raw, sha = module.read_state_snapshot(job)
finally:
    Path.lstat = original_lstat
    module.state_lock = original_state_lock
assert child is not None and child.wait(timeout=3) == 0
terminal, terminal_raw, terminal_sha = module.read_state_snapshot(job)
assert writer_was_blocked
assert snapshot["sequence"] == 1 and sha == module.digest(raw)
assert terminal["sequence"] == 2
assert terminal["previous_state_sha256"] == sha
assert terminal_sha == module.digest(terminal_raw)
PY
state_snapshot_rc=$?
if [[ "$state_snapshot_rc" == 0 ]]; then
    ok "state snapshot serializes an approved atomic replacement without weakening identity checks"
else
    bad "state snapshot atomic-replacement identity boundary"
fi

printf 'orphan fixture\n' | FAKE_EXIT_CODE=23 \
    run_worker orphan-no-resume --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/orphan-no-resume.out" 2> "$TMP/orphan-no-resume.err"
ORPHAN_JOB="$TMP/logs/orphan-no-resume"
rm -f "$ORPHAN_JOB/dispatch-state.json"
rm -f "$ORPHAN_JOB/stream.ndjson" "$ORPHAN_JOB/stderr.txt"
PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$ORPHAN_JOB" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location("agy_dispatch_orphan", sys.argv[1])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
job = Path(sys.argv[2])
command, raw, identity = module.load_command(job)
state = module.initial_state(
    command, "initial", 1, command_sha=module.digest(raw),
    command_identity=identity, stage_sha=None, stage_identity=None,
)
state.update({
    "status": "orphaned", "reason": "status_unavailable", "exit_code": 20,
    "finished_epoch": 1.0, "conversation_id": "fake-conversation-01",
    "resume_available": False,
})
module.write_atomic(job, module.STATE_NAME, state)
PY
orphan_sha="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$ORPHAN_JOB/dispatch-state.json" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
orphan_calls_before="$(wc -l < "$TMP/orphan-no-resume.calls" | tr -d ' ')"
control_worker resume orphan-no-resume --approve-state-sha "$orphan_sha" >/dev/null 2>&1
orphan_resume_rc=$?
control_worker restart orphan-no-resume --approve-state-sha "$orphan_sha" >/dev/null 2>&1
orphan_restart_rc=$?
orphan_calls_after="$(wc -l < "$TMP/orphan-no-resume.calls" | tr -d ' ')"
if [[ "$orphan_resume_rc" == 21 && "$orphan_restart_rc" == 64 \
        && "$orphan_calls_before" == "$orphan_calls_after" ]]; then
    ok "orphaned dispatch is preserve-only and cannot resume or restart a provider call"
else
    bad "orphaned dispatch continuation boundary"
fi

printf 'private-resume-task-sentinel\n' | FAKE_DISPATCH_MODE=conversation-fail \
    run_worker resume-case --idle-timeout 1s --hard-timeout 4s --max-runtime 8s \
    > "$TMP/resume-case.out" 2> "$TMP/resume-case.err"
rc=$?
resume_sha="$(status_sha "$TMP/resume-case.err")"
FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker resume resume-case --approve-state-sha "$resume_sha" --format text \
    > "$TMP/resume-case.resume"
resume_rc=$?
control_worker status resume-case > "$TMP/resume-case.resume-status"
wait_terminal resume-case "$TMP/resume-case.resume-status"
resume_wait_rc=$?
control_worker result resume-case > "$TMP/resume-case.result"
result_rc=$?
if [[ "$rc" == 4 && "$resume_rc" == 0 && "$resume_wait_rc" == 0 && "$result_rc" == 0 ]] && python3 - \
        "$TMP/resume-case.argv" "$TMP/resume-case.resume-status" \
        "$TMP/resume-case.resume" "$TMP/resume-case.err" "$TMP" <<'PY'
import json
import sys
argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
state = json.load(open(sys.argv[2], encoding="utf-8"))
assert argv.count(b"--conversation") == 1
assert argv[argv.index(b"--conversation") + 1] == b"fake-conversation-01"
assert b"Continue the existing bounded task" in argv[-1]
assert state["attempt_origin"] == "conversation-resume"
assert state["attempt"] == 2
assert state["next_action"] == "result"
assert state["next_action_command"] == '"$PIPELINE/agy-worker.sh" result --job-id resume-case --format json'
text = open(sys.argv[3], encoding="utf-8").read()
assert len(text.splitlines()) == 3
failed = json.load(open(sys.argv[4], encoding="utf-8"))
assert failed["next_action"] == "none"
assert failed["next_action_command"] is None
assert [item["action"] for item in failed["available_actions"]] == ["resume", "restart"]
assert failed["available_actions"][0]["command"] == (
    '"$PIPELINE/agy-worker.sh" resume --job-id resume-case --approve-state-sha '
    + failed["state_sha256"] + " --format text"
)
assert failed["available_actions"][1]["command"] == (
    '"$PIPELINE/agy-worker.sh" restart --job-id resume-case --approve-state-sha '
    + failed["state_sha256"] + " --format text"
)
for sentinel in ("private-resume-task-sentinel", "fake-conversation-01", sys.argv[5]):
    assert sentinel not in text
PY
then
    ok "resume text succeeds with the exact private conversation and no private output"
else
    bad "conversation resume format and privacy contract"
fi

printf 'restart without conversation\n' | FAKE_DISPATCH_MODE=conversation-fail \
    run_worker restart-case --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/restart-case.out" 2> "$TMP/restart-case.err"
restart_sha="$(status_sha "$TMP/restart-case.err")"
FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker restart restart-case --approve-state-sha "$restart_sha" \
    > "$TMP/restart-case.restart"
restart_rc=$?
wait_terminal restart-case "$TMP/restart-case.restart"
restart_wait_rc=$?
control_worker result restart-case > "$TMP/restart-case.result"
result_rc=$?
if [[ "$restart_rc" == 0 && "$restart_wait_rc" == 0 && "$result_rc" == 0 ]] && python3 - \
        "$TMP/restart-case.argv" "$TMP/restart-case.restart" <<'PY'
import json
import sys
argv = [item for item in open(sys.argv[1], "rb").read().split(b"\0") if item]
state = json.load(open(sys.argv[2], encoding="utf-8"))
assert b"--conversation" not in argv
assert state["attempt_origin"] == "fresh-restart"
assert state["attempt"] == 2
PY
then
    ok "restart is explicit fresh origin and remains distinct from resume"
else
    bad "fresh restart contract"
fi

printf 'resume unavailable\n' | FAKE_EXIT_CODE=23 \
    run_worker resume-unavailable --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/resume-unavailable.out" 2> "$TMP/resume-unavailable.err"
unavailable_sha="$(status_sha "$TMP/resume-unavailable.err")"
resume_unavailable_calls_before="$(cat "$TMP/resume-unavailable.calls")"
resume_unavailable_state_before="$(shasum -a 256 "$TMP/logs/resume-unavailable/dispatch-state.json")"
FAKE_DISPATCH_MODE=heartbeat-success control_worker resume resume-unavailable \
    --approve-state-sha "$unavailable_sha" > "$TMP/resume-unavailable.resume" 2>&1
resume_rc=$?
resume_unavailable_calls="$(cat "$TMP/resume-unavailable.calls")"
if [[ "$resume_rc" == 21 && "$resume_unavailable_calls" == "$resume_unavailable_calls_before" \
        && "$resume_unavailable_state_before" == "$(shasum -a 256 "$TMP/logs/resume-unavailable/dispatch-state.json")" ]]; then
    resume_unavailable_ok=1
else
    resume_unavailable_ok=0
fi

project_feedback() {
    python3 - "$TMP/logs/$1/dispatch-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({"schema_version": 2, "summary": "driver checks found one repairable failure",
    "passed_checks": ["lint"], "failed_checks": ["unit-tests"], "advisory_checks": 0,
    "missing_checks": 0, "candidate_sha256": state["result_sha256"], "coverage": "partial",
    "verified_findings": 0, "unresolved_gaps": 1, "diff_review_complete": True}, separators=(",", ":")))
PY
}
project_verified_feedback() {
    python3 - "$TMP/logs/$1/dispatch-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({"schema_version": 2, "summary": "driver checks passed",
    "passed_checks": ["lint", "unit-tests"], "failed_checks": [], "advisory_checks": 0,
    "missing_checks": 0, "candidate_sha256": state["result_sha256"], "coverage": "complete",
    "verified_findings": 0, "unresolved_gaps": 0, "diff_review_complete": True}, separators=(",", ":")))
PY
}
project_missing_feedback() {
    python3 - "$TMP/logs/$1/dispatch-state.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({"schema_version": 2, "summary": "one required driver check is missing",
    "passed_checks": ["lint"], "failed_checks": [], "advisory_checks": 0,
    "missing_checks": 1, "candidate_sha256": state["result_sha256"], "coverage": "partial",
    "verified_findings": 0, "unresolved_gaps": 1, "diff_review_complete": True}, separators=(",", ":")))
PY
}

if python3 -B - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" <<'PYTHON'
import json
from pathlib import Path
import re
import sys
source = Path(sys.argv[1]).resolve()
provider_schema = source.parent.parent / "schemas" / "worker-result.provider.schema.json"
# The provider consumes RE2, where `$` is a strict end-of-text anchor. Keep the
# driver schema's Python-search spelling separate while enforcing the same IDs.
provider_document = json.loads(provider_schema.read_text(encoding="utf-8"))
provider_id_pattern = provider_document["properties"]["requested_check_ids"]["items"]["pattern"]
assert provider_id_pattern == r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
assert "(?" not in provider_id_pattern
strict_id = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}").fullmatch
assert all(strict_id(value) for value in ("A", "unit_core", "Lint-2", "Z" * 64))
assert all(not strict_id(value) for value in ("", "1unit", "unit.", "unit\n", "A" * 65, "é"))
PYTHON
then ok "provider check-id regex remains RE2-compatible and driver validation stays strict"
else bad "provider check-id schema boundary"; fi
if [[ "$resume_unavailable_ok" == 1 ]]; then
    ok "unavailable resume preserves failure state and starts no probes or provider"
else bad "unavailable resume action parity"; fi

# Operation-specific recovery requirements retain the prior candidate and frozen effort.
capability_root="$(cd "$TMP" && pwd -P)"
git -C "$TMP/source-repo" worktree add -q -b capability-recovery "$capability_root/capability-worktree" HEAD
capability_workdir="$(cd "$capability_root/capability-worktree" && pwd -P)"
printf 'unchanged candidate\n' > "$capability_workdir/target.txt"
capability_scope="$capability_root/capability-recovery.scope.json"
printf '%s\n' '{"schema_version":1,"kind":"agy-worker-provider-scope","read":[{"path":"target.txt","kind":"file"}],"write":[{"path":"target.txt","kind":"file"}]}' > "$capability_scope"
chmod 0600 "$capability_scope"
for capability_case in resume continue scoped-repair effort no-effort restart; do
    job="capability-$capability_case"
    capability_args=(--workflow project --max-cycles 2 --idle-timeout 1s --hard-timeout 2s --max-runtime 30s)
    initial_mode=heartbeat-success
    initial_help=missing---conversation
    recovery_action=continue
    missing=conversation
    scoped_edit=''
    case "$capability_case" in
        resume|restart) initial_mode=conversation-fail; recovery_action="$capability_case" ;;
        scoped-repair)
            scoped_edit=target.txt
            capability_sha="$("$WORKER" transmission-preview --task fixture --workdir "$capability_workdir" \
                --provider-scope "$capability_scope" --format json \
                | python3 -B -c 'import json,sys; print(json.load(sys.stdin)["transmission_sha256"])')"
            capability_args+=(--provider-scope "$capability_scope" --approve-transmission-sha "$capability_sha" --allow-scoped-repair)
            ;;
        effort) initial_help=ready; missing=effort; capability_args+=(--model vendor/Future --effort Caller-Level) ;;
        no-effort) initial_help=missing---effort; missing=effort; capability_args+=(--model vendor/Future) ;;
    esac
    printf 'capability recovery fixture\n' | AGY_TEST_WORKDIR="$capability_workdir" \
        FAKE_DISPATCH_MODE="$initial_mode" FAKE_HEARTBEAT_COUNT=1 FAKE_HELP_MODE="$initial_help" \
        FAKE_EDIT_FROM_BOUND_ROOT="$scoped_edit" FAKE_EDIT_CONTENT='scoped candidate changed' \
        run_worker "$job" "${capability_args[@]}" > "$TMP/$job.out" 2> "$TMP/$job.err"
    initial_rc=$?
    control_worker status "$job" > "$TMP/$job.before"
    capability_state_sha="$(status_sha "$TMP/$job.before")"
    cp "$TMP/logs/$job/dispatch-state.json" "$TMP/$job.before-raw"
    cp "$capability_workdir/target.txt" "$TMP/$job.target-before"
    if [[ "$recovery_action" == continue ]]; then
        project_feedback "$job" | FAKE_HELP_MODE="missing---$missing" AGY_WORKER_EFFORT=Ambient-Later \
            FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=1 \
            control_worker continue "$job" --approve-state-sha "$capability_state_sha" \
            > "$TMP/$job.recovery" 2> "$TMP/$job.recovery.err"
    else
        FAKE_HELP_MODE="missing---$missing" FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=1 \
            control_worker "$recovery_action" "$job" --approve-state-sha "$capability_state_sha" \
            > "$TMP/$job.recovery" 2> "$TMP/$job.recovery.err"
    fi
    recovery_rc=$?
    wait_terminal "$job" "$TMP/$job.recovery"
    recovery_wait_rc=$?
    if [[ "$recovery_rc" == 0 && "$recovery_wait_rc" == 0 ]] \
            && python3 -B - "$capability_root" "$job" "$capability_case" "$initial_rc" "$missing" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
temp, job, case, initial_rc, missing = sys.argv[1:]
temp = Path(temp)
before = json.loads((temp / f'{job}.before-raw').read_bytes())
after = json.loads((temp / 'logs' / job / 'dispatch-state.json').read_bytes())
assert int(initial_rc) == (4 if case in {'resume', 'restart'} else 0), initial_rc
passed = case in {'no-effort', 'restart'}
assert after['status'] == ('succeeded' if passed else 'failed'), after
calls = (temp / f'{job}.calls').read_text().splitlines()
assert calls == ['version', 'help'] * 2 + ['worker', 'version', 'help'] + (['worker'] if passed else []), calls
assert len((temp / f'{job}.worker-calls').read_text().splitlines()) == (2 if passed else 1)
assert after['attempt'] == 2
assert (temp / 'capability-worktree' / 'target.txt').read_bytes() == (temp / f'{job}.target-before').read_bytes()
if passed:
    argv = (temp / f'{job}.argv').read_bytes().split(b'\0')
    assert b'--effort' not in argv
    assert (b'--conversation' in argv) == (case != 'restart')
else:
    assert after['reason'] == 'selection_preflight_failed', after
    assert f'agy missing required capabilities: --{missing}\n' in (temp / 'logs' / job / 'attempt-002.stderr.txt').read_text()
    if before['result_path'] is not None:
        candidate = Path(before['result_path']).read_bytes()
        assert hashlib.sha256(candidate).hexdigest() == before['result_sha256']
        assert after['last_success_path'] == before['result_path']
        assert after['last_success_sha256'] == before['result_sha256']
    if case == 'scoped-repair':
        assert (temp / 'capability-worktree' / 'target.txt').read_text() == 'scoped candidate changed\n'
        assert after['reconciliation_manifest_sha256'] == before['reconciliation_manifest_sha256']
        assert after['repair_lineage_sha256'] == before['repair_lineage_sha256']
selection = json.loads((temp / 'logs' / job / 'selection.json').read_bytes())
assert selection.get('user_effort') == ('Caller-Level' if case == 'effort' else None)
PY
    then ok "$capability_case checks only active flags with fresh probes and preserves prior evidence"
    else bad "$capability_case conditional recovery (initial $initial_rc, recovery $recovery_rc/$recovery_wait_rc)"; fi
done

. "$ROOT/tests/agy_worker_project_lifecycle_cases.sh"

printf 'project missing verification repair\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_HEARTBEAT_COUNT=2 AGY_TEST_WORKDIR="$TMP/project-worktree" \
    start_worker project-missing-check --workflow project \
    --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-missing-check.start" 2> "$TMP/project-missing-check.err"
wait_terminal project-missing-check "$TMP/project-missing-check.start"
control_worker status project-missing-check > "$TMP/project-missing-check.status"
project_missing_sha="$(status_sha "$TMP/project-missing-check.status")"
project_missing_feedback project-missing-check | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker continue project-missing-check --approve-state-sha "$project_missing_sha" --format text \
    > "$TMP/project-missing-check.continue" 2> "$TMP/project-missing-check.continue.err"
project_missing_rc=$?
control_worker status project-missing-check > "$TMP/project-missing-check.status"
wait_terminal project-missing-check "$TMP/project-missing-check.status"
project_missing_wait_rc=$?
project_missing_calls="$(wc -l < "$TMP/project-missing-check.worker-calls" | tr -d ' ')"
if [[ "$project_missing_rc" == 0 && "$project_missing_wait_rc" == 0 \
        && "$project_missing_calls" == 2 ]] \
        && python3 - "$TMP/project-missing-check.status" \
            "$TMP/project-missing-check.continue" "$TMP" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["cycle"] == 2
assert value["attempt_origin"] == "conversation-continue"
assert value["check_counts"] == {"passed": 0, "failed": 0, "advisory": 0, "missing": 0}
assert value["next_action"] == "result"
assert value["next_action_command"] == '"$PIPELINE/agy-worker.sh" result --job-id project-missing-check --format json'
text = open(sys.argv[2], encoding="utf-8").read()
assert len(text.splitlines()) == 3
assert text.splitlines()[1] == "Driver evidence: 1 passed, 0 failed, 0 advisory, 1 missing; cycle: 2/5."
for sentinel in ("one required driver check is missing", "lint", "fake-conversation-01", sys.argv[3]):
    assert sentinel not in text
PY
then
    ok "project continuation text keeps trigger evidence while the replacement candidate resets stored evidence"
else
    bad "project continuation format and privacy contract"
fi

project_provider_path="$TMP/project-worktree/provider-created-during-initial"
printf 'project provider creates a new path\n' | \
    FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    FAKE_PROVIDER_CREATE_PATH="$project_provider_path" \
    AGY_TEST_WORKDIR="$TMP/project-worktree" \
    start_worker project-provider-path --workflow project \
    --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-provider-path.start" 2> "$TMP/project-provider-path.err"
project_provider_start_rc=$?
wait_terminal project-provider-path "$TMP/project-provider-path.start"
project_provider_wait_rc=$?
control_worker status project-provider-path > "$TMP/project-provider-path.status"
project_provider_sha="$(status_sha "$TMP/project-provider-path.status")"
project_feedback project-provider-path | \
    FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker continue project-provider-path \
    --approve-state-sha "$project_provider_sha" \
    > "$TMP/project-provider-path.continue" 2> "$TMP/project-provider-path.continue.err"
project_provider_continue_rc=$?
wait_terminal project-provider-path "$TMP/project-provider-path.continue"
project_provider_continue_wait_rc=$?
control_worker status project-provider-path > "$TMP/project-provider-path.status"
project_provider_calls="$(wc -l < "$TMP/project-provider-path.worker-calls" | tr -d ' ')"
if [[ "$project_provider_start_rc" == 0 && "$project_provider_wait_rc" == 0 \
        && "$project_provider_continue_rc" == 0 \
        && "$project_provider_continue_wait_rc" == 0 \
        && "$project_provider_calls" == 2 && -f "$project_provider_path" ]] \
        && python3 - "$TMP/project-provider-path.status" <<'PY'
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == "succeeded"
assert state["cycle"] == 2
assert state["attempt_origin"] == "conversation-continue"
assert state["candidate_recognized"] is True
PY
then
    ok "project continuation preserves initial-only whole-worktree approval after provider-created paths"
else
    bad "project continuation provider-created path boundary"
fi
rm -f "$project_provider_path"

project_missing_sha="$(status_sha "$TMP/project-missing-check.status")"
project_missing_calls_before_finalize="$(wc -l < "$TMP/project-missing-check.worker-calls" | tr -d ' ')"
project_missing_feedback project-missing-check | control_worker finalize project-missing-check \
    --approve-state-sha "$project_missing_sha" --assurance partially-verified \
    > /dev/null 2>&1
project_hyphen_assurance_rc=$?
project_missing_feedback project-missing-check | control_worker finalize project-missing-check \
    --approve-state-sha "$project_missing_sha" --assurance partially_verified --format text \
    > "$TMP/project-missing-check.finalize" 2> "$TMP/project-missing-check.finalize.err"
project_partial_assurance_rc=$?
control_worker status project-missing-check > "$TMP/project-missing-check.finalized-status"
project_missing_calls_after_finalize="$(wc -l < "$TMP/project-missing-check.worker-calls" | tr -d ' ')"
if [[ "$project_hyphen_assurance_rc" == 64 && "$project_partial_assurance_rc" == 0 \
        && "$project_missing_calls_after_finalize" == "$project_missing_calls_before_finalize" ]] \
        && python3 - "$TMP/project-missing-check.finalized-status" \
            "$TMP/project-missing-check.finalize" "$TMP" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["phase"] == "completed"
assert value["assurance"] == "partially_verified"
assert value["check_counts"] == {"passed": 1, "failed": 0, "advisory": 0, "missing": 1}
assert value["next_action"] == "result"
assert value["next_action_command"] == '"$PIPELINE/agy-worker.sh" result --job-id project-missing-check --format json'
lines = open(sys.argv[2], encoding="utf-8").read().splitlines()
assert len(lines) == 3
assert lines[0] == "Provider attempt: succeeded; reason: none; failure stage: none; bound result available: yes; driver disposition: partially_verified."
assert lines[1] == f"Driver evidence: 1 passed, 0 failed, 0 advisory, 1 missing; cycle: {value['cycle']}/{value['max_cycles']}."
assert lines[2] == (
    'Next safe action: optional finalized result JSON readback with "$PIPELINE/agy-worker.sh" result --job-id project-missing-check --format json; '
    'driver disposition is already recorded; do not construct Verification v2, continue, or finalize. '
    'Available fresh restart command: "$PIPELINE/agy-worker.sh" restart --job-id project-missing-check --approve-state-sha '
    + value["state_sha256"] + " --format text."
)
for sentinel in ("one required driver check is missing", "lint", "fake-conversation-01", sys.argv[3]):
    assert sentinel not in "\n".join(lines)
PY
then
    ok "project finalization text is three-line, driver-owned, and invokes no provider"
else
    bad "project finalization format and assurance contract"
fi

project_cycle_ok=1
for project_cycle in 2 3 4 5; do
    project_feedback project-cycles | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
        control_worker continue project-cycles --approve-state-sha "$project_sha" \
        > "$TMP/project-cycles.$project_cycle" 2> "$TMP/project-cycles.$project_cycle.err"
    project_continue_rc=$?
    wait_terminal project-cycles "$TMP/project-cycles.$project_cycle" || project_cycle_ok=0
    control_worker status project-cycles > "$TMP/project-cycles.status"
    project_sha="$(status_sha "$TMP/project-cycles.status")"
    [[ "$project_continue_rc" == 0 ]] || project_cycle_ok=0
done
project_feedback project-cycles | control_worker continue project-cycles --approve-state-sha "$project_sha" \
    > "$TMP/project-cycles.exhausted" 2> "$TMP/project-cycles.exhausted.err"
project_exhausted_rc=$?
project_calls="$(wc -l < "$TMP/project-cycles.worker-calls" | tr -d ' ')"
if [[ "$project_cycle_ok" == 1 && "$project_exhausted_rc" == 64 && "$project_calls" == 5 ]] \
        && python3 - "$TMP/project-cycles.status" "$TMP/project-cycles.argv" "$TMP/project-cycles.calls" <<'PY'
import json, sys
from pathlib import Path
state = json.load(open(sys.argv[1], encoding="utf-8"))
argv = [item.decode() for item in open(sys.argv[2], "rb").read().split(b"\0") if item]
assert state["cycle"] == 5 and state["continue_available"] is False
assert Path(sys.argv[3]).read_text().splitlines() == ["version", "help"] + ["version", "help", "worker"] * 5
assert argv.count("--conversation") == 1
assert "unit-tests" not in " ".join(argv)
assert "driver checks found one repairable failure" not in " ".join(argv)
PY
then
    ok "project continuation is same-conversation, feedback-private, and bounded to initial plus four repairs"
else
    bad "project continuation cycle bound"
fi

printf 'project finalization\n' | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    AGY_TEST_WORKDIR="$TMP/project-worktree" start_worker project-final --workflow project --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-final.start" 2> "$TMP/project-final.err"
wait_terminal project-final "$TMP/project-final.start"
control_worker status project-final > "$TMP/project-final.status"
project_final_sha="$(status_sha "$TMP/project-final.status")"
project_final_calls_before="$(wc -l < "$TMP/project-final.calls" | tr -d ' ')"
project_verified_feedback project-final | control_worker finalize project-final --approve-state-sha "$project_final_sha" \
    --assurance verified > "$TMP/project-final.finalize" 2> "$TMP/project-final.finalize.err"
project_finalize_rc=$?
project_verified_feedback project-final | control_worker finalize project-final --approve-state-sha "$project_final_sha" \
    --assurance verified > /dev/null 2>&1
project_finalize_stale_rc=$?
project_final_calls_after="$(wc -l < "$TMP/project-final.calls" | tr -d ' ')"
if [[ "$project_finalize_rc" == 0 && "$project_finalize_stale_rc" == 64 \
        && "$project_final_calls_before" == "$project_final_calls_after" ]] \
        && python3 - "$TMP/project-final.finalize" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["phase"] == "completed"
assert value["assurance"] == "verified"
assert value["check_counts"] == {"passed": 2, "failed": 0, "advisory": 0, "missing": 0}
PY
then
    ok "project finalization is a SHA-bound no-provider Codex quality decision"
else
    bad "project finalization contract"
fi

mkdir -p "$TMP/project-outside"
ln -s "$TMP/project-outside" "$TMP/project-worktree/outward-link"
printf 'outward link\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" run_worker project-outward --workflow project > "$TMP/project-outward.out" 2> "$TMP/project-outward.err"
project_outward_rc=$?
rm "$TMP/project-worktree/outward-link"
mkdir -p "$TMP/project-worktree/internal-link-target"
ln -s "$TMP/project-worktree/internal-link-target" "$TMP/project-worktree/internal-link"
printf 'internal link\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" run_worker project-internal --workflow project > "$TMP/project-internal.out" 2> "$TMP/project-internal.err"
project_internal_rc=$?
ln -s .git "$TMP/project-worktree/admin"
printf 'Git admin alias\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" run_worker project-internal-git-alias --workflow project > "$TMP/project-internal-git-alias.out" 2> "$TMP/project-internal-git-alias.err"
project_internal_git_alias_rc=$?
rm "$TMP/project-worktree/admin"
if [[ "$project_outward_rc" == 64 && "$project_internal_rc" == 0 \
        && "$project_internal_git_alias_rc" == 64 \
        && ! -e "$TMP/logs/project-internal-git-alias/task.txt" \
        && ! -e "$TMP/project-internal-git-alias.called" ]]; then
    ok "project workflow rejects Git-admin aliases while allowing ordinary contained links"
else
    bad "project worktree symlink boundary"
fi

printf 'main checkout is not an eligible project worktree\n' | \
    AGY_TEST_SKIP_WHOLE_APPROVAL=1 AGY_TEST_WORKDIR="$PRIMARY_WORKTREE" \
    run_worker project-main-reject --workflow project \
    > "$TMP/project-main-reject.out" 2> "$TMP/project-main-reject.err"
project_main_rc=$?
if [[ "$project_main_rc" == 64 && ! -e "$TMP/logs/project-main-reject/task.txt" ]]; then
    ok "project workflow requires a linked-worktree Git marker file"
else
    bad "project workflow main-checkout boundary"
fi

# The preflight binds only the linked-worktree root marker.  A nested Git
# marker is rejected as an authority boundary before worker/provider setup;
# its kind and contents must not be inspected as worktree input.
project_nested_git_ok=1
for project_nested_kind in file directory symlink special; do
    project_nested_dir="$TMP/project-worktree/nested-$project_nested_kind"
    project_nested_marker="$project_nested_dir/.git"
    mkdir -p "$project_nested_dir"
    case "$project_nested_kind" in
        file) printf 'nested marker\n' > "$project_nested_marker" ;;
        directory) mkdir "$project_nested_marker"; printf 'secret\n' > "$project_nested_marker/secret" ;;
        symlink) ln -s "$TMP/project-outside" "$project_nested_marker" ;;
        special) mkfifo "$project_nested_marker" ;;
    esac
    printf 'nested Git marker\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" \
        run_worker "project-nested-git-$project_nested_kind" --workflow project \
        > "$TMP/project-nested-git-$project_nested_kind.out" \
        2> "$TMP/project-nested-git-$project_nested_kind.err"
    project_nested_rc=$?
    [[ "$project_nested_rc" == 64 && ! -e "$TMP/logs/project-nested-git-$project_nested_kind/task.txt" ]] \
        || project_nested_git_ok=0
    rm -rf "$project_nested_dir"
done
if [[ "$project_nested_git_ok" == 1 ]]; then
    ok "project shell preflight rejects every nested Git marker before provider setup"
else
    bad "project shell nested Git marker boundary"
fi

# On a case-insensitive volume `.GIT` aliases the canonical marker lookup.
# Directory-entry spelling, not that later lookup, must reject it before the
# launcher can create task/provider artifacts.
project_casefold_nested_dir="$TMP/project-worktree/nested-casefold"
mkdir -p "$project_casefold_nested_dir"
printf 'nested alias marker\n' > "$project_casefold_nested_dir/.GIT"
printf 'casefold nested Git marker\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" \
    run_worker project-nested-git-casefold --workflow project \
    > "$TMP/project-nested-git-casefold.out" 2> "$TMP/project-nested-git-casefold.err"
project_casefold_nested_rc=$?
rm -rf "$project_casefold_nested_dir"
if [[ "$project_casefold_nested_rc" == 64 && ! -e "$TMP/logs/project-nested-git-casefold/task.txt" ]]; then
    ok "project shell preflight rejects casefold nested .GIT aliases before provider setup"
else
    bad "project shell casefold nested Git marker boundary"
fi

cp "$TMP/project-worktree/.git" "$TMP/project-marker.saved"
printf 'project marker drift\n' | AGY_TEST_WORKDIR="$TMP/project-worktree" \
    FAKE_MUTATE_PROJECT_MARKER="$TMP/project-worktree/.git" run_worker project-marker-drift --workflow project \
    > "$TMP/project-marker-drift.out" 2> "$TMP/project-marker-drift.err"
project_marker_rc=$?
cp "$TMP/project-marker.saved" "$TMP/project-worktree/.git"
control_worker status project-marker-drift > "$TMP/project-marker-drift.status"
if [[ "$project_marker_rc" == 20 ]] && python3 - "$TMP/project-marker-drift.status" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["status"] == "failed"
assert value["phase"] == "blocked"
assert value["assurance"] is None
assert value["continue_available"] is False
PY
then
    ok "project workflow binds the linked-worktree marker before and after provider execution"
else
    bad "project workflow marker drift boundary"
fi

cp "$TMP/project-worktree/.git" "$TMP/project-marker-sparse-post.saved"
printf 'project sparse marker drift after provider start\n' | \
    AGY_TEST_WORKDIR="$TMP/project-worktree" \
    FAKE_SPARSE_PROJECT_MARKER="$TMP/project-worktree/.git" \
    run_worker project-marker-sparse-post --workflow project \
    > "$TMP/project-marker-sparse-post.out" 2> "$TMP/project-marker-sparse-post.err"
project_marker_sparse_post_rc=$?
cp "$TMP/project-marker-sparse-post.saved" "$TMP/project-worktree/.git"
control_worker status project-marker-sparse-post > "$TMP/project-marker-sparse-post.status"
project_marker_sparse_post_calls="$(wc -l < "$TMP/project-marker-sparse-post.worker-calls" | tr -d ' ')"
if [[ "$project_marker_sparse_post_rc" == 20 && "$project_marker_sparse_post_calls" == 1 ]] \
        && python3 - "$TMP/project-marker-sparse-post.status" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value["status"] == "failed"
assert value["phase"] == "blocked"
assert value["assurance"] is None
assert value["has_prior_candidate"] is False
PY
then
    ok "project post-provider boundary rejects a sparse oversized marker without accepting a result"
else
    bad "project post-provider sparse marker boundary"
fi

printf 'project boundary cannot rebaseline between cycles\n' | \
    FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    AGY_TEST_WORKDIR="$TMP/project-worktree" start_worker project-between-cycle-drift \
    --workflow project --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-between-cycle-drift.start" 2> "$TMP/project-between-cycle-drift.err"
wait_terminal project-between-cycle-drift "$TMP/project-between-cycle-drift.start"
control_worker status project-between-cycle-drift > "$TMP/project-between-cycle-drift.status"
project_between_sha="$(status_sha "$TMP/project-between-cycle-drift.status")"
cp "$TMP/logs/project-between-cycle-drift/dispatch-state.json" \
    "$TMP/project-between-cycle-drift.state-before"
mv "$TMP/project-worktree/.git" "$TMP/project-between-cycle-drift.marker"
printf 'gitdir: between-cycle-tamper\n' > "$TMP/project-worktree/.git"
project_between_calls_before="$(wc -l < "$TMP/project-between-cycle-drift.worker-calls" | tr -d ' ')"
project_feedback project-between-cycle-drift | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker continue project-between-cycle-drift --approve-state-sha "$project_between_sha" \
    > "$TMP/project-between-cycle-drift.continue" 2> "$TMP/project-between-cycle-drift.continue.err"
project_between_rc=$?
project_between_calls_after="$(wc -l < "$TMP/project-between-cycle-drift.worker-calls" | tr -d ' ')"
rm "$TMP/project-worktree/.git"
mv "$TMP/project-between-cycle-drift.marker" "$TMP/project-worktree/.git"
if [[ "$project_between_rc" == 64 \
        && "$project_between_calls_before" == 1 \
        && "$project_between_calls_after" == "$project_between_calls_before" \
        && ! -e "$TMP/logs/project-between-cycle-drift/continue-staged/cycle-002.json" ]] \
        && cmp -s "$TMP/project-between-cycle-drift.state-before" \
            "$TMP/logs/project-between-cycle-drift/dispatch-state.json"; then
    ok "project continuation rejects between-cycle marker drift without provider call or state replacement"
else
    bad "project continuation must not rebaseline a changed worktree boundary"
fi

project_oversized_boundary_case() {
    local job="$1" fixture_kind="$2" description="$3"
    printf 'project oversized boundary fixture\n' | \
        FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
        AGY_TEST_WORKDIR="$TMP/project-worktree" start_worker "$job" \
        --workflow project --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
        > "$TMP/$job.start" 2> "$TMP/$job.err"
    wait_terminal "$job" "$TMP/$job.start"
    control_worker status "$job" > "$TMP/$job.status"
    local approved_sha calls_before calls_after continue_rc
    approved_sha="$(status_sha "$TMP/$job.status")"
    cp "$TMP/logs/$job/dispatch-state.json" "$TMP/$job.state-before"
    mv "$TMP/project-worktree/.git" "$TMP/$job.marker"
    if [[ "$fixture_kind" == "dense" ]]; then
        PYTHONDONTWRITEBYTECODE=1 python3 - "$TMP/project-worktree/.git" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"x" * 4097)
PY
    else
        PYTHONDONTWRITEBYTECODE=1 python3 - "$TMP/project-worktree/.git" <<'PY'
import os
import sys
descriptor = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.ftruncate(descriptor, 1 << 20)
finally:
    os.close(descriptor)
PY
    fi
    calls_before="$(wc -l < "$TMP/$job.worker-calls" | tr -d ' ')"
    project_feedback "$job" | control_worker continue "$job" --approve-state-sha "$approved_sha" \
        > "$TMP/$job.continue" 2> "$TMP/$job.continue.err"
    continue_rc=$?
    calls_after="$(wc -l < "$TMP/$job.worker-calls" | tr -d ' ')"
    rm "$TMP/project-worktree/.git"
    mv "$TMP/$job.marker" "$TMP/project-worktree/.git"
    if [[ "$continue_rc" == 64 && "$calls_before" == 1 && "$calls_after" == "$calls_before" \
            && ! -e "$TMP/logs/$job/continue-staged/cycle-002.json" ]] \
            && cmp -s "$TMP/$job.state-before" "$TMP/logs/$job/dispatch-state.json"; then
        ok "$description"
    else
        bad "$description"
    fi
}

project_oversized_boundary_case project-between-cycle-oversized dense \
    "project continuation rejects a 4097-byte marker before state replacement or provider call"
project_oversized_boundary_case project-between-cycle-sparse sparse \
    "project continuation rejects a sparse oversized marker before state replacement or provider call"

printf 'project orphan preserve-only fixture\n' | \
    FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    AGY_TEST_WORKDIR="$TMP/project-worktree" start_worker project-orphan-preserve \
    --workflow project --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-orphan-preserve.start" 2> "$TMP/project-orphan-preserve.err"
wait_terminal project-orphan-preserve "$TMP/project-orphan-preserve.start"
PROJECT_ORPHAN_JOB="$TMP/logs/project-orphan-preserve"
PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$PROJECT_ORPHAN_JOB" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location("agy_dispatch_project_orphan", sys.argv[1])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
job = Path(sys.argv[2])
state, raw, _sha = module.load_state(job)
state.update({
    "sequence": state["sequence"] + 1,
    "previous_state_sha256": module.digest(raw),
    "status": "orphaned", "reason": "status_unavailable", "exit_code": 20,
    "attempt": 2, "cycle": 2, "attempt_origin": "conversation-continue",
    "controller_pid": None, "finished_epoch": 1.0,
    "resume_available": False, "continue_available": False,
    "result_path": None, "result_sha256": None, "result_identity": None,
    "last_success_path": state["result_path"],
    "last_success_sha256": state["result_sha256"],
    "last_success_identity": state["result_identity"],
    "phase": "repairing", "assurance": "pending",
})
module.write_atomic(job, module.STATE_NAME, state)
PY
project_orphan_sha="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$PROJECT_ORPHAN_JOB/dispatch-state.json" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
cp "$PROJECT_ORPHAN_JOB/dispatch-state.json" "$TMP/project-orphan-preserve.state-before"
project_orphan_calls_before="$(wc -l < "$TMP/project-orphan-preserve.worker-calls" | tr -d ' ')"
project_feedback project-orphan-preserve | control_worker continue project-orphan-preserve \
    --approve-state-sha "$project_orphan_sha" > /dev/null 2>&1
project_orphan_continue_rc=$?
control_worker resume project-orphan-preserve \
    --approve-state-sha "$project_orphan_sha" > /dev/null 2>&1
project_orphan_resume_rc=$?
control_worker restart project-orphan-preserve \
    --approve-state-sha "$project_orphan_sha" > /dev/null 2>&1
project_orphan_restart_rc=$?
project_feedback project-orphan-preserve | control_worker finalize project-orphan-preserve \
    --approve-state-sha "$project_orphan_sha" --assurance partially_verified > /dev/null 2>&1
project_orphan_finalize_rc=$?
control_worker result project-orphan-preserve > /dev/null 2>&1
project_orphan_result_rc=$?
project_orphan_calls_after="$(wc -l < "$TMP/project-orphan-preserve.worker-calls" | tr -d ' ')"
if [[ "$project_orphan_continue_rc" == 64 && "$project_orphan_resume_rc" == 21 \
        && "$project_orphan_restart_rc" == 64 && "$project_orphan_finalize_rc" == 64 \
        && "$project_orphan_result_rc" == 20 \
        && "$project_orphan_calls_after" == "$project_orphan_calls_before" ]] \
        && cmp -s "$TMP/project-orphan-preserve.state-before" \
            "$PROJECT_ORPHAN_JOB/dispatch-state.json"; then
    ok "orphaned project state is preserve-only across continuation, finalization, and result surfaces"
else
    bad "orphaned project state must not progress or expose a trusted partial result"
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/logs/project-between-cycle-drift" "$TMP/project-worktree" <<'PY'
import importlib.util
from pathlib import Path
import sys
source, job_text, workdir = sys.argv[1:]
spec = importlib.util.spec_from_file_location("agy_dispatch_rollback", source)
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
job = Path(job_text)
before = (job / module.STATE_NAME).read_bytes()
state, _raw, sha = module.load_state(job)
verification = {"schema_version": 2, "summary": "retryable injected write failure",
    "passed_checks": ["lint"], "failed_checks": ["unit"],
    "advisory_checks": 0, "missing_checks": 0,
    "candidate_sha256": state["result_sha256"], "coverage": "partial",
    "verified_findings": 0, "unresolved_gaps": 1, "diff_review_complete": True}
original = module.write_atomic
def fail_state_write(target, name, value):
    if name == module.STATE_NAME:
        raise module.DispatchError("injected state write failure")
    return original(target, name, value)
module.write_atomic = fail_state_write
try:
    module.create_state(job, "conversation-continue", resume=True,
        approve_sha=sha, verification=verification)
except module.DispatchError as exc:
    assert str(exc) == "injected state write failure"
else:
    raise AssertionError("injected write unexpectedly succeeded")
finally:
    module.write_atomic = original
assert (job / module.STATE_NAME).read_bytes() == before
assert not (job / "continue-staged" / "cycle-002.json").exists()
next_state, _next_sha = module.create_state(job, "conversation-continue", resume=True,
    approve_sha=sha, verification=verification)
assert next_state["cycle"] == 2 and next_state["phase"] == "repairing"
PY
verification_rollback_rc=$?
if [[ "$verification_rollback_rc" == 0 ]]; then
    ok "verification staging rolls back exactly on injected state-write failure and retries cleanly"
else
    bad "verification staging rollback and retry"
fi

PYTHONDONTWRITEBYTECODE=1 python3 - "$ROOT/skills/agy-worker/runtime/scripts/agy_dispatch.py" \
        "$TMP/boundary-cap" <<'PY'
import importlib.util
import os
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location("agy_dispatch_boundary_cap", sys.argv[1])
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
root = Path(sys.argv[2]).resolve(); root.mkdir(mode=0o700)
(root / ".git").write_text("gitdir: bounded\n", encoding="ascii")
(root / "one").write_text("1", encoding="ascii")
(root / "two").write_text("2", encoding="ascii")
module.WORKTREE.MAX_BOUNDARY_ENTRIES = 2
module._project_boundary(str(root))
(root / "three").write_text("3", encoding="ascii")
try:
    module._project_boundary(str(root))
except module.DispatchError as exc:
    assert str(exc) == "project worktree boundary scan is too large"
else:
    raise AssertionError("over-cap boundary scan unexpectedly succeeded")
PY
boundary_cap_rc=$?
if [[ "$boundary_cap_rc" == 0 ]]; then
    ok "project boundary accepts the exact entry cap and rejects one entry over it"
else
    bad "project boundary entry cap"
fi

printf 'project concurrent decision fixture\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_HEARTBEAT_COUNT=2 AGY_TEST_WORKDIR="$TMP/project-worktree" \
    start_worker project-concurrent-decision --workflow project \
    --idle-timeout 1s --hard-timeout 2s --max-runtime 8s \
    > "$TMP/project-concurrent-decision.start" 2> "$TMP/project-concurrent-decision.err"
wait_terminal project-concurrent-decision "$TMP/project-concurrent-decision.start"
control_worker status project-concurrent-decision > "$TMP/project-concurrent-decision.status"
project_concurrent_sha="$(status_sha "$TMP/project-concurrent-decision.status")"
( project_feedback project-concurrent-decision | FAKE_DISPATCH_MODE=heartbeat-success FAKE_HEARTBEAT_COUNT=2 \
    control_worker continue project-concurrent-decision --approve-state-sha "$project_concurrent_sha" \
    > "$TMP/project-concurrent-decision.continue" 2> /dev/null; \
    printf '%s\n' "$?" > "$TMP/project-concurrent-decision.continue.rc" ) &
project_concurrent_continue_pid=$!
( project_feedback project-concurrent-decision | control_worker finalize project-concurrent-decision \
    --approve-state-sha "$project_concurrent_sha" --assurance partially_verified \
    > "$TMP/project-concurrent-decision.finalize" 2> /dev/null; \
    printf '%s\n' "$?" > "$TMP/project-concurrent-decision.finalize.rc" ) &
project_concurrent_finalize_pid=$!
wait "$project_concurrent_continue_pid"
wait "$project_concurrent_finalize_pid"
project_concurrent_continue_rc="$(<"$TMP/project-concurrent-decision.continue.rc")"
project_concurrent_finalize_rc="$(<"$TMP/project-concurrent-decision.finalize.rc")"
if [[ "$project_concurrent_continue_rc" == 0 ]]; then
    wait_terminal project-concurrent-decision "$TMP/project-concurrent-decision.continue"
fi
project_concurrent_calls="$(wc -l < "$TMP/project-concurrent-decision.worker-calls" | tr -d ' ')"
if [[ $(( (project_concurrent_continue_rc == 0 ? 1 : 0) \
        + (project_concurrent_finalize_rc == 0 ? 1 : 0) )) == 1 \
        && "$project_concurrent_calls" -ge 1 && "$project_concurrent_calls" -le 2 ]]; then
    ok "concurrent continue and finalize on one approved SHA publish exactly one winner"
else
    bad "concurrent project continuation/finalization arbitration"
fi

printf 'project cancel repair fixture\n' | FAKE_DISPATCH_MODE=heartbeat-success \
    FAKE_HEARTBEAT_COUNT=2 AGY_TEST_WORKDIR="$TMP/project-worktree" \
    start_worker project-cancel-repair --workflow project --idle-timeout 1s --hard-timeout 3s --max-runtime 8s \
    > "$TMP/project-cancel-repair.start" 2> "$TMP/project-cancel-repair.err"
wait_terminal project-cancel-repair "$TMP/project-cancel-repair.start"
control_worker status project-cancel-repair > "$TMP/project-cancel-repair.status"
project_cancel_sha="$(status_sha "$TMP/project-cancel-repair.status")"
project_cancel_barrier_ready="$TMP/project-cancel-repair.barrier-ready"
project_cancel_barrier_release="$TMP/project-cancel-repair.barrier-release"
project_feedback project-cancel-repair | FAKE_DISPATCH_MODE=heartbeat-forever \
    FAKE_HEARTBEAT_BARRIER_READY="$project_cancel_barrier_ready" \
    FAKE_HEARTBEAT_BARRIER_RELEASE="$project_cancel_barrier_release" \
    control_worker continue project-cancel-repair --approve-state-sha "$project_cancel_sha" \
    > "$TMP/project-cancel-repair.continue" 2> "$TMP/project-cancel-repair.continue.err"
project_cancel_barrier_observed=0
# Controller ownership is acknowledged before its strict candidate/worktree
# preflight.  Under full-suite scheduling that bounded preflight can outlive a
# two-second fixture poll even though the public startup handshake remains
# healthy.  Observe the same five-second bound as spawn(); do not manufacture
# progress or weaken the provider hard deadline.
for (( project_cancel_index=0; project_cancel_index<500; project_cancel_index++ )); do
    if [[ -e "$project_cancel_barrier_ready" ]]; then
        control_worker status project-cancel-repair > "$TMP/project-cancel-repair.running"
        if [[ "$(status_field "$TMP/project-cancel-repair.running" progress_count)" -ge 1 ]]; then
            project_cancel_barrier_observed=1
            break
        fi
    fi
    sleep 0.01
done
project_cancel_rc=64
project_cancel_wait_rc=64
project_cancel_finalize_rc=64
project_cancel_result_rc=64
project_cancel_latency_ok=0
project_cancel_preserved_rc=64
if [[ "$project_cancel_barrier_observed" == 1 ]]; then
    project_cancel_running_sha="$(status_sha "$TMP/project-cancel-repair.running")"
    project_cancel_started_epoch="$(python3 -c 'import time; print(time.time())')"
    control_worker cancel project-cancel-repair --approve-state-sha "$project_cancel_running_sha" \
        > "$TMP/project-cancel-repair.cancel"
    project_cancel_rc=$?
fi
: > "$project_cancel_barrier_release"
if [[ "$project_cancel_rc" == 0 ]] \
        && wait_terminal project-cancel-repair "$TMP/project-cancel-repair.cancel"; then
    project_cancel_wait_rc=0
    if python3 - "$project_cancel_started_epoch" \
            "$TMP/logs/project-cancel-repair/dispatch-state.json" <<'PY'
import json
import sys
started = float(sys.argv[1])
state = json.load(open(sys.argv[2], encoding="utf-8"))
# Measure the terminal state transition itself. The subsequent public wait
# deliberately rebinds candidate actions and can include a bounded Git scan.
assert 0 <= state["finished_epoch"] - started < 2.0
PY
    then
        project_cancel_latency_ok=1
    fi
    if python3 - "$TMP/logs/project-cancel-repair/dispatch-state.json" <<'PY'
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert (state["status"], state["reason"]) == ("cancelled", "cancelled")
assert state["candidate_recognized"] is True
assert state["candidate_source"] == "provider_success"
assert state["result_available"] is True
assert state["driver_disposition"] == "unreviewed"
# A local repair cancellation adds no new provider candidate/worktree fact.
# Preserve the old exact binding and let result/finalize rebind it on use.
assert state["worktree_reconciliation"] == "unavailable"
PY
    then
        project_cancel_preserved_rc=0
    fi
    project_cancel_terminal_sha="$(status_sha "$TMP/project-cancel-repair.cancel")"
    project_feedback project-cancel-repair | control_worker finalize project-cancel-repair \
        --approve-state-sha "$project_cancel_terminal_sha" --assurance partially_verified \
        > "$TMP/project-cancel-repair.finalize"
    project_cancel_finalize_rc=$?
    control_worker result project-cancel-repair > "$TMP/project-cancel-repair.result"
    project_cancel_result_rc=$?
fi
if [[ "$project_cancel_wait_rc" == 0 && "$project_cancel_latency_ok" == 1 \
        && "$project_cancel_preserved_rc" == 0 \
        && "$project_cancel_finalize_rc" == 0 \
        && "$project_cancel_result_rc" == 0 ]]; then
    ok "cancelled repair can partially finalize and return the prior bound success"
else
    bad "cancelled repair prior-candidate finalization"
fi

SYMLINK_STATE_DIR="$TMP/logs/resume-unavailable"
mv "$SYMLINK_STATE_DIR/dispatch-state.json" "$SYMLINK_STATE_DIR/dispatch-state.real"
ln -s dispatch-state.real "$SYMLINK_STATE_DIR/dispatch-state.json"
control_worker status resume-unavailable > "$TMP/symlink-state.out" 2> "$TMP/symlink-state.err"
symlink_state_rc=$?
if [[ "$symlink_state_rc" == 20 ]] && [[ ! -s "$TMP/symlink-state.out" ]]; then
    ok "control state refuses symlink replacement rather than following a swapped state file"
else
    bad "control state symlink replacement"
fi

echo
# Exercise the actual resolved core after copying only the public skill folder.
if python3 -B - "$ROOT" "$TMP" <<'PY'
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
tmp = Path(sys.argv[2]).resolve() / "folder-only-workflow"
tmp.mkdir(mode=0o700)
skill = tmp / "skill"
shutil.copytree(root / "skills/agy-worker", skill)
assert not (skill / ".pipeline-root").exists()
assert not (skill / "runtime/scripts/benchmark.py").exists()
assert not (skill / "runtime/scripts/model_intelligence.py").exists()
resolved = subprocess.run(["bash", str(skill / "scripts/resolve-pipeline.sh")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
runtime = Path(resolved.stdout.decode().strip())
assert runtime == skill / "runtime" and not resolved.stderr
bin_dir = tmp / "bin"
bin_dir.mkdir(mode=0o700)
shutil.copy2(Path(sys.argv[2]) / "bin/agy.package-original", bin_dir / "agy")
env = {key: value for key, value in os.environ.items() if not key.startswith(("FAKE_", "AGY_WORKER_"))}
env["PATH"] = str(bin_dir) + ":" + os.environ["PATH"]
env["XDG_STATE_HOME"] = str(tmp / "state-home")
Path(env["XDG_STATE_HOME"]).mkdir(mode=0o700)
fake_outputs = ("FAKE_MODEL_FILE", "FAKE_PROMPT_FILE", "FAKE_DIRS_FILE", "FAKE_ARGV_FILE", "FAKE_STAGE_RESULT_FILE")
for name in fake_outputs:
    env[name] = str(tmp / name.lower())
provider_arguments = [argument for name in fake_outputs for argument in ("--provider-env", name)]
repo = tmp / "repo"
repo.mkdir(mode=0o700)
def call(*argv, expected=0):
    result = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    assert result.returncode == expected, (argv, result.returncode, result.stderr)
    return result
call("/usr/bin/git", "-C", str(repo), "init", "-q")
(repo / "proof.txt").write_text("unchanged fixture\n")
call("/usr/bin/git", "-C", str(repo), "add", "proof.txt")
call("/usr/bin/git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
workflow = str(runtime / "workflow.sh")
preview = json.loads(call(workflow, "run", "--repo", str(repo), "--job-id", "folder-only", "--preview", "--model", "literal", "--task", "Return the unchanged synthetic candidate", *provider_arguments).stdout)
call(workflow, "run", "--repo", str(repo), "--job-id", "folder-only", "--approve-whole-worktree", preview["launch_approval_sha256"], "--model", "literal", "--task", "Return the unchanged synthetic candidate", *provider_arguments)
state_files = list(Path(env["XDG_STATE_HOME"]).glob("agy-worker/workflows/*/folder-only/workflow.json"))
assert len(state_files) == 1
state_file = state_files[0]
workflow_state = json.loads(state_file.read_bytes())
job = Path(workflow_state["dispatch_job_dir"])
# The ordinary synchronous facade must expose the provider candidate for review.
status = json.loads(call(workflow, "status", "--state", str(state_file)).stdout)
dispatch = json.loads((job / "dispatch-state.json").read_bytes())
assert dispatch["status"] == "succeeded" and dispatch["phase"] == "awaiting-verification"
assert status["dispatch"]["state_sha256"]
candidate_root = Path(workflow_state["worktree_path"])
assert (candidate_root / "proof.txt").read_text() == "unchanged fixture\n"
assert not call("/usr/bin/git", "-C", str(candidate_root), "status", "--porcelain=v1", "--untracked-files=all").stdout
verification = {
    "schema_version": 2, "summary": "Driver checked unchanged fixture",
    "passed_checks": ["exact unchanged fixture", "driver diff review"], "failed_checks": [],
    "advisory_checks": 0, "missing_checks": 0,
    "candidate_sha256": dispatch["result_sha256"], "coverage": "complete",
    "verified_findings": 0, "unresolved_gaps": 0, "diff_review_complete": True,
}
verification_path = tmp / "verification.json"
verification_path.write_text(json.dumps(verification))
verification_path.chmod(0o600)
receipt = tmp / "receipt.json"
call(workflow, "verify-finalize", "--state", str(state_file), "--receipt", str(receipt), "--envelope", dispatch["result_path"], "--verify-argv", '["/usr/bin/git","diff","--check"]', "--assurance", "verified", "--approve-dispatch-sha", status["dispatch"]["state_sha256"], "--verification-json", str(verification_path))
assert json.loads(receipt.read_bytes())["verdict"] == "gate-passed"
final = json.loads(call(workflow, "status", "--state", str(state_file)).stdout)
assert final["dispatch"]["assurance"] == "verified"
assert (Path(workflow_state["worktree_path"]) / "proof.txt").read_text() == "unchanged fixture\n"
(runtime / "scripts/candidate_state.py").unlink()
missing = call("bash", str(skill / "scripts/resolve-pipeline.sh"), expected=2)
assert not missing.stdout and b"complete agy-worker skill bundle" in missing.stderr
PY
then
    ok "folder-only core resolves and completes synthetic ordinary workflow verification"
else
    bad "folder-only core resolves and completes synthetic ordinary workflow verification"
fi

echo
echo "installer path handling:"
SPECIAL="$TMP/repo&with|chars"
mkdir -p "$SPECIAL/skills" "$TMP/installed"
cp "$ROOT/install.sh" "$SPECIAL/install.sh"
cp -R "$ROOT/skills/agy-worker" "$SPECIAL/skills/agy-worker"
chmod +x "$SPECIAL/install.sh"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$TMP/installed" "$SPECIAL/install.sh" > "$TMP/install.out" 2>/dev/null
rc=$?
expect_exit "installer accepts replacement metacharacters in clone path" 0 "$rc"
SPECIAL_REAL="$(cd "$SPECIAL" && pwd -P)"
if [[ "$(<"$TMP/installed/agy-worker/.pipeline-root")" == "$SPECIAL_REAL" ]] \
        && [[ -f "$TMP/installed/agy-worker/agents/openai.yaml" ]] \
        && [[ -x "$TMP/installed/agy-worker/scripts/resolve-pipeline.sh" ]]; then
    ok "installer copies the canonical bundle and records the exact clone path"
else
    bad "installer copies the canonical bundle and records the exact clone path"
fi

echo
if (( fail )); then
    echo "FAILED: $fail failed, $pass passed"
    exit 1
fi
echo "PASSED: $pass tests"
