#!/usr/bin/env bash
# Explicit project release updater for agy-worker.
# Optional background notification invokes check only; no automatic pull and no
# update from a dirty checkout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REMOTE="origin"
EXPECTED_HTTPS="https://github.com/cagdasyurekli/agy-worker.git"
EXPECTED_HTTPS_NO_SUFFIX="https://github.com/cagdasyurekli/agy-worker"
EXPECTED_SSH="git@github.com:cagdasyurekli/agy-worker.git"
EXPECTED_SSH_URL="ssh://git@github.com/cagdasyurekli/agy-worker.git"

usage() {
    cat >&2 <<'EOF'
usage: update.sh check [--watch]
       update.sh apply [vMAJOR.MINOR.PATCH]

check: read-only official project release check; no installed AGY/Codex needed.
       --watch uses the same check: unchanged 0, different commit 3, unavailable 2.
apply: explicit fast-forward update from a verified release tag. Refuses a dirty
       checkout, validates the candidate in a disposable worktree, then reinstalls
       the Codex skill. It never runs during an agy worker job.
EOF
    exit 64
}

[[ $# -ge 1 ]] || usage
command_name="$1"; shift

cd "$SCRIPT_DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "update: pipeline directory is not a Git worktree" >&2; exit 64;
}

remote="$DEFAULT_REMOTE"
origin_available=1
remote_url="$(git config --get "remote.$remote.url" 2>/dev/null)" || {
    echo "update: origin remote is unavailable" >&2
    origin_available=0
    remote_url=""
}
if [[ -n "$remote_url" ]]; then
    case "$remote_url" in
        "$EXPECTED_HTTPS"|"$EXPECTED_HTTPS_NO_SUFFIX"|"$EXPECTED_SSH"|"$EXPECTED_SSH_URL") ;;
        *)
            # Do not echo an unexpected URL: Git remotes sometimes contain credentials.
            echo "update: refusing unexpected origin URL" >&2
            echo "update: expected the official cagdasyurekli/agy-worker repository" >&2
            origin_available=0 ;;
    esac
fi
if [[ "$command_name" == "apply" && "$origin_available" == 0 ]]; then
    exit 2
fi

latest_release() {
    local evidence="" probe_rc=0 tool tag revision extra
    evidence="$(python3 -I -B "$SCRIPT_DIR/scripts/compatibility_probe.py" \
        official-project 2>/dev/null)" || probe_rc=$?
    case "$probe_rc" in
        0) ;;
        129|130|143) exit "$probe_rc" ;;
        *)
        echo "update: could not query release tags from official origin" >&2
        return 2
            ;;
    esac
    IFS=$'\t' read -r tool tag revision extra <<< "$evidence"
    if [[ "$tool" != "project" || -n "$extra" \
            || ! "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ \
            || ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then
        echo "update: could not query release tags from official origin" >&2
        return 2
    fi
    printf '%s\n' "$tag"
}

remote_release_commit() {
    local tag="$1" evidence="" probe_rc=0 tool observed_tag revision extra
    evidence="$(python3 -I -B "$SCRIPT_DIR/scripts/compatibility_probe.py" \
        official-project-release "$tag" 2>/dev/null)" || probe_rc=$?
    case "$probe_rc" in
        0) ;;
        129|130|143) exit "$probe_rc" ;;
        *) echo "update: could not resolve release tag $tag" >&2; return 2 ;;
    esac
    IFS=$'\t' read -r tool observed_tag revision extra <<< "$evidence"
    if [[ "$tool" != "project" || "$observed_tag" != "$tag" || -n "$extra" \
            || ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then
        echo "update: release tag not found: $tag" >&2
        return 2
    fi
    printf '%s\n' "$revision"
}

check_updates() {
    local latest="" current_tag current_commit latest_commit release_rc=0
    if [[ $# -ne 0 && ! ( $# -eq 1 && "$1" == "--watch" ) ]]; then
        usage
    fi
    if [[ "$origin_available" == 0 ]]; then
        echo "tool update: evidence-unavailable (official project origin is unavailable)"
        return 2
    fi
    latest="$(latest_release)" || release_rc=$?
    case "$release_rc" in 129|130|143) return "$release_rc" ;; esac
    if (( release_rc != 0 )); then
        echo "tool update: evidence-unavailable (official release query failed)"
        return 2
    fi
    current_commit="$(git rev-parse HEAD)"
    current_tag="$(git describe --tags --exact-match --match 'v[0-9]*' HEAD 2>/dev/null || true)"
    latest_commit="$(remote_release_commit "$latest")" || release_rc=$?
    case "$release_rc" in 129|130|143) return "$release_rc" ;; esac
    if (( release_rc != 0 )); then
        echo "tool update: evidence-unavailable (official release tag is inconclusive)"
        return 2
    fi
    if [[ "$current_commit" == "$latest_commit" ]]; then
        echo "tool update: up to date at $latest"
        return 0
    elif [[ -n "$current_tag" ]]; then
        echo "tool update: different release commit ($current_tag; official $latest)"
    else
        echo "tool update: current checkout is not release-tagged; official $latest has a different commit"
    fi
    echo "update: check is read-only; no files were changed" >&2
    return 3
}

apply_update() {
    [[ $# -le 1 ]] || usage
    local tag="${1:-}" remote_commit temp_ref candidate_commit candidate_wt="" current_branch
    if [[ -z "$tag" ]]; then
        tag="$(latest_release)" || exit $?
    fi
    [[ -n "$tag" ]] || { echo "update: no stable release tag is available" >&2; exit 2; }
    [[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
        echo "update: apply requires a stable vMAJOR.MINOR.PATCH tag" >&2; exit 64;
    }
    [[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
        echo "update: refusing to update a dirty checkout" >&2; exit 2;
    }
    current_branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)" || {
        echo "update: apply requires a checked-out branch, not detached HEAD" >&2; exit 2;
    }

    remote_commit="$(remote_release_commit "$tag")" || exit $?
    temp_ref="refs/agy-worker-update/candidate-$$"
    cleanup_update() {
        if [[ -n "$candidate_wt" && -d "$candidate_wt" ]]; then
            git worktree remove --force "$candidate_wt" >/dev/null 2>&1 || true
        fi
        git update-ref -d "$temp_ref" >/dev/null 2>&1 || true
    }
    trap cleanup_update EXIT INT TERM

    git fetch --quiet --no-tags "$remote" "refs/tags/$tag:$temp_ref" || {
        echo "update: failed to fetch $tag" >&2; exit 2;
    }
    candidate_commit="$(git rev-parse "$temp_ref^{commit}")" || {
        echo "update: fetched release does not resolve to a commit" >&2; exit 2;
    }
    [[ "$candidate_commit" == "$remote_commit" ]] || {
        echo "update: release verification failed; remote and fetched commits differ" >&2
        exit 2
    }
    git merge-base --is-ancestor HEAD "$candidate_commit" || {
        echo "update: release is not a fast-forward from $current_branch" >&2; exit 2;
    }

    protect_ignored_paths() {
        python3 - "$SCRIPT_DIR" "$candidate_commit" <<'PY'
import subprocess
import sys

repo, candidate = sys.argv[1:3]

def git_paths(*args):
    output = subprocess.run(
        ["git", "-C", repo, *args], check=True, stdout=subprocess.PIPE
    ).stdout
    return {part for part in output.split(b"\0") if part}

ignored = git_paths("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--")
tracked = git_paths("ls-tree", "-r", "--name-only", "-z", candidate)
collisions = sorted(ignored & tracked)
if collisions:
    print("update: release would overwrite ignored local path(s):", file=sys.stderr)
    for path in collisions:
        display = path.decode("utf-8", "backslashreplace")
        print(f"    {display!r}", file=sys.stderr)
    raise SystemExit(1)
PY
    }

    protect_ignored_paths || {
        echo "update: preserve or remove those local files before retrying" >&2
        exit 2
    }

    candidate_wt="$(mktemp -d -t agy-worker-update.XXXXXX)"
    rmdir "$candidate_wt"
    git worktree add --quiet --detach "$candidate_wt" "$candidate_commit"
    echo "update: verified $tag -> $candidate_commit"
    echo "update: validating candidate in $candidate_wt"
    (
        cd "$candidate_wt"
        bash -n ./*.sh tests/*.sh skills/*/scripts/*.sh skills/*/runtime/*.sh || exit $?
        preflight_skills="$(mktemp -d -t agy-worker-skill-preflight.XXXXXX)"
        trap 'rm -rf -- "$preflight_skills"' EXIT
        CODEX_SKILLS_DIR="$preflight_skills" ./install.sh || exit $?
        for suite in tests/test-*.sh; do "$suite" || exit $?; done
        git diff --check || exit $?
    ) || { echo "update: candidate validation failed; checkout unchanged" >&2; exit 2; }
    git worktree remove "$candidate_wt"
    candidate_wt=""

    [[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
        echo "update: checkout changed during validation; refusing apply" >&2; exit 2;
    }
    protect_ignored_paths || {
        echo "update: ignored local paths changed during validation; refusing apply" >&2
        exit 2
    }
    git update-ref "refs/tags/$tag" "$(git rev-parse "$temp_ref")"
    git update-ref -d "$temp_ref"
    trap - EXIT INT TERM
    git merge --ff-only "$candidate_commit"
    if ! "$SCRIPT_DIR/install.sh"; then
        echo "update: PARTIAL UPDATE - checkout is now at $candidate_commit, but Codex skill installation failed" >&2
        echo "update: recovery - fix the skill destination, then run: $SCRIPT_DIR/install.sh" >&2
        exit 4
    fi
    echo "update: applied $tag and reinstalled the Codex skill"
}

case "$command_name" in
    check) check_updates "$@" ;;
    apply) apply_update "$@" ;;
    *) usage ;;
esac
