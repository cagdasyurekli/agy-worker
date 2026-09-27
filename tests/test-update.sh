#!/usr/bin/env bash
# Offline updater tests using local Git repositories and release tags.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HERE/.."
TMP="$(mktemp -d -t agyworker-update-tests.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
REAL_PYTHON_REAL="$(command -v python3)"
export REAL_PYTHON_REAL

ok() { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail+1)); }
expect_exit() {
    local name="$1" want="$2" got="$3"
    if [[ "$got" == "$want" ]]; then ok "$name (exit $got)"; else bad "$name (exit $got, wanted $want)"; fi
}
snapshot_repo() {
    local repo="$1" output="$2"
    python3 - "$repo" "$output" <<'PY'
import hashlib
import json
import os
import subprocess
import sys

repo, output = sys.argv[1:]

def git(*args):
    return subprocess.run(
        ["git", "-C", repo, *args],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout

paths = {
    item
    for item in git(
        "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"
    ).split(b"\0")
    if item
}

files = []
for encoded in sorted(paths):
    relative = os.fsdecode(encoded)
    path = os.path.join(repo, relative)
    if os.path.islink(path):
        kind = "symlink"
        digest = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    elif os.path.isfile(path):
        kind = "file"
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
    elif os.path.isdir(path):
        kind = "directory"
        digest = ""
    else:
        kind = "missing"
        digest = ""
    files.append([relative, kind, digest])

state = {
    "head": git("rev-parse", "HEAD").decode("ascii").strip(),
    "head_ref": git("symbolic-ref", "-q", "HEAD").decode("utf-8").strip(),
    "refs_hex": git("for-each-ref", "--format=%(refname)%00%(objectname)").hex(),
    "index_hex": git("ls-files", "--stage", "-z", "--").hex(),
    "status_hex": git(
        "status", "--porcelain=v1", "-z", "--untracked-files=all"
    ).hex(),
    "tracked_and_untracked_bytes": files,
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True, separators=(",", ":"))
PY
}
snapshot_ignored_pyc() {
    git -C "$ROOT" ls-files --others --ignored --exclude-standard -z -- '*.pyc' > "$1"
}
expect_same_snapshot() {
    local name="$1" before="$2" after="$3"
    if cmp -s "$before" "$after"; then ok "$name"; else bad "$name"; fi
}

SOURCE="$TMP/source"
REMOTE="$TMP/remote.git"
NO_TAG_REMOTE="$TMP/no-tag-remote.git"
CLIENT="$TMP/client"
DIRTY_CLIENT="$TMP/dirty-client"
NO_TAG_CLIENT="$TMP/no-tag-client"
IGNORED_CLIENT="$TMP/ignored-client"
INSTALL_FAIL_CLIENT="$TMP/install-fail-client"
SKILLS="$TMP/skills"
OFFICIAL_TOOL_URL="https://github.com/cagdasyurekli/codex-agy-worker.git"
mkdir -p "$SOURCE/skills" "$SOURCE/tests" "$SOURCE/scripts" "$TMP/bin" "$SKILLS"
cp "$ROOT/update.sh" "$ROOT/install.sh" "$SOURCE/"
cp -R "$ROOT/skills/agy-worker" "$SOURCE/skills/agy-worker"
cp "$ROOT/scripts/official_github.py" "$SOURCE/scripts/"
cp "$ROOT/scripts/compatibility_probe.py" "$SOURCE/scripts/"

cat > "$SOURCE/tests/test-qa-gate.sh" <<'STUB'
#!/usr/bin/env bash
echo "fixture qa suite passed"
STUB
cat > "$SOURCE/tests/test-agy-worker.sh" <<'STUB'
#!/usr/bin/env bash
echo "fixture dispatcher suite passed"
STUB
cat > "$TMP/bin/python3" <<'STUB'
#!/usr/bin/env bash
set -u
arguments=("$@")
while [[ "${1:-}" == "-I" || "${1:-}" == "-B" ]]; do shift; done
case "${1:-}" in
  */scripts/compatibility_probe.py)
    probe_script="$1"
    profile="${2:-}"
    argument="${3:-}"
    case "$profile" in
      official-project)
        case "${FAKE_PROJECT_OFFICIAL_MODE:-unchanged}" in
          unavailable) exit 2 ;;
          malformed) printf '%s\n' 'private malformed evidence'; exit 0 ;;
          signal-hup) exit 129 ;;
          signal-int) exit 130 ;;
          signal-term) exit 143 ;;
        esac
        tag="${FAKE_PROJECT_TAG:-v1.1.0}"
        revision="$(git --git-dir="$FAKE_PROJECT_REMOTE" rev-parse "refs/tags/$tag^{commit}" 2>/dev/null)" || exit 2
        printf 'project\t%s\t%s\n' "$tag" "$revision"
        ;;
      official-project-release)
        [[ "$argument" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || exit 2
        revision="$(git --git-dir="$FAKE_PROJECT_REMOTE" rev-parse "refs/tags/$argument^{commit}" 2>/dev/null)" || exit 2
        printf 'project\t%s\t%s\n' "$argument" "$revision"
        ;;
      *) exit 2 ;;
    esac
    exit 0
    ;;

esac
exec "$REAL_PYTHON_REAL" "${arguments[@]}"
STUB
chmod +x "$SOURCE/"*.sh "$SOURCE/tests/"*.sh "$TMP/bin/python3" \
    "$SOURCE/scripts/official_github.py" "$SOURCE/scripts/compatibility_probe.py"

git -C "$SOURCE" init -q -b main
git -C "$SOURCE" config user.email test@example.com
git -C "$SOURCE" config user.name test
printf 'v1\n' > "$SOURCE/release-marker.txt"
printf '*.cache\n' > "$SOURCE/.gitignore"
git -C "$SOURCE" add -A
git -C "$SOURCE" commit -qm 'v1 fixture'
git -C "$SOURCE" tag v1.0.0
printf 'v2\n' > "$SOURCE/release-marker.txt"
printf 'release-owned cache\n' > "$SOURCE/private.cache"
git -C "$SOURCE" add release-marker.txt
git -C "$SOURCE" add -f private.cache
git -C "$SOURCE" commit -qm 'v2 fixture'
V2_COMMIT="$(git -C "$SOURCE" rev-parse HEAD)"
git -C "$SOURCE" tag v1.1.0

git init -q --bare "$REMOTE"
git -C "$SOURCE" remote add publish "$REMOTE"
git -C "$SOURCE" push -q publish main --tags
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main
export FAKE_PROJECT_REMOTE="$REMOTE"
git init -q --bare "$NO_TAG_REMOTE"
git -C "$SOURCE" push -q "$NO_TAG_REMOTE" main
git --git-dir="$NO_TAG_REMOTE" symbolic-ref HEAD refs/heads/main
git clone -q "$REMOTE" "$CLIENT"
git clone -q "$REMOTE" "$DIRTY_CLIENT"
git clone -q "$REMOTE" "$IGNORED_CLIENT"
git clone -q "$REMOTE" "$INSTALL_FAIL_CLIENT"
git clone -q "$NO_TAG_REMOTE" "$NO_TAG_CLIENT"

configure_official_urls() {
    local checkout="$1" release_remote="$2"
    git -C "$checkout" remote set-url origin "$OFFICIAL_TOOL_URL"
    git -C "$checkout" config "url.$release_remote.insteadOf" "$OFFICIAL_TOOL_URL"
}

for checkout in "$CLIENT" "$DIRTY_CLIENT" "$IGNORED_CLIENT" "$INSTALL_FAIL_CLIENT"; do
    git -C "$checkout" checkout -qb local-v1 v1.0.0
    git -C "$checkout" tag -d v1.1.0 >/dev/null
    configure_official_urls "$checkout" "$REMOTE"
done
configure_official_urls "$NO_TAG_CLIENT" "$NO_TAG_REMOTE"

echo "update.sh offline test suite"
echo

# These cases exercise the project watch path without any installed AGY/Codex.
for mode in local watch; do
    arguments=(check)
    [[ "$mode" == local ]] || arguments+=(--watch)
    for observation in unchanged changed unavailable malformed; do
        expected=3
        tag=v1.1.0
        official_mode=unchanged
        case "$observation" in
            unchanged) expected=0; tag=v1.0.0 ;;
            unavailable) expected=2; official_mode=unavailable ;;
            malformed) expected=2; official_mode=malformed ;;
        esac
        snapshot_repo "$CLIENT" "$TMP/check.before"
        PATH="$TMP/bin:$PATH" FAKE_PROJECT_TAG="$tag" FAKE_PROJECT_OFFICIAL_MODE="$official_mode" \
            "$CLIENT/update.sh" "${arguments[@]}" > "$TMP/check.out" 2> "$TMP/check.err"
        rc=$?
        expect_exit "$mode project $observation" "$expected" "$rc"
        snapshot_repo "$CLIENT" "$TMP/check.after"
        expect_same_snapshot "$mode $observation preserves HEAD, refs, index and bytes" \
            "$TMP/check.before" "$TMP/check.after"
        if [[ "$observation" == changed ]]; then
            if grep -Fq 'different release commit (v1.0.0; official v1.1.0)' "$TMP/check.out"; then
                ok "$mode identifies both tags without inferring ordering"
            else bad "$mode identifies both tags without inferring ordering"; fi
        fi
    done
done

NO_AGY_BIN="$TMP/no-agy-bin"
mkdir -p "$NO_AGY_BIN"
for required_tool in bash git dirname; do
    ln -s "$(command -v "$required_tool")" "$NO_AGY_BIN/$required_tool"
done
ln -s "$TMP/bin/python3" "$NO_AGY_BIN/python3"
PATH="$NO_AGY_BIN" FAKE_PROJECT_TAG=v1.0.0 "$CLIENT/update.sh" check --watch > "$TMP/no-tools.out" 2>&1
expect_exit "watch works without installed AGY or Codex" 0 "$?"

# A checkout without a matching local tag must not acquire a version-order claim.
git -C "$CLIENT" tag -d v1.0.0 >/dev/null
PATH="$TMP/bin:$PATH" "$CLIENT/update.sh" check --watch > "$TMP/untagged.out" 2>&1
expect_exit "untagged checkout observes a different official commit" 3 "$?"
if grep -Fq 'current checkout is not release-tagged' "$TMP/untagged.out"; then
    ok "untagged state is explicit"
else bad "untagged state is explicit"; fi
git -C "$CLIENT" tag v1.0.0

REAL_GIT="$(command -v git)"
export REAL_GIT
NO_REMOTE_GIT_BIN="$TMP/no-remote-git-bin"
mkdir -p "$NO_REMOTE_GIT_BIN"
cat > "$NO_REMOTE_GIT_BIN/git" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "ls-remote" ]]; then
    : > "$GIT_LS_REMOTE_MARKER"
    exit 91
fi
exec "$REAL_GIT" "$@"
STUB
chmod +x "$NO_REMOTE_GIT_BIN/git"
cat > "$TMP/hostile-global.gitconfig" <<'EOF'
[url "https://credential.invalid/"]
    insteadOf = https://github.com/
[http]
    proxy = https://credential.invalid/proxy
[credential]
    helper = !printf credential-secret
EOF
GIT_LS_REMOTE_MARKER="$TMP/ls-remote.marker" \
GIT_CONFIG_GLOBAL="$TMP/hostile-global.gitconfig" \
HTTP_PROXY=https://credential.invalid/proxy \
HTTPS_PROXY=https://credential.invalid/proxy \
GIT_ASKPASS="$TMP/credential-askpass" \
PATH="$NO_REMOTE_GIT_BIN:$TMP/bin:$PATH" \
    "$CLIENT/update.sh" check --watch \
    > "$TMP/ambient-transport.out" 2> "$TMP/ambient-transport.err"
rc=$?
expect_exit "ambient Git rewrite/proxy/credential controls cannot redirect watch evidence" 3 "$rc"
if [[ ! -e "$TMP/ls-remote.marker" ]] \
        && ! grep -Eq 'credential\.invalid|credential-secret' \
            "$TMP/ambient-transport.out" "$TMP/ambient-transport.err"; then
    ok "watch performs no Git network query and discloses no ambient transport bytes"
else
    bad "watch performs no Git network query and discloses no ambient transport bytes"
fi

for signal_case in hup int term; do
    case "$signal_case" in
        hup) expected_signal_rc=129 ;;
        int) expected_signal_rc=130 ;;
        term) expected_signal_rc=143 ;;
    esac
    PATH="$TMP/bin:$PATH" FAKE_PROJECT_OFFICIAL_MODE="signal-$signal_case" \
        "$CLIENT/update.sh" check --watch > "$TMP/project-signal-$signal_case.out" \
        2> "$TMP/project-signal-$signal_case.err"
    rc=$?
    expect_exit "project evidence $signal_case signal propagates through update check" \
        "$expected_signal_rc" "$rc"
done

PATH="$TMP/bin:$PATH" FAKE_PROJECT_OFFICIAL_MODE=unavailable CODEX_SKILLS_DIR="$SKILLS" \
    "$NO_TAG_CLIENT/update.sh" apply \
    > "$TMP/no-tag.out" 2> "$TMP/no-tag.err"
rc=$?
expect_exit "implicit apply fails closed when official release evidence is unavailable" 2 "$rc"

printf 'dirty\n' > "$DIRTY_CLIENT/dirty.txt"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$SKILLS" \
    "$DIRTY_CLIENT/update.sh" apply v1.1.0 > "$TMP/dirty.out" 2> "$TMP/dirty.err"
rc=$?
expect_exit "apply refuses a dirty checkout" 2 "$rc"
if [[ "$(git -C "$DIRTY_CLIENT" rev-parse HEAD)" != "$V2_COMMIT" ]]; then ok "dirty refusal leaves HEAD unchanged"; else bad "dirty refusal leaves HEAD unchanged"; fi

printf 'private local bytes\n' > "$IGNORED_CLIENT/private.cache"
IGNORED_BEFORE="$(<"$IGNORED_CLIENT/private.cache")"
IGNORED_HEAD="$(git -C "$IGNORED_CLIENT" rev-parse HEAD)"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$SKILLS" \
    "$IGNORED_CLIENT/update.sh" apply v1.1.0 > "$TMP/ignored.out" 2> "$TMP/ignored.err"
rc=$?
expect_exit "apply refuses an ignored path the release would track" 2 "$rc"
if [[ "$(<"$IGNORED_CLIENT/private.cache")" == "$IGNORED_BEFORE" ]] \
        && [[ "$(git -C "$IGNORED_CLIENT" rev-parse HEAD)" == "$IGNORED_HEAD" ]]; then
    ok "ignored collision refusal preserves bytes and HEAD"
else
    bad "ignored collision refusal preserves bytes and HEAD"
fi

printf 'harmless local cache\n' > "$CLIENT/harmless.cache"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$SKILLS" \
    "$CLIENT/update.sh" apply v1.1.0 > "$TMP/apply.out" 2> "$TMP/apply.err"
rc=$?
expect_exit "explicit apply validates and fast-forwards" 0 "$rc"
if [[ "$(git -C "$CLIENT" rev-parse HEAD)" == "$V2_COMMIT" ]] \
        && [[ "$(<"$CLIENT/release-marker.txt")" == "v2" ]]; then
    ok "apply lands the verified release commit"
else
    bad "apply lands the verified release commit"
fi
CLIENT_REAL="$(cd "$CLIENT" && pwd -P)"
if [[ "$(<"$SKILLS/agy-worker/.pipeline-root")" == "$CLIENT_REAL" ]] \
        && [[ -f "$SKILLS/agy-worker/agents/openai.yaml" ]]; then
    ok "apply reinstalls the canonical Codex skill bundle"
else
    bad "apply reinstalls the canonical Codex skill bundle"
fi
if [[ "$(<"$CLIENT/harmless.cache")" == "harmless local cache" ]]; then ok "harmless ignored cache is preserved"; else bad "harmless ignored cache is preserved"; fi

BLOCKED_SKILLS="$TMP/not-a-directory"
printf 'not a directory\n' > "$BLOCKED_SKILLS"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$BLOCKED_SKILLS" \
    "$INSTALL_FAIL_CLIENT/update.sh" apply v1.1.0 \
    > "$TMP/install-fail.out" 2> "$TMP/install-fail.err"
rc=$?
expect_exit "post-merge skill installation failure is explicit" 4 "$rc"
if [[ "$(git -C "$INSTALL_FAIL_CLIENT" rev-parse HEAD)" == "$V2_COMMIT" ]] \
        && grep -Fq 'PARTIAL UPDATE' "$TMP/install-fail.err" \
        && grep -Fq 'recovery' "$TMP/install-fail.err"; then
    ok "partial update reports exact recovery state"
else
    bad "partial update reports exact recovery state"
fi

printf '#!/usr/bin/env bash\nexit 1\n' > "$SOURCE/tests/test-qa-gate.sh"
chmod +x "$SOURCE/tests/test-qa-gate.sh"
printf 'v3-bad\n' > "$SOURCE/release-marker.txt"
git -C "$SOURCE" add tests/test-qa-gate.sh release-marker.txt
git -C "$SOURCE" commit -qm 'failing candidate fixture'
git -C "$SOURCE" tag v1.2.0
git -C "$SOURCE" push -q publish main --tags
BEFORE_FAILED_APPLY="$(git -C "$CLIENT" rev-parse HEAD)"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$SKILLS" \
    "$CLIENT/update.sh" apply v1.2.0 > "$TMP/failing.out" 2> "$TMP/failing.err"
rc=$?
expect_exit "candidate test failure blocks apply" 2 "$rc"
if [[ "$(git -C "$CLIENT" rev-parse HEAD)" == "$BEFORE_FAILED_APPLY" ]]; then ok "failed candidate leaves checkout unchanged"; else bad "failed candidate leaves checkout unchanged"; fi

cat > "$SOURCE/tests/test-qa-gate.sh" <<'STUB'
#!/usr/bin/env bash
echo "fixture qa suite passed"
STUB
printf '#!/usr/bin/env bash\nexit 1\n' > "$SOURCE/install.sh"
chmod +x "$SOURCE/install.sh" "$SOURCE/tests/test-qa-gate.sh"
git -C "$SOURCE" add install.sh tests/test-qa-gate.sh
git -C "$SOURCE" commit -qm 'failing install preflight fixture'
git -C "$SOURCE" tag v1.3.0
git -C "$SOURCE" push -q publish main --tags
BEFORE_INSTALL_PREFLIGHT="$(git -C "$CLIENT" rev-parse HEAD)"
PATH="$TMP/bin:$PATH" CODEX_SKILLS_DIR="$SKILLS" \
    "$CLIENT/update.sh" apply v1.3.0 > "$TMP/preflight.out" 2> "$TMP/preflight.err"
rc=$?
expect_exit "candidate install preflight blocks a broken installer" 2 "$rc"
if [[ "$(git -C "$CLIENT" rev-parse HEAD)" == "$BEFORE_INSTALL_PREFLIGHT" ]]; then ok "install preflight failure leaves checkout unchanged"; else bad "install preflight failure leaves checkout unchanged"; fi

git -C "$CLIENT" remote set-url origin 'https://user:credential-value@example.invalid/repo.git'
PATH="$TMP/bin:$PATH" \
    "$CLIENT/update.sh" check > "$TMP/unexpected-origin.out" 2> "$TMP/unexpected-origin.err"
rc=$?
expect_exit "default updater refuses an unexpected origin" 2 "$rc"
if ! grep -Fq 'credential-value' "$TMP/unexpected-origin.err"; then
    ok "unexpected origin credentials are redacted"
else
    bad "unexpected origin credentials are redacted"
fi

snapshot_ignored_pyc "$TMP/github-probe-pyc-before"
OFFICIAL_GITHUB_TEST_OUTPUT="$($REAL_PYTHON_REAL -B "$ROOT/tests/test-official-github.py" 2>&1)"
official_github_rc=$?
printf '%s\n' "$OFFICIAL_GITHUB_TEST_OUTPUT"
OFFICIAL_GITHUB_RESULT="$(printf '%s\n' "$OFFICIAL_GITHUB_TEST_OUTPUT" | tail -1)"
if [[ "$official_github_rc" == 0 \
        && "$OFFICIAL_GITHUB_RESULT" =~ ^OFFICIAL_GITHUB_TEST_RESULT\ passed=([0-9]+)\ failed=0$ ]]; then
    pass=$((pass+BASH_REMATCH[1]))
else
    bad "fixed official GitHub transport tests (controlled passes)"
fi

COMPATIBILITY_PROBE_TEST_OUTPUT="$($REAL_PYTHON_REAL -B "$ROOT/tests/test-compatibility-probe.py" 2>&1)"
compatibility_probe_rc=$?
printf '%s\n' "$COMPATIBILITY_PROBE_TEST_OUTPUT"
COMPATIBILITY_PROBE_RESULT="$(printf '%s\n' "$COMPATIBILITY_PROBE_TEST_OUTPUT" | tail -1)"
if [[ "$compatibility_probe_rc" == 0 \
        && "$COMPATIBILITY_PROBE_RESULT" =~ ^COMPATIBILITY_PROBE_TEST_RESULT\ passed=([0-9]+)\ failed=0$ ]]; then
    pass=$((pass+BASH_REMATCH[1]))
else
    bad "bounded compatibility probe tests (controlled passes)"
fi

snapshot_ignored_pyc "$TMP/github-probe-pyc-after"
if cmp -s "$TMP/github-probe-pyc-before" "$TMP/github-probe-pyc-after"; then
    ok "official GitHub and probe tests create no ignored bytecode"
else
    bad "official GitHub and probe tests create no ignored bytecode"
fi


echo
if (( fail )); then
    echo "FAILED: $fail failed, $pass passed"
    exit 1
fi
echo "PASSED: $pass tests"
