#!/usr/bin/env python3
"""Focused offline positive, negative, and adversarial tests for workflow.sh facade."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable
from unittest import mock

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "skills" / "agy-worker" / "runtime"
SCRIPT = RUNTIME / "scripts" / "workflow.py"
SCHEMA_PATH = RUNTIME / "schemas" / "workflow-state.schema.json"
SUBJECT_MODES = {
    ROOT / "workflow.sh": {0o700, 0o755},
    RUNTIME / "workflow.sh": {0o700, 0o755},
    SCRIPT: {0o700, 0o755},
    SCHEMA_PATH: {0o600, 0o644},
}
SUBJECT_MODES_BEFORE_IMPORT = {
    path: stat.S_IMODE(path.stat().st_mode) for path in SUBJECT_MODES
}

sys.path.insert(0, str(RUNTIME / "scripts"))
import candidate_state as CANDIDATE  # noqa: E402 -- sibling imports follow startup isolation/path setup
import workflow as WORKFLOW_MODULE  # noqa: E402 -- sibling imports follow startup isolation/path setup

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


def run_cmd(
    *argv: str,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    env: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    full_env = dict(os.environ)
    if env:
        for name, value in env.items():
            if value is None:
                full_env.pop(name, None)
            else:
                full_env[name] = value
    return subprocess.run(
        argv,
        input=input_bytes,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=full_env,
    )


def run_workflow(
    *argv: str,
    cwd: Path | None = None,
    input_bytes: bytes | None = None,
    env: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return run_cmd(
        sys.executable, "-I", "-S", "-B", str(SCRIPT), *argv,
        cwd=cwd, input_bytes=input_bytes, env=env
    )


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.decode("utf-8").strip()


def test_import_does_not_mutate_subject_modes() -> bool:
    after_import = {
        path: stat.S_IMODE(path.stat().st_mode) for path in SUBJECT_MODES
    }
    assert SUBJECT_MODES_BEFORE_IMPORT == after_import
    # Both checkout and owner-private scoped staging modes are legitimate.
    assert all(mode in SUBJECT_MODES[path] for path, mode in after_import.items())
    for path, allowed in SUBJECT_MODES.items():
        for unsafe in (0o666, 0o777, 0o4755, 0o2755):
            assert unsafe not in allowed, path
    assert 0o644 not in SUBJECT_MODES[SCRIPT]
    assert 0o755 not in SUBJECT_MODES[SCHEMA_PATH]
    return True


check("import does not mutate or self-heal workflow subject modes", test_import_does_not_mutate_subject_modes)


def test_workflow_mode_defaults_and_conflicts() -> bool:
    parser = WORKFLOW_MODULE.build_parser()
    for workflow, expected in (("explore", "plan"), ("task", "accept-edits"), ("project", "accept-edits")):
        args = parser.parse_args(["run", "--repo", "/tmp/repo", "--job-id", "mode-test", "--workflow", workflow])
        assert WORKFLOW_MODULE._resolved_mode(args) == expected
    task_plan = parser.parse_args(["run", "--repo", "/tmp/repo", "--job-id", "mode-test", "--workflow", "task", "--mode", "plan"])
    assert WORKFLOW_MODULE._resolved_mode(task_plan) == "plan"
    args = parser.parse_args(["run", "--repo", "/tmp/repo", "--job-id", "mode-test", "--workflow", "explore", "--mode", "accept-edits"])
    try:
        WORKFLOW_MODULE._resolved_mode(args)
    except WORKFLOW_MODULE.WorkflowError:
        pass
    else:
        raise AssertionError("conflicting explicit mode accepted")
    return True


check("workflow mode derives from intent and rejects only explicit conflicts", test_workflow_mode_defaults_and_conflicts)


def test_finalize_is_required_for_unreviewed_bound_candidate() -> bool:
    actions = [{"action": "result"}, {"action": "finalize"}]
    assert WORKFLOW_MODULE._next_required_workflow_action({
        "result_available": True, "driver_disposition": "unreviewed", "available_actions": actions,
    }) == "verify-finalize"
    assert WORKFLOW_MODULE._next_required_workflow_action({
        "result_available": False, "driver_disposition": "not_applicable", "available_actions": [],
    }) is None
    assert WORKFLOW_MODULE._next_required_workflow_action({
        "result_available": True, "driver_disposition": "verified", "available_actions": actions,
    }) is None
    return True


check("workflow status names verify-finalize for a pending bound candidate", test_finalize_is_required_for_unreviewed_bound_candidate)


def test_public_workflow_status_shows_required_finalize() -> bool:
    with tempfile.TemporaryDirectory() as directory:
        dispatch_dir = Path(directory) / "logs" / "pending-job"
        dispatch_dir.mkdir(parents=True)
        state = {
            "job_id": "pending-job", "repo_path": directory, "worktree_path": directory,
            "branch": "test", "base": "0" * 40, "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "0" * 64,
            "preview_launch_approval_sha256": "0" * 64, "native_grant_profile": "baseline",
            "dispatch_job_dir": str(dispatch_dir), "provider_execution": None,
            "provider_isolation": "session", "receipt_path": None,
        }
        facts = {
            "job_id": "pending-job", "status": "succeeded", "reason": None,
            "workflow": "task", "attempt": 1, "max_cycles": 2,
            "state_sha256": "a" * 64, "phase": "awaiting-verification",
            "controller_phase": "awaiting-verification", "result_available": True,
            "driver_disposition": "unreviewed", "candidate_sha256": "b" * 64,
            "available_actions": [{"action": "result"}, {"action": "finalize"}],
            "provider_execution": {"legacy": False}, "provider_isolation": "session",
            "assurance": None,
        }
        store = mock.Mock(value=state)
        with mock.patch.object(WORKFLOW_MODULE, "WorkflowStateStore", return_value=store), \
             mock.patch.object(WORKFLOW_MODULE, "_bound_dispatch_status", return_value=facts):
            for output_format in ("json", "text"):
                captured = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
                with mock.patch.object(WORKFLOW_MODULE.sys, "stdout", captured):
                    assert WORKFLOW_MODULE._workflow_status(
                        WORKFLOW_MODULE.argparse.Namespace(state=str(Path(directory) / "workflow.json"), format=output_format)
                    ) == 0
                    captured.flush()
                output = captured.buffer.getvalue().decode("utf-8")
                if output_format == "json":
                    assert json.loads(output)["next_required_action"] == "verify-finalize"
                else:
                    assert "next-required-action=verify-finalize" in output
    return True


check("public workflow status JSON and text require verify-finalize", test_public_workflow_status_shows_required_finalize)


def test_advanced_log_root_requires_bound_workflow_job() -> bool:
    state = {"job_id": "approved", "dispatch_job_dir": "/private/tmp/step16-logs/approved"}
    fake_store = mock.Mock()
    fake_store.value = state
    with mock.patch.object(WORKFLOW_MODULE, "WorkflowStateStore", return_value=fake_store), \
         mock.patch.object(WORKFLOW_MODULE.DISPATCH, "canonical_job", side_effect=lambda path: path), \
         mock.patch.object(WORKFLOW_MODULE.DISPATCH, "load_state", return_value=({"job_id": "approved"}, b"{}", "0" * 64)):
        assert WORKFLOW_MODULE.dispatch_log_root_from_workflow_state(Path("/private/tmp/state"), "approved") == Path("/private/tmp/step16-logs")
        try:
            WORKFLOW_MODULE.dispatch_log_root_from_workflow_state(Path("/private/tmp/state"), "other")
        except WORKFLOW_MODULE.WorkflowError:
            pass
        else:
            raise AssertionError("unbound job was accepted")
    return True


check("advanced controls derive log root only from a bound workflow job", test_advanced_log_root_requires_bound_workflow_job)


def test_canonical_path_hint_for_macos_var_alias() -> bool:
    alias = Path("/var/folders/example/agy-state.json")
    canonical = Path("/private/var/folders/example/agy-state.json")
    with mock.patch.object(WORKFLOW_MODULE.os.path, "realpath", return_value=str(canonical)):
        try:
            WORKFLOW_MODULE.real_absolute(alias, "workflow state", must_exist=False)
        except WORKFLOW_MODULE.WorkflowError as exc:
            assert str(canonical) in str(exc)
        else:
            raise AssertionError("noncanonical alias was accepted")

    # Other symlink resolutions must not disclose their targets as a path hint.
    with mock.patch.object(WORKFLOW_MODULE.os.path, "realpath", return_value="/private/secret"):
        try:
            WORKFLOW_MODULE.real_absolute(alias, "workflow state", must_exist=False)
        except WORKFLOW_MODULE.WorkflowError as exc:
            assert "/private/secret" not in str(exc)
        else:
            raise AssertionError("unrelated symlink resolution was accepted")

    unsafe_alias = Path("/var/folders/example/\x1b[31m")
    with mock.patch.object(
        WORKFLOW_MODULE.os.path, "realpath", return_value="/private/var/folders/example/\x1b[31m"
    ):
        try:
            WORKFLOW_MODULE.real_absolute(unsafe_alias, "workflow state", must_exist=False)
        except WORKFLOW_MODULE.WorkflowError as exc:
            assert "\x1b" not in str(exc)
        else:
            raise AssertionError("unsafe alias was accepted")

    if sys.platform == "darwin" and Path("/var/folders").is_symlink():
        try:
            WORKFLOW_MODULE.real_absolute(Path("/var/folders"), "workflow state")
        except WORKFLOW_MODULE.WorkflowError as exc:
            assert "/private/var/folders" in str(exc)
        else:
            raise AssertionError("macOS /var/folders alias was accepted")
    return True


check("canonical path error hints only for macOS /var/folders alias", test_canonical_path_hint_for_macos_var_alias)


class RepoFixture:
    def __init__(self, name: str) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix=f"agy-wf-{name}-")).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir(mode=0o700)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Workflow Tester")
        git(self.repo, "config", "user.email", "workflow@example.com")

        initial_file = self.repo / "README.md"
        initial_file.write_text("# Initial Repo\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-q", "-m", "Initial commit")
        self.base = git(self.repo, "rev-parse", "HEAD")

        self.worktree = self.tmp / "wt"
        self.branch = f"agy/{name}-branch"
        git(self.repo, "worktree", "add", "-q", "-b", self.branch, str(self.worktree), self.base)

        self.state_dir = self.tmp / "state"
        self.state_dir.mkdir(mode=0o700)
        self.state_file = self.state_dir / "workflow-state.json"
        self.receipt_file = self.state_dir / "receipt.json"
        self.envelope_file = self.state_dir / "envelope.json"
        self.job_id = f"job-{name}-001"

    def write_envelope(self, *, path: str = "README.md", content: str = "Updated README\n") -> None:
        (self.worktree / path).write_text(content, encoding="utf-8")
        envelope = {
            "status": "completed",
            "summary": "Updated content for testing",
            "files_changed": [{"path": path, "change": "modified"}],
            "commands_run": [],
            "tests_run": [],
            "risks": [],
            "open_questions": [],
            "confidence": 1.0,
            "requires_human": False,
        }
        self.envelope_file.write_bytes(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        self.envelope_file.chmod(0o600)

    def clean(self) -> None:
        try:
            git(self.repo, "worktree", "remove", "--force", str(self.worktree))
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


# ============================================================================
# 1. run command positive, negative, and adversarial tests
# ============================================================================

def test_run_missing_args() -> bool:
    f = RepoFixture("missing-args")
    try:
        res = run_workflow("run")
        assert res.returncode != 0
        res = run_workflow("run", "--state", str(f.state_file))
        assert res.returncode != 0
        return True
    finally:
        f.clean()

check("run rejects missing required arguments", test_run_missing_args)


def test_public_explore_mode_preview_and_conflict() -> bool:
    f = RepoFixture("explore-mode")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        env = {"XDG_STATE_HOME": str(state_home)}
        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", f.job_id,
            "--workflow", "explore", "--preview", env=env,
        )
        assert preview.returncode == 0, preview.stderr
        conflict = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", f.job_id,
            "--workflow", "explore", "--mode", "accept-edits", "--preview",
            env=env,
        )
        assert conflict.returncode == 20, conflict.stderr
        assert b"--workflow explore conflicts with --mode accept-edits" in conflict.stderr
        return True
    finally:
        f.clean()


check("public explore preview derives plan and rejects an explicit editing conflict", test_public_explore_mode_preview_and_conflict)


def test_literal_model_effort_forwarded_exactly() -> bool:
    f = RepoFixture("literal-model-effort")
    try:
        parser = WORKFLOW_MODULE.build_parser()
        args = parser.parse_args(["run", "--repo", str(f.repo), "--job-id", f.job_id,
                                  "--model", "Caller.Future/model", "--effort", "maximum", "--task", "bounded task"])
        args.provider_isolation = "session"
        with mock.patch.object(WORKFLOW_MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], 17)) as child:
            assert WORKFLOW_MODULE._dispatch_run(args, worktree=f.worktree,
                dispatch_job_dir=f.state_dir / "literal-job", approved_whole_worktree="b" * 64) == 17
        command = child.call_args.args[0]
        assert command[command.index("--model") + 1] == "Caller.Future/model"
        assert command[command.index("--effort") + 1] == "maximum"
        assert "--compatibility-disposition" not in command and "--approve-help-sha" not in command
        return True
    finally:
        f.clean()

check("run forwards literal caller model and effort unchanged", test_literal_model_effort_forwarded_exactly)


def test_removed_approval_flags_reject_before_effects() -> bool:
    f = RepoFixture("retired-approval")
    try:
        base = ["run", "--repo", str(f.repo), "--job-id", f.job_id, "--model", "Caller.Future/model"]
        before = sorted(str(path) for path in f.state_dir.rglob("*")) if f.state_dir.exists() else []
        for extra in (["--compatibility-disposition", "proceed"], ["--approve-help-sha", "a" * 64],
                      ["--compatibility-disposition", "proceed", "--approve-help-sha", "a" * 64]):
            failed = run_workflow(*(base + extra))
            assert failed.returncode == 2 and b"unrecognized arguments" in failed.stderr
            assert (sorted(str(path) for path in f.state_dir.rglob("*")) if f.state_dir.exists() else []) == before
        for extra in (["--model", "second"], ["--effort", "low", "--effort", "high"], ["--tier", "bulk", "--tier", "default"]):
            failed = run_workflow(*(base + extra))
            assert failed.returncode == 2 and b"repeated --" in failed.stderr
        return True
    finally:
        f.clean()

check("run rejects retired approval flags before effects and duplicate caller selectors", test_removed_approval_flags_reject_before_effects)


def test_run_path_boundary_enforcement() -> bool:
    f = RepoFixture("boundary")
    try:
        # State inside repo
        bad_state = f.repo / "state.json"
        res = run_workflow(
            "run", "--state", str(bad_state), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode != 0
        assert b"state must be outside" in res.stderr

        # State parent not 0700
        f.state_dir.chmod(0o755)
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode != 0
        assert b"mode-0700" in res.stderr
        f.state_dir.chmod(0o700)

        # Invalid base commit
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", "0" * 40, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode != 0
        assert b"base commit does not exist" in res.stderr

        # Worktree not registered
        unregistered = f.tmp / "unreg"
        unregistered.mkdir(mode=0o700)
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(unregistered), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode != 0
        assert b"not registered" in res.stderr

        return True
    finally:
        f.clean()

check("run enforces immutable base and worktree path boundaries", test_run_path_boundary_enforcement)


def test_run_preview_and_approval_enforcement() -> bool:
    f = RepoFixture("preview-approval")
    try:
        # 1. Preview flag outputs preview canonical JSON and exits 0
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode == 0
        direct = run_cmd(
            str(RUNTIME / "agy-worker.sh"),
            "transmission-preview", "--workdir", str(f.worktree),
        )
        assert direct.returncode == 0
        assert res.stdout == direct.stdout
        preview = json.loads(res.stdout.decode("utf-8"))
        assert "kind" not in preview
        assert preview["manifest"]["kind"] == "agy-worker-readable-path-manifest"
        manifest_sha = preview["manifest_sha256"]
        content_sha = preview["content_manifest_sha256"]
        launch_approval_sha = preview["launch_approval_sha256"]
        assert len(manifest_sha) == len(content_sha) == len(launch_approval_sha) == 64
        assert preview["native_grant_profile"] == "baseline"
        assert "authority_summary" in preview
        summary = preview["authority_summary"]
        assert summary["contents_read"] is True
        assert summary["network_used"] is False
        assert summary["provider_launched"] is False
        assert summary["provider_isolation"] == "session"
        assert summary["manifest_sha256"] == manifest_sha
        assert summary["content_manifest_sha256"] == content_sha
        assert summary["native_grant_profile"] == "baseline"
        assert summary["launch_approval_sha256"] == launch_approval_sha
        assert summary["provider_authority"] == "normal same-user filesystem and network authority; selected scope is staging and reconciliation, not host confinement"

        # 2. Invoking run without an explicit transmission mode exits 20 with preview info
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id
        )
        assert res.returncode == 20
        assert b"explicit provider-transmission mode required" in res.stderr

        # 3. Invoking run with mismatched whole-worktree approval fails closed
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id,
            "--approve-whole-worktree", "a" * 64
        )
        assert res.returncode != 0
        assert b"stale or mismatched" in res.stderr

        # 4. Exact whole-worktree approval creates a content-bound workflow state
        # Use fake mock for agy to avoid real provider dispatch
        fake_bin = f.tmp / "bin"
        fake_bin.mkdir(mode=0o700)
        fake_agy = fake_bin / "agy"
        fake_agy.write_text("""#!/bin/sh
case "$1" in
  --version) echo workflow-fixture; exit 0 ;;
  --help) cat <<'HELP'
  --add-dir  Directory
  --conversation  Conversation
  --disable-slash-commands  Disable expansion
  --effort  Caller effort
  --json-schema  Schema
  --mode  Mode (accept-edits, plan)
  --model  Caller model
  --output-format  Format (stream-json)
  --print  Prompt
  --print-timeout  Deadline
  --sandbox  Sandbox
HELP
    exit 0 ;;
esac
exit 0
""", encoding="utf-8")
        fake_agy.chmod(0o755)

        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id,
            "--approve-whole-worktree", launch_approval_sha,
            "--task", "Test prompt",
            env={"PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        )
        assert f.state_file.exists()
        state_data = json.loads(f.state_file.read_bytes())
        assert state_data["schema_version"] == WORKFLOW_MODULE.BOUND_SCHEMA_VERSION
        assert state_data["provider_isolation"] == "session"
        assert state_data["provider_execution"] is None
        assert state_data["kind"] == "agy-worker-workflow-state"
        assert state_data["job_id"] == f.job_id
        assert state_data["base"] == f.base
        assert state_data["branch"] == f.branch
        assert state_data["preview_manifest_sha256"] == manifest_sha
        assert state_data["preview_content_sha256"] == content_sha
        assert state_data["preview_launch_approval_sha256"] == launch_approval_sha
        assert state_data["native_grant_profile"] == "baseline"
        assert state_data["dispatch_job_dir"] is not None
        assert "last_result" not in state_data
        assert "final_assurance" not in state_data
        assert "final_disposition" not in state_data
        assert stat.S_IMODE(f.state_file.stat().st_mode) == 0o600

        # Check schema metadata agrees with the current state
        schema = json.loads(SCHEMA_PATH.read_bytes())
        assert state_data["schema_version"] in schema["properties"]["schema_version"]["enum"]
        assert state_data["kind"] == schema["properties"]["kind"]["enum"][0]

        return True
    finally:
        f.clean()

check("run generates preview, rejects unapproved/stale preview, and binds approved preview", test_run_preview_and_approval_enforcement)


def test_preview_timeout_covers_bounded_path_and_content_scans() -> bool:
    f = RepoFixture("preview-budget")
    try:
        direct = run_cmd(
            str(RUNTIME / "agy-worker.sh"), "transmission-preview",
            "--workdir", str(f.worktree), "--provider-isolation", "session",
        )
        assert direct.returncode == 0, direct.stderr
        observed: list[float] = []

        def completed(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            observed.append(kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0, direct.stdout, b"")

        with mock.patch.object(WORKFLOW_MODULE.subprocess, "run", side_effect=completed):
            raw, preview = WORKFLOW_MODULE.canonical_transmission_preview(f.worktree)
        assert raw == direct.stdout
        assert preview["content_manifest_sha256"]
        assert observed == [60.0]
        return True
    finally:
        f.clean()


check("facade preview timeout covers bounded path and content scan budgets", test_preview_timeout_covers_bounded_path_and_content_scans)


def test_run_drift_rejection() -> bool:
    f = RepoFixture("drift")
    try:
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert res.returncode == 0
        launch_approval_sha = json.loads(res.stdout.decode("utf-8"))["launch_approval_sha256"]

        # Modify worktree after preview
        (f.worktree / "untracked.txt").write_text("drift", encoding="utf-8")

        # Approval with old manifest sha now fails closed
        res = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id,
            "--approve-whole-worktree", launch_approval_sha
        )
        assert res.returncode != 0
        assert b"stale or mismatched" in res.stderr
        return True
    finally:
        f.clean()

check("run rejects worktree drift after preview generation", test_run_drift_rejection)


def test_whole_preview_binds_bytes_mode_and_link_target() -> bool:
    for kind in ("bytes", "mode", "link"):
        f = RepoFixture(f"whole-content-{kind}")
        try:
            target = f.worktree / "README.md"
            if kind == "link":
                (f.worktree / "NOTICE.md").write_text("# Other Repo\n", encoding="utf-8")
                (f.worktree / "alias.txt").symlink_to("README.md")
            argv = (
                "run", "--state", str(f.state_file), "--repo", str(f.repo),
                "--worktree", str(f.worktree), "--branch", f.branch,
                "--base", f.base, "--job-id", f.job_id,
            )
            first = run_workflow(*argv, "--preview")
            assert first.returncode == 0, first.stderr
            prior = json.loads(first.stdout)
            if kind == "bytes":
                data = target.read_bytes()
                target.write_bytes(data.replace(b"Initial", b"Changed"))
                assert target.stat().st_size == len(data)
            elif kind == "mode":
                target.chmod(0o600)
            else:
                alias = f.worktree / "alias.txt"
                alias.unlink()
                alias.symlink_to("NOTICE.md")
            current = run_workflow(*argv, "--preview")
            assert current.returncode == 0, current.stderr
            latest = json.loads(current.stdout)
            assert latest["manifest_sha256"] == prior["manifest_sha256"]
            assert latest["content_manifest_sha256"] != prior["content_manifest_sha256"]
            assert latest["launch_approval_sha256"] != prior["launch_approval_sha256"]
            rejected = run_workflow(
                *argv, "--approve-whole-worktree", prior["launch_approval_sha256"],
            )
            assert rejected.returncode != 0
            assert b"stale or mismatched" in rejected.stderr
            assert not f.state_file.exists()
        finally:
            f.clean()
    return True


check("whole-worktree preview rejects same-size bytes, mode, and link drift", test_whole_preview_binds_bytes_mode_and_link_target)


def test_run_pre_dispatch_failure_rolls_back_exact_state() -> bool:
    f = RepoFixture("predispatch-rollback")
    try:
        preview = run_workflow(
            "run", "--state", str(f.state_file), "--repo", str(f.repo),
            "--worktree", str(f.worktree), "--branch", f.branch,
            "--base", f.base, "--job-id", f.job_id, "--preview"
        )
        assert preview.returncode == 0
        manifest_sha = json.loads(preview.stdout.decode("utf-8"))["manifest_sha256"]
        launch_approval_sha = json.loads(preview.stdout.decode("utf-8"))["launch_approval_sha256"]
        dispatch_dir = f.state_dir / "logs" / f.job_id

        def rejected_preflight() -> subprocess.CompletedProcess[bytes]:
            return run_workflow(
                "run", "--state", str(f.state_file), "--repo", str(f.repo),
                "--worktree", str(f.worktree), "--branch", f.branch,
                "--base", f.base, "--job-id", f.job_id,
                "--approve-whole-worktree", launch_approval_sha,
                "--provider-env", "BASH_ENV", "--task", "bounded task",
            )

        first = rejected_preflight()
        assert first.returncode == 64
        assert b"unsafe --provider-env name" in first.stderr
        assert not f.state_file.exists()
        assert not dispatch_dir.exists()

        # The identical provider-free preflight remains retryable instead of
        # failing on a stranded facade state.
        retry = rejected_preflight()
        assert retry.returncode == 64
        assert b"unsafe --provider-env name" in retry.stderr
        assert not f.state_file.exists()
        assert not dispatch_dir.exists()

        protected_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": manifest_sha,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": launch_approval_sha,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": str(dispatch_dir),
            "job_state_path": None,
            "receipt_path": None,
        }
        original = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        original_sha = original.create(protected_state)
        assert original.metadata is not None
        original_identity = WORKFLOW_MODULE.identity(original.metadata)
        original.close()

        replacement = dict(protected_state)
        replacement["preview_manifest_sha256"] = "f" * 64
        replacement_raw = WORKFLOW_MODULE.canonical_json(replacement) + b"\n"
        f.state_file.write_bytes(replacement_raw)
        f.state_file.chmod(0o600)
        guarded = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=False)
        try:
            try:
                guarded.discard_exact(original_sha, original_identity)
            except WORKFLOW_MODULE.WorkflowError as exc:
                assert "changed before pre-dispatch rollback" in str(exc)
            else:
                raise AssertionError("replaced workflow state was removed")
        finally:
            guarded.close()
        assert f.state_file.read_bytes() == replacement_raw
        return True
    finally:
        f.clean()


check(
    "run rolls back only its exact state after provider-free pre-dispatch rejection",
    test_run_pre_dispatch_failure_rolls_back_exact_state,
)


def _derived_files(state_home: Path, job_id: str) -> tuple[Path, Path, Path]:
    matches = list(
        state_home.glob(f"agy-worker/workflows/*/{job_id}/workflow.json")
    )
    assert len(matches) == 1
    workflow_state = matches[0]
    return workflow_state, workflow_state.with_name("job.json"), workflow_state.with_name("worktree")


def test_ordinary_run_owns_private_initialization_and_reuses_preview() -> bool:
    f = RepoFixture("ordinary-owned")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        job_id = "ordinary-owned-job"
        env = {"XDG_STATE_HOME": str(state_home)}
        # The caller checkout may be dirty; the derived worktree remains isolated
        # at the immutable HEAD selected once for lifecycle initialization.
        (f.repo / "README.md").write_text("dirty caller checkout\n", encoding="utf-8")
        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id, "--preview", env=env
        )
        assert preview.returncode == 0, preview.stderr
        launch_approval_sha = json.loads(preview.stdout.decode("utf-8"))["launch_approval_sha256"]
        workflow_state, job_state, worktree = _derived_files(state_home, job_id)
        workflow_value = json.loads(workflow_state.read_bytes())
        job_value = json.loads(job_state.read_bytes())
        assert workflow_value["schema_version"] == WORKFLOW_MODULE.BOUND_FACADE_SCHEMA_VERSION
        assert workflow_value["origin"] == "workflow-facade"
        assert workflow_value["provider_isolation"] == "session"
        assert workflow_value["provider_execution"] is None
        assert job_value["schema_version"] == 2
        assert job_value["origin"] == "workflow-facade"
        assert workflow_value["base"] == f.base == job_value["base"]
        assert worktree.joinpath("README.md").read_text(encoding="utf-8") == "# Initial Repo\n"
        assert git(f.repo, "status", "--short") == "M README.md"
        for directory in (
            state_home / "agy-worker",
            state_home / "agy-worker" / "workflows",
            workflow_state.parent.parent,
            workflow_state.parent,
            workflow_state.parent / "logs",
        ):
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(workflow_state.stat().st_mode) == 0o600
        assert stat.S_IMODE(job_state.stat().st_mode) == 0o600

        before_workflow = workflow_state.read_bytes()
        before_job = job_state.read_bytes()
        # A later caller-checkout HEAD movement cannot silently rebind an
        # omitted --base on the approved second call.
        (f.repo / "README.md").write_text("# Initial Repo\n", encoding="utf-8")
        (f.repo / "NEXT.md").write_text("later commit\n", encoding="utf-8")
        git(f.repo, "add", "README.md", "NEXT.md")
        git(f.repo, "commit", "-q", "-m", "Later caller commit")
        assert git(f.repo, "rev-parse", "HEAD") != f.base
        approved = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--approve-whole-worktree", launch_approval_sha,
            "--provider-env", "BASH_ENV", "--task", "bounded task", env=env,
        )
        assert approved.returncode == 64
        assert b"unsafe --provider-env name" in approved.stderr
        # These resources came from the prior preview invocation, so this later
        # preflight failure must retain them for explicit recovery.
        assert workflow_state.read_bytes() == before_workflow
        assert job_state.read_bytes() == before_job
        assert worktree.is_dir()

        stale = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--approve-whole-worktree", "0" * 64, "--task", "bounded task", env=env,
        )
        assert stale.returncode == 20
        assert workflow_state.exists() and job_state.exists() and worktree.exists()
        return True
    finally:
        f.clean()


check(
    "ordinary run derives private lifecycle resources, isolates dirty checkout, and reuses preview bindings",
    test_ordinary_run_owns_private_initialization_and_reuses_preview,
)


def test_invalid_scope_preview_rolls_back_new_facade_resources() -> bool:
    f = RepoFixture("invalid-scope-rollback")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        scope_path = f.tmp / "provider-scope.json"
        scope_path.write_bytes(json.dumps({
            "schema_version": 1,
            "kind": "agy-worker-provider-scope",
            "read": [{"path": "README.md", "kind": "file"}],
            "write": [{"path": "README.md", "kind": "file"}],
        }).encode("utf-8"))
        scope_path.chmod(0o644)
        job_id = "invalid-scope-rollback-job"

        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path), "--preview",
            env={"XDG_STATE_HOME": str(state_home)},
        )
        assert preview.returncode == 20
        assert not preview.stdout
        assert b"transmission preview invalid: provider scope authority is invalid" in preview.stderr
        assert b"advanced recovery" not in preview.stderr

        job_roots = list(state_home.glob(f"agy-worker/workflows/*/{job_id}"))
        assert len(job_roots) == 1
        job_root = job_roots[0]
        assert not (job_root / "job.json").exists()
        assert not (job_root / "workflow.json").exists()
        assert not (job_root / "worktree").exists()
        assert git(f.repo, "branch", "--list", "agy/workflow-*") == ""
        assert str(job_root / "worktree") not in git(f.repo, "worktree", "list", "--porcelain")
        assert stat.S_IMODE(scope_path.stat().st_mode) == 0o644
        return True
    finally:
        f.clean()


check(
    "invalid scoped preview releases its lock and rolls back new facade resources",
    test_invalid_scope_preview_rolls_back_new_facade_resources,
)


def test_ordinary_run_requires_one_explicit_transmission_mode() -> bool:
    f = RepoFixture("ordinary-scope")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        scope_path = f.tmp / "provider-scope.json"
        scope_path.write_bytes(json.dumps({
            "schema_version": 1,
            "kind": "agy-worker-provider-scope",
            "read": [{"path": "README.md", "kind": "file"}],
            "write": [{"path": "README.md", "kind": "file"}],
        }, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n")
        scope_path.chmod(0o600)
        job_id = "ordinary-scope-job"
        env = {"XDG_STATE_HOME": str(state_home)}

        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path), "--preview", env=env,
        )
        assert preview.returncode == 0, preview.stderr
        preview_value = json.loads(preview.stdout)
        transmission_sha = preview_value["transmission_sha256"]
        assert preview_value["contents_read"] is True
        assert "authority_summary" in preview_value
        summary = preview_value["authority_summary"]
        assert summary["contents_read"] is True
        assert summary["network_used"] is False
        assert summary["provider_launched"] is False
        assert summary["provider_isolation"] == "session"
        assert summary["manifest_sha256"] == preview_value["manifest_sha256"]
        assert summary["native_grant_profile"] == "baseline"
        assert summary["policy_sha256"] == preview_value["policy_sha256"]
        assert summary["selected_content_sha256"] == preview_value["selected_content_sha256"]
        assert summary["transmission_sha256"] == transmission_sha
        assert summary["launch_approval_sha256"] == preview_value["launch_approval_sha256"]
        assert summary["provider_authority"] == "normal same-user filesystem and network authority; selected scope is staging and reconciliation, not host confinement"

        missing = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path), "--task", "bounded task", env=env,
        )
        assert missing.returncode == 20
        assert b"explicit provider-transmission mode required" in missing.stderr
        assert transmission_sha.encode("ascii") in missing.stderr

        conflicting = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path),
            "--approve-whole-worktree", preview_value["manifest_sha256"],
            "--task", "bounded task", env=env,
        )
        assert conflicting.returncode == 20
        assert b"conflicts with whole-worktree approval options" in conflicting.stderr

        passed_to_raw_boundary = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path),
            "--approve-transmission-sha", transmission_sha,
            "--provider-env", "BASH_ENV", "--task", "bounded task", env=env,
        )
        assert passed_to_raw_boundary.returncode == 64
        assert b"unsafe --provider-env name" in passed_to_raw_boundary.stderr
        assert b"conflicts with --add-dir" not in passed_to_raw_boundary.stderr

        workflow_state, job_state, worktree = _derived_files(state_home, job_id)
        assert workflow_state.exists() and job_state.exists() and worktree.exists()
        bound = json.loads(workflow_state.read_bytes())
        assert bound["schema_version"] == WORKFLOW_MODULE.BOUND_FACADE_SCHEMA_VERSION
        assert bound["preview_content_sha256"] == preview_value["selected_content_sha256"]
        assert bound["preview_launch_approval_sha256"] == transmission_sha
        assert bound["native_grant_profile"] == "baseline"
        (worktree / "README.md").write_text("scoped content drift\n", encoding="utf-8")
        stale = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-scope", str(scope_path),
            "--approve-transmission-sha", transmission_sha,
            "--task", "bounded task", env=env,
        )
        assert stale.returncode == 20
        assert b"facade workflow binding or preview changed" in stale.stderr
        return True
    finally:
        f.clean()


check(
    "ordinary run requires explicit whole-worktree or scoped transmission evidence",
    test_ordinary_run_requires_one_explicit_transmission_mode,
)


def test_preview_reports_scope_validation_errors() -> bool:
    f = RepoFixture("scope-validation-errors")
    try:
        scope_path = f.tmp / "provider-scope.json"
        for read, expected in (
            ([{"path": "textkit/wrap.py", "kind": "file"},
              {"path": "textkit/slug.py", "kind": "file"}],
             "read entries must be strictly sorted"),
            ([{"path": "textkit", "kind": "directory"}],
             "read entry 0 kind must be 'file' or 'tree'"),
        ):
            scope_path.write_text(json.dumps({
                "schema_version": 1,
                "kind": "agy-worker-provider-scope",
                "read": read,
                "write": [],
            }), encoding="utf-8")
            scope_path.chmod(0o600)
            try:
                WORKFLOW_MODULE.canonical_transmission_preview(
                    f.worktree, provider_scope=str(scope_path),
                )
            except WORKFLOW_MODULE.WorkflowError as exc:
                assert expected in str(exc), str(exc)
                assert "unavailable" not in str(exc)
            else:
                raise AssertionError("invalid provider scope was accepted")
        return True
    finally:
        f.clean()


check("preview reports exact sorted-read and kind validation errors", test_preview_reports_scope_validation_errors)


def test_preview_identifies_main_checkout_marker() -> bool:
    f = RepoFixture("main-checkout-preview")
    try:
        try:
            WORKFLOW_MODULE.canonical_transmission_preview(f.repo)
        except WORKFLOW_MODULE.WorkflowError as exc:
            assert "control marker is not regular" in str(exc), str(exc)
            assert "linked worktree" in str(exc), str(exc)
            assert "unavailable" not in str(exc)
        else:
            raise AssertionError("main checkout preview was accepted")
        return True
    finally:
        f.clean()


check("preview names the main-checkout marker requirement", test_preview_identifies_main_checkout_marker)


def test_native_ready_profile_remains_bound_on_repreview() -> bool:
    f = RepoFixture("native-profile-bind")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        scope_path = f.tmp / "scope.json"
        scope_path.write_bytes(json.dumps({
            "schema_version": 1,
            "kind": "agy-worker-provider-scope",
            "read": [{"path": "README.md", "kind": "file"}],
            "write": [{"path": "README.md", "kind": "file"}],
        }, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n")
        scope_path.chmod(0o600)
        job_id = "native-profile-bound"
        env = {"XDG_STATE_HOME": str(state_home)}
        argv = (
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--provider-isolation", "native", "--provider-scope", str(scope_path),
        )
        initial = run_workflow(*argv, "--preview", env=env)
        assert initial.returncode == 0, initial.stderr
        preview = json.loads(initial.stdout)
        assert preview["native_grant_profile"] == "baseline"
        workflow_state, _job_state, _worktree = _derived_files(state_home, job_id)
        state = json.loads(workflow_state.read_bytes())
        assert state["schema_version"] == WORKFLOW_MODULE.BOUND_FACADE_SCHEMA_VERSION
        assert state["native_grant_profile"] == "baseline"
        malformed = dict(state)
        malformed["native_grant_profile"] = []
        try:
            WORKFLOW_MODULE.validate_workflow_state(malformed)
        except WORKFLOW_MODULE.WorkflowError:
            pass
        else:
            raise AssertionError("malformed profile was accepted")
        state["native_grant_profile"] = "A"
        workflow_state.write_bytes(WORKFLOW_MODULE.canonical_json(state) + b"\n")
        workflow_state.chmod(0o600)
        changed = run_workflow(*argv, "--preview", env=env)
        assert changed.returncode == 20
        assert b"facade workflow binding or preview changed" in changed.stderr
        return True
    finally:
        f.clean()


check("ready native workflow rejects a changed persisted grant profile", test_native_ready_profile_remains_bound_on_repreview)






def test_ordinary_run_home_fallback_and_partial_advanced_rejection() -> bool:
    f = RepoFixture("ordinary-home")
    try:
        fake_home = f.tmp / "home"
        fake_home.mkdir(mode=0o700)
        job_id = "ordinary-home-job"
        env = {"XDG_STATE_HOME": None, "HOME": str(fake_home)}
        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--base", f.base, "--preview", env=env,
        )
        assert preview.returncode == 0, preview.stderr
        workflow_state, job_state, worktree = _derived_files(
            fake_home / ".local" / "state", job_id
        )
        assert workflow_state.exists() and job_state.exists() and worktree.exists()
        partial = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", "partial-job",
            "--state", str(f.state_file), "--preview", env=env,
        )
        assert partial.returncode == 20
        assert b"advanced mode requires" in partial.stderr
        return True
    finally:
        f.clean()


check(
    "ordinary run supports HOME state fallback and rejects mixed advanced authority",
    test_ordinary_run_home_fallback_and_partial_advanced_rejection,
)


def test_ordinary_same_invocation_predispatch_failure_rolls_back_lifecycle() -> bool:
    f = RepoFixture("ordinary-rollback")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        job_id = "ordinary-rollback-job"
        env = {"XDG_STATE_HOME": str(state_home)}
        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id, "--preview", env=env
        )
        assert preview.returncode == 0
        launch_approval_sha = json.loads(preview.stdout.decode("utf-8"))["launch_approval_sha256"]
        workflow_state, job_state, worktree = _derived_files(state_home, job_id)
        workflow_value = json.loads(workflow_state.read_bytes())
        job_value = json.loads(job_state.read_bytes())
        dispatch_dir = workflow_state.parent / "logs" / job_id
        lifecycle_rollback = run_cmd(
            str(RUNTIME / "job.sh"), "rollback-ready",
            "--state", str(job_state), "--approve-job", job_id,
            "--approve-state-sha", hashlib.sha256(job_state.read_bytes()).hexdigest(),
            "--repo", str(f.repo), "--worktree", str(worktree),
            "--branch", workflow_value["branch"], "--base", job_value["base"],
            "--dispatch-job-dir", str(dispatch_dir), env=env,
        )
        assert lifecycle_rollback.returncode == 0, lifecycle_rollback.stderr
        workflow_state.unlink()
        assert not job_state.exists() and not worktree.exists()

        failed = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id,
            "--approve-whole-worktree", launch_approval_sha,
            "--provider-env", "BASH_ENV", "--task", "bounded task", env=env,
        )
        assert failed.returncode == 64, (failed.returncode, failed.stdout, failed.stderr)
        assert b"unsafe --provider-env name" in failed.stderr
        assert not workflow_state.exists()
        assert not job_state.exists()
        assert not worktree.exists()
        assert not dispatch_dir.exists()
        branch_probe = run_cmd(
            "/usr/bin/git", "-C", str(f.repo), "show-ref", "--verify", "--quiet",
            f"refs/heads/{workflow_value['branch']}", env=env,
        )
        assert branch_probe.returncode == 1
        return True
    finally:
        f.clean()


check(
    "ordinary run delegates same-invocation pre-dispatch rollback to lifecycle authority",
    test_ordinary_same_invocation_predispatch_failure_rolls_back_lifecycle,
)


# ============================================================================
# 2. status command positive, negative, and read-only tests
# ============================================================================

def test_delegation_projection_uses_bound_facts_without_assurance_inference() -> bool:
    base = {
        "state_sha256": "a" * 64, "status": "failed", "reason": "idle_timeout",
        "workflow": "task", "attempt": 1, "max_cycles": 2,
        "result_available": False, "failure_stage": None,
    }
    for reason in ("idle_timeout", "hard_deadline_exceeded"):
        facts = {**base, "reason": reason}
        projection = WORKFLOW_MODULE._delegation_from_dispatch(
            facts, approval_bound=True,
        )
        assert projection["decision"]["reason_code"] == "provider-unavailable"
        assert projection["decision"]["direct_codex_authorized"] is False
        assert projection["source_state_sha256"] == facts["state_sha256"]
    permission = WORKFLOW_MODULE._delegation_from_dispatch(
        {**base, "reason": "permission_required"}, approval_bound=True,
    )
    assert permission["decision"]["reason_code"] == "hard-stop-active"
    assert permission["decision"]["direct_codex_authorized"] is False
    native_host = WORKFLOW_MODULE._delegation_from_dispatch(
        {**base, "reason": "native_host_sandbox_unavailable"}, approval_bound=True,
    )
    assert native_host["decision"]["reason_code"] == "hard-stop-active"
    assert native_host["decision"]["direct_codex_authorized"] is False
    unapproved = WORKFLOW_MODULE._delegation_from_dispatch(
        base, approval_bound=False,
    )
    assert unapproved["state"] == "pending"
    assert "decision" not in unapproved
    succeeded = WORKFLOW_MODULE._delegation_from_dispatch(
        {**base, "status": "succeeded", "reason": None,
         "attempt": 2, "max_cycles": 2, "result_available": True},
        approval_bound=True,
    )
    assert succeeded["state"] == "completed"
    assert succeeded["source_attempt"] == succeeded["source_max_cycles"] == 2
    assert "decision" not in succeeded
    return True


check(
    "delegation projection uses bound timeout and cycle facts without claiming driver assurance",
    test_delegation_projection_uses_bound_facts_without_assurance_inference,
)

def test_status_read_only_and_sanitized() -> bool:
    f = RepoFixture("status")
    try:
        # Create initial state
        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": None,
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        state_sha_before = hashlib.sha256(f.state_file.read_bytes()).hexdigest()

        # Status in json format
        res = run_workflow("status", "--state", str(f.state_file), "--format", "json")
        assert res.returncode == 0
        status_data = json.loads(res.stdout.decode("utf-8"))
        assert status_data["kind"] == "agy-worker-workflow-status"
        assert status_data["schema_version"] == WORKFLOW_MODULE.STATUS_SCHEMA_VERSION == 3
        assert status_data["job_id"] == f.job_id
        assert status_data["dispatch"] is None

        # Status in text format
        res_txt = run_workflow("status", "--state", str(f.state_file), "--format", "text")
        assert res_txt.returncode == 0
        lines = res_txt.stdout.decode("utf-8").strip().splitlines()
        assert len(lines) == 4
        assert lines[0].startswith("workflow: job=")
        assert lines[1].startswith("dispatch: status=")
        assert lines[2].startswith("verification: verdict=")
        assert lines[3] == "delegation: state=pending decision=none reason=dispatch-not-started"

        # Strictly read-only: state file SHA did not change
        state_sha_after = hashlib.sha256(f.state_file.read_bytes()).hexdigest()
        assert state_sha_before == state_sha_after

        return True
    finally:
        f.clean()

check("status is strictly read-only, emits sanitized facts, and does not infer assurance", test_status_read_only_and_sanitized)


def test_status_projects_existing_job_state_without_migration() -> bool:
    f = RepoFixture("status-job-state")
    try:
        state_home = f.tmp / "xdg-state"
        state_home.mkdir(mode=0o700)
        job_id = "status-existing-job"
        env = {"XDG_STATE_HOME": str(state_home)}
        preview = run_workflow(
            "run", "--repo", str(f.repo), "--job-id", job_id, "--preview", env=env
        )
        assert preview.returncode == 0
        workflow_state, job_state, _worktree = _derived_files(state_home, job_id)
        before = job_state.read_bytes()

        explicit = run_workflow(
            "status", "--job-state", str(job_state), "--format", "json", env=env
        )
        assert explicit.returncode == 0, explicit.stderr
        projection = json.loads(explicit.stdout.decode("utf-8"))
        assert projection["source_kind"] == "job_lifecycle"
        assert projection["phase"] == projection["controller_phase"] == "ready"
        assert projection["available_actions"] == ["status", "verify"]
        assert "Mutations remain with job.sh" in projection["advanced_recovery"]

        detected = run_workflow(
            "status", "--state", str(job_state), "--format", "json", env=env
        )
        assert detected.returncode == 0
        assert json.loads(detected.stdout.decode("utf-8"))["source_kind"] == "job_lifecycle"
        assert job_state.read_bytes() == before

        facade = run_workflow(
            "status", "--state", str(workflow_state), "--format", "json", env=env
        )
        assert facade.returncode == 0
        facade_projection = json.loads(facade.stdout.decode("utf-8"))
        assert facade_projection["source_kind"] == "workflow_facade"
        assert facade_projection["phase"] == "ready"
        return True
    finally:
        f.clean()


check(
    "status projects existing lifecycle state read-only without migrating legacy authority",
    test_status_projects_existing_job_state_without_migration,
)


def test_status_projects_dispatcher_state_and_job_id_read_only() -> bool:
    f = RepoFixture("status-dispatcher")
    try:
        copied_runtime = f.tmp / "runtime-status"
        shutil.copytree(RUNTIME, copied_runtime)
        fake_dispatch = copied_runtime / "scripts" / "agy_dispatch.py"
        shutil.copyfile(fake_dispatch, fake_dispatch.with_name("_real_agy_dispatch.py"))
        fake_dispatch.write_text(
            "from _real_agy_dispatch import UnsupportedSchemaError, _require_supported_schema\n"
            "import hashlib,json,os,pathlib\n"
            "STATE_NAME='dispatch-state.json'\n"
            "class DispatchError(ValueError): pass\n"
            "def canonical_job(path):\n"
            " path=pathlib.Path(path)\n"
            " if not path.is_absolute() or pathlib.Path(os.path.realpath(path))!=path: raise DispatchError('bad job')\n"
            " return path\n"
            "def load_state(job):\n"
            " raw=(job/STATE_NAME).read_bytes(); value=json.loads(raw); return value,raw,hashlib.sha256(raw).hexdigest()\n"
            "def public_status(value,sha,job=None):\n"
            " return {'job_id':value['job_id'],'phase':'awaiting-verification',"
            "'controller_phase':'awaiting-verification','state_sha256':sha,"
            "'available_actions':[{'action':'result','command':'agy-worker.sh result'}]}\n"
            "def bound_provider_execution(job,value):\n"
            " return {'legacy':False,'scope':'provider-scope','agy_sandbox':False,'native_containment':False}\n",
            encoding="utf-8",
        )
        script = copied_runtime / "scripts" / "workflow.py"
        log_root = f.state_dir / "dispatcher-logs"
        log_root.mkdir(mode=0o700)
        job_id = "existing-dispatcher-job"
        job_dir = log_root / job_id
        job_dir.mkdir(mode=0o700)
        dispatch_state = job_dir / "dispatch-state.json"
        dispatch_state.write_bytes(
            json.dumps(
                {"job_id": job_id, "phase": "awaiting-verification"},
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8") + b"\n"
        )
        dispatch_state.chmod(0o600)
        before = dispatch_state.read_bytes()

        by_state = run_cmd(
            sys.executable, "-I", "-S", "-B", str(script),
            "status", "--dispatch-state", str(dispatch_state), "--format", "json",
        )
        assert by_state.returncode == 0, by_state.stderr
        projection = json.loads(by_state.stdout.decode("utf-8"))
        assert projection["source_kind"] == "dispatcher"
        assert projection["controller_phase"] == "awaiting-verification"
        assert projection["available_actions"][0]["action"] == "result"
        assert "Mutations remain with agy-worker.sh" in projection["advanced_recovery"]
        assert dispatch_state.read_bytes() == before

        by_id = run_cmd(
            sys.executable, "-I", "-S", "-B", str(script),
            "status", "--job-id", job_id, "--format", "json",
            env={"AGY_WORKER_LOG_DIR": str(log_root)},
        )
        assert by_id.returncode == 0, by_id.stderr
        assert json.loads(by_id.stdout.decode("utf-8"))["source_kind"] == "dispatcher"
        return True
    finally:
        f.clean()


check(
    "status projects dispatcher state or job ID through read-only controller authority",
    test_status_projects_dispatcher_state_and_job_id_read_only,
)






# ============================================================================
# 3. verify-finalize command positive, negative, and verifier boundary tests
# ============================================================================

def test_verify_finalize_structured_argv() -> bool:
    f = RepoFixture("verify-argv")
    try:
        # Create initial state
        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": None,
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        f.write_envelope(path="README.md", content="Verified content\n")

        # 1. Reject missing verifiers
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--assurance", "verified"
        )
        assert res.returncode != 0
        assert b"verifier is required" in res.stderr

        # 2. Structured argv verification succeeds
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--verify-argv", '["/usr/bin/git","diff","--check"]',
            "--verify-argv", json.dumps([
                sys.executable, "-I", "-S", "-B", "-c",
                "import os,sys; sys.exit(0 if os.environ.get('PYTHONDONTWRITEBYTECODE') == '1' "
                "and '-p no:cacheprovider' in os.environ.get('PYTEST_ADDOPTS', '') else 1)",
            ], separators=(",", ":")),
            "--assurance", "verified"
        )
        assert res.returncode == 0
        assert f.receipt_file.exists()
        receipt = json.loads(f.receipt_file.read_bytes())
        assert receipt["verdict"] == "gate-passed"
        assert receipt["gate_exit"] == 0

        # State is updated with receipt handle only
        state_updated = json.loads(f.state_file.read_bytes())
        assert state_updated["receipt_path"] == str(f.receipt_file)
        assert "last_result" not in state_updated
        assert "final_assurance" not in state_updated
        assert "final_disposition" not in state_updated

        return True
    finally:
        f.clean()

check("verify-finalize runs structured argv verification and records receipt handle", test_verify_finalize_structured_argv)


def test_verify_finalize_shell_acknowledgements() -> bool:
    f = RepoFixture("verify-shell")
    try:
        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": None,
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        f.write_envelope(path="README.md", content="Shell verified\n")

        # 1. Unacknowledged --verify-shell fails closed
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--verify-shell", "true",
            "--assurance", "verified"
        )
        assert res.returncode != 0
        assert b"requires network and credential access acknowledgements" in res.stderr

        # 2. Acknowledged --verify-shell succeeds
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--verify-shell", "true",
            "--acknowledge-verifier-network",
            "--acknowledge-verifier-credential-access",
            "--assurance", "verified"
        )
        assert res.returncode == 0
        assert f.receipt_file.exists()

        return True
    finally:
        f.clean()

check("verify-finalize enforces explicit acknowledgements for shell verifiers", test_verify_finalize_shell_acknowledgements)


def test_verify_finalize_candidate_binding() -> bool:
    f = RepoFixture("cand-binding")
    try:
        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": None,
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        f.write_envelope(path="README.md", content="Candidate\n")

        # Wrong --candidate-sha fails closed
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--candidate-sha", "f" * 64,
            "--verify-argv", '["true"]',
            "--assurance", "verified"
        )
        assert res.returncode != 0
        assert b"candidate state SHA mismatch" in res.stderr

        # A structurally valid but stale path identity fails before verification.
        current_cand = CANDIDATE.candidate_state_digest(f.worktree, f.base)
        stale_state = copy.deepcopy(initial_state)
        stale_state["worktree_identity"]["ino"] += 1
        f.state_file.write_bytes(WORKFLOW_MODULE.canonical_json(stale_state) + b"\n")
        f.state_file.chmod(0o600)
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--candidate-sha", current_cand,
            "--verify-argv", '["true"]',
            "--assurance", "verified"
        )
        assert res.returncode != 0
        assert b"worktree identity changed" in res.stderr
        assert not f.receipt_file.exists()

        # Correct stored binding and --candidate-sha succeed.
        f.state_file.write_bytes(WORKFLOW_MODULE.canonical_json(initial_state) + b"\n")
        f.state_file.chmod(0o600)
        res = run_workflow(
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file), "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--candidate-sha", current_cand,
            "--verify-argv", '["true"]',
            "--assurance", "partially_verified"
        )
        assert res.returncode == 0
        assert f.receipt_file.exists()
        receipt = json.loads(f.receipt_file.read_bytes())
        assert receipt["final_candidate_state_sha256"] == current_cand

        return True
    finally:
        f.clean()

check("verify-finalize binds exact candidate state and rejects mismatched candidate SHA", test_verify_finalize_candidate_binding)


def test_verify_finalize_propagates_finalize_failure() -> bool:
    f = RepoFixture("finalize-failure")
    try:
        f.write_envelope(path="README.md", content="Finalize candidate\n")
        candidate_sha = CANDIDATE.candidate_state_digest(f.worktree, f.base)
        dispatch_dir = f.state_dir / "dispatch"
        dispatch_dir.mkdir(mode=0o700)
        dispatch_state = dispatch_dir / "dispatch-state.json"
        dispatch_state.write_text(
            json.dumps({"job_id": f.job_id, "provider_isolation": "session"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        dispatch_state.chmod(0o600)
        dispatch_sha = hashlib.sha256(dispatch_state.read_bytes()).hexdigest()

        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": str(dispatch_dir),
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        copied_runtime = f.tmp / "runtime-copy"
        shutil.copytree(RUNTIME, copied_runtime)
        fake_dispatch_module = copied_runtime / "scripts" / "agy_dispatch.py"
        shutil.copyfile(fake_dispatch_module, fake_dispatch_module.with_name("_real_agy_dispatch.py"))
        fake_dispatch_module.write_text(
            "from _real_agy_dispatch import UnsupportedSchemaError, _require_supported_schema\n"
            "import hashlib, json, os, pathlib\n"
            "STATE_NAME='dispatch-state.json'\n"
            "class DispatchError(ValueError): pass\n"
            "def canonical_job(path):\n"
            " path=pathlib.Path(path)\n"
            " if not path.is_absolute() or pathlib.Path(os.path.realpath(path))!=path: raise DispatchError('bad job')\n"
            " return path\n"
            "def load_state(job):\n"
            " raw=(job/STATE_NAME).read_bytes(); value=json.loads(raw); return value,raw,hashlib.sha256(raw).hexdigest()\n"
            "def bound_provider_execution(job,value):\n"
            " return {'legacy':False,'scope':'whole-worktree','agy_sandbox':False,'native_containment':False}\n"
            "def public_status(value,sha,job=None):\n"
            " execution=bound_provider_execution(job,value); return {'job_id':value['job_id'],'phase':'awaiting-verification','controller_phase':'awaiting-verification','state_sha256':sha,'available_actions':[],'provider_isolation':value['provider_isolation'],'provider_execution':execution}\n",
            encoding="utf-8",
        )
        fake_verify = copied_runtime / "verify-job.sh"
        fake_verify.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "receipt = pathlib.Path(sys.argv[sys.argv.index('--receipt') + 1])\n"
            f"receipt.write_text(json.dumps({{'final_candidate_state_sha256': '{candidate_sha}'}}) + '\\n', encoding='utf-8')\n"
            "os.chmod(receipt, 0o600)\n",
            encoding="utf-8",
        )
        fake_verify.chmod(0o755)
        fake_dispatch = copied_runtime / "agy-worker.sh"
        fake_dispatch.write_text(
            "#!/bin/sh\n"
            "for arg in \"$@\"; do if [ \"$arg\" = \"--job-dir\" ]; then echo \"no --job-dir\" >&2; exit 1; fi; done\n"
            "has_id=0; for arg in \"$@\"; do if [ \"$arg\" = \"--job-id\" ]; then has_id=1; fi; done\n"
            "if [ $has_id -eq 0 ]; then echo \"missing --job-id\" >&2; exit 1; fi\n"
            "if [ \"$AGY_WORKER_LOG_DIR\" != \"$FAKE_LOG_ROOT\" ]; then echo \"wrong AGY_WORKER_LOG_DIR\" >&2; exit 1; fi\n"
            "printf '%s\\n' 'finalize rejected exact approval' >&2\n"
            "exit 37\n",
            encoding="utf-8",
        )
        fake_dispatch.chmod(0o755)
        verification_file = f.state_dir / "verification.json"
        verification_file.write_bytes(
            json.dumps(
                {
                    "schema_version": 2,
                    "summary": "driver verification for finalizer failure test",
                    "passed_checks": ["fake bounded verifier"],
                    "failed_checks": [],
                    "advisory_checks": 0,
                    "missing_checks": 0,
                    "candidate_sha256": candidate_sha,
                    "coverage": "complete",
                    "verified_findings": 0,
                    "unresolved_gaps": 0,
                    "diff_review_complete": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        verification_file.chmod(0o600)

        missing_receipt = f.state_dir / "missing-verification-receipt.json"
        missing = run_cmd(
            sys.executable, "-I", "-S", "-B",
            str(copied_runtime / "scripts" / "workflow.py"),
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(missing_receipt),
            "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--candidate-sha", candidate_sha,
            "--verify-argv", '["true"]',
            "--approve-dispatch-sha", dispatch_sha,
            "--assurance", "verified",
            env={"FAKE_LOG_ROOT": str(dispatch_dir.parent)},
        )
        assert missing.returncode == 20
        assert b"driver-authored --verification-json is required" in missing.stderr
        assert not missing_receipt.exists()

        res = run_cmd(
            sys.executable, "-I", "-S", "-B",
            str(copied_runtime / "scripts" / "workflow.py"),
            "verify-finalize", "--state", str(f.state_file),
            "--receipt", str(f.receipt_file),
            "--envelope", str(f.envelope_file),
            "--expect-edits", "--only", "README.md",
            "--candidate-sha", candidate_sha,
            "--verify-argv", '["true"]',
            "--approve-dispatch-sha", dispatch_sha,
            "--verification-json", str(verification_file),
            "--assurance", "verified",
            env={"FAKE_LOG_ROOT": str(dispatch_dir.parent)},
        )
        assert res.returncode == 37
        assert b"finalize rejected exact approval" in res.stderr
        updated = json.loads(f.state_file.read_bytes())
        assert updated["receipt_path"] == str(f.receipt_file)
        return True
    finally:
        f.clean()


check("verify-finalize propagates controller finalization failure", test_verify_finalize_propagates_finalize_failure)


def test_verify_finalize_gate_and_dispatch_approval_boundaries() -> bool:
    f = RepoFixture("finalize-boundaries")
    try:
        f.write_envelope(path="README.md", content="Bound finalization candidate\n")
        candidate_sha = CANDIDATE.candidate_state_digest(f.worktree, f.base)
        dispatch_dir = f.state_dir / "dispatch"
        dispatch_dir.mkdir(mode=0o700)
        dispatch_state = dispatch_dir / "dispatch-state.json"
        dispatch_state.write_text(
            json.dumps({"job_id": f.job_id, "provider_isolation": "session"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        dispatch_state.chmod(0o600)
        dispatch_raw = dispatch_state.read_bytes()
        dispatch_sha = hashlib.sha256(dispatch_raw).hexdigest()

        initial_state = {
            "schema_version": WORKFLOW_MODULE.BOUND_SCHEMA_VERSION,
            "kind": "agy-worker-workflow-state",
            "job_id": f.job_id,
            "repo_path": str(f.repo),
            "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
            "worktree_path": str(f.worktree),
            "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
            "branch": f.branch,
            "branch_ref": f"refs/heads/{f.branch}",
            "base": f.base,
            "provider_isolation": "session",
            "provider_execution": None,
            "preview_manifest_sha256": "0" * 64,
            "preview_content_sha256": "1" * 64,
            "preview_launch_approval_sha256": "2" * 64,
            "native_grant_profile": "baseline",
            "dispatch_job_dir": str(dispatch_dir),
            "job_state_path": None,
            "receipt_path": None,
        }
        store = WORKFLOW_MODULE.WorkflowStateStore(f.state_file, initial=True)
        store.create(initial_state)
        store.close()

        verification_file = f.state_dir / "verification.json"
        verification_file.write_bytes(
            json.dumps(
                {
                    "schema_version": 2,
                    "summary": "driver verification for facade boundary test",
                    "passed_checks": ["bounded verifier"],
                    "failed_checks": [],
                    "advisory_checks": 0,
                    "missing_checks": 0,
                    "candidate_sha256": candidate_sha,
                    "coverage": "complete",
                    "verified_findings": 0,
                    "unresolved_gaps": 0,
                    "diff_review_complete": True,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        verification_file.chmod(0o600)

        copied_runtime = f.tmp / "runtime-boundaries"
        shutil.copytree(RUNTIME, copied_runtime)
        fake_dispatch_module = copied_runtime / "scripts" / "agy_dispatch.py"
        shutil.copyfile(fake_dispatch_module, fake_dispatch_module.with_name("_real_agy_dispatch.py"))
        fake_dispatch_module.write_text(
            "from _real_agy_dispatch import UnsupportedSchemaError, _require_supported_schema\n"
            "import hashlib, json, os, pathlib\n"
            "STATE_NAME='dispatch-state.json'\n"
            "class DispatchError(ValueError): pass\n"
            "def canonical_job(path):\n"
            " path=pathlib.Path(path)\n"
            " if not path.is_absolute() or pathlib.Path(os.path.realpath(path))!=path: raise DispatchError('bad job')\n"
            " return path\n"
            "def load_state(job):\n"
            " raw=(job/STATE_NAME).read_bytes(); value=json.loads(raw); return value,raw,hashlib.sha256(raw).hexdigest()\n"
            "def bound_provider_execution(job,value):\n"
            " return {'legacy':False,'scope':'whole-worktree','agy_sandbox':False,'native_containment':False}\n"
            "def public_status(value,sha,job=None):\n"
            " execution=bound_provider_execution(job,value); return {'job_id':value['job_id'],'phase':'awaiting-verification','controller_phase':'awaiting-verification','state_sha256':sha,'available_actions':[],'provider_isolation':value['provider_isolation'],'provider_execution':execution}\n",
            encoding="utf-8",
        )
        status = run_cmd(
            sys.executable, "-I", "-S", "-B", str(copied_runtime / "scripts" / "workflow.py"),
            "status", "--state", str(f.state_file),
        )
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout)["dispatch"]["state_sha256"] == dispatch_sha

        fake_verify = copied_runtime / "verify-job.sh"
        fake_verify.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "receipt = pathlib.Path(sys.argv[sys.argv.index('--receipt') + 1])\n"
            "candidate = os.environ['FAKE_CANDIDATE_SHA']\n"
            "receipt.write_text(json.dumps({'final_candidate_state_sha256': candidate}) + '\\n', encoding='utf-8')\n"
            "os.chmod(receipt, 0o600)\n"
            "changed = os.environ.get('FAKE_CHANGED_DISPATCH')\n"
            "if changed:\n"
            "    path = pathlib.Path(changed)\n"
            "    path.write_text(json.dumps({'job_id': os.environ['FAKE_JOB_ID'], 'provider_isolation': 'session', 'changed': True}, sort_keys=True) + '\\n', encoding='utf-8')\n"
            "    os.chmod(path, 0o600)\n"
            "raise SystemExit(int(os.environ.get('FAKE_GATE_RC', '0')))\n",
            encoding="utf-8",
        )
        fake_verify.chmod(0o755)
        sentinel = f.state_dir / "finalizer-called"
        fake_dispatch = copied_runtime / "agy-worker.sh"
        fake_dispatch.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "if '--job-dir' in sys.argv:\n"
            "    raise SystemExit('agy-worker.sh does not accept --job-dir')\n"
            "if '--job-id' not in sys.argv or sys.argv[sys.argv.index('--job-id') + 1] != os.environ['FAKE_JOB_ID']:\n"
            "    raise SystemExit('missing or wrong --job-id')\n"
            "if os.environ.get('AGY_WORKER_LOG_DIR') != os.environ['FAKE_LOG_ROOT']:\n"
            "    raise SystemExit('missing or wrong AGY_WORKER_LOG_DIR')\n"
            "pathlib.Path(os.environ['FAKE_FINALIZER_SENTINEL']).write_text('called\\n', encoding='utf-8')\n"
            "print('{}')\n",
            encoding="utf-8",
        )
        fake_dispatch.chmod(0o755)

        def invoke(
            receipt: Path,
            *,
            approval: str | None,
            gate_rc: int = 0,
            change_dispatch: bool = False,
        ) -> subprocess.CompletedProcess[bytes]:
            argv = [
                sys.executable, "-I", "-S", "-B",
                str(copied_runtime / "scripts" / "workflow.py"),
                "verify-finalize", "--state", str(f.state_file),
                "--receipt", str(receipt), "--envelope", str(f.envelope_file),
                "--expect-edits", "--only", "README.md",
                "--candidate-sha", candidate_sha,
                "--verify-argv", '["true"]',
                "--verification-json", str(verification_file),
                "--assurance", "verified",
            ]
            if approval is not None:
                argv += ["--approve-dispatch-sha", approval]
            env = {
                "FAKE_CANDIDATE_SHA": candidate_sha,
                "FAKE_FINALIZER_SENTINEL": str(sentinel),
                "FAKE_GATE_RC": str(gate_rc),
                "FAKE_JOB_ID": f.job_id,
                "FAKE_LOG_ROOT": str(dispatch_dir.parent),
            }
            if change_dispatch:
                env["FAKE_CHANGED_DISPATCH"] = str(dispatch_state)
            return run_cmd(*argv, env=env)

        missing = invoke(f.state_dir / "missing-approval.json", approval=None)
        assert missing.returncode == 20
        assert b"--approve-dispatch-sha" in missing.stderr
        assert not sentinel.exists()

        stale = invoke(f.state_dir / "stale-approval.json", approval="f" * 64)
        assert stale.returncode == 20
        assert b"stale or mismatched" in stale.stderr
        assert not sentinel.exists()

        for gate_rc in (10, 11, 12, 13, 14, 15):
            receipt = f.state_dir / f"gate-{gate_rc}.json"
            rejected = invoke(receipt, approval=dispatch_sha, gate_rc=gate_rc)
            assert rejected.returncode == gate_rc
            assert receipt.exists()
            assert not sentinel.exists()
            assert dispatch_state.read_bytes() == dispatch_raw

        exact = invoke(f.state_dir / "exact.json", approval=dispatch_sha)
        assert exact.returncode == 0
        assert sentinel.read_text(encoding="utf-8") == "called\n"
        sentinel.unlink()

        changed = invoke(
            f.state_dir / "changed.json",
            approval=dispatch_sha,
            change_dispatch=True,
        )
        assert changed.returncode == 20
        assert b"changed during verification" in changed.stderr
        assert not sentinel.exists()
        return True
    finally:
        f.clean()


check(
    "verify-finalize requires exact dispatch approval and never finalizes failed gates",
    test_verify_finalize_gate_and_dispatch_approval_boundaries,
)


def _tree_snapshot(root: Path) -> dict[str, tuple[Any, ...]]:
    """Observe artifacts, Git metadata, and directory mtimes without atime noise."""
    result = {}
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        payload = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_ino, info.st_size, info.st_mtime_ns, payload,
        )
    return result


def _rejection_without_effects(root: Path, argv: list[str], expected: str, *, code: int = 20) -> None:
    before = _tree_snapshot(root)
    original_run = subprocess.run

    def read_only_git(command: list[str], *args: Any, **kwargs: Any) -> Any:
        assert Path(command[0]).name == "git", "provider/verifier/controller process started"
        assert not {"remove", "prune", "reset", "clean", "update-ref", "checkout", "-D"}.intersection(command)
        return original_run(command, *args, **kwargs)

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        for name in ("_dispatch_run", "_run_lifecycle", "canonical_transmission_preview"):
            stack.enter_context(mock.patch.object(WORKFLOW_MODULE, name, side_effect=AssertionError("effect before rejection")))
        stack.enter_context(mock.patch.object(subprocess, "run", side_effect=read_only_git))
        stack.enter_context(contextlib.redirect_stdout(stdout))
        stack.enter_context(contextlib.redirect_stderr(stderr))
        try:
            result = WORKFLOW_MODULE.main(argv)
        except SystemExit as exc:
            raise AssertionError(f"parser exited before schema validation: {stderr.getvalue()}") from exc
        assert result == code, stderr.getvalue()
    diagnostic = stderr.getvalue()
    assert expected in diagnostic, diagnostic
    assert "Traceback" not in diagnostic and "fatal error" not in diagnostic
    assert "untrusted-version-marker" not in diagnostic
    assert not stdout.getvalue()
    assert _tree_snapshot(root) == before, "rejected input changed bytes, identities, modes, or mtimes"


def _explicit_state(f: RepoFixture) -> dict[str, Any]:
    return {
        "schema_version": 5, "kind": "agy-worker-workflow-state", "job_id": f.job_id,
        "repo_path": str(f.repo), "repo_identity": WORKFLOW_MODULE.identity(f.repo.lstat()),
        "worktree_path": str(f.worktree), "worktree_identity": WORKFLOW_MODULE.identity(f.worktree.lstat()),
        "branch": f.branch, "branch_ref": f"refs/heads/{f.branch}", "base": f.base,
        "provider_isolation": "session", "provider_execution": None,
        "preview_manifest_sha256": "0" * 64, "preview_content_sha256": "1" * 64,
        "preview_launch_approval_sha256": "2" * 64, "native_grant_profile": "baseline",
        "dispatch_job_dir": None, "job_state_path": None, "receipt_path": None,
    }


def test_workflow_versions_reject_before_effects() -> bool:
    f = RepoFixture("version-boundary")
    try:
        current = _explicit_state(f)
        assert WORKFLOW_MODULE.validate_workflow_state(current) == current
        for version in (1, 2, 3, 4, None, True, False, "untrusted-version-marker", "5", 5.5, 0, -1, 999999):
            state = dict(current)
            if version is None:
                del state["schema_version"]
            else:
                state["schema_version"] = version
            f.state_file.write_bytes(WORKFLOW_MODULE.canonical_json(state) + b"\n")
            f.state_file.chmod(0o600)
            before = _tree_snapshot(f.tmp)
            try:
                WORKFLOW_MODULE.WorkflowStateStore(f.state_file)
            except WORKFLOW_MODULE.UnsupportedWorkflowSchemaError as exc:
                assert "supported: v5 or v6" in str(exc)
                assert "Finish or discard the job" in str(exc)
                assert "untrusted-version-marker" not in str(exc)
            else:
                raise AssertionError(f"unsupported workflow schema accepted: {version!r}")
            assert _tree_snapshot(f.tmp) == before
            commands = [
                ["status", "--state", str(f.state_file)],
                ["run", "--state", str(f.state_file), "--repo", str(f.repo),
                 "--worktree", str(f.worktree), "--branch", f.branch, "--base", f.base,
                 "--job-id", f.job_id, "--approve-whole-worktree", "2" * 64, "--task", "bounded"],
                ["verify-finalize", "--state", str(f.state_file), "--receipt", str(f.receipt_file),
                 "--envelope", str(f.envelope_file),
                 "--verify-argv", '["/usr/bin/true"]', "--assurance", "verified"],
            ]
            for argv in commands:
                _rejection_without_effects(f.tmp, argv, "workflow state schema")
        schema = json.loads(SCHEMA_PATH.read_bytes())
        assert schema["properties"]["schema_version"]["enum"] == [5, 6]
        return True
    finally:
        f.clean()


check("retired and malformed workflow versions reject before reads become effects", test_workflow_versions_reject_before_effects)


def test_referenced_dispatch_versions_reject_before_effects() -> bool:
    f = RepoFixture("dispatch-version-boundary")
    try:
        spec = importlib.util.spec_from_file_location("workflow_dispatch_fixture", ROOT / "tests/test-self-verification-lifecycle.py")
        assert spec is not None and spec.loader is not None
        fixture_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture_module)
        job, _sha, worktree = fixture_module.SelfVerificationLifecycle().fixture(str(f.tmp / "dispatch-fixture"), allow=False)
        # The explicit dispatcher-status route requires dirname == job_id.
        canonical_job = job.with_name("fixture")
        job.rename(canonical_job)
        job = canonical_job
        dispatch = WORKFLOW_MODULE.DISPATCH
        state_path, command_path = job / dispatch.STATE_NAME, job / dispatch.COMMAND_NAME
        state_raw, command_raw = state_path.read_bytes(), command_path.read_bytes()
        current_state, current_command = json.loads(state_raw), json.loads(command_raw)
        assert (current_state["schema_version"], current_command["schema_version"]) == (dispatch.CURRENT_STATE_SCHEMA, dispatch.CURRENT_COMMAND_SCHEMA)
        state = _explicit_state(f)
        repo = worktree.parent / "owner"
        branch = git(worktree, "branch", "--show-current")
        state.update({"job_id": current_state["job_id"], "repo_path": str(repo),
                      "repo_identity": WORKFLOW_MODULE.identity(repo.lstat()),
                      "worktree_path": str(worktree), "worktree_identity": WORKFLOW_MODULE.identity(worktree.lstat()),
                      "branch": branch, "branch_ref": f"refs/heads/{branch}",
                      "base": git(worktree, "rev-parse", "HEAD"), "dispatch_job_dir": str(job)})
        f.state_file.write_bytes(WORKFLOW_MODULE.canonical_json(state) + b"\n")
        f.state_file.chmod(0o600)
        for target, current, versions, label in (
            (state_path, current_state, range(1, dispatch.CURRENT_STATE_SCHEMA), "dispatch state schema"),
            (command_path, current_command, range(1, dispatch.CURRENT_COMMAND_SCHEMA), "dispatch command schema"),
        ):
            for version in versions:
                state_path.write_bytes(state_raw)
                command_path.write_bytes(command_raw)
                target.write_bytes(dispatch.canonical({**current, "schema_version": version}))
                before = _tree_snapshot(f.tmp)
                try:
                    WORKFLOW_MODULE._bound_dispatch_status(job, current_state["job_id"])
                except WORKFLOW_MODULE.UnsupportedWorkflowSchemaError as exc:
                    assert label in str(exc)
                    assert "Finish or discard the job" in str(exc)
                else:
                    raise AssertionError("retired dispatch record was projected")
                assert _tree_snapshot(f.tmp) == before
                for argv in (
                    ["status", "--state", str(f.state_file)],
                    ["status", "--dispatch-state", str(state_path)],
                    ["verify-finalize", "--state", str(f.state_file), "--receipt", str(f.receipt_file),
                     "--envelope", str(f.envelope_file),
                     "--verify-argv", '["/usr/bin/true"]', "--approve-dispatch-sha", hashlib.sha256(state_path.read_bytes()).hexdigest(),
                     "--assurance", "verified"],
                ):
                    _rejection_without_effects(f.tmp, argv, label)
        return True
    finally:
        f.clean()


check("workflow projections and finalization reject retired referenced dispatch records", test_referenced_dispatch_versions_reject_before_effects)


def test_removed_approval_flags_reject_before_effects() -> bool:
    f = RepoFixture("removed-approval-flags")
    try:
        f.state_file.write_bytes(WORKFLOW_MODULE.canonical_json(_explicit_state(f)) + b"\n")
        f.state_file.chmod(0o600)
        for flag, replacement, base in (
            ("--approve-preview-sha", "--approve-whole-worktree", ["run", "--repo", str(f.repo), "--job-id", f.job_id]),
            ("--legacy-preview-approval", "--approve-whole-worktree", ["run", "--repo", str(f.repo), "--job-id", f.job_id]),
            ("--approve-state-sha", "--approve-dispatch-sha", ["verify-finalize", "--state", str(f.state_file),
                                                                  "--envelope", str(f.envelope_file),
                                                                  "--receipt", str(f.receipt_file), "--assurance", "verified"]),
        ):
            for removed in ([flag, "a" * 64], [f"{flag}={'a' * 64}"]):
                for current in ([], [replacement, "b" * 64]):
                    _rejection_without_effects(f.tmp, base + current + removed,
                                               f"{flag} was removed after v0.22.0; use {replacement}.", code=64)
        return True
    finally:
        f.clean()


check("removed workflow approval flags reject split, equals, and mixed current forms before effects", test_removed_approval_flags_reject_before_effects)


# ============================================================================
# 4. Packaging and wrappers parity tests
# ============================================================================

def test_packaging_and_wrappers() -> bool:
    root_wrapper = ROOT / "workflow.sh"
    runtime_wrapper = RUNTIME / "workflow.sh"
    script_file = RUNTIME / "scripts" / "workflow.py"
    schema_file = RUNTIME / "schemas" / "workflow-state.schema.json"

    assert root_wrapper.exists() and os.access(root_wrapper, os.X_OK)
    assert runtime_wrapper.exists() and os.access(runtime_wrapper, os.X_OK)
    assert script_file.exists() and os.access(script_file, os.X_OK)
    assert schema_file.exists()

    # Verify root wrapper executes runtime wrapper
    res = run_cmd(str(root_wrapper), "--help")
    assert res.returncode == 0
    assert b"Canonical workflow facade" in res.stdout

    # Verify runtime wrapper executes workflow.py
    res = run_cmd(str(runtime_wrapper), "--help")
    assert res.returncode == 0
    assert b"Canonical workflow facade" in res.stdout

    return True

check("root and runtime workflow wrappers and permissions are intact", test_packaging_and_wrappers)


print()
print(f"PASSED: {passed} tests")
if failed:
    print(f"FAILED: {failed} tests")
    raise SystemExit(1)
