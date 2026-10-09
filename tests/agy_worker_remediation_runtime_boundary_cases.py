#!/usr/bin/env python3
"""Runtime-boundary cases loaded by the canonical remediation suite."""
from __future__ import annotations

from typing import TYPE_CHECKING

# run() receives these names from test-agy-worker-remediation.py globals.
# These declarations are static only; the live objects still come from context.
if TYPE_CHECKING:
    from types import ModuleType
    from typing import cast
    from typing import Callable
    MODULE: ModuleType = cast(ModuleType, ...)
    from pathlib import Path
    SOURCE: Path = cast(Path, ...)
    def check(label: str, action: Callable[[], object]) -> None: ...
    def current_command_fixture(values: dict, *, bind_launch: bool=True) -> dict: ...
    import copy
    import importlib.util
    import stat
    import fcntl
    import io
    import json
    import os
    def provider_schema(path: Path) -> None: ...
    def report(**updates: object) -> dict: ...
    root: Path = cast(Path, ...)
    def run_controller(job: Path, bin_dir: Path) -> int: ...
    import shlex
    import signal
    import subprocess
    import sys
    import threading
    import time


def run(context: dict[str, object]) -> None:
    """Run the direct-selection boundary check in the canonical context."""
    globals().update(context)
    def direct_selection_reprobes_every_controller_attempt() -> None:
        """The controller, not PATH, owns the exact direct executable launch."""
        help_text = """Usage of agy:
  --add-dir  Add a directory
  --conversation  Resume a conversation
  --disable-slash-commands  Disable slash commands
  --effort  Reasoning effort (low|medium|high|max)
  --json-schema  Schema path
  --mode  Execution mode (accept-edits, plan)
  --model  Select a model
  --output-format  Format (text, json, stream-json)
  --print  Run a prompt
  --print-timeout  Print timeout
  --sandbox  Sandboxed
"""

        def fixture(
            label: str, workflow: str = "task", *, idle_seconds: float = 2,
            hard_seconds: float = 3, max_seconds: float = 20,
            max_cycles: int = 2,
        ) -> tuple[Path, Path, Path, Path, dict]:
            repo = (root / f"direct-reprobe-repo-{label}").resolve()
            source_repo = (root / f"direct-reprobe-source-{label}").resolve()
            subprocess.run(["git", "init", "-q", str(source_repo)], check=True)
            subprocess.run([
                "git", "-C", str(source_repo), "-c", "user.name=Fixture",
                "-c", "user.email=fixture@example.invalid", "commit",
                "--allow-empty", "-qm", "fixture",
            ], check=True)
            subprocess.run([
                "git", "-C", str(source_repo), "worktree", "add", "-q", "-b",
                f"fixture-{label}", str(repo), "HEAD",
            ], check=True)
            job = root / f"direct-reprobe-job-{label}"; job.mkdir(mode=0o700); job = job.resolve()
            bin_dir = root / f"direct-reprobe-bin-{label}"; bin_dir.mkdir()
            calls = root / f"direct-reprobe-calls-{label}"
            args = root / f"direct-reprobe-args-{label}"
            cwd = root / f"direct-reprobe-cwd-{label}"
            schema = root / f"direct-reprobe-provider-{label}.json"; provider_schema(schema)
            events = [
                {"event": "init", "init": {}, "conversation_id": "conversation-1"},
                {"event": "step_update", "step_update": {}},
                {"event": "result", "result": {"conversation_id": "conversation-1", "status": "SUCCESS", "structured_output": report()}},
            ]
            fake = bin_dir / "agy"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then printf 'version\\n' >> " + shlex.quote(str(calls)) + "; printf '1.2.11\\n'; exit 0; fi\n"
                "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then printf 'help\\n' >> " + shlex.quote(str(calls)) + "; sleep \"${FAKE_DIRECT_HELP_DELAY:-0}\"; cat >&2 <<'HELP'\n" + help_text + "HELP\nexit 0\nfi\n"
                "printf 'provider\\n' >> " + shlex.quote(str(calls)) + "\nprintf '%s\\n' \"$@\" > " + shlex.quote(str(args)) + "\npwd > " + shlex.quote(str(cwd)) + "\n"
                + "if [ -n \"${FAKE_DIRECT_HEARTBEAT_COUNT:-}\" ]; then\n"
                + "  printf '%s\\n' " + shlex.quote(json.dumps(events[0])) + "\n"
                + "  i=0\n  while [ \"$i\" -lt \"$FAKE_DIRECT_HEARTBEAT_COUNT\" ]; do\n"
                + "    printf '%s\\n' " + shlex.quote(json.dumps(events[1])) + "\n"
                + "    sleep \"${FAKE_DIRECT_HEARTBEAT_DELAY:-0.10}\"\n"
                + "    i=$((i + 1))\n  done\n"
                + "  printf '%s\\n' " + shlex.quote(json.dumps(events[2])) + "\n"
                + "  exit 0\nfi\n"
                + "\n".join("printf '%s\\n' " + shlex.quote(json.dumps(item)) for item in events) + "\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            previous_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{previous_path}"
            try:
                selection = MODULE.MODEL_SELECTION.resolve_selection(
                    "gemini-3.6-flash", "high", "cli", "cli", probe_version=True,
                )
            finally:
                os.environ["PATH"] = previous_path
            assert selection["schema_version"] == 5
            assert not ({"compatibility_disposition", "approved_help_sha256", "compatibility_decision_sha256"} & set(selection))
            selection_path = job / "selection.json"
            MODULE.MODEL_SELECTION.publish_record(selection_path, selection)
            raw, info = MODULE.read_regular(selection_path, MODULE.MAX_COMMAND_BYTES, "fixture selection")
            command = current_command_fixture({
                "schema_version": MODULE.CURRENT_COMMAND_SCHEMA, "kind": "agy-worker-dispatch-command", "job_id": f"direct-{label}",
                "workdir": str(repo), "argv": ["agy", "--mode", "accept-edits", "--add-dir", str(repo), "--json-schema", str(schema), "--model", "gemini-3.6-flash", "--effort", "high", "--print", "task"],
                "agy_version": "1.2.11", "agy_version_observed": True,
                "selection_path": str(selection_path), "selection_sha256": MODULE.digest(raw), "selection_identity": list(MODULE._identity(info)),
                "idle_seconds": idle_seconds, "hard_seconds": hard_seconds, "max_seconds": max_seconds, "notice_seconds": 3,
                "stage_dir": None, "stage_file": None, "child_umask": "022", "workflow": workflow,
                "max_cycles": max_cycles, "resume_prompt": "resume", "continue_prompt": "continue",
                "provider_env": [
                    "FAKE_DIRECT_HEARTBEAT_COUNT", "FAKE_DIRECT_HEARTBEAT_DELAY",
                    "FAKE_DIRECT_HELP_DELAY",
                ],
                "provider_scope_path": None, "provider_scope_sha256": None,
                "provider_scope_identity": None, "approved_transmission_sha256": None,
            })
            MODULE.write_atomic(job, MODULE.COMMAND_NAME, command)
            MODULE.create_state(job, "initial", resume=False)
            calls.unlink(missing_ok=True)
            return job, bin_dir, calls, fake, command

        def assert_attempt(job: Path, bin_dir: Path, calls: Path, command: dict, origin: str) -> None:
            observed_provider_executables: list[str | None] = []
            real_popen = MODULE.subprocess.Popen

            def inspect_popen(arguments, *popen_args, **popen_kwargs):
                if isinstance(arguments, list) and arguments and arguments[0] == "agy":
                    observed_provider_executables.append(popen_kwargs.get("executable"))
                return real_popen(arguments, *popen_args, **popen_kwargs)

            MODULE.subprocess.Popen = inspect_popen
            try:
                returncode = run_controller(job, bin_dir)
            finally:
                MODULE.subprocess.Popen = real_popen
            if returncode != 0:
                failed, _raw, _sha = MODULE.load_state(job)
                raise AssertionError((returncode, failed.get("reason"), calls.read_text(encoding="utf-8").splitlines()))
            assert observed_provider_executables == [str((bin_dir / "agy").resolve())]
            assert calls.read_text(encoding="utf-8").splitlines() == ["version", "help", "provider"]
            state, _raw, _sha = MODULE.load_state(job)
            assert state["status"] == "succeeded"
            assert state["selection_sha256"] == command["selection_sha256"]
            assert state["selection_identity"] == command["selection_identity"]
            assert state["attempt_origin"] == origin
            label = command["job_id"].removeprefix("direct-")
            provider_arguments = (root / f"direct-reprobe-args-{label}").read_text(
                encoding="utf-8",
            ).splitlines()
            if origin in {"conversation-resume", "conversation-continue"}:
                assert provider_arguments.count("--conversation") == 1
                conversation_index = provider_arguments.index("--conversation")
                assert provider_arguments[conversation_index + 1] == "conversation-1"
            else:
                assert "--conversation" not in provider_arguments

        # Initial, resume, and explicit restart each enter the same controller
        # path and must re-probe directly before their provider Popen.
        initial_job, initial_bin, initial_calls, _initial_fake, initial_command = fixture("initial")
        assert_attempt(initial_job, initial_bin, initial_calls, initial_command, "initial")

        for origin in ("conversation-resume", "fresh-restart"):
            job, bin_dir, calls, _fake, command = fixture(origin)
            state, _raw, sha = MODULE.load_state(job)
            state.update({
                "status": "failed", "reason": "agy_failed_unclassified", "exit_code": 5,
                "finished_epoch": 1.0, "conversation_id": "conversation-1",
                "resume_available": True, "phase": "attempt-failed", "assurance": "pending",
                "next_action": "resume", "driver_disposition": "not_applicable",
            })
            _raw, sha = MODULE.write_atomic(job, MODULE.STATE_NAME, state)
            queued, _next_sha = MODULE.create_state(job, origin, resume=True, approve_sha=sha)
            assert queued["status"] == "queued"
            calls.unlink(missing_ok=True)
            assert_attempt(job, bin_dir, calls, command, origin)

        # A continuation preserves one accepted conversation and candidate, but
        # still gets a fresh executable/version/help proof before launch.
        job, bin_dir, calls, _fake, command = fixture("continue")
        state, _raw, sha = MODULE.load_state(job)
        envelope = job / "envelope.json"; payload = json.dumps(report()).encode() + b"\n"
        envelope.write_bytes(payload); envelope.chmod(0o600)
        _bound, info = MODULE.read_regular(envelope, 1024 * 1024, "fixture envelope")
        snapshot = MODULE._worktree_snapshot(command["workdir"])
        assert snapshot is not None
        state.update({
            "status": "succeeded", "exit_code": 0, "finished_epoch": 1.0,
            "conversation_id": "conversation-1", "result_path": str(envelope),
            "result_sha256": MODULE.digest(payload), "result_identity": list(MODULE._identity(info)),
            "candidate_recognized": True, "candidate_source": "provider_success", "result_available": True,
            "driver_disposition": "unreviewed", "phase": "awaiting-verification", "assurance": "pending",
            "continue_available": True, "next_action": "driver_review",
            "candidate_worktree_sha256": snapshot["sha256"], "candidate_worktree_entries": snapshot["entries"],
        })
        _raw, sha = MODULE.write_atomic(job, MODULE.STATE_NAME, state)
        verification = {
            "schema_version": 2, "summary": "driver found a repair", "passed_checks": [], "failed_checks": ["fixture"],
            "advisory_checks": 0, "missing_checks": 0, "candidate_sha256": state["result_sha256"],
            "coverage": "partial", "verified_findings": 1, "unresolved_gaps": 1, "diff_review_complete": True,
        }
        queued, _next_sha = MODULE.create_state(job, "conversation-continue", resume=True, approve_sha=sha, verification=verification)
        assert queued["conversation_id"] == "conversation-1"
        calls.unlink(missing_ok=True)
        assert_attempt(job, bin_dir, calls, command, "conversation-continue")
        repaired, _raw, repaired_sha = MODULE.load_state(job)
        # This repair input is bound audit evidence for the prior candidate;
        # it is not evidence about the replacement candidate which arrived
        # from the provider on this new attempt.
        assert repaired["verification_path"] is not None
        assert json.loads(Path(repaired["verification_path"]).read_text(encoding="utf-8")) == verification
        assert repaired["check_summary"] is None
        assert repaired["check_counts"] == {"passed": 0, "failed": 0, "advisory": 0, "missing": 0}
        repaired_public = MODULE.public_status(repaired, repaired_sha, job=job)
        assert repaired_public["driver_disposition"] == "unreviewed"
        assert repaired_public["check_summary"] is None
        assert repaired_public["check_counts"] == {"passed": 0, "failed": 0, "advisory": 0, "missing": 0}

        def queue_bound_origin(job: Path, command: dict, origin: str) -> None:
            state, _raw, sha = MODULE.load_state(job)
            if origin in {"conversation-resume", "fresh-restart"}:
                state.update({
                    "status": "failed", "reason": "agy_failed_unclassified", "exit_code": 5,
                    "finished_epoch": 1.0, "conversation_id": "conversation-1",
                    "resume_available": True, "phase": "attempt-failed", "assurance": "pending",
                    "next_action": "resume", "driver_disposition": "not_applicable",
                })
                _raw, sha = MODULE.write_atomic(job, MODULE.STATE_NAME, state)
                MODULE.create_state(job, origin, resume=True, approve_sha=sha)
                return
            envelope = job / "matrix-mutation-envelope.json"
            payload = json.dumps(report()).encode() + b"\n"
            envelope.write_bytes(payload); envelope.chmod(0o600)
            _bound, info = MODULE.read_regular(envelope, 1024 * 1024, "fixture envelope")
            snapshot = MODULE._worktree_snapshot(command["workdir"])
            assert snapshot is not None
            state.update({
                "status": "succeeded", "exit_code": 0, "finished_epoch": 1.0,
                "conversation_id": "conversation-1", "result_path": str(envelope),
                "result_sha256": MODULE.digest(payload), "result_identity": list(MODULE._identity(info)),
                "candidate_recognized": True, "candidate_source": "provider_success", "result_available": True,
                "driver_disposition": "unreviewed", "phase": "awaiting-verification", "assurance": "pending",
                "continue_available": True, "next_action": "driver_review",
                "candidate_worktree_sha256": snapshot["sha256"], "candidate_worktree_entries": snapshot["entries"],
            })
            _raw, sha = MODULE.write_atomic(job, MODULE.STATE_NAME, state)
            continuation_feedback = {
                "schema_version": 2, "summary": "driver found a repair", "passed_checks": [], "failed_checks": ["fixture"],
                "advisory_checks": 0, "missing_checks": 0, "candidate_sha256": state["result_sha256"],
                "coverage": "partial", "verified_findings": 1, "unresolved_gaps": 1, "diff_review_complete": True,
            }
            MODULE.create_state(
                job, "conversation-continue", resume=True, approve_sha=sha,
                verification=continuation_feedback,
            )

        # Malformed frozen caller selection remains rejected before any
        # executable or provider action on later attempts.
        bad_frozen = root / "bad-frozen-selection.json"
        malformed_frozen = json.loads(Path(initial_command["selection_path"]).read_text(encoding="utf-8"))
        malformed_frozen["resolved_agy_model"] = "different-model"
        bad_frozen.write_text(json.dumps(malformed_frozen), encoding="utf-8")
        try:
            MODULE.MODEL_SELECTION.read_selection_record(bad_frozen, frozen=True)
        except MODULE.MODEL_SELECTION.CallerError:
            pass
        else:
            raise AssertionError("malformed frozen selection evidence was accepted")

        # The bound read, not a later pathname reopen, owns frozen selection
        # semantics.  Swap a valid B record immediately after read_regular has
        # returned A: this call must still decode A, and the next controller
        # binding check must reject the replacement before any local probe or
        # provider launch.
        swap_job, swap_bin, swap_calls, _swap_fake, swap_command = fixture("record-toctou")
        swap_state, _raw, _sha = MODULE.load_state(swap_job)
        selection_path = Path(swap_command["selection_path"])
        record_a = json.loads(selection_path.read_text(encoding="utf-8"))
        record_b = copy.deepcopy(record_a)
        record_b["resolved_agy_model"] = "gemini-3.1-pro-high"
        replacement = selection_path.with_name("selection-b.json")
        replacement.write_text(json.dumps(record_b) + "\n", encoding="utf-8")
        replacement.chmod(0o600)
        original_read_regular = MODULE.read_regular
        swapped = False

        def swap_after_bound_read(path: Path, limit: int, label: str):
            nonlocal swapped
            payload, info = original_read_regular(path, limit, label)
            if label == "dispatch selection" and Path(path) == selection_path and not swapped:
                os.replace(replacement, selection_path)
                swapped = True
            return payload, info

        MODULE.read_regular = swap_after_bound_read
        try:
            bound_record = MODULE._load_bound_selection(swap_command, swap_state)
        finally:
            MODULE.read_regular = original_read_regular
        assert swapped and bound_record is not None
        assert bound_record["resolved_agy_model"] == record_a["resolved_agy_model"]
        assert bound_record["resolved_agy_model"] != record_b["resolved_agy_model"]
        assert run_controller(swap_job, swap_bin) == MODULE.EXIT_BY_REASON["status_unavailable"]
        assert not swap_calls.exists(), "selection replacement reached a local probe or provider"
        swap_terminal, _raw, _sha = MODULE.load_state(swap_job)
        assert (swap_terminal["reason"], swap_terminal["failure_stage"]) == (
            "status_unavailable", "binding_failure",
        )

        # Local controller proofs run before a provider process exists.  A
        # slow exact version/help probe therefore cannot consume the provider
        # hard or idle lease; the provider still gets its full bounded window.
        expired_job, expired_bin, expired_calls, _expired_fake, _expired_command = fixture(
            "deadline-preflight", idle_seconds=0.25, hard_seconds=0.50, max_seconds=5,
        )
        previous_delay = os.environ.get("FAKE_DIRECT_HELP_DELAY")
        os.environ["FAKE_DIRECT_HELP_DELAY"] = "0.75"
        try:
            assert run_controller(expired_job, expired_bin) == 0
        finally:
            if previous_delay is None:
                os.environ.pop("FAKE_DIRECT_HELP_DELAY", None)
            else:
                os.environ["FAKE_DIRECT_HELP_DELAY"] = previous_delay
        expired, _raw, _sha = MODULE.load_state(expired_job)
        assert expired["status"] == "succeeded"
        assert expired["elapsed_seconds"] < expired["hard_seconds"]
        assert expired_calls.read_text(encoding="utf-8").splitlines() == ["version", "help", "provider"]

        # The worktree reconciliation has the same ownership: it is a strict
        # local launch guard, not provider execution.  Simulate a slow safe
        # Git path without relaxing any provider timeout.
        scan_job, scan_bin, scan_calls, _scan_fake, _scan_command = fixture(
            "deadline-worktree-scan", idle_seconds=0.25, hard_seconds=0.50, max_seconds=5,
        )
        original_baseline = MODULE._bound_worktree_baseline

        def slow_bound_baseline(state: dict, command: dict) -> None:
            time.sleep(0.75)
            original_baseline(state, command)

        MODULE._bound_worktree_baseline = slow_bound_baseline
        try:
            assert run_controller(scan_job, scan_bin) == 0
        finally:
            MODULE._bound_worktree_baseline = original_baseline
        scanned, _raw, _sha = MODULE.load_state(scan_job)
        assert scanned["status"] == "succeeded"
        assert scanned["elapsed_seconds"] < scanned["hard_seconds"]
        assert scan_calls.read_text(encoding="utf-8").splitlines() == ["version", "help", "provider"]

        # Exercise the public asynchronous start surface, whose startup
        # handshake is deliberately only five seconds.  Controller-owned
        # queued state must acknowledge startup before a safe but slow local
        # probe completes; the probe itself remains outside provider runtime.
        spawn_job, spawn_bin, spawn_calls, _spawn_fake, _spawn_command = fixture(
            "public-spawn-slow-preflight", idle_seconds=0.50,
            hard_seconds=1.0, max_seconds=5,
        )
        (spawn_job / MODULE.STATE_NAME).unlink()
        spawn_output = io.BytesIO()

        class _SpawnStdout:
            buffer = spawn_output

        previous_stdout = MODULE.sys.stdout
        previous_path = os.environ.get("PATH", "")
        real_spawn_popen = MODULE.subprocess.Popen
        slow_controller = root / "slow-public-spawn-controller.py"
        slow_controller.write_text(
            "import importlib.util\n"
            "from pathlib import Path\n"
            "import sys\n"
            "import time\n"
            "source, job, ownership_fd = sys.argv[1:]\n"
            "spec = importlib.util.spec_from_file_location('slow_spawn_dispatch', source)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "original = module._bound_worktree_baseline\n"
            "def slow_baseline(state, command):\n"
            "    time.sleep(5.25)\n"
            "    original(state, command)\n"
            "module._bound_worktree_baseline = slow_baseline\n"
            "raise SystemExit(module.controller(Path(job), int(ownership_fd)))\n",
            encoding="utf-8",
        )

        def spawn_slow_controller(arguments, *popen_args, **popen_kwargs):
            if (
                isinstance(arguments, list)
                and "controller" in arguments
                and "--ownership-fd" in arguments
            ):
                ownership_index = arguments.index("--ownership-fd") + 1
                job_index = arguments.index("--job-dir") + 1
                arguments = [
                    sys.executable, "-B", str(slow_controller), str(SOURCE),
                    arguments[job_index], arguments[ownership_index],
                ]
            return real_spawn_popen(arguments, *popen_args, **popen_kwargs)

        MODULE.sys.stdout = _SpawnStdout()
        MODULE.subprocess.Popen = spawn_slow_controller
        os.environ["PATH"] = f"{spawn_bin}{os.pathsep}{previous_path}"
        try:
            assert MODULE.spawn(
                spawn_job, "initial", resume=False, foreground=False,
            ) == 0
        finally:
            MODULE.sys.stdout = previous_stdout
            MODULE.subprocess.Popen = real_spawn_popen
            os.environ["PATH"] = previous_path
        acknowledged = json.loads(spawn_output.getvalue())
        assert acknowledged["status"] == "queued"
        # The child may atomically replace state as its slow preflight ends.
        # Read the public asynchronous handoff through the state lock, just as
        # spawn(), status, and wait do, so an approved replacement cannot be
        # misreported as external tampering on macOS.
        handshake_state, _raw, _sha = MODULE.read_state_snapshot(spawn_job)
        assert handshake_state["status"] == "queued"
        assert type(handshake_state["controller_pid"]) is int
        assert handshake_state["started_epoch"] is None
        assert handshake_state["elapsed_seconds"] == 0
        assert not spawn_calls.exists() or "provider" not in spawn_calls.read_text(
            encoding="utf-8",
        ).splitlines()
        spawn_deadline = time.monotonic() + 12.0
        while time.monotonic() < spawn_deadline:
            spawned, _raw, _sha = MODULE.read_state_snapshot(spawn_job)
            if spawned["status"] in MODULE.TERMINAL:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("public spawn did not finish after its slow local preflight")
        assert spawned["status"] == "succeeded"
        assert spawned["elapsed_seconds"] < spawned["hard_seconds"]
        assert spawn_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # A cancellation that lands after the controller child exists but
        # before it claims queued ownership is terminalized atomically.  The
        # async start surface waits for that true terminal state rather than
        # accepting a transient cancel-requested record.
        claim_job, claim_bin, claim_calls, _claim_fake, _claim_command = fixture(
            "public-spawn-cancel-at-claim", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        (claim_job / MODULE.STATE_NAME).unlink()
        claim_output = io.BytesIO()

        class _ClaimStdout:
            buffer = claim_output

        claim_controller = root / "cancel-at-claim-controller.py"
        claim_controller.write_text(
            "import importlib.util\n"
            "from pathlib import Path\n"
            "import sys\n"
            "source, job, ownership_fd = sys.argv[1:]\n"
            "spec = importlib.util.spec_from_file_location('claim_cancel_dispatch', source)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "state, raw, approval = module.load_state(Path(job))\n"
            "module.command_control(Path(job), 'cancel', approval, None)\n"
            "raise SystemExit(module.controller(Path(job), int(ownership_fd)))\n",
            encoding="utf-8",
        )
        previous_stdout = MODULE.sys.stdout
        real_claim_popen = MODULE.subprocess.Popen

        def spawn_cancel_at_claim(arguments, *popen_args, **popen_kwargs):
            if (
                isinstance(arguments, list)
                and "controller" in arguments
                and "--ownership-fd" in arguments
            ):
                ownership_index = arguments.index("--ownership-fd") + 1
                job_index = arguments.index("--job-dir") + 1
                arguments = [
                    sys.executable, "-B", str(claim_controller), str(SOURCE),
                    arguments[job_index], arguments[ownership_index],
                ]
            return real_claim_popen(arguments, *popen_args, **popen_kwargs)

        MODULE.sys.stdout = _ClaimStdout()
        MODULE.subprocess.Popen = spawn_cancel_at_claim
        try:
            assert MODULE.spawn(claim_job, "initial", resume=False, foreground=False) == 0
        finally:
            MODULE.sys.stdout = previous_stdout
            MODULE.subprocess.Popen = real_claim_popen
        claimed_public = json.loads(claim_output.getvalue())
        claimed, _raw, _sha = MODULE.load_state(claim_job)
        assert claimed_public["status"] == "cancelled"
        assert (claimed["status"], claimed["reason"]) == ("cancelled", "cancelled")
        assert claimed["controller_pid"] is None and claimed["status"] != "orphaned"
        assert not claim_calls.exists(), "cancel-at-claim reached a provider"

        # The intentionally slow help probe remains outside the provider
        # lease.  Keep the lease well above host scheduling jitter while making
        # the probe itself longer than that lease, so this still fails if the
        # controller starts charging provider time before the final reprobe.
        within_job, within_bin, within_calls, _within_fake, within_command = fixture(
            "deadline-within", idle_seconds=0.25, hard_seconds=5, max_seconds=5,
        )
        os.environ["FAKE_DIRECT_HELP_DELAY"] = "0.75"
        try:
            within_code = run_controller(within_job, within_bin)
        finally:
            if previous_delay is None:
                os.environ.pop("FAKE_DIRECT_HELP_DELAY", None)
            else:
                os.environ["FAKE_DIRECT_HELP_DELAY"] = previous_delay
        within, _raw, _sha = MODULE.load_state(within_job)
        assert within_code == 0, (within_code, within["reason"], within["limit_kind"], within["elapsed_seconds"])
        assert within["status"] == "succeeded" and within["elapsed_seconds"] < within_command["max_seconds"]
        assert within["progress_count"] >= 3
        assert within_calls.read_text(encoding="utf-8").splitlines() == ["version", "help", "provider"]

        # Binding or executable drift replaces the queued state without calling
        # the provider.  The reprobe target is never selected through fallback.
        for kind in ("selection", "executable"):
            job, bin_dir, calls, fake, command = fixture(f"reject-{kind}")
            if kind == "selection":
                Path(command["selection_path"]).write_text("{}\n", encoding="utf-8")
                Path(command["selection_path"]).chmod(0o600)
            else:
                fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8"); fake.chmod(0o755)
            calls.unlink(missing_ok=True)
            expected_reason = "status_unavailable" if kind == "selection" else "selection_preflight_failed"
            assert run_controller(job, bin_dir) == MODULE.EXIT_BY_REASON[expected_reason]
            assert not calls.exists() or "provider" not in calls.read_text(encoding="utf-8")
            terminal, _raw, _sha = MODULE.load_state(job)
            assert terminal["status"] == "failed" and terminal["reason"] == expected_reason
            if kind == "executable":
                assert terminal["failure_stage"] == "selection_preflight"

        # A target that rewrites itself during the final help probe must not turn
        # the already-returned pathname into authority to launch new content.
        job, bin_dir, calls, fake, _command = fixture("reject-help-rewrite")
        replacement = bin_dir / "agy.replacement"
        replacement.write_text(
            "#!/bin/sh\n"
            "printf 'provider\\n' >> " + shlex.quote(str(calls)) + "\n"
            "exit 0\n",
            encoding="utf-8",
        )
        replacement.chmod(0o755)
        fake.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then "
            "printf 'version\\n' >> " + shlex.quote(str(calls)) + "; printf '1.1.16\\n'; exit 0; fi\n"
            "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then "
            "printf 'help\\n' >> " + shlex.quote(str(calls)) + "; cat >&2 <<'HELP'\n"
            + help_text
            + "HELP\n"
            "mv " + shlex.quote(str(replacement)) + " \"$0\"\n"
            "exit 0\n"
            "fi\n"
            "printf 'provider\\n' >> " + shlex.quote(str(calls)) + "\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        calls.unlink(missing_ok=True)
        assert run_controller(job, bin_dir) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        assert calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]
        terminal, _raw, _sha = MODULE.load_state(job)
        assert (terminal["status"], terminal["reason"], terminal["failure_stage"]) == (
            "failed", "selection_preflight_failed", "selection_preflight",
        )

        # A final direct-selection probe failure is a deterministic local
        # preflight outcome, not an unclassified status failure.  It preserves
        # the caller-selected record as forensic input, but cannot safely
        # relaunch that frozen selection in the same job.
        def selection_preflight_failure(
            label: str, *, max_cycles: int, idle_seconds: float = 2,
            hard_seconds: float = 3, max_seconds: float = 20,
        ) -> tuple[Path, Path, Path, dict]:
            job, bin_dir, calls, fake, command = fixture(
                label, idle_seconds=idle_seconds, hard_seconds=hard_seconds,
                max_seconds=max_seconds,
            )
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then printf 'version\\n' >> " + shlex.quote(str(calls)) + "; printf '1.1.16\\n'; exit 0; fi\n"
                "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then printf 'help\\n' >> " + shlex.quote(str(calls)) + "; sleep \"${FAKE_DIRECT_HELP_DELAY:-0}\"; printf 'incompatible interface\\n' >&2; exit 0; fi\n"
                "printf 'provider\\n' >> " + shlex.quote(str(calls)) + "\nexit 99\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            if max_cycles != command["max_cycles"]:
                state, _raw, _sha = MODULE.load_state(job)
                state["max_cycles"] = max_cycles
                MODULE.write_atomic(job, MODULE.STATE_NAME, state)
            calls.unlink(missing_ok=True)
            return job, bin_dir, calls, command

        job, bin_dir, calls, command = selection_preflight_failure("selection-preflight", max_cycles=2)
        assert run_controller(job, bin_dir) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        assert calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]
        terminal, _raw, terminal_sha = MODULE.load_state(job)
        assert (terminal["reason"], terminal["failure_stage"], terminal["next_action"]) == (
            "selection_preflight_failed", "selection_preflight", "none",
        )
        assert terminal["selection_sha256"] == command["selection_sha256"]
        public = MODULE.public_status(terminal, terminal_sha, job=job)
        assert {item["action"] for item in public["available_actions"]}.isdisjoint({"resume", "restart"})
        assert public["next_action"] == "none" and public["next_action_command"] is None
        captured_status = io.BytesIO()
        original_stdout = MODULE.sys.stdout

        class _StatusStdout:
            buffer = captured_status

        MODULE.sys.stdout = _StatusStdout()
        try:
            MODULE.print_text_status(terminal, terminal_sha, job=job)
        finally:
            MODULE.sys.stdout = original_stdout
        captured_lines = captured_status.getvalue().decode("utf-8").splitlines()
        assert captured_lines == [
            "Provider attempt: failed; reason: selection_preflight_failed; failure stage: selection_preflight; bound result available: no; driver disposition: not_applicable.",
            "Driver evidence: 0 passed, 0 failed, 0 advisory, 0 missing; cycle: 1/2.",
            "Next safe action: create a fresh job using the unchanged caller selection after reviewing the current sanitized agy interface evidence. No same-job action is available.",
        ]
        captured_text = "\n".join(captured_lines)
        for private in (
            str(job), str(command["selection_path"]), command["selection_sha256"],
            "gemini-3.6-flash", "--job-id", "--approve-state-sha",
        ):
            assert private not in captured_text
        state_before_rejected_restart = (job / MODULE.STATE_NAME).read_bytes()
        rejected_restart = subprocess.run(
            [sys.executable, str(SOURCE), "restart", "--job-dir", str(job),
             "--approve-state-sha", terminal_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert rejected_restart.returncode == 64 and not rejected_restart.stdout
        assert (job / MODULE.STATE_NAME).read_bytes() == state_before_rejected_restart
        assert calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]

        # A failed earlier attempt can already have a conversation before its
        # resumed direct selection later fails final preflight.  This is a real
        # resume route, not merely an in-memory status projection: both public
        # advice and the command guard must reject it without staging a new
        # attempt, modifying state, or reaching the provider.
        resume_job, resume_bin, resume_calls, resume_fake, _resume_command = fixture(
            "selection-preflight-resume", max_seconds=20,
        )
        resumable, _raw, resumable_sha = MODULE.load_state(resume_job)
        resumable.update({
            "status": "failed", "reason": "agy_failed_unclassified", "exit_code": 5,
            "finished_epoch": 1.0, "conversation_id": "conversation-1",
            "resume_available": True, "phase": "attempt-failed", "assurance": "pending",
            "next_action": "resume", "driver_disposition": "not_applicable",
        })
        _raw, resumable_sha = MODULE.write_atomic(resume_job, MODULE.STATE_NAME, resumable)
        MODULE.create_state(
            resume_job, "conversation-resume", resume=True, approve_sha=resumable_sha,
        )
        resume_fake.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then printf 'version\\n' >> " + shlex.quote(str(resume_calls)) + "; printf '1.1.16\\n'; exit 0; fi\n"
            "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then printf 'help\\n' >> " + shlex.quote(str(resume_calls)) + "; printf 'incompatible interface\\n' >&2; exit 0; fi\n"
            "printf 'provider\\n' >> " + shlex.quote(str(resume_calls)) + "\nexit 99\n",
            encoding="utf-8",
        )
        resume_fake.chmod(0o755)
        resume_calls.unlink(missing_ok=True)
        assert run_controller(resume_job, resume_bin) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        resume_terminal, _raw, resume_terminal_sha = MODULE.load_state(resume_job)
        assert resume_terminal["conversation_id"] == "conversation-1"
        assert not resume_terminal["resume_available"] and resume_terminal["next_action"] == "none"
        resume_public = MODULE.public_status(resume_terminal, resume_terminal_sha, job=resume_job)
        assert {item["action"] for item in resume_public["available_actions"]}.isdisjoint({"resume", "restart"})
        resume_before_rejected_command = (resume_job / MODULE.STATE_NAME).read_bytes()
        rejected_resume = subprocess.run(
            [sys.executable, str(SOURCE), "resume", "--job-dir", str(resume_job),
             "--approve-state-sha", resume_terminal_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert rejected_resume.returncode == MODULE.EXIT_BY_REASON["resume_failed"] and not rejected_resume.stdout
        assert (resume_job / MODULE.STATE_NAME).read_bytes() == resume_before_rejected_command
        assert resume_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]

        # A continuation can fail its final direct-selection probe after its
        # exact prior candidate and driver feedback were already staged.  The
        # candidate remains reviewable/finalizable, but this local preflight
        # failure must never become authority for another provider attempt in
        # the same job merely because one cycle remains.
        continue_job, continue_bin, continue_calls, continue_fake, continue_command = fixture(
            "selection-preflight-continue", workflow="project", max_cycles=3,
        )
        assert_attempt(
            continue_job, continue_bin, continue_calls, continue_command, "initial",
        )
        candidate, _raw, candidate_sha = MODULE.load_state(continue_job)
        continue_verification = {
            "schema_version": 2,
            "summary": "driver found a repair",
            "passed_checks": [],
            "failed_checks": ["fixture"],
            "advisory_checks": 0,
            "missing_checks": 0,
            "candidate_sha256": candidate["result_sha256"],
            "coverage": "partial",
            "verified_findings": 1,
            "unresolved_gaps": 1,
            "diff_review_complete": True,
        }
        MODULE.create_state(
            continue_job, "conversation-continue", resume=True,
            approve_sha=candidate_sha, verification=continue_verification,
        )
        continue_fake.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then printf 'version\\n' >> " + shlex.quote(str(continue_calls)) + "; printf '1.1.16\\n'; exit 0; fi\n"
            "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then printf 'help\\n' >> " + shlex.quote(str(continue_calls)) + "; printf 'incompatible interface\\n' >&2; exit 0; fi\n"
            "printf 'provider\\n' >> " + shlex.quote(str(continue_calls)) + "\nexit 99\n",
            encoding="utf-8",
        )
        continue_fake.chmod(0o755)
        continue_calls.unlink(missing_ok=True)
        assert run_controller(continue_job, continue_bin) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        failed_continue, _raw, failed_continue_sha = MODULE.load_state(continue_job)
        assert failed_continue["attempt_origin"] == "conversation-continue"
        assert failed_continue["attempt"] < failed_continue["max_cycles"]
        assert failed_continue["candidate_recognized"] and failed_continue["result_available"]
        assert failed_continue["driver_disposition"] == "unreviewed"
        assert failed_continue["reason"] == "selection_preflight_failed"
        assert failed_continue["continue_available"] is False
        continue_public = MODULE.public_status(
            failed_continue, failed_continue_sha, job=continue_job,
        )
        continue_actions = {item["action"] for item in continue_public["available_actions"]}
        assert {"result", "finalize"} <= continue_actions
        assert not ({"continue", "resume", "restart"} & continue_actions)

        captured_continue_status = io.BytesIO()

        class _ContinueStatusStdout:
            buffer = captured_continue_status

        MODULE.sys.stdout = _ContinueStatusStdout()
        try:
            MODULE.print_text_status(
                failed_continue, failed_continue_sha, job=continue_job,
            )
        finally:
            MODULE.sys.stdout = original_stdout
        continue_status_lines = captured_continue_status.getvalue().decode("utf-8").splitlines()
        assert continue_status_lines[2] == (
            'Next safe action: retrieve current bound result JSON with "$PIPELINE/agy-worker.sh" '
            "result --job-id direct-selection-preflight-continue --format json; review it and run driver checks, "
            "then the driver may finalize after review. "
            "No provider-launching same-job recovery is available."
        )

        immutable_state = (continue_job / MODULE.STATE_NAME).read_bytes()
        immutable_calls = continue_calls.read_bytes()
        staged_before = sorted((continue_job / "continue-staged").iterdir())
        verification_input = MODULE.canonical(continue_verification)
        rejected_commands = (
            ("resume", ["--approve-state-sha", failed_continue_sha], None),
            ("restart", ["--approve-state-sha", failed_continue_sha], None),
            ("continue", ["--approve-state-sha", failed_continue_sha], verification_input),
        )
        for action, arguments, command_input in rejected_commands:
            rejected = subprocess.run(
                [sys.executable, str(SOURCE), action, "--job-dir", str(continue_job), *arguments],
                input=command_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            expected = MODULE.EXIT_BY_REASON["resume_failed"] if action == "resume" else 64
            assert rejected.returncode == expected and not rejected.stdout, (action, rejected.returncode)
            assert (continue_job / MODULE.STATE_NAME).read_bytes() == immutable_state
            assert continue_calls.read_bytes() == immutable_calls
            assert sorted((continue_job / "continue-staged").iterdir()) == staged_before

        result_output = io.BytesIO()

        class _ResultStdout:
            buffer = result_output

        MODULE.sys.stdout = _ResultStdout()
        try:
            assert MODULE.command_result(continue_job) == 0
        finally:
            MODULE.sys.stdout = original_stdout
        assert json.loads(result_output.getvalue()) == report()

        finalized_run = subprocess.run(
            [
                sys.executable, str(SOURCE), "finalize", "--job-dir", str(continue_job),
                "--approve-state-sha", failed_continue_sha,
                "--assurance", "partially_verified",
            ],
            input=verification_input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert finalized_run.returncode == 0, finalized_run.stderr.decode("utf-8", "replace")
        finalized = json.loads(finalized_run.stdout)
        assert finalized["driver_disposition"] == "partially_verified"

        # Positive control: an unrelated provider repair failure with a bound
        # candidate still permits strict same-conversation continuation.
        repair_job, repair_bin, repair_calls, _repair_fake, repair_command = fixture(
            "repair-failed-continue-control", workflow="project", max_cycles=3,
        )
        assert_attempt(repair_job, repair_bin, repair_calls, repair_command, "initial")
        repair_state, _raw, repair_sha = MODULE.load_state(repair_job)
        repair_state.update({
            "status": "failed",
            "reason": "provider_terminal_error",
            "exit_code": MODULE.EXIT_BY_REASON["provider_terminal_error"],
            "attempt_origin": "conversation-continue",
            "phase": "repair-failed",
            "continue_available": True,
        })
        _raw, repair_sha = MODULE.write_atomic(repair_job, MODULE.STATE_NAME, repair_state)
        repair_actions = {
            item["action"] for item in MODULE.public_status(
                repair_state, repair_sha, job=repair_job,
            )["available_actions"]
        }
        assert "continue" in repair_actions
        queued_repair, _queued_repair_sha = MODULE.create_state(
            repair_job, "conversation-continue", resume=True,
            approve_sha=repair_sha,
            verification={**continue_verification, "candidate_sha256": repair_state["result_sha256"]},
        )
        assert queued_repair["status"] == "queued"
        assert queued_repair["attempt_origin"] == "conversation-continue"

        blocked_job, blocked_bin, blocked_calls, _blocked_command = selection_preflight_failure(
            "selection-preflight-exhausted", max_cycles=1,
        )
        assert run_controller(blocked_job, blocked_bin) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        assert blocked_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]
        blocked, _raw, blocked_sha = MODULE.load_state(blocked_job)
        assert blocked["next_action"] == "none"
        assert MODULE.public_status(blocked, blocked_sha)["next_action_command"] is None
        try:
            MODULE.create_state(blocked_job, "fresh-restart", resume=True, approve_sha=blocked_sha)
        except MODULE.DispatchError:
            pass
        else:
            raise AssertionError("exhausted selection-preflight state advertised an invalid restart")

        # A failed final probe has no provider runtime to charge.  The
        # selection failure itself still blocks same-job recovery, independent
        # of the provider budget left in the state.
        deadline_job, deadline_bin, deadline_calls, _deadline_command = selection_preflight_failure(
            "selection-preflight-deadline", max_cycles=2,
            idle_seconds=0.01, hard_seconds=0.10, max_seconds=0.10,
        )
        previous_delay = os.environ.get("FAKE_DIRECT_HELP_DELAY")
        os.environ["FAKE_DIRECT_HELP_DELAY"] = "0.25"
        try:
            assert run_controller(deadline_job, deadline_bin) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        finally:
            if previous_delay is None:
                os.environ.pop("FAKE_DIRECT_HELP_DELAY", None)
            else:
                os.environ["FAKE_DIRECT_HELP_DELAY"] = previous_delay
        deadline_state, _raw, deadline_sha = MODULE.load_state(deadline_job)
        assert deadline_state["elapsed_seconds"] < deadline_state["max_seconds"]
        assert deadline_state["next_action"] == "none"
        deadline_public = MODULE.public_status(deadline_state, deadline_sha)
        assert deadline_public["next_action_command"] is None
        rejected_restart = subprocess.run(
            [sys.executable, str(SOURCE), "restart", "--job-dir", str(deadline_job),
             "--approve-state-sha", deadline_sha],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert rejected_restart.returncode == 64 and not rejected_restart.stdout
        assert deadline_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]

        # ProbeInterrupted is deliberately a BaseException so a local probe
        # cannot mistake HUP/INT/TERM for an evidence failure.  The controller
        # must nevertheless own the terminal state and the probe's group must
        # be gone before the no-provider result is reported.
        for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal_name = signal.Signals(number).name.lower()
            signal_job, signal_bin, signal_calls, signal_fake, _signal_command = fixture(
                f"probe-{signal_name}", idle_seconds=1, hard_seconds=3, max_seconds=10,
            )
            ready = root / f"probe-{signal_name}-ready"
            probe_pid = root / f"probe-{signal_name}-pid"
            signal_fake.write_text(
                "#!/bin/sh\n"
                "if [ \"${1:-}\" = --version ] && [ \"$#\" = 1 ]; then printf 'version\\n' >> " + shlex.quote(str(signal_calls)) + "; printf '1.1.16\\n'; exit 0; fi\n"
                "if [ \"${1:-}\" = --help ] && [ \"$#\" = 1 ]; then "
                "printf 'help\\n' >> " + shlex.quote(str(signal_calls)) + "; "
                "printf '%s\\n' \"$$\" > " + shlex.quote(str(probe_pid)) + "; "
                "touch " + shlex.quote(str(ready)) + "; while :; do sleep 1; done; fi\n"
                "printf 'provider\\n' >> " + shlex.quote(str(signal_calls)) + "\nexit 0\n",
                encoding="utf-8",
            )
            signal_fake.chmod(0o755)
            lock = signal_job / MODULE.LOCK_NAME
            descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            child_env = dict(os.environ)
            child_env["PATH"] = f"{signal_bin}{os.pathsep}{child_env.get('PATH', '')}"
            controller_process = subprocess.Popen(
                [sys.executable, str(SOURCE), "controller", "--job-dir", str(signal_job),
                 "--ownership-fd", str(descriptor)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, pass_fds=(descriptor,), env=child_env,
            )
            os.close(descriptor)
            descriptor = -1
            try:
                deadline = time.monotonic() + 3.0
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert ready.exists(), f"{signal_name} never reached the blocked help probe"
                os.killpg(controller_process.pid, number)
                assert controller_process.wait(timeout=5.0) == 128 + number
            finally:
                if controller_process.poll() is None:
                    MODULE._terminate(controller_process)
                if descriptor >= 0:
                    os.close(descriptor)
            recorded_pid = int(probe_pid.read_text(encoding="ascii"))
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.killpg(recorded_pid, 0)
                except ProcessLookupError:
                    break
                except PermissionError:
                    try:
                        os.kill(recorded_pid, 0)
                    except ProcessLookupError:
                        break
                time.sleep(0.02)
            else:
                raise AssertionError(f"{signal_name} left a probe process group behind")
            interrupted, _raw, _sha = MODULE.load_state(signal_job)
            assert (interrupted["status"], interrupted["reason"], interrupted["exit_code"]) == (
                "cancelled", "interrupted", 128 + number,
            )
            assert interrupted["controller_pid"] is None and interrupted["status"] != "orphaned"
            assert interrupted["remote_cancel_unverified"] and not interrupted["resume_available"]
            assert signal_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]

        # Once the direct version/help probe is complete, a signal can arrive
        # while the bounded worktree scan still owns the launch path.  The
        # controller must resample its local signal fact before provider Popen.
        baseline_job, baseline_bin, baseline_calls, _baseline_fake, _baseline_command = fixture(
            "baseline-signal", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_baseline = MODULE._bound_worktree_baseline
        signal_delivered = False

        def signal_during_baseline(state: dict, command: dict) -> None:
            nonlocal signal_delivered
            original_baseline(state, command)
            os.kill(os.getpid(), signal.SIGTERM)
            signal_delivered = True
            # Keep this wrapper on the worktree-scan side of the launch
            # boundary while CPython dispatches the installed controller
            # handler.  No provider process exists to reap in this window.
            time.sleep(0.01)

        MODULE._bound_worktree_baseline = signal_during_baseline
        try:
            assert run_controller(baseline_job, baseline_bin) == 128 + signal.SIGTERM
        finally:
            MODULE._bound_worktree_baseline = original_baseline
        assert signal_delivered
        observed_baseline_calls = baseline_calls.read_text(encoding="utf-8").splitlines()
        assert observed_baseline_calls == ["version", "help"], observed_baseline_calls
        baseline_terminal, _raw, _sha = MODULE.load_state(baseline_job)
        assert (baseline_terminal["status"], baseline_terminal["reason"], baseline_terminal["exit_code"]) == (
            "cancelled", "interrupted", 128 + signal.SIGTERM,
        )
        assert baseline_terminal["controller_pid"] is None and baseline_terminal["status"] != "orphaned"
        assert baseline_terminal["remote_cancel_unverified"] and not baseline_terminal["resume_available"]

        # A direct executable binding is evidence for the target probed before
        # the scan, not a capability to launch a replacement after it.  Swap A
        # for B from the scan hook: B must never receive a provider invocation.
        swap_job, swap_bin, swap_calls, swap_fake, _swap_command = fixture(
            "scan-window-executable-swap", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        swap_replacement = swap_bin / "agy-B"
        swap_replacement.write_text(
            "#!/bin/sh\nprintf 'B-provider\\n' >> " + shlex.quote(str(swap_calls)) + "\nexit 0\n",
            encoding="utf-8",
        )
        swap_replacement.chmod(0o755)
        original_baseline = MODULE._bound_worktree_baseline
        swapped = False

        def replace_after_scan(state: dict, command: dict) -> None:
            nonlocal swapped
            original_baseline(state, command)
            os.replace(swap_replacement, swap_fake)
            swapped = True

        MODULE._bound_worktree_baseline = replace_after_scan
        try:
            assert run_controller(swap_job, swap_bin) == MODULE.EXIT_BY_REASON["selection_preflight_failed"]
        finally:
            MODULE._bound_worktree_baseline = original_baseline
        assert swapped
        assert swap_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]
        swap_terminal, _raw, _sha = MODULE.load_state(swap_job)
        assert (swap_terminal["reason"], swap_terminal["failure_stage"]) == (
            "selection_preflight_failed", "selection_preflight",
        )

        # The final state/CAS launch transition is also an executable
        # replacement window.  It must happen before the last binding
        # confirmation so replacement B cannot inherit A's probe evidence.
        launch_job, launch_bin, launch_calls, launch_fake, _launch_command = fixture(
            "state-launch-window-executable-swap",
            idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        launch_replacement = launch_bin / "agy-B"
        launch_replacement.write_text(
            "#!/bin/sh\nprintf 'B-provider\\n' >> "
            + shlex.quote(str(launch_calls)) + "\nexit 0\n",
            encoding="utf-8",
        )
        launch_replacement.chmod(0o755)
        original_transition = MODULE._transition_locked
        launch_swapped = False

        def replace_during_running_transition(
            job_path: Path, state: dict, prior_raw: bytes, updates: dict,
        ):
            nonlocal launch_swapped
            result = original_transition(
                job_path, state, prior_raw, updates,
            )
            if updates.get("status") == "running" and not launch_swapped:
                os.replace(launch_replacement, launch_fake)
                launch_swapped = True
            return result

        MODULE._transition_locked = replace_during_running_transition
        try:
            assert run_controller(launch_job, launch_bin) == MODULE.EXIT_BY_REASON[
                "selection_preflight_failed"
            ]
        finally:
            MODULE._transition_locked = original_transition
        assert launch_swapped
        assert launch_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]
        launch_terminal, _raw, _sha = MODULE.load_state(launch_job)
        assert (launch_terminal["reason"], launch_terminal["failure_stage"]) == (
            "selection_preflight_failed", "selection_preflight",
        )

        # Cancellation during the final local launch guard is linearized by
        # the provider-launch lock.  It wins before executable confirmation or
        # Popen, so the provider is never invoked.
        prelaunch_job, prelaunch_bin, prelaunch_calls, _prelaunch_fake, _prelaunch_command = fixture(
            "cancel-before-popen", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_baseline = MODULE._bound_worktree_baseline
        original_print_json = MODULE.print_json
        prelaunch_control_output: list[dict] = []
        cancelled_prelaunch = False

        def cancel_during_launch_guard(state: dict, command: dict) -> None:
            nonlocal cancelled_prelaunch
            original_baseline(state, command)
            _current, _raw, approval = MODULE.load_state(prelaunch_job)
            MODULE.command_control(prelaunch_job, "cancel", approval, None)
            cancelled_prelaunch = True

        MODULE._bound_worktree_baseline = cancel_during_launch_guard
        MODULE.print_json = lambda value: prelaunch_control_output.append(value)
        try:
            assert run_controller(prelaunch_job, prelaunch_bin) == MODULE.EXIT_BY_REASON["cancelled"]
        finally:
            MODULE._bound_worktree_baseline = original_baseline
            MODULE.print_json = original_print_json
        assert cancelled_prelaunch
        assert len(prelaunch_control_output) == 1
        prelaunch_terminal, _raw, _sha = MODULE.load_state(prelaunch_job)
        assert (prelaunch_terminal["status"], prelaunch_terminal["reason"]) == (
            "cancelled", "cancelled",
        )
        assert prelaunch_terminal["controller_pid"] is None
        assert prelaunch_calls.read_text(encoding="utf-8").splitlines() == ["version", "help"]

        # Failures after a successful Popen still pass through the ordinary
        # reaping/freeze/terminal projection rather than relying on finally.
        register_job, register_bin, register_calls, _register_fake, _register_command = fixture(
            "post-popen-register-failure", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_selector = MODULE.selectors.DefaultSelector

        class FailingRegisterSelector:
            def __init__(self) -> None:
                self.inner = original_selector()

            def register(self, fileobj, events, data=None) -> None:
                # The controller is the only caller that labels its two
                # provider pipes.  Git's safe read probe may also use a
                # selector during preflight, so leave that implementation
                # untouched and inject only at the post-Popen controller
                # registration boundary.
                if data in {"stdout", "stderr"}:
                    raise OSError("fixture selector registration failure")
                return self.inner.register(fileobj, events, data)

            def get_map(self):
                return self.inner.get_map()

            def select(self, _timeout=None):
                return self.inner.select(_timeout)

            def unregister(self, fileobj):
                return self.inner.unregister(fileobj)

            def close(self) -> None:
                self.inner.close()

        MODULE.selectors.DefaultSelector = FailingRegisterSelector
        try:
            assert run_controller(register_job, register_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE.selectors.DefaultSelector = original_selector
        registered_terminal, _raw, _sha = MODULE.load_state(register_job)
        assert (registered_terminal["status"], registered_terminal["reason"], registered_terminal["failure_stage"]) == (
            "failed", "status_unavailable", "binding_failure",
        )
        assert registered_terminal["started_epoch"] is None
        assert registered_terminal["controller_pid"] is None and registered_terminal["status"] != "orphaned"
        assert register_calls.read_text(encoding="utf-8").splitlines() in (
            ["version", "help"], ["version", "help", "provider"],
        )

        # A stream-read failure after Popen follows the same terminal route;
        # it cannot escape to finally with a live controller record.
        read_job, read_bin, read_calls, _read_fake, _read_command = fixture(
            "post-popen-read-failure", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_read = MODULE.os.read
        original_read_popen = MODULE.subprocess.Popen
        provider_pipe_fds: set[int] = set()

        def record_provider_pipes(arguments, *popen_args, **popen_kwargs):
            child = original_read_popen(arguments, *popen_args, **popen_kwargs)
            if isinstance(arguments, list) and arguments and arguments[0] == "agy":
                assert child.stdout is not None and child.stderr is not None
                provider_pipe_fds.update({child.stdout.fileno(), child.stderr.fileno()})
            return child

        def fail_provider_read(descriptor: int, count: int) -> bytes:
            if descriptor in provider_pipe_fds:
                raise OSError("fixture stream read failure")
            return original_read(descriptor, count)

        MODULE.subprocess.Popen = record_provider_pipes
        MODULE.os.read = fail_provider_read
        try:
            assert run_controller(read_job, read_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE.subprocess.Popen = original_read_popen
            MODULE.os.read = original_read
        read_terminal, _raw, _sha = MODULE.load_state(read_job)
        assert (read_terminal["status"], read_terminal["reason"], read_terminal["failure_stage"]) == (
            "failed", "status_unavailable", "binding_failure",
        )
        assert read_terminal["started_epoch"] is None and read_terminal["controller_pid"] is None
        assert read_calls.read_text(encoding="utf-8").splitlines() in (
            ["version", "help"], ["version", "help", "provider"],
        )

        # An otherwise uncategorized provider-session exception is caught by
        # the structured unwind, which reaps, freezes, and terminalizes rather
        # than leaving finally as the only cleanup path.
        generic_job, generic_bin, generic_calls, _generic_fake, _generic_command = fixture(
            "post-popen-generic-failure", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_selector = MODULE.selectors.DefaultSelector
        original_generic_popen = MODULE.subprocess.Popen
        original_generic_terminate = MODULE._terminate
        original_generic_freeze = MODULE._freeze_reaped_runtime
        provider_pipe_fds: set[int] = set()
        generic_terminate_count = 0
        generic_reap_completed: list[float] = []
        generic_frozen_elapsed: list[float] = []

        def record_generic_provider_pipes(arguments, *popen_args, **popen_kwargs):
            child = original_generic_popen(arguments, *popen_args, **popen_kwargs)
            if isinstance(arguments, list) and arguments and arguments[0] == "agy":
                assert child.stdout is not None and child.stderr is not None
                provider_pipe_fds.update({child.stdout.fileno(), child.stderr.fileno()})
            return child

        def counted_generic_terminate(process):
            nonlocal generic_terminate_count
            generic_terminate_count += 1
            # Make the reap boundary observable: controller-local recovery
            # must freeze this provider time, not sample a later finally path.
            time.sleep(0.10)
            outcome = original_generic_terminate(process)
            generic_reap_completed.append(time.monotonic())
            return outcome

        def capture_generic_freeze(job, attempt, controller_pid, elapsed):
            assert generic_reap_completed, "runtime froze before successful reap"
            generic_frozen_elapsed.append(elapsed)
            return original_generic_freeze(job, attempt, controller_pid, elapsed)

        class ExplodingSelectSelector:
            def __init__(self) -> None:
                self.inner = original_selector()
                self.provider_session = False

            def register(self, fileobj, events, data=None) -> None:
                # Do not alter any selector a preflight Git/subprocess probe
                # may create.  Arm only for the controller's two pipe FDs
                # after the actual provider Popen has returned them.
                if (
                    data in {"stdout", "stderr"}
                    and fileobj.fileno() in provider_pipe_fds
                ):
                    self.provider_session = True
                return self.inner.register(fileobj, events, data)

            def get_map(self):
                return self.inner.get_map()

            def select(self, _timeout=None):
                if self.provider_session:
                    raise RuntimeError("fixture generic provider-session failure")
                return self.inner.select(_timeout)

            def unregister(self, fileobj):
                return self.inner.unregister(fileobj)

            def close(self) -> None:
                self.inner.close()

        MODULE.subprocess.Popen = record_generic_provider_pipes
        MODULE.selectors.DefaultSelector = ExplodingSelectSelector
        MODULE._terminate = counted_generic_terminate
        MODULE._freeze_reaped_runtime = capture_generic_freeze
        try:
            assert run_controller(generic_job, generic_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE.subprocess.Popen = original_generic_popen
            MODULE.selectors.DefaultSelector = original_selector
            MODULE._terminate = original_generic_terminate
            MODULE._freeze_reaped_runtime = original_generic_freeze
        generic_terminal, _raw, _sha = MODULE.load_state(generic_job)
        assert (generic_terminal["status"], generic_terminal["reason"], generic_terminal["failure_stage"]) == (
            "failed", "status_unavailable", "binding_failure",
        )
        assert generic_terminal["started_epoch"] is None
        assert generic_terminal["controller_pid"] is None and generic_terminal["status"] != "orphaned"
        assert generic_terminate_count == 1
        assert len(generic_frozen_elapsed) == 1
        assert generic_frozen_elapsed[0] >= 0.09
        assert generic_terminal["elapsed_seconds"] == generic_frozen_elapsed[0]
        assert generic_calls.read_text(encoding="utf-8").splitlines() in (
            ["version", "help"], ["version", "help", "provider"],
        )

        # A delayed exception after the normal reaped-runtime freeze must not
        # recharge envelope/reconciliation time in the recovery projection.
        frozen_error_job, frozen_error_bin, frozen_error_calls, _frozen_error_fake, _frozen_error_command = fixture(
            "post-freeze-delayed-error", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_reconciliation_projection = MODULE._reconciliation_from_snapshot
        frozen_elapsed_observation: list[float] = []
        fail_once = True

        def fail_after_observing_freeze(*args, **kwargs):
            nonlocal fail_once
            if fail_once:
                fail_once = False
                frozen, _raw, _sha = MODULE.load_state(frozen_error_job)
                assert frozen["started_epoch"] is None
                frozen_elapsed_observation.append(frozen["elapsed_seconds"])
                time.sleep(0.25)
                raise RuntimeError("fixture delayed post-freeze failure")
            return original_reconciliation_projection(*args, **kwargs)

        MODULE._reconciliation_from_snapshot = fail_after_observing_freeze
        try:
            assert run_controller(frozen_error_job, frozen_error_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE._reconciliation_from_snapshot = original_reconciliation_projection
        frozen_error_terminal, _raw, _sha = MODULE.load_state(frozen_error_job)
        assert frozen_elapsed_observation == [frozen_error_terminal["elapsed_seconds"]]
        assert (frozen_error_terminal["status"], frozen_error_terminal["reason"]) == (
            "failed", "status_unavailable",
        )
        assert frozen_error_terminal["elapsed_seconds"] < frozen_error_terminal["hard_seconds"]
        assert frozen_error_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # Persistent reconciliation failure uses the helper's unavailable
        # fallback; it cannot escape recovery and strand an active controller.
        persistent_job, persistent_bin, _persistent_calls, _persistent_fake, _persistent_command = fixture(
            "persistent-recovery-reconcile-failure", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_reconcile = MODULE._reconcile_worktree

        def always_fail_reconcile(*args, **kwargs):
            raise RuntimeError("fixture persistent reconciliation failure")

        original_selector = MODULE.selectors.DefaultSelector

        class PersistentFailureSelector:
            def __init__(self) -> None:
                self.inner = original_selector()
                self.provider_session = False

            def register(self, fileobj, events, data=None) -> None:
                if data in {"stdout", "stderr"}:
                    self.provider_session = True
                return self.inner.register(fileobj, events, data)

            def get_map(self):
                return self.inner.get_map()

            def select(self, _timeout=None):
                if self.provider_session:
                    raise RuntimeError("fixture recovery trigger")
                return self.inner.select(_timeout)

            def unregister(self, fileobj):
                return self.inner.unregister(fileobj)

            def close(self) -> None:
                self.inner.close()

        MODULE._reconcile_worktree = always_fail_reconcile
        MODULE.selectors.DefaultSelector = PersistentFailureSelector
        try:
            assert run_controller(persistent_job, persistent_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE._reconcile_worktree = original_reconcile
            MODULE.selectors.DefaultSelector = original_selector
        persistent_terminal, _raw, _sha = MODULE.load_state(persistent_job)
        assert (persistent_terminal["status"], persistent_terminal["reason"], persistent_terminal["failure_stage"]) == (
            "failed", "status_unavailable", "binding_failure",
        )
        assert persistent_terminal["controller_pid"] is None
        assert persistent_terminal["worktree_reconciliation"] == "unavailable"

        # The same recovery fallback preserves the post-launch cancellation
        # residual rather than claiming that the provider observed it.
        recovery_cancel_job, recovery_cancel_bin, _recovery_cancel_calls, _recovery_cancel_fake, _recovery_cancel_command = fixture(
            "persistent-recovery-cancel", idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_reconcile = MODULE._reconcile_worktree
        original_selector = MODULE.selectors.DefaultSelector
        original_print_json = MODULE.print_json
        recovery_cancel_output: list[dict] = []

        class CancelThenFailSelector:
            def __init__(self) -> None:
                self.inner = original_selector()
                self.cancelled = False
                self.provider_session = False

            def register(self, fileobj, events, data=None) -> None:
                if data in {"stdout", "stderr"}:
                    self.provider_session = True
                return self.inner.register(fileobj, events, data)

            def get_map(self):
                return self.inner.get_map()

            def select(self, _timeout=None):
                if not self.provider_session:
                    return self.inner.select(_timeout)
                if not self.cancelled:
                    self.cancelled = True
                    _current, _raw, approval = MODULE.load_state(recovery_cancel_job)
                    assert MODULE.command_control(recovery_cancel_job, "cancel", approval, None) == 0
                raise RuntimeError("fixture recovery cancellation failure")

            def unregister(self, fileobj):
                return self.inner.unregister(fileobj)

            def close(self) -> None:
                self.inner.close()

        MODULE._reconcile_worktree = always_fail_reconcile
        MODULE.selectors.DefaultSelector = CancelThenFailSelector
        MODULE.print_json = lambda value: recovery_cancel_output.append(value)
        try:
            assert run_controller(recovery_cancel_job, recovery_cancel_bin) == MODULE.EXIT_BY_REASON[
                "cancelled"
            ]
        finally:
            MODULE._reconcile_worktree = original_reconcile
            MODULE.selectors.DefaultSelector = original_selector
            MODULE.print_json = original_print_json
        recovery_cancel_terminal, _raw, _sha = MODULE.load_state(recovery_cancel_job)
        MODULE.validate_state(recovery_cancel_terminal)
        assert len(recovery_cancel_output) == 1
        assert (recovery_cancel_terminal["status"], recovery_cancel_terminal["reason"]) == (
            "cancelled", "cancelled",
        )
        assert recovery_cancel_terminal["exit_code"] == MODULE.EXIT_BY_REASON["cancelled"]
        assert recovery_cancel_terminal["failure_stage"] is None
        assert recovery_cancel_terminal["remote_cancel_unverified"]
        assert recovery_cancel_terminal["controller_pid"] is None

        # A failed scan while a *repair* controller is active is different
        # from the no-candidate case above.  Its prior candidate was already
        # bound before this provider launch.  A post-launch cancel must retain
        # that exact forensic/driver-review binding, even though the new
        # attempt's reconciliation cannot run.  This reproduces the fallback
        # path directly and validates the persisted schema rather than merely
        # inspecting a public projection.
        prior_job, prior_bin, prior_calls, _prior_fake, prior_command = fixture(
            "persistent-recovery-prior-candidate-cancel", workflow="project",
            max_cycles=3, idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        assert_attempt(prior_job, prior_bin, prior_calls, prior_command, "initial")
        first_candidate, _raw, first_sha = MODULE.load_state(prior_job)
        prior_verification = {
            "schema_version": 2,
            "summary": "driver found a repair",
            "passed_checks": [],
            "failed_checks": ["fixture"],
            "advisory_checks": 0,
            "missing_checks": 0,
            "candidate_sha256": first_candidate["result_sha256"],
            "coverage": "partial",
            "verified_findings": 1,
            "unresolved_gaps": 1,
            "diff_review_complete": True,
        }
        queued_prior, _queued_sha = MODULE.create_state(
            prior_job, "conversation-continue", resume=True,
            approve_sha=first_sha, verification=prior_verification,
        )
        prior_binding = {
            key: queued_prior[key] for key in (
                "result_path", "result_sha256", "result_identity",
                "candidate_source", "candidate_worktree_sha256",
                "candidate_worktree_entries",
            )
        }
        prior_calls.unlink(missing_ok=True)
        original_reconcile = MODULE._reconcile_worktree
        original_selector = MODULE.selectors.DefaultSelector
        original_prior_popen = MODULE.subprocess.Popen
        original_print_json = MODULE.print_json
        prior_pipe_fds: set[int] = set()
        prior_cancel_output: list[dict] = []

        def record_prior_provider_pipes(arguments, *popen_args, **popen_kwargs):
            child = original_prior_popen(arguments, *popen_args, **popen_kwargs)
            if isinstance(arguments, list) and arguments and arguments[0] == "agy":
                assert child.stdout is not None and child.stderr is not None
                prior_pipe_fds.update({child.stdout.fileno(), child.stderr.fileno()})
            return child

        class PriorCandidateCancelThenFailSelector:
            def __init__(self) -> None:
                self.inner = original_selector()
                self.provider_session = False
                self.cancelled = False

            def register(self, fileobj, events, data=None) -> None:
                if (
                    data in {"stdout", "stderr"}
                    and fileobj.fileno() in prior_pipe_fds
                ):
                    self.provider_session = True
                return self.inner.register(fileobj, events, data)

            def get_map(self):
                return self.inner.get_map()

            def select(self, _timeout=None):
                if not self.provider_session:
                    return self.inner.select(_timeout)
                if not self.cancelled:
                    self.cancelled = True
                    _current, _raw, approval = MODULE.load_state(prior_job)
                    assert MODULE.command_control(prior_job, "cancel", approval, None) == 0
                raise RuntimeError("fixture prior candidate recovery cancellation failure")

            def unregister(self, fileobj):
                return self.inner.unregister(fileobj)

            def close(self) -> None:
                self.inner.close()

        MODULE._reconcile_worktree = always_fail_reconcile
        MODULE.subprocess.Popen = record_prior_provider_pipes
        MODULE.selectors.DefaultSelector = PriorCandidateCancelThenFailSelector
        MODULE.print_json = lambda value: prior_cancel_output.append(value)
        try:
            assert run_controller(prior_job, prior_bin) == MODULE.EXIT_BY_REASON["cancelled"]
        finally:
            MODULE._reconcile_worktree = original_reconcile
            MODULE.subprocess.Popen = original_prior_popen
            MODULE.selectors.DefaultSelector = original_selector
            MODULE.print_json = original_print_json
        prior_terminal, _raw, _sha = MODULE.load_state(prior_job)
        MODULE.validate_state(prior_terminal)
        assert len(prior_cancel_output) == 1
        assert prior_cancel_output[0]["status"] == "cancel-requested"
        assert (prior_terminal["status"], prior_terminal["reason"], prior_terminal["failure_stage"]) == (
            "cancelled", "cancelled", None,
        )
        assert prior_terminal["remote_cancel_unverified"]
        assert prior_terminal["result_available"]
        assert prior_terminal["driver_disposition"] == "unreviewed"
        assert prior_terminal["worktree_reconciliation"] == "unavailable"
        assert all(prior_terminal[key] == expected for key, expected in prior_binding.items())
        assert prior_terminal["controller_pid"] is None
        assert prior_pipe_fds, "fixture did not reach provider Popen"
        assert prior_calls.read_text(encoding="utf-8").splitlines() in (
            ["version", "help"], ["version", "help", "provider"],
        )

        # Provider elapsed time starts at the Popen invocation boundary, then
        # is persisted only after successful creation.  It ends after
        # process-group termination/reap.  Terminal envelope parsing and
        # worktree reconciliation remain outside the budget.
        timing_job, timing_bin, timing_calls, _timing_fake, _timing_command = fixture(
            "runtime-termination-boundary",
            idle_seconds=1, hard_seconds=3, max_seconds=10,
        )
        original_terminate = MODULE._terminate
        original_validate_terminal = MODULE._validate_terminal_envelope
        original_reconciliation_projection = MODULE._reconciliation_from_snapshot
        original_timing_popen = MODULE.subprocess.Popen
        timing_reconciliation_observation: dict[str, object] = {}

        def delayed_provider_popen(arguments, *popen_args, **popen_kwargs):
            if isinstance(arguments, list) and arguments and arguments[0] == "agy":
                time.sleep(0.40)
            return original_timing_popen(arguments, *popen_args, **popen_kwargs)

        def delayed_terminate(process):
            time.sleep(0.20)
            return original_terminate(process)

        def delayed_validate_terminal(*args, **kwargs):
            time.sleep(0.25)
            return original_validate_terminal(*args, **kwargs)

        def delayed_reconciliation_projection(*args, **kwargs):
            frozen, frozen_raw, frozen_sha = MODULE.load_state(timing_job)
            visible = MODULE.public_status(frozen, frozen_sha)
            repeated, repeated_raw, repeated_sha = MODULE.load_state(timing_job)
            repeated_visible = MODULE.public_status(repeated, repeated_sha)
            timing_reconciliation_observation.update({
                "elapsed": frozen["elapsed_seconds"],
                "started_epoch": frozen["started_epoch"],
                "actions": {item["action"] for item in visible["available_actions"]},
                "repeat_elapsed": repeated["elapsed_seconds"],
                "repeat_actions": {item["action"] for item in repeated_visible["available_actions"]},
            })
            assert frozen_raw == repeated_raw and frozen_sha == repeated_sha
            try:
                MODULE.command_control(timing_job, "extend", frozen_sha, 1.0)
            except MODULE.DispatchError:
                pass
            else:
                raise AssertionError("post-reap reconciliation accepted an extension")
            assert (timing_job / MODULE.STATE_NAME).read_bytes() == frozen_raw
            time.sleep(0.25)
            return original_reconciliation_projection(*args, **kwargs)

        MODULE.subprocess.Popen = delayed_provider_popen
        MODULE._terminate = delayed_terminate
        MODULE._validate_terminal_envelope = delayed_validate_terminal
        MODULE._reconciliation_from_snapshot = delayed_reconciliation_projection
        timing_started = time.monotonic()
        try:
            assert run_controller(timing_job, timing_bin) == 0
        finally:
            timing_wall = time.monotonic() - timing_started
            MODULE.subprocess.Popen = original_timing_popen
            MODULE._terminate = original_terminate
            MODULE._validate_terminal_envelope = original_validate_terminal
            MODULE._reconciliation_from_snapshot = original_reconciliation_projection
        timing_state, _raw, _sha = MODULE.load_state(timing_job)
        assert timing_state["status"] == "succeeded"
        # The delayed provider Popen is charged: a descendant can schedule
        # work as soon as Popen returns, so sampling only afterwards would
        # leave a hard-deadline escape window.  The later validation and
        # reconciliation delays are not provider runtime.
        assert 0.55 <= timing_state["elapsed_seconds"] < 0.95
        assert timing_wall - timing_state["elapsed_seconds"] >= 0.40
        assert timing_reconciliation_observation["started_epoch"] is None
        assert timing_reconciliation_observation["elapsed"] == timing_state["elapsed_seconds"]
        assert "extend" not in timing_reconciliation_observation["actions"]
        assert timing_reconciliation_observation["repeat_elapsed"] == timing_state["elapsed_seconds"]
        assert "extend" not in timing_reconciliation_observation["repeat_actions"]
        assert timing_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # A fixed control poll can extend beyond a nearer provider boundary.
        # Make that overshoot deterministic: the selector records a simulated
        # side effect whenever the requested wait itself exceeds the 80ms hard
        # lease, then returns already-ready terminal bytes after the lease.
        # The controller must request only the remaining lease, classify the
        # resampled time before treating those bytes as progress, and preserve
        # the complete report by draining the reaped pipe as bounded evidence.
        wait_job, wait_bin, wait_calls, _wait_fake, _wait_command = fixture(
            "deadline-aware-selector", idle_seconds=0.08,
            hard_seconds=0.08, max_seconds=0.50,
        )
        original_wait_selector = MODULE.selectors.DefaultSelector
        requested_waits: list[float] = []
        simulated_overshoot = root / "deadline-aware-selector-side-effect"

        class DeadlineAwareSelector(original_wait_selector):
            delayed = False

            def select(self, timeout=None):
                if not self.delayed and {
                    key.data for key in self.get_map().values()
                } == {"stdout", "stderr"}:
                    self.delayed = True
                    requested = float(timeout or 0.0)
                    requested_waits.append(requested)
                    if requested > 0.10:
                        simulated_overshoot.write_text("overshot\n", encoding="ascii")
                    time.sleep(requested + 0.04)
                    return super().select(0)
                return super().select(timeout)

        MODULE.selectors.DefaultSelector = DeadlineAwareSelector
        try:
            assert run_controller(wait_job, wait_bin) == MODULE.EXIT_BY_REASON[
                "hard_deadline_exceeded"
            ]
        finally:
            MODULE.selectors.DefaultSelector = original_wait_selector
        wait_state, _raw, _sha = MODULE.load_state(wait_job)
        assert requested_waits and 0.0 < requested_waits[0] <= 0.08
        assert not simulated_overshoot.exists()
        assert (wait_state["reason"], wait_state["limit_kind"]) == (
            "hard_deadline_exceeded", "hard",
        )
        assert wait_state["candidate_recognized"] and wait_state["result_available"]
        assert wait_state["candidate_source"] == "provider_success"
        assert wait_state["progress_count"] == 0
        assert wait_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # The post-select state reload is equally important in the other
        # direction: an approved extension that lands while the provider is
        # live replaces the old hard boundary.  A report arriving after the
        # original lease but before the extended lease must succeed.
        extended_job, extended_bin, extended_calls, _extended_fake, _extended_command = fixture(
            "selector-extension", idle_seconds=0.50,
            # Leave a wide bounded margin after the original lease: process
            # scheduling and heartbeat sleeps can accumulate several seconds
            # of overhead on a loaded macOS runner.
            hard_seconds=3.00, max_seconds=8.00,
        )
        original_extension_selector = MODULE.selectors.DefaultSelector
        original_print_json = MODULE.print_json
        extension_applied = False
        extension_output: list[dict] = []

        class ExtendingSelector(original_extension_selector):
            def select(self, timeout=None):
                nonlocal extension_applied
                current, _raw, approval = MODULE.load_state(extended_job)
                if current["progress_count"] > 0 and not extension_applied:
                    MODULE.command_control(extended_job, "extend", approval, 5.0)
                    extension_applied = True
                return super().select(timeout)

        MODULE.selectors.DefaultSelector = ExtendingSelector
        MODULE.print_json = lambda value: extension_output.append(value)
        prior_heartbeat_count = os.environ.get("FAKE_DIRECT_HEARTBEAT_COUNT")
        prior_heartbeat_delay = os.environ.get("FAKE_DIRECT_HEARTBEAT_DELAY")
        # The result remains after the original three-second lease but before
        # the approved eight-second lease, with a meaningful scheduling margin.
        os.environ["FAKE_DIRECT_HEARTBEAT_COUNT"] = "32"
        os.environ["FAKE_DIRECT_HEARTBEAT_DELAY"] = "0.10"
        extended_returncode: int | None = None
        try:
            extended_returncode = run_controller(extended_job, extended_bin)
        finally:
            MODULE.selectors.DefaultSelector = original_extension_selector
            MODULE.print_json = original_print_json
            if prior_heartbeat_count is None:
                os.environ.pop("FAKE_DIRECT_HEARTBEAT_COUNT", None)
            else:
                os.environ["FAKE_DIRECT_HEARTBEAT_COUNT"] = prior_heartbeat_count
            if prior_heartbeat_delay is None:
                os.environ.pop("FAKE_DIRECT_HEARTBEAT_DELAY", None)
            else:
                os.environ["FAKE_DIRECT_HEARTBEAT_DELAY"] = prior_heartbeat_delay
        extended_state, _raw, _sha = MODULE.load_state(extended_job)
        assert extended_returncode == 0, {
            "returncode": extended_returncode,
            "extension_applied": extension_applied,
            "reason": extended_state["reason"],
            "limit_kind": extended_state["limit_kind"],
            "elapsed_seconds": extended_state["elapsed_seconds"],
            "hard_seconds": extended_state["hard_seconds"],
            "progress_count": extended_state["progress_count"],
        }
        assert extension_applied and len(extension_output) == 1
        assert extended_state["hard_seconds"] == 8.00
        assert 3.00 < extended_state["elapsed_seconds"] < 8.00
        assert extended_state["status"] == "succeeded"
        assert extended_state["candidate_recognized"] and extended_state["result_available"]
        assert extended_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # Reaping is the provider-runtime boundary, even when controller-local
        # envelope and worktree work follows it.  A valid terminal report after
        # that boundary remains a reviewable candidate, but a hard deadline is
        # still the terminal disposition and must not be advertised as success.
        hard_job, hard_bin, hard_calls, _hard_fake, _hard_command = fixture(
            "runtime-freeze-hard-candidate", idle_seconds=0.50, hard_seconds=1,
            max_seconds=2,
        )
        original_terminate = MODULE._terminate
        original_reconciliation_projection = MODULE._reconciliation_from_snapshot
        reconciliation_observation: dict[str, object] = {}

        def late_reap(process):
            time.sleep(1.15)
            return original_terminate(process)

        def inspect_frozen_reconciliation(*args, **kwargs):
            frozen, frozen_raw, frozen_sha = MODULE.load_state(hard_job)
            frozen_public = MODULE.public_status(frozen, frozen_sha)
            reconciliation_observation.update({
                "raw": frozen_raw,
                "elapsed": frozen["elapsed_seconds"],
                "started_epoch": frozen["started_epoch"],
                "actions": {item["action"] for item in frozen_public["available_actions"]},
            })
            return original_reconciliation_projection(*args, **kwargs)

        MODULE._terminate = late_reap
        MODULE._reconciliation_from_snapshot = inspect_frozen_reconciliation
        try:
            assert run_controller(hard_job, hard_bin) == MODULE.EXIT_BY_REASON[
                "hard_deadline_exceeded"
            ]
        finally:
            MODULE._terminate = original_terminate
            MODULE._reconciliation_from_snapshot = original_reconciliation_projection
        hard_state, hard_raw, hard_sha = MODULE.load_state(hard_job)
        assert (hard_state["status"], hard_state["reason"], hard_state["limit_kind"]) == (
            "failed", "hard_deadline_exceeded", "hard",
        )
        assert hard_state["elapsed_seconds"] >= hard_state["hard_seconds"]
        assert hard_state["candidate_recognized"] and hard_state["result_available"]
        assert hard_state["candidate_source"] == "provider_success"
        assert hard_state["driver_disposition"] == "unreviewed"
        assert reconciliation_observation["started_epoch"] is None
        assert reconciliation_observation["elapsed"] == hard_state["elapsed_seconds"]
        assert "extend" not in reconciliation_observation["actions"]
        # The same stale extension predicate is used by the command path and
        # must reject without a state write or another provider launch.
        before_extend = hard_raw
        try:
            MODULE.command_control(hard_job, "extend", hard_sha, 1.0)
        except MODULE.DispatchError:
            pass
        else:
            raise AssertionError("terminal frozen deadline accepted an extension")
        assert (hard_job / MODULE.STATE_NAME).read_bytes() == before_extend
        assert hard_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # Candidate binding can use the same bounded Git path as
        # reconciliation.  It is outside the final transition lock: a
        # SHA-approved cancellation completes while the snapshot is blocked,
        # then the controller consumes that cancellation without retrying the
        # provider or turning the report into a candidate.
        cancel_job, cancel_bin, cancel_calls, _cancel_fake, _cancel_command = fixture(
            "cancel-during-candidate-scan", idle_seconds=0.50, hard_seconds=3,
            max_seconds=5,
        )
        original_candidate_snapshot = MODULE._state_worktree_snapshot
        candidate_scan_entered = threading.Event()
        cancel_completed = threading.Event()
        cancel_errors: list[BaseException] = []
        cancel_thread: threading.Thread | None = None

        def cancel_while_candidate_snapshot(state: dict, workdir: str):
            nonlocal cancel_thread
            if (
                state["status"] == "running" and state["started_epoch"] is None
                and not candidate_scan_entered.is_set()
            ):
                candidate_scan_entered.set()

                def request_cancel() -> None:
                    try:
                        _current, _raw, approval = MODULE.load_state(cancel_job)
                        assert MODULE.command_control(cancel_job, "cancel", approval, None) == 0
                    except BaseException as exc:  # surfaced after the hook returns
                        cancel_errors.append(exc)
                    finally:
                        cancel_completed.set()

                cancel_thread = threading.Thread(target=request_cancel)
                cancel_thread.start()
                assert cancel_completed.wait(3.0), "cancel remained blocked by candidate scan"
                assert not cancel_errors
            return original_candidate_snapshot(state, workdir)

        MODULE._state_worktree_snapshot = cancel_while_candidate_snapshot
        original_print_json = MODULE.print_json
        cancel_control_output: list[dict] = []
        MODULE.print_json = lambda value: cancel_control_output.append(value)
        try:
            assert run_controller(cancel_job, cancel_bin) == MODULE.EXIT_BY_REASON["cancelled"]
        finally:
            MODULE._state_worktree_snapshot = original_candidate_snapshot
            MODULE.print_json = original_print_json
            if cancel_thread is not None:
                cancel_thread.join(timeout=1.0)
        assert candidate_scan_entered.is_set() and cancel_completed.is_set() and not cancel_errors
        assert len(cancel_control_output) == 1 and cancel_control_output[0]["status"] == "cancel-requested"
        cancelled, _raw, _sha = MODULE.load_state(cancel_job)
        assert (cancelled["status"], cancelled["reason"]) == ("cancelled", "cancelled")
        assert not cancelled["candidate_recognized"] and not cancelled["result_available"]
        assert cancel_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # A cancellation that wins after the pipe loop/reap but before
        # terminal reconciliation has no usable candidate.  It must not wait
        # for the expensive repository snapshot merely because the provider
        # happened to have emitted a report bytes-before the cancellation.  A
        # deliberately slow reconciliation therefore must never be entered;
        # this is also the direct control-path bound for the shell lifecycle
        # regression below.
        prompt_cancel_job, prompt_cancel_bin, prompt_cancel_calls, _fake, _command = fixture(
            "post-reap-cancel-skips-reconciliation", idle_seconds=0.50,
            hard_seconds=3, max_seconds=5,
        )
        original_prompt_selector = MODULE.selectors.DefaultSelector
        original_prompt_reconcile = MODULE._reconcile_worktree
        original_prompt_print_json = MODULE.print_json
        prompt_cancelled = threading.Event()
        prompt_cancel_output: list[dict] = []
        prompt_scan_calls = 0

        class CancelBeforeTerminalReconciliation(original_prompt_selector):
            def select(self, timeout=None):
                if (
                    not prompt_cancelled.is_set()
                    and {key.data for key in self.get_map().values()} == {"stdout", "stderr"}
                ):
                    _current, _raw, approval = MODULE.load_state(prompt_cancel_job)
                    assert MODULE.command_control(
                        prompt_cancel_job, "cancel", approval, None,
                    ) == 0
                    prompt_cancelled.set()
                return super().select(timeout)

        def prohibited_slow_reconciliation(*args, **kwargs):
            nonlocal prompt_scan_calls
            prompt_scan_calls += 1
            time.sleep(2.5)
            raise AssertionError("no-candidate cancellation entered reconciliation")

        MODULE.selectors.DefaultSelector = CancelBeforeTerminalReconciliation
        MODULE._reconcile_worktree = prohibited_slow_reconciliation
        MODULE.print_json = lambda value: prompt_cancel_output.append(value)
        prompt_cancel_started = time.monotonic()
        try:
            assert run_controller(prompt_cancel_job, prompt_cancel_bin) == MODULE.EXIT_BY_REASON[
                "cancelled"
            ]
        finally:
            prompt_cancel_elapsed = time.monotonic() - prompt_cancel_started
            MODULE.selectors.DefaultSelector = original_prompt_selector
            MODULE._reconcile_worktree = original_prompt_reconcile
            MODULE.print_json = original_prompt_print_json
        prompt_terminal, _raw, _sha = MODULE.load_state(prompt_cancel_job)
        MODULE.validate_state(prompt_terminal)
        assert prompt_cancelled.is_set() and prompt_scan_calls == 0
        assert prompt_cancel_elapsed < 2.0
        assert len(prompt_cancel_output) == 1
        assert (prompt_terminal["status"], prompt_terminal["reason"], prompt_terminal["exit_code"]) == (
            "cancelled", "cancelled", MODULE.EXIT_BY_REASON["cancelled"],
        )
        assert prompt_terminal["remote_cancel_unverified"]
        assert not prompt_terminal["candidate_recognized"] and not prompt_terminal["result_available"]
        assert prompt_terminal["driver_disposition"] == "not_applicable"
        assert prompt_terminal["worktree_reconciliation"] == "unavailable"
        assert prompt_terminal["worktree_changes_present"] is None
        assert prompt_terminal["worktree_changed_since_dispatch"] is None
        assert prompt_cancel_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # A deadline never launders an unbound terminal artifact into a
        # candidate.  Binding/security failure keeps its fail-closed terminal
        # disposition and drops the report.
        binding_job, binding_bin, binding_calls, _binding_fake, _binding_command = fixture(
            "runtime-freeze-binding-failure", idle_seconds=0.50, hard_seconds=1,
            max_seconds=2,
        )
        original_validate_terminal = MODULE._validate_terminal_envelope

        def reject_terminal_binding(*args, **kwargs):
            raise MODULE.DispatchError("fixture terminal binding changed")

        MODULE._terminate = late_reap
        MODULE._validate_terminal_envelope = reject_terminal_binding
        try:
            assert run_controller(binding_job, binding_bin) == MODULE.EXIT_BY_REASON[
                "status_unavailable"
            ]
        finally:
            MODULE._terminate = original_terminate
            MODULE._validate_terminal_envelope = original_validate_terminal
        binding_state, _raw, _sha = MODULE.load_state(binding_job)
        assert (binding_state["reason"], binding_state["failure_stage"]) == (
            "status_unavailable", "binding_failure",
        )
        assert not binding_state["candidate_recognized"] and not binding_state["result_available"]
        assert binding_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # Maximum-runtime exhaustion has the same candidate preservation but
        # never leaves a continuation route, regardless of a valid report.
        max_job, max_bin, max_calls, _max_fake, _max_command = fixture(
            "runtime-freeze-max-candidate", workflow="project", max_cycles=3,
            idle_seconds=0.50, hard_seconds=1, max_seconds=1,
        )
        MODULE._terminate = late_reap
        try:
            assert run_controller(max_job, max_bin) == MODULE.EXIT_BY_REASON[
                "hard_deadline_exceeded"
            ]
        finally:
            MODULE._terminate = original_terminate
        max_state, _raw, max_sha = MODULE.load_state(max_job)
        assert (max_state["reason"], max_state["limit_kind"]) == (
            "hard_deadline_exceeded", "max-runtime",
        )
        assert max_state["candidate_recognized"] and not max_state["continue_available"]
        assert "continue" not in {
            item["action"] for item in MODULE.public_status(max_state, max_sha, job=max_job)["available_actions"]
        }
        assert max_calls.read_text(encoding="utf-8").splitlines() == [
            "version", "help", "provider",
        ]

        # The locked freeze and the shared extend predicate have no race
        # window: extending before freeze changes the classified hard limit;
        # freezing first makes the otherwise identical extension stale.
        extend_job, _extend_bin, _extend_calls, _extend_fake, _extend_command = fixture(
            "extend-before-freeze", idle_seconds=1, hard_seconds=2, max_seconds=4,
        )
        extend_state, extend_raw, extend_sha = MODULE.load_state(extend_job)
        extend_state.update({
            "status": "running", "controller_pid": os.getpid(),
            "started_epoch": time.time() - 0.05, "progress_count": 1,
            "last_progress_epoch": time.time(),
        })
        _extend_raw, extend_sha = MODULE.write_atomic(
            extend_job, MODULE.STATE_NAME, extend_state,
        )
        original_print_json = MODULE.print_json
        extend_control_output: list[dict] = []
        MODULE.print_json = lambda value: extend_control_output.append(value)
        try:
            assert MODULE.command_control(extend_job, "extend", extend_sha, 1.0) == 0
        finally:
            MODULE.print_json = original_print_json
        assert len(extend_control_output) == 1 and extend_control_output[0]["hard_seconds"] == 3.0
        extended, _extended_raw, _extended_sha = MODULE.load_state(extend_job)
        frozen_extended, _raw, _sha, extended_deadline = MODULE._freeze_reaped_runtime(
            extend_job, extended["attempt"], os.getpid(), 2.10,
        )
        assert frozen_extended["started_epoch"] is None
        assert frozen_extended["hard_seconds"] == 3.0 and extended_deadline is None

        frozen_job, _frozen_bin, _frozen_calls, _frozen_fake, _frozen_command = fixture(
            "freeze-before-extend", idle_seconds=1, hard_seconds=2, max_seconds=4,
        )
        frozen_state, _raw, frozen_sha = MODULE.load_state(frozen_job)
        frozen_state.update({
            "status": "running", "controller_pid": os.getpid(),
            "started_epoch": time.time() - 0.05, "progress_count": 1,
            "last_progress_epoch": time.time(),
        })
        _frozen_raw, frozen_sha = MODULE.write_atomic(
            frozen_job, MODULE.STATE_NAME, frozen_state,
        )
        frozen, frozen_raw, frozen_sha, frozen_deadline = MODULE._freeze_reaped_runtime(
            frozen_job, frozen_state["attempt"], os.getpid(), 2.10,
        )
        assert frozen_deadline == "hard"
        assert not MODULE._extend_is_eligible(frozen, time.time())
        try:
            MODULE.command_control(frozen_job, "extend", frozen_sha, 1.0)
        except MODULE.DispatchError:
            pass
        else:
            raise AssertionError("freeze-before-extend accepted a stale extension")
        assert (frozen_job / MODULE.STATE_NAME).read_bytes() == frozen_raw

        # A post-reap but under-hard reconciliation must be equally inert:
        # status does not advertise extension and the direct control endpoint
        # rejects without changing state or contacting a provider.
        under_job, _under_bin, under_calls, _under_fake, _under_command = fixture(
            "under-hard-freeze", idle_seconds=1, hard_seconds=3, max_seconds=5,
        )
        under_state, _raw, under_sha = MODULE.load_state(under_job)
        under_state.update({
            "status": "running", "controller_pid": os.getpid(),
            "started_epoch": time.time() - 0.05, "progress_count": 1,
            "last_progress_epoch": time.time(),
        })
        _under_raw, under_sha = MODULE.write_atomic(under_job, MODULE.STATE_NAME, under_state)
        under_frozen, under_raw, under_sha, under_deadline = MODULE._freeze_reaped_runtime(
            under_job, under_state["attempt"], os.getpid(), 0.10,
        )
        assert under_deadline is None and under_frozen["elapsed_seconds"] == 0.10
        assert "extend" not in {
            item["action"] for item in MODULE.public_status(under_frozen, under_sha)["available_actions"]
        }
        try:
            MODULE.command_control(under_job, "extend", under_sha, 1.0)
        except MODULE.DispatchError:
            pass
        else:
            raise AssertionError("under-hard frozen reconciliation accepted an extension")
        assert (under_job / MODULE.STATE_NAME).read_bytes() == under_raw
        assert not under_calls.exists(), "stale extension contacted a provider"

    check("direct selections bind public startup, launch replacement windows, and provider runtime boundaries", direct_selection_reprobes_every_controller_attempt)

    def source_fixture(label: str, mutation: str = "", *, scoped: bool = False, terminal: str = "success", native: bool = False, separate_git: bool = False):
        origin = (root / f"source-guard-{label}-origin").resolve()
        candidate = (root / f"source-guard-{label}-candidate").resolve()
        origin.mkdir()
        git_init = ["/usr/bin/git", "init", "-q"]
        if separate_git:
            git_init += ["--separate-git-dir", str(root / f"source-guard-{label}-git")]
        subprocess.run([*git_init, str(origin)], check=True)
        (origin / "tracked.txt").write_text("base\n")
        (origin / "candidate.txt").write_text("base\n")
        (origin / ".gitignore").write_text("ignored/\n")
        subprocess.run(["/usr/bin/git", "-C", str(origin), "add", "."], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "base"], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "worktree", "add", "-q", "-b", label, str(candidate)], check=True)
        job = (root / f"source-guard-{label}-job").resolve(); job.mkdir(mode=0o700)
        bin_dir = root / f"source-guard-{label}-bin"; bin_dir.mkdir()
        calls = root / f"source-guard-{label}-calls"
        schema = root / f"source-guard-{label}-schema.json"; provider_schema(schema)
        fake = bin_dir / "agy"
        fake.write_text(
            "#!/usr/bin/env python3\nimport json, pathlib, subprocess, sys, time\n"
            + f"origin = pathlib.Path({str(origin)!r})\ncalls = pathlib.Path({str(calls)!r})\n"
            + "calls.write_text(calls.read_text() + 'call\\n' if calls.exists() else 'call\\n')\n"
            + "def git(*args, payload=None):\n    return subprocess.check_output(['/usr/bin/git', '-C', str(origin), *args], input=payload).decode().strip()\n"
            + mutation + "\n"
            + ("" if terminal in {"permission", "timeout", "model"} else
               "print(json.dumps({'event':'init','init':{},'conversation_id':'source-guard'}), flush=True)\n")
            + ("print('permission that headless mode cannot prompt for', file=sys.stderr); raise SystemExit(6)\n" if terminal == "permission" else
               "print('[agy] print timeout after 30s with turn in progress; returning partial output', file=sys.stderr); raise SystemExit(17)\n" if terminal == "timeout" else
               "print('error: invalid model selection (fixture)', file=sys.stderr); raise SystemExit(1)\n" if terminal == "model" else
               "time.sleep(20)\n" if terminal == "wait" else "")
            + "(pathlib.Path.cwd() / 'candidate.txt').write_text('candidate\\n')\n"
            + f"report = {report(files_changed=[{'path': 'candidate.txt', 'change': 'modified'}])!r}\n"
            + "print(json.dumps({'event':'result','result':{'conversation_id':'source-guard','status':'SUCCESS','structured_output':report}}))\n"
        )
        fake.chmod(0o755)
        values = {"job_id": label, "workdir": str(candidate),
                  "argv": ["agy", "--json-schema", str(schema), "--print", "task"],
                  "idle_seconds": 2, "hard_seconds": 8, "max_seconds": 30, "max_cycles": 2}
        if native:
            values["provider_isolation"] = "native"
            values["argv"].insert(1, "--sandbox")
        if scoped:
            scope_path = job / "scope.json"
            raw = MODULE.canonical({"schema_version": 1, "kind": "agy-worker-provider-scope",
                                    "read": [{"kind": "file", "path": "candidate.txt"}, {"kind": "file", "path": "tracked.txt"}],
                                    "write": [{"kind": "file", "path": "candidate.txt"}]})
            scope_path.write_bytes(raw); scope_path.chmod(0o600)
            values.update(provider_scope_path=str(scope_path), provider_scope_sha256=MODULE.digest(raw),
                          provider_scope_identity=list(MODULE._identity(scope_path.stat())), allow_scoped_repair=True)
        command = current_command_fixture(values)
        MODULE.write_atomic(job, MODULE.COMMAND_NAME, command)
        MODULE.create_state(job, "initial", resume=False)
        return origin, candidate, job, bin_dir, calls

    def assert_source_veto(job: Path, expected: str = "source_checkout_changed") -> dict:
        state, _raw, sha = MODULE.load_state(job)
        assert state["reason"] == expected, state
        assert state["status"] == "failed" and state["phase"] == state["assurance"] == "blocked", state
        assert not any(state[key] for key in ("candidate_recognized", "result_available", "resume_available", "continue_available"))
        assert state["candidate_source"] == "none"
        assert all(state[key] is None for key in ("result_path", "result_sha256", "candidate_worktree_sha256",
                                                 "last_success_path", "verification_path", "repair_lineage_sha256"))
        public = MODULE.public_status(state, sha)
        assert public["available_actions"] == [] and public["reason_message"]
        assert public["assurance"] == "blocked" and public["controller_phase"] == "blocked"
        for origin, resume in (("fresh-restart", False), ("conversation-resume", True), ("conversation-continue", True)):
            try:
                MODULE.create_state(job, origin, resume=resume, approve_sha=sha)
            except MODULE.DispatchError:
                pass
            else:
                raise AssertionError("guard failure authorized another attempt")
        assert MODULE.load_state(job)[2] == sha
        return state

    mutations = {
        "untracked": "(origin / 'escape.txt').write_text('escape\\n')",
        "tracked": "(origin / 'tracked.txt').write_text('changed\\n')",
        "staging": "oid = git('hash-object', '-w', '--stdin', payload=b'index only\\n')\ngit('update-index', '--cacheinfo', '100644', oid, 'tracked.txt')",
        "head": "tree = git('rev-parse', 'HEAD^{tree}')\nhead = git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit-tree', tree, '-p', 'HEAD', payload=b'same tree\\n')\ngit('update-ref', 'HEAD', head)",
    }
    for kind, mutation in mutations.items():
        for scoped in (False, True):
            def mutation_case(kind=kind, mutation=mutation, scoped=scoped) -> None:
                _origin, candidate, job, bin_dir, calls = source_fixture(f"{kind}-{scoped}", mutation, scoped=scoped)
                assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
                state = assert_source_veto(job)
                assert state["source_checkout_guard"]["status"] == "changed"
                assert state["source_checkout_guard"]["before_sha256"] != state["source_checkout_guard"]["after_sha256"]
                assert calls.read_text() == "call\n"
                if scoped:
                    assert (candidate / "candidate.txt").read_text() == "base\n", "suspect stage reconciled"
                    assert not (job / "stage-001").exists()
            check(f"source guard rejects {kind} changes in {'scoped' if scoped else 'whole'} attempts", mutation_case)

    def source_budget_closed_before_spawn() -> None:
        for scoped in (False, True):
            origin, _candidate, job, bin_dir, calls = source_fixture(f"oversized-{scoped}", scoped=scoped)
            with (origin / "oversized.bin").open("wb") as handle:
                handle.truncate(64 * 1024 * 1024 + 1)
            assert run_controller(job, bin_dir) == 29
            state = assert_source_veto(job, "source_checkout_guard_unavailable")
            assert not calls.exists()
            assert "smaller dedicated source checkout" in MODULE.public_status(state, MODULE.load_state(job)[2])["reason_message"]
        origin, _candidate, job, bin_dir, calls = source_fixture("oversized-dirty")
        with (origin / "tracked.txt").open("wb") as handle:
            handle.truncate(64 * 1024 * 1024 + 1)
        assert run_controller(job, bin_dir) == 29
        assert_source_veto(job, "source_checkout_guard_unavailable")
        assert not calls.exists()
        _origin, candidate, job, bin_dir, calls = source_fixture("oversized-post", "with (origin / 'huge.bin').open('wb') as handle: handle.truncate(64 * 1024 * 1024 + 1)", scoped=True)
        assert run_controller(job, bin_dir) == 29
        assert_source_veto(job, "source_checkout_guard_unavailable")
        assert calls.read_text() == "call\n" and (candidate / "candidate.txt").read_text() == "base\n"
    check("source guard budget exhaustion blocks provider spawn with actionable status", source_budget_closed_before_spawn)

    def unchanged_source_controls() -> None:
        # Every bound terminal report requires proof regardless of its outer
        # disposition. These are admissible controls and mutation vetoes.
        for terminal in ("SUCCESS", "ERROR", "CANCELLED", "timeout"):
            for mutated in (False, True):
                _origin, _candidate, job, bin_dir, _calls = source_fixture(
                    f"report-{terminal}-{mutated}", mutations["untracked"] if mutated else "",
                )
                fake = bin_dir / "agy"
                text = fake.read_text()
                if terminal == "timeout":
                    text += "print('[agy] print timeout after 30s with turn in progress; returning partial output', file=sys.stderr)\n"
                else:
                    text = text.replace("'status':'SUCCESS'", f"'status':{terminal!r}")
                fake.write_text(text)
                code = run_controller(job, bin_dir)
                if mutated:
                    assert code == 28
                    assert_source_veto(job)
                else:
                    state, _raw, _sha = MODULE.load_state(job)
                    assert state["candidate_recognized"] and state["result_available"], state
                    assert state["source_checkout_guard"]["status"] == "unchanged"

        for scoped in (False, True):
            origin, candidate, job, bin_dir, _calls = source_fixture(f"control-{scoped}", scoped=scoped)
            (origin / "tracked.txt").write_text("preexisting dirty\n")
            (origin / "dirty-untracked.txt").write_text("preexisting\n")
            ignored = origin / "ignored"; ignored.mkdir(); (ignored / "data").write_text("old")
            fake = bin_dir / "agy"
            fake.write_text(fake.read_text().replace("print(json.dumps({'event':'init'", "(origin / 'ignored' / 'data').write_text('new')\nprint(json.dumps({'event':'init'"))
            assert run_controller(job, bin_dir) == 0
            state, _raw, _sha = MODULE.load_state(job)
            assert state["candidate_recognized"] and state["result_available"]
            assert (candidate / "candidate.txt").read_text() == "candidate\n"
            if hasattr(MODULE, "_observe_source_checkout"):
                assert state["source_checkout_guard"]["status"] == "unchanged"
    check("source guard preserves stage workdir dirty-source and ignored-output controls", unchanged_source_controls)

    def main_workdir_skip() -> None:
        origin, _candidate, _job, _bin_dir, _calls = source_fixture("main-skip")
        before = MODULE._worktree_snapshot(str(origin))["sha256"]
        if hasattr(MODULE, "_observe_source_checkout"):
            assert MODULE._observe_source_checkout(str(origin))["status"] == "skipped_main_worktree"
            binding = MODULE._ControllerBinding(state={"attempt": 1, "workdir": str(origin), "source_checkout_guard": MODULE._pending_source_guard(1)}, command={"workdir": str(origin)})
            execution = MODULE._ProviderExecution()
            guard = MODULE._prepare_controller_source(binding, execution)
            assert guard["status"] == "skipped_main_worktree"
        (origin / "candidate.txt").write_text("candidate\n")
        assert MODULE._worktree_snapshot(str(origin))["sha256"] != before
        if hasattr(MODULE, "_observe_source_checkout"):
            MODULE._check_controller_source(binding, execution)
            assert execution.source_guard_result == guard
            assert MODULE._source_guard_reason({"source_checkout_guard": guard}) is None
    check("source guard helper skips a verified main workdir without changing write behavior", main_workdir_skip)

    def source_reason_precedence() -> None:
        from unittest import mock
        for terminal in ("permission", "timeout", "model", "cancel", "interrupt"):
            origin, _candidate, job, bin_dir, calls = source_fixture(f"precedence-{terminal}", mutations["untracked"], terminal=terminal if terminal not in {"cancel", "interrupt"} else "wait")
            expected = {"permission": 6, "timeout": 17, "model": 26, "cancel": 22, "interrupt": 143}[terminal]
            observations = []
            observe = MODULE._observe_source_checkout
            def counted(workdir, observations=observations, observe=observe):
                observations.append(workdir)
                return observe(workdir)
            if terminal in {"cancel", "interrupt"}:
                def request_stop(origin=origin, terminal=terminal, job=job):
                    deadline = time.monotonic() + 10
                    while not (origin / "escape.txt").exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if terminal == "cancel":
                        state, raw, _sha = MODULE.load_state(job)
                        MODULE.transition(job, state, raw, {"cancel_requested": True, "status": "cancel-requested"})
                    else:
                        os.kill(os.getpid(), signal.SIGTERM)
                thread = threading.Thread(target=request_stop); thread.start()
                try:
                    with mock.patch.object(MODULE, "_observe_source_checkout", side_effect=counted):
                        assert run_controller(job, bin_dir) == expected, MODULE.load_state(job)[0]
                finally:
                    thread.join(10)
            else:
                with mock.patch.object(MODULE, "_observe_source_checkout", side_effect=counted):
                    assert run_controller(job, bin_dir) == expected, MODULE.load_state(job)[0]
            state, _raw, sha = MODULE.load_state(job)
            assert len(observations) == 1, "no-candidate attempt re-digested after reap"
            assert state["source_checkout_guard"]["status"] == "deferred"
            assert state["source_checkout_guard"]["after_sha256"] is None
            assert not state["candidate_recognized"] and not state["result_available"]
            MODULE.validate_state(state)
            for updates in ({"candidate_recognized": True}, {"result_available": True},
                            {"result_path": "/tmp/forged"}, {"last_success_path": "/tmp/forged"}):
                try:
                    MODULE.validate_state({**state, **updates})
                except MODULE.DispatchError:
                    pass
                else:
                    raise AssertionError("deferred state accepted candidate authority")
            assert MODULE.public_status(state, sha)["source_checkout_guard"]["status"] == "deferred"
            if state["resume_available"]:
                MODULE.create_state(job, "conversation-resume", resume=True, approve_sha=sha)
            else:
                # These provider failures emit no conversation; a resume stays
                # unavailable, but the eligible fresh restart must compare too.
                try:
                    MODULE.create_state(job, "conversation-resume", resume=True, approve_sha=sha)
                except MODULE.DispatchError:
                    pass
                else:
                    raise AssertionError("unavailable resume became eligible")
                MODULE.create_state(job, "fresh-restart", resume=True, approve_sha=sha)
            assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
            assert_source_veto(job)
            assert calls.read_text() == "call\n", "changed source started another fake provider"
    check("source guard defers no-candidate failures cancellation and interrupt until relaunch", source_reason_precedence)

    def native_attempt_detects_independent_owner_change() -> None:
        from unittest import mock
        origin, candidate, job, bin_dir, _calls = source_fixture("native-owner", scoped=True, native=True)
        fake = bin_dir / "agy"
        # A contained provider must not write the external invocation marker.
        fake.write_text(fake.read_text().replace("calls.write_text(calls.read_text() + 'call\\n' if calls.exists() else 'call\\n')\n", ""))
        monitor = MODULE._monitor_controller_provider
        def edit_after_native_spawn(*args):
            (origin / "tracked.txt").write_text("independent owner edit\n")
            return monitor(*args)
        with mock.patch.object(MODULE, "_monitor_controller_provider", side_effect=edit_after_native_spawn):
            assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
        state = assert_source_veto(job)
        assert state["provider_isolation"] == "native" and state["agy_returncode"] == 0
        events = [json.loads(line) for line in Path(state["stream_path"]).read_text().splitlines()]
        assert sum(event.get("event") == "result" for event in events) == 1
        assert (candidate / "candidate.txt").read_text() == "base\n"
    check("source guard detects an independent owner edit during native containment", native_attempt_detects_independent_owner_change)

    def source_repair_attempt_is_fresh_and_terminal() -> None:
        from unittest import mock
        def feedback(state):
            return {"schema_version": 2, "summary": "repair", "passed_checks": [], "failed_checks": ["fixture"],
                    "advisory_checks": 0, "missing_checks": 0, "candidate_sha256": state["result_sha256"],
                    "coverage": "partial", "verified_findings": 1, "unresolved_gaps": 1, "diff_review_complete": True}
        for edited in (False, True):
            origin, _candidate, job, bin_dir, calls = source_fixture(f"baseline-{edited}", scoped=True)
            assert run_controller(job, bin_dir) == 0
            state, _raw, sha = MODULE.load_state(job)
            baseline = state["source_checkout_guard"]["before_sha256"]
            fake = bin_dir / "agy"
            fake.write_text(fake.read_text().replace("write_text('candidate\\n')", "write_text('repair\\n')"))
            MODULE.create_state(job, "conversation-continue", resume=True, approve_sha=sha, verification=feedback(state))
            if edited:
                (origin / "tracked.txt").write_text("between attempts\n")
                assert run_controller(job, bin_dir) == 28
                assert_source_veto(job)
                assert calls.read_text() == "call\n", "source edit launched repair"
            else:
                assert run_controller(job, bin_dir) == 0, MODULE.load_state(job)[0]
                final = MODULE.load_state(job)[0]
                assert final["source_checkout_guard"]["before_sha256"] == baseline
                assert final["source_checkout_guard"]["after_sha256"] == baseline
                assert calls.read_text() == "call\ncall\n"
        # A completed prelaunch veto must survive a stop arriving after the
        # observation, including a concurrently substituted persisted baseline.
        prepare = MODULE._prepare_controller_source
        for proof in ("changed", "unavailable", "transplant"):
            for stop in ("cancel", "interrupt", "max-runtime", "hard"):
                origin, _candidate, job, bin_dir, calls = source_fixture(
                    f"prelaunch-{proof}-{stop}", scoped=True,
                )
                assert run_controller(job, bin_dir) == 0
                state, _raw, sha = MODULE.load_state(job)
                MODULE.create_state(job, "conversation-continue", resume=True,
                                    approve_sha=sha, verification=feedback(state))
                if proof == "changed":
                    (origin / "tracked.txt").write_text("between attempts\n")

                def stop_after_proof(binding, execution, proof=proof, stop=stop, job=job):
                    if proof == "unavailable":
                        with mock.patch.object(MODULE, "_observe_source_checkout",
                                               side_effect=ValueError("incomplete proof")):
                            guard = prepare(binding, execution)
                    else:
                        guard = prepare(binding, execution)
                    current, raw, _sha = MODULE.load_state(job)
                    updates = {}
                    if proof == "transplant":
                        updates["source_checkout_guard"] = {
                            **guard, "before_sha256": "f" * 64,
                        }
                        MODULE._validate_source_guard({**current, **updates})
                    if stop == "cancel":
                        updates.update(cancel_requested=True, status="cancel-requested")
                    elif stop == "interrupt":
                        execution.stop_signal = signal.SIGTERM
                    elif stop == "max-runtime":
                        execution.elapsed = MODULE._provider_max_seconds(binding.state)
                    else:
                        execution.elapsed = float(binding.state["hard_seconds"])
                    if updates:
                        MODULE.transition(job, current, raw, updates)
                    return guard

                expected = "source_checkout_changed" if proof == "changed" else "source_checkout_guard_unavailable"
                with mock.patch.object(MODULE, "_prepare_controller_source", side_effect=stop_after_proof):
                    assert run_controller(job, bin_dir) == MODULE.EXIT_BY_REASON[expected], MODULE.load_state(job)[0]
                assert_source_veto(job, expected)
                assert calls.read_text() == "call\n", "prelaunch stop/veto race started a provider"

        # A no-report repair cancellation still owns an inherited candidate,
        # and therefore cannot defer its source proof.
        origin, _candidate, job, bin_dir, calls = source_fixture("inherited-cancel", scoped=True)
        assert run_controller(job, bin_dir) == 0
        state, _raw, sha = MODULE.load_state(job)
        fake = bin_dir / "agy"
        fake.write_text(fake.read_text().replace("print(json.dumps({'event':'init'", mutations["untracked"] + "\ntime.sleep(20)\nprint(json.dumps({'event':'init'"))
        MODULE.create_state(job, "conversation-continue", resume=True, approve_sha=sha, verification=feedback(state))
        monitor = MODULE._monitor_controller_provider
        def cancel_inherited(*args):
            deadline = time.monotonic() + 5
            while not (origin / "escape.txt").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            current, raw, _sha = MODULE.load_state(job)
            MODULE.transition(job, current, raw, {"cancel_requested": True, "status": "cancel-requested"})
            return monitor(*args)
        with mock.patch.object(MODULE, "_monitor_controller_provider", side_effect=cancel_inherited):
            assert run_controller(job, bin_dir) == 28
        assert_source_veto(job)
        assert calls.read_text() == "call\ncall\n"
        _origin, _candidate, job, bin_dir, calls = source_fixture("repair", scoped=True)
        assert run_controller(job, bin_dir) == 0
        state, _raw, sha = MODULE.load_state(job)
        assert state["continue_available"]
        first_guard = state.get("source_checkout_guard")
        verification = {"schema_version": 2, "summary": "repair", "passed_checks": [], "failed_checks": ["fixture"],
                        "advisory_checks": 0, "missing_checks": 0, "candidate_sha256": state["result_sha256"],
                        "coverage": "partial", "verified_findings": 1, "unresolved_gaps": 1, "diff_review_complete": True}
        fake = bin_dir / "agy"
        fake.write_text(fake.read_text().replace("print(json.dumps({'event':'init'", mutations["tracked"] + "\nprint(json.dumps({'event':'init'"))
        MODULE.create_state(job, "conversation-continue", resume=True, approve_sha=sha, verification=verification)
        pending, _raw, _sha = MODULE.load_state(job)
        if first_guard is not None:
            assert pending["source_checkout_guard"] == {**first_guard, "attempt": 2}
        assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
        final = assert_source_veto(job)
        assert final["source_checkout_guard"]["attempt"] == 2 and final["source_checkout_guard"] != first_guard
        assert calls.read_text() == "call\ncall\n"
    check("source guard preserves the job baseline across repairs and clears inherited candidate authority", source_repair_attempt_is_fresh_and_terminal)

    def source_exception_orphan_and_transplant() -> None:
        from unittest import mock
        origin, candidate, job, bin_dir, _calls = source_fixture("exception", mutations["untracked"], scoped=True, terminal="wait")
        def fail_after_write(*_args):
            deadline = time.monotonic() + 5
            while not (origin / "escape.txt").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise RuntimeError("synthetic controller failure")
        with mock.patch.object(MODULE, "_monitor_controller_provider", side_effect=fail_after_write):
            assert run_controller(job, bin_dir) == 20, MODULE.load_state(job)[0]
        assert MODULE.load_state(job)[0]["source_checkout_guard"]["status"] == "deferred"
        assert not (job / "stage-001").exists(), "scoped exception guard left owned provider stage behind"
        assert (candidate / "candidate.txt").read_text() == "base\n"
        origin, candidate, job, bin_dir, _calls = source_fixture("exception-replaced-stage", mutations["untracked"], scoped=True, terminal="wait")
        def replace_stage_after_write(_job, _binding, _execution, _streams, scoped_launch, _outcome):
            deadline = time.monotonic() + 5
            while not (origin / "escape.txt").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            scoped_launch.stage_dir.rename(job / "stage-held")
            scoped_launch.stage_dir.mkdir(mode=0o700)
            (scoped_launch.stage_dir / "replacement-marker").write_text("preserve\n")
            raise RuntimeError("synthetic exception after stage replacement")
        with mock.patch.object(MODULE, "_monitor_controller_provider", side_effect=replace_stage_after_write):
            assert run_controller(job, bin_dir) == 20, MODULE.load_state(job)[0]
        assert MODULE.load_state(job)[0]["source_checkout_guard"]["status"] == "deferred"
        assert (job / "stage-001" / "replacement-marker").read_text() == "preserve\n"
        assert (job / "stage-held").is_dir()
        assert (candidate / "candidate.txt").read_text() == "base\n"
        origin, _candidate, job, _bin, _calls = source_fixture("orphan")
        observed = MODULE._observe_source_checkout(MODULE.load_state(job)[0]["workdir"])
        state, raw, _sha = MODULE.load_state(job)
        guard = {"algorithm": "source-checkout-v1", "attempt": 1, "status": "armed", "before_sha256": observed["sha256"], "after_sha256": None,
                 **{key: observed[key] for key in MODULE._SOURCE_BINDING_KEYS}}
        MODULE.transition(job, state, raw, {"status": "running", "controller_pid": 123, "source_checkout_guard": guard})
        with mock.patch.object(MODULE, "print_control_status"):
            assert MODULE.command_status(job, "text") == 0
        assert_source_veto(job, "source_checkout_guard_unavailable")
        _origin, _candidate, job, bin_dir, _calls = source_fixture("transplant")
        original_check = MODULE._check_controller_source
        def transplant(binding, execution):
            state, raw, _sha = MODULE.load_state(job)
            altered = dict(state["source_checkout_guard"]); altered["before_sha256"] = "f" * 64
            MODULE.transition(job, state, raw, {"source_checkout_guard": altered})
            original_check(binding, execution)
        with mock.patch.object(MODULE, "_check_controller_source", side_effect=transplant):
            assert run_controller(job, bin_dir) == 29
        assert_source_veto(job, "source_checkout_guard_unavailable")
        _origin, _candidate, job, bin_dir, calls = source_fixture("prelaunch-transplant")
        original_prepare = MODULE._prepare_controller_source
        def prelaunch_transplant(binding, execution):
            guard = original_prepare(binding, execution)
            state, raw, _sha = MODULE.load_state(job)
            MODULE.transition(job, state, raw, {"source_checkout_guard": {**guard, "before_sha256": "f" * 64}})
            return guard
        with mock.patch.object(MODULE, "_prepare_controller_source", side_effect=prelaunch_transplant):
            assert run_controller(job, bin_dir) == 29
        assert_source_veto(job, "source_checkout_guard_unavailable")
        assert not calls.exists(), "transplanted baseline launched a provider"
        _origin, _candidate, job, bin_dir, _calls = source_fixture("authority-replaced", "origin.rename(origin.with_name(origin.name + '-moved'))", scoped=True)
        assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
        assert_source_veto(job)
        # An unconfirmed process-group exit cannot authorize a post observation.
        observed = MODULE._observe_source_checkout(MODULE.load_state(root / "source-guard-transplant-job")[0]["workdir"])
        binding = MODULE._ControllerBinding(state={"attempt": 1}, command={"workdir": str(root / "source-guard-transplant-candidate")})
        baseline = {"algorithm": "source-checkout-v1", "attempt": 1, "status": "armed", "before_sha256": observed["sha256"], "after_sha256": None,
                    **{key: observed[key] for key in MODULE._SOURCE_BINDING_KEYS}}
        execution = MODULE._ProviderExecution(started_mono=1.0, process=mock.Mock(), source_guard_baseline=baseline)
        with mock.patch.object(MODULE, "_observe_source_checkout", side_effect=AssertionError("unreaped provider scanned")):
            MODULE._check_controller_source(binding, execution)
        assert execution.source_guard_result["status"] == "unavailable"
        live_stage = root / "unreaped-stage"; live_stage.mkdir(mode=0o700)
        (live_stage / "marker").write_text("preserve\n")
        binding.state.update(elapsed_seconds=0.0, attempt_base_elapsed=0.0)
        launch = MODULE._ScopedLaunch(stage_dir=live_stage, stage_identity=MODULE._identity(live_stage.stat()))
        with mock.patch.object(MODULE, "_terminate_provider_process", side_effect=MODULE.DispatchError("unconfirmed reap")), \
             mock.patch.object(MODULE, "_freeze_reaped_runtime", return_value=(binding.state, b"", "0" * 64, None)), \
             mock.patch.object(MODULE, "_terminalize_owned", return_value=({"exit_code": 29}, b"", "0" * 64)), \
             mock.patch.object(MODULE.WORKTREE, "_cleanup_stage", side_effect=AssertionError("unreaped stage removed")) as cleanup:
            assert MODULE._recover_controller_failure(job, binding, execution, launch) == 29
            cleanup.assert_not_called()
        assert (live_stage / "marker").read_text() == "preserve\n"
    check("source guard checks exception reaps and blocks orphan or transplanted baselines", source_exception_orphan_and_transplant)

    def source_hardened_git_and_paths() -> None:
        from unittest import mock
        origin, candidate, _job, bin_dir, _calls = source_fixture("hardening")
        expected = MODULE._observe_source_checkout(str(candidate))["sha256"]
        combined_paths = ["rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"]
        assert MODULE.WORKTREE._fixed_git_read_argv(combined_paths)
        for near_miss in (combined_paths[:-1], [*combined_paths, "HEAD"],
                          [combined_paths[0], *reversed(combined_paths[1:])]):
            assert not MODULE.WORKTREE._fixed_git_read_argv(near_miss)
        real_reader = MODULE.WORKTREE._bounded_git_read
        filter_shape = ["config", "--includes", "--name-only", "--get-regexp",
                        r"^filter\..*\.(clean|process|required)$"]
        for reject in (False, True):
            _barrier_origin, barrier_candidate, barrier_job, barrier_bin, barrier_calls = source_fixture(
                f"filter-barrier-{reject}",
            )
            discovery_seen = {}
            filter_done = set()
            sampled = []
            def filter_barrier(*args, discovery_seen=discovery_seen, filter_done=filter_done,
                               sampled=sampled, reject=reject, **kwargs):
                read_root, shape = args[2], args[3]
                event = discovery_seen.setdefault(read_root, threading.Event())
                if shape == filter_shape:
                    assert event.wait(1.0), "safe discovery was serialized behind filter inspection"
                    time.sleep(0.01)
                    if not reject:
                        filter_done.add(read_root)
                    return (0, b"filter.evil.clean\n") if reject else (1, b"")
                if shape == combined_paths or shape == ["worktree", "list", "--porcelain", "-z"]:
                    event.set()
                else:
                    assert read_root in filter_done, "content sampling preceded filter verdict"
                    sampled.append(shape)
                return real_reader(*args, **kwargs)
            # Discovery may run under a blocked filter proof, but an unsuccessful
            # verdict must prevent every content/index read and provider start.
            original_observe = MODULE._observe_source_checkout
            def guarded_observe(workdir, original_observe=original_observe, filter_barrier=filter_barrier):
                with mock.patch.object(MODULE.WORKTREE, "_bounded_git_read", side_effect=filter_barrier):
                    return original_observe(workdir)
            with mock.patch.object(MODULE, "_observe_source_checkout", side_effect=guarded_observe):
                if reject:
                    assert run_controller(barrier_job, barrier_bin) == 29
                    assert_source_veto(barrier_job, "source_checkout_guard_unavailable")
                else:
                    MODULE._observe_source_checkout(str(barrier_candidate))
            if reject:
                assert not sampled and not barrier_calls.exists()
            else:
                assert sampled and len(filter_done) == 2
        for malformed in (b"one\ntwo\n", b"one\ntwo\nthree", b"one\ntwo\nthree\nfour\n",
                          b"one\n\nthree\n", b"one\ntwo\nthree\0\n", b"\xff\ntwo\nthree\n"):
            def malformed_paths(*args, malformed=malformed, **kwargs):
                return (0, malformed) if args[3] == combined_paths else real_reader(*args, **kwargs)
            with mock.patch.object(MODULE.WORKTREE, "_bounded_git_read", side_effect=malformed_paths):
                try:
                    MODULE._observe_source_checkout(str(candidate))
                except (ValueError, UnicodeError):
                    pass
                else:
                    raise AssertionError("ambiguous combined path output accepted")
        def relative_common(*args, **kwargs):
            result = real_reader(*args, **kwargs)
            if args[3] == combined_paths and result is not None:
                code, raw = result
                fields = raw.split(b"\n")
                common_path = Path(os.fsdecode(fields[2]))
                if not common_path.is_absolute():
                    common_path = Path(args[2]) / common_path
                fields[2] = os.fsencode(os.path.relpath(common_path, args[2]))
                return code, b"\n".join(fields)
            return result
        with mock.patch.object(MODULE.WORKTREE, "_bounded_git_read", side_effect=relative_common):
            assert MODULE._observe_source_checkout(str(candidate))["sha256"] == expected
        _separate_origin, _separate_candidate, separate_job, separate_bin, separate_calls = source_fixture(
            "separate-git", separate_git=True,
        )
        # Git registers the external Git dir as the main worktree here, so
        # no verified main registration exists. Preserve unavailable, not skip.
        assert run_controller(separate_job, separate_bin) == 29
        assert_source_veto(separate_job, "source_checkout_guard_unavailable")
        assert not separate_calls.exists()
        marker = root / "source-guard-helper-ran"
        helper = bin_dir / "hostile-helper"
        helper.write_text(f"#!/bin/sh\nprintf ran > {shlex.quote(str(marker))}\n"); helper.chmod(0o755)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "core.fsmonitor", str(helper)], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "core.hooksPath", str(bin_dir)], check=True)
        (bin_dir / "git").write_text(f"#!/bin/sh\nprintf ran > {shlex.quote(str(marker))}\n"); (bin_dir / "git").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(bin_dir), "GIT_DIR": str(origin / "wrong"), "GIT_WORK_TREE": str(origin / "wrong"), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": str(helper)}):
            assert MODULE._observe_source_checkout(str(candidate))["sha256"] == expected
        assert not marker.exists()
        include = root / "source-guard-filter-include"; include.write_text(f'[filter "evil"]\n clean = {helper}\n')
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "include.path", str(include)], check=True)
        try:
            MODULE._observe_source_checkout(str(candidate))
        except ValueError:
            pass
        else:
            raise AssertionError("effective content filter accepted")
        assert not marker.exists()
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "--unset", "include.path"], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "core.fsmonitor", "false"], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "config", "core.autocrlf", "true"], check=True)
        normalized_before = MODULE._observe_source_checkout(str(candidate))["sha256"]
        tracked_info = (origin / "tracked.txt").stat()
        (origin / "tracked.txt").write_bytes(b"base\r\n")
        os.utime(origin / "tracked.txt", ns=(tracked_info.st_atime_ns, tracked_info.st_mtime_ns))
        normalized = subprocess.check_output(["/usr/bin/git", "-C", str(origin), "diff", "--name-only", "--", "tracked.txt"])
        assert not normalized, normalized
        assert MODULE._observe_source_checkout(str(candidate))["sha256"] != normalized_before
        (origin / "link").symlink_to("tracked.txt")
        before = MODULE._observe_source_checkout(str(candidate))["sha256"]
        (origin / "link").unlink(); (origin / "link").symlink_to("missing")
        assert MODULE._observe_source_checkout(str(candidate))["sha256"] != before
        (origin / "link").unlink()
        directory = origin / "folder"; directory.mkdir(); (directory / "file").write_text("base")
        subprocess.run(["/usr/bin/git", "-C", str(origin), "add", "folder/file"], check=True)
        (directory / "file").unlink(); directory.rmdir(); directory.symlink_to(root)
        try:
            MODULE._observe_source_checkout(str(candidate))
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError("symlink parent followed")
    check("source guard uses fixed hardened Git rejects effective filters and never follows content parents", source_hardened_git_and_paths)

    def source_scale_and_race_boundaries() -> None:
        from unittest import mock
        origin, candidate, _job, _bin, _calls = source_fixture("scale")
        with (origin / "large.bin").open("wb") as handle:
            handle.truncate(65 * 1024 * 1024)
        subprocess.run(["/usr/bin/git", "-C", str(origin), "add", "large.bin"], check=True)
        real_read = os.read
        total = 0
        def count_read(fd, size):
            nonlocal total
            payload = real_read(fd, size); total += len(payload); return payload
        with mock.patch.object(MODULE.CANDIDATE_STATE.os, "read", side_effect=count_read):
            MODULE._observe_source_checkout(str(candidate))
        assert total < 1024 * 1024, total
        with mock.patch.object(MODULE.CANDIDATE_STATE, "SOURCE_CHECKOUT_PATH_LIMIT", 1):
            try:
                MODULE._observe_source_checkout(str(candidate))
            except ValueError:
                pass
            else:
                raise AssertionError("path count budget ignored")
        with mock.patch.object(MODULE.CANDIDATE_STATE, "SOURCE_CHECKOUT_LIST_TOTAL", 1):
            try:
                MODULE._observe_source_checkout(str(candidate))
            except ValueError:
                pass
            else:
                raise AssertionError("listing budget ignored")
        real_reader = MODULE.WORKTREE._bounded_git_read
        deadlines = []
        def capture(*args, **kwargs):
            deadlines.append(kwargs["deadline"])
            return real_reader(*args, **kwargs)
        with mock.patch.object(MODULE.WORKTREE, "_bounded_git_read", side_effect=capture):
            MODULE._observe_source_checkout(str(candidate))
        assert len(deadlines) > 10 and len(set(deadlines)) == 1
        # A failed sibling cannot return while another owned Git read runs.
        lock = threading.Lock()
        active = maximum_active = finished = 0
        def sibling_failure(*args, **kwargs):
            nonlocal active, maximum_active, finished
            if args[3][0] == "config":
                return real_reader(*args, **kwargs)
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.03)
                if args[3] == ["rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"]:
                    return None
                return real_reader(*args, **kwargs)
            finally:
                with lock:
                    active -= 1
                    finished += 1
        with mock.patch.object(MODULE.WORKTREE, "_bounded_git_read", side_effect=sibling_failure):
            try:
                MODULE._observe_source_checkout(str(candidate))
            except ValueError:
                pass
            else:
                raise AssertionError("failed source sibling accepted")
        assert maximum_active >= 2 and active == 0 and finished == 2
        original_binding = MODULE.CANDIDATE_STATE._source_binding
        count = 0
        def replace_authority(*args):
            nonlocal count
            result = original_binding(*args); count += 1
            if count == 2:
                result["source_identity"] = [0, 0, stat.S_IFDIR, 0]
            return result
        with mock.patch.object(MODULE.CANDIDATE_STATE, "_source_binding", side_effect=replace_authority):
            try:
                MODULE._observe_source_checkout(str(candidate))
            except ValueError:
                pass
            else:
                raise AssertionError("authority race accepted")
        # Exercise the same source adapter against real hanging/oversized Git
        # child groups. The fixed executable binder is replaced only in this fixture.
        for label, program in (("hang", "sleep 20"), ("overflow", "/usr/bin/head -c 8388609 /dev/zero")):
            fake_git = root / f"source-guard-{label}-git"
            fake_git.write_text("#!/bin/sh\n" + program + "\n"); fake_git.chmod(0o700)
            binding = MODULE.WORKTREE._safe_git_executable(str(fake_git))
            assert binding is not None
            started = time.monotonic()
            with mock.patch.object(MODULE.WORKTREE, "_safe_git_executable", return_value=binding), mock.patch.object(MODULE.CANDIDATE_STATE, "SOURCE_CHECKOUT_SECONDS", 0.2):
                try:
                    MODULE._observe_source_checkout(str(candidate))
                except ValueError:
                    pass
                else:
                    raise AssertionError("hanging or oversized source Git accepted")
            assert time.monotonic() - started < 3.0
    check("source guard bounds metadata and listings without rereading clean large tracked bytes", source_scale_and_race_boundaries)

    def source_schema_veto_and_old_state() -> None:
        _origin, _candidate, job, bin_dir, _calls = source_fixture("schema", mutations["untracked"])
        assert run_controller(job, bin_dir) == 28, MODULE.load_state(job)[0]
        state = assert_source_veto(job)
        for updates in ({"resume_available": True}, {"next_action": "restart"}, {"continue_available": True},
                        {"assurance": "verified"}, {"last_success_path": "/tmp/forged", "last_success_sha256": "a" * 64, "last_success_identity": [0, 0, 0, 0, 0]}):
            try:
                MODULE.validate_state({**state, **updates})
            except MODULE.DispatchError:
                pass
            else:
                raise AssertionError("forged guard candidate/action state accepted")
        for update in ({"extra": None}, {"attempt": 2}, {"status": "unchanged"}, {"after_sha256": "z" * 64}):
            try:
                MODULE.validate_state({**state, "source_checkout_guard": {**state["source_checkout_guard"], **update}})
            except MODULE.DispatchError:
                pass
            else:
                raise AssertionError("forged guard observation accepted")
        old = {**state, "schema_version": 19}
        (job / MODULE.STATE_NAME).write_bytes(MODULE.canonical(old)); (job / MODULE.STATE_NAME).chmod(0o600)
        before = {path.name: path.read_bytes() for path in job.iterdir() if path.is_file()}
        try:
            MODULE.command_status(job)
        except MODULE.UnsupportedSchemaError:
            pass
        else:
            raise AssertionError("old state accepted")
        assert {path.name: path.read_bytes() for path in job.iterdir() if path.is_file()} == before
        # The facade reads these fixed reasons through its existing reason plumbing.
        facade_spec = importlib.util.spec_from_file_location("source_guard_facade", SOURCE.with_name("workflow.py"))
        facade = importlib.util.module_from_spec(facade_spec)
        sys.modules[facade_spec.name] = facade; facade_spec.loader.exec_module(facade)
        for reason in ("source_checkout_changed", "source_checkout_guard_unavailable"):
            facts = {"state_sha256": "a" * 64, "status": "failed", "reason": reason, "workflow": "task", "attempt": 1, "max_cycles": 2, "result_available": False}
            decision = facade._delegation_from_dispatch(facts, approval_bound=True)
            assert decision["state"] == "evaluated" and decision["decision"]["decision"] == "blocked", decision
            assert decision["decision"]["reason_code"] == "hard-stop-active", decision
    check("source guard schema veto rejects forged authority and old state without recovery writes", source_schema_veto_and_old_state)
