#!/usr/bin/env python3
"""Focused checks for driver-owned optional verification contracts."""
from __future__ import annotations

import copy
import contextlib
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import time
from pathlib import Path
import sys
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "skills/agy-worker/runtime/scripts/agy_dispatch_verification.py"
spec = importlib.util.spec_from_file_location("verification_under_test", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CollectionFixture:
    """Collection-only children do not fork; native containment is tested separately."""

    ROLE_SELF_VERIFY = "self-verify"
    NETWORK_DENY_ALL = "deny-all"

    def __init__(self):
        self.processes = {}
        self.real_popen = subprocess.Popen

    def popen(self, *args, **kwargs):
        process = self.real_popen(*args, **kwargs)
        self.processes[process.pid] = process
        return process

    @staticmethod
    def confirm_contained_launch(prepared):
        return SimpleNamespace(argv=prepared.target_argv, executable=sys.executable,
                               cwd=prepared.cwd, environment={"PATH": "/usr/bin:/bin"})

    def bind_new_process_group(self, pid):
        return self.processes[pid]

    @staticmethod
    def terminate_bound_process_group(process, number):
        # Popen reaps an exited child before signalling. Raw killpg can return
        # EPERM for an unreaped zombie on macOS; permission errors on live
        # children must still propagate through Popen.send_signal.
        process.send_signal(number)
        return ()


class VerificationContracts(unittest.TestCase):
    def manifest(self):
        return {"schema_version": 1, "kind": "agy-worker-self-verification", "max_seconds": 60,
                "checks": [
                    {"id": name, "argv": ["/usr/bin/python3", "-m", "unittest", name],
                     "required": required, "timeout_seconds": 20, "output_limit_bytes": 4096}
                    for name, required in (("optional_a", False), ("required_b", True), ("optional_c", False))]}

    def parse(self, value):
        return module.parse_manifest(json.dumps(value).encode())

    def test_worker_cannot_skip_required_checks_or_reorder_optional_checks(self):
        manifest = self.parse(self.manifest())
        self.assertEqual([c.identifier for c in module.select_checks(manifest, [])], ["required_b"])
        self.assertEqual([c.identifier for c in module.select_checks(manifest, ["optional_c", "optional_a"])],
                         ["required_b", "optional_a", "optional_c"])

    def test_untrusted_ids_never_become_commands(self):
        manifest = self.parse(self.manifest())
        for request in (["unknown"], ["required_b"], ["optional_a", "optional_a"], ["optional_a\n"],
                        ["../secret"], ["$(touch bad)"], [False], "optional_a", ["A"] * 33):
            with self.subTest(request=request), self.assertRaises(module.VerificationError):
                module.select_checks(manifest, request)

    def test_frozen_manifest_rejects_ambiguous_authority(self):
        for field, value in (("required", 1), ("argv", "echo unsafe"),
                             ("argv", ["python3"]), ("argv", ["/bin/sh", "-c", "true"]),
                             ("argv", ["/usr/bin/python3", "bad\0arg"]),
                             ("timeout_seconds", True), ("timeout_seconds", float("inf")),
                             ("output_limit_bytes", 65537)):
            data = self.manifest()
            data["checks"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(module.VerificationError):
                self.parse(data)
        data = self.manifest()
        data["checks"].append(copy.deepcopy(data["checks"][0]))
        with self.assertRaises(module.VerificationError):
            self.parse(data)
        with self.assertRaises(module.VerificationError):
            module.parse_manifest(b'{"checks":[],"checks":[]}')

    def test_explicit_shell_script_preserves_arguments_without_command_mode(self):
        data = self.manifest()
        data["checks"][0]["argv"] = ["/bin/bash", "tests/check.sh", "-c", "literal argument"]
        self.assertEqual(self.parse(data).checks[0].argv,
                         ("/bin/bash", "tests/check.sh", "-c", "literal argument"))
        for argv in (["/bin/sh"], ["/bin/sh", "-c", "echo wrong"],
                     ["/bin/bash", "--", "tests/check.sh"], ["/bin/bash", "-s"],
                     ["/bin/sh", "../outside.sh"], ["/bin/sh", "/outside.sh"],
                     ["/bin/bash", "./tests/check.sh"], ["/usr/bin/env", "bash", "tests/check.sh"]):
            data["checks"][0]["argv"] = argv
            with self.subTest(argv=argv), self.assertRaises(module.VerificationError):
                self.parse(data)

    def test_script_binding_rejects_aliases_and_observes_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            script = root / "check.sh"
            script.write_text("exit 0\n")
            before = module._bind_script(root, "check.sh")
            script.write_text("exit 1\n")
            self.assertNotEqual(module._bind_script(root, "check.sh"), before)
            alias = root / "alias.sh"
            alias.symlink_to(script)
            with self.assertRaises(module.VerificationError):
                module._bind_script(root, "alias.sh")
            os.link(script, root / "hardlink.sh")
            with self.assertRaises(module.VerificationError):
                module._bind_script(root, "check.sh")
            with self.assertRaises(module.VerificationError):
                module._bind_script(root, "../outside.sh")

    def test_runtime_preflight_diagnoses_unqualified_dependencies(self):
        module.validate_runtime(self.parse(self.manifest()), Path("/private/tmp/candidate"))
        data = self.manifest()
        data["checks"][0]["argv"] = ["/opt/unqualified-toolchain/bin/python", "check.py"]
        with self.assertRaisesRegex(module.VerificationError, "qualified system toolchain"):
            module.validate_runtime(self.parse(data), Path("/private/tmp/candidate"))

    def test_verification_spends_existing_total_budget(self):
        self.assertEqual(module.remaining_seconds(60, 40, 15), 5)
        self.assertEqual(module.remaining_seconds(60, 40, 21), 0)
        for value in (True, -1, float("nan"), float("inf")):
            with self.assertRaises(module.VerificationError):
                module.remaining_seconds(60, value, 0)

    def test_batch_rejects_unknown_requests_before_preparation(self):
        native = mock.Mock()
        with self.assertRaises(module.VerificationError):
            module.run_checks(self.parse(self.manifest()), ["unknown"], containment=native,
                              job_directory=Path("/unused"), copy_directory=Path("/unused/copy"),
                              log_directory=Path("/unused/logs"), remaining=60)
        native.prepare_contained_launch.assert_not_called()

    def test_batch_charges_preparation_and_preserves_not_run_checks(self):
        manifest = self.parse(self.manifest())
        clock = [0.0]
        native = mock.Mock(ROLE_SELF_VERIFY="self-verify", NETWORK_DENY_ALL="deny-all")
        def prepare(**kwargs):
            clock[0] += 1
            self.assertEqual(kwargs["child_environment"], {})
            self.assertFalse(kwargs["allow_keychain"])
            return object()
        native.prepare_contained_launch.side_effect = prepare
        def collect(check, _prepared, **kwargs):
            available = kwargs["remaining"]
            if available == 0:
                return module.CheckResult(check.identifier, "not-run", None, 0, 0, 0)
            self.assertEqual(available, 4)
            clock[0] += 3
            return module.CheckResult(check.identifier, "failed", 1, 3, 0, 0)
        with mock.patch.object(module.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(module, "run_check", side_effect=collect):
            results = module.run_checks(manifest, ["optional_c", "optional_a"], containment=native,
                                        job_directory=Path("/unused"), copy_directory=Path("/unused/copy"),
                                        log_directory=Path("/unused/logs"), remaining=5)
        self.assertEqual([(r.identifier, r.outcome) for r in results],
                         [("required_b", "failed"), ("optional_a", "not-run"), ("optional_c", "not-run")])
        self.assertEqual(native.prepare_contained_launch.call_count, 2)

    def test_batch_stops_on_execution_uncertainty_but_not_test_failure(self):
        native = mock.Mock(ROLE_SELF_VERIFY="self-verify", NETWORK_DENY_ALL="deny-all")
        seen = []
        def collect(check, _prepared, **_kwargs):
            seen.append(check.identifier)
            return module.CheckResult(check.identifier, "blocked", 71, 0, 0, 0)
        with mock.patch.object(module, "run_check", side_effect=collect):
            results = module.run_checks(self.parse(self.manifest()), ["optional_a"], containment=native,
                                        job_directory=Path("/unused"), copy_directory=Path("/unused/copy"),
                                        log_directory=Path("/unused/logs"), remaining=60)
        self.assertEqual(seen, ["required_b"])
        self.assertEqual([r.outcome for r in results], ["blocked", "not-run"])

    def test_scoped_copy_omits_unapproved_files_and_rejects_candidate_drift(self):
        copy_path = source.with_name("agy_dispatch_worktree.py")
        copy_spec = importlib.util.spec_from_file_location("verification_copy_engine", copy_path)
        engine = importlib.util.module_from_spec(copy_spec)
        sys.modules[copy_spec.name] = engine
        copy_spec.loader.exec_module(engine)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_uid,
                                 info.st_gid, stat.S_IMODE(info.st_mode))
        api = SimpleNamespace(
            MAX_COMMAND_BYTES=65536, digest=lambda raw: hashlib.sha256(raw).hexdigest(),
            _identity=identity, _read_provider_scope_file=engine._read_provider_scope_file,
            _parse_provider_scope=engine._parse_provider_scope,
            _build_selected_content_manifest=engine._build_selected_content_manifest,
            _selected_content_digest=engine._selected_content_digest,
            _materialize_stage=engine._materialize_stage,
            _bound_current_candidate=mock.Mock(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            worktree = root / "worktree"
            worktree.mkdir(mode=0o700)
            (worktree / "candidate.py").write_text("answer = 42\n")
            (worktree / "check.py").write_text("from candidate import answer\nassert answer == 42\n")
            (worktree / "private-omitted.env").write_text("fixture-must-not-be-copied\n")
            scope_path = root / "scope.json"
            raw = json.dumps({"schema_version": 1, "kind": "agy-worker-provider-scope",
                              "read": [{"path": name, "kind": "file"}
                                       for name in ("candidate.py", "check.py")],
                              "write": [{"path": "candidate.py", "kind": "file"}]}).encode()
            scope_path.write_bytes(raw)
            scope_path.chmod(0o600)
            selected = engine._build_selected_content_manifest(worktree, engine._parse_provider_scope(raw))
            command = {"workdir": str(worktree), "provider_scope_path": str(scope_path),
                       "provider_scope_sha256": api.digest(raw),
                       "provider_scope_identity": list(identity(scope_path.stat()))}
            state = {"selected_content_sha256": engine._selected_content_digest(selected),
                     "selected_file_count": 2, "selected_tree_count": 0}
            destination = root / "copy"
            module._copy_candidate(api, root, command, state, destination)
            self.assertEqual(sorted(p.name for p in destination.iterdir()), ["candidate.py", "check.py"])
            self.assertNotEqual((destination / "candidate.py").stat().st_ino,
                                (worktree / "candidate.py").stat().st_ino)
            (destination / "candidate.py").write_text("copy-only\n")
            self.assertEqual((worktree / "candidate.py").read_text(), "answer = 42\n")
            (worktree / "candidate.py").write_text("externally changed\n")
            with self.assertRaises(module.VerificationError):
                module._copy_candidate(api, root, command, state, root / "drift-copy")
            self.assertFalse((root / "drift-copy").exists())

    def test_action_rejects_real_candidate_executable_before_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate = root / "candidate"
            candidate.mkdir()
            script = candidate / "check.py"
            script.write_text("raise SystemExit(0)\n")
            script.chmod(0o700)
            state = {"schema_version": 16, "allow_self_verification": True,
                     "phase": "awaiting-verification", "attempt": 1,
                     "self_verification_run": 0}
            command = {"schema_version": 14, "allow_self_verification": True,
                       "workflow": "task", "workdir": str(candidate)}
            manifest = module.Manifest((module.Check("check", (str(script),), True, 5, 4096),), 5)
            api = SimpleNamespace(
                CURRENT_STATE_SCHEMA=16, CURRENT_COMMAND_SCHEMA=14,
                DispatchError=ValueError,
                lifecycle_lock=lambda *_args, **_kwargs: contextlib.nullcontext(),
                state_lock=lambda *_args: contextlib.nullcontext(),
                load_state=lambda *_args: (state, b"bound-state", "a" * 64),
                _bound_current_candidate=lambda *_args: (command, b"{}"),
                _job_is_inside_worktree=lambda *_args: False,
                _bound_self_verification_manifest=lambda *_args: manifest,
                _transition_locked=mock.Mock(),
            )
            with self.assertRaisesRegex(ValueError, "outside the original candidate"):
                module.command_self_verify(api, root, "a" * 64, "json", containment=mock.Mock())
            api._transition_locked.assert_not_called()
            command.update({"schema_version": 10, "provider_isolation": "session"})
            with self.assertRaisesRegex(ValueError, "was not enabled"):
                module.command_self_verify(api, root, "a" * 64, "json", containment=mock.Mock())
            api._transition_locked.assert_not_called()
            command["schema_version"] = 14
            command.pop("provider_isolation")
            with self.assertRaisesRegex(ValueError, "state changed"):
                module.command_self_verify(api, root, "b" * 64, "json", containment=mock.Mock())
            state["self_verification_run"] = 1
            with self.assertRaisesRegex(ValueError, "unavailable"):
                module.command_self_verify(api, root, "a" * 64, "json", containment=mock.Mock())
            api._transition_locked.assert_not_called()

    def test_feedback_cannot_copy_logs_or_claim_review(self):
        value = module.advisory_feedback("a" * 64, [("required_b", "failed")])
        self.assertFalse(value["diff_review_complete"])
        self.assertEqual(value["failed_checks"], ["required_b"])
        self.assertEqual(value["coverage"], "partial")
        for outcome in ("timeout", "secret raw output", "containment-failed"):
            with self.assertRaises(module.VerificationError):
                module.advisory_feedback("a" * 64, [("required_b", outcome)])

    def test_process_collection_bounds_output_and_time(self):
        fixture = CollectionFixture()
        for program, expected in (("print('ok')", "passed"),
                                  ("raise SystemExit(7)", "failed"),
                                  ("raise SystemExit(71)", "blocked"),
                                  ("print('x' * 10000)", "output-limit"),
                                  ("import time; time.sleep(5)", "timeout")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                logs = Path(directory).resolve()
                logs.chmod(0o700)
                argv = (sys.executable, "-I", "-S", "-B", "-c", program)
                check = module.Check("check", argv, True, 0.2, 128)
                prepared = SimpleNamespace(role="self-verify", network_policy="deny-all",
                                           allow_keychain=False, target_argv=argv, cwd=str(logs))
                with mock.patch.object(module.subprocess, "Popen", side_effect=fixture.popen):
                    result = module.run_check(check, prepared, containment=fixture,
                                              log_directory=logs, remaining=1)
                self.assertEqual(result.outcome, expected)
                self.assertLess(result.elapsed_seconds, 3)
                for stream in ("stdout", "stderr"):
                    path = logs / ("check." + stream)
                    self.assertLessEqual(path.stat().st_size, 128)
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_collection_cleanup_reaps_exited_child_and_preserves_live_errors(self):
        fixture = CollectionFixture()
        # Observe exit without reaping, reproducing the macOS zombie-only
        # group that makes raw killpg fail with EPERM.
        process = fixture.popen([sys.executable, "-I", "-S", "-c", "pass"],
                                stdout=subprocess.PIPE, start_new_session=True)
        try:
            self.assertEqual(process.stdout.read(), b"")
            deadline = time.monotonic() + 2
            while True:
                status = subprocess.check_output(
                    ["/bin/ps", "-o", "stat=", "-p", str(process.pid)],
                    text=True, timeout=1).strip()
                if status.startswith("Z"):
                    break
                self.assertLess(time.monotonic(), deadline, "child did not reach zombie state")
                time.sleep(0.005)
            self.assertIsNone(process.returncode)
            with mock.patch.object(os, "killpg", side_effect=PermissionError("zombie group")), \
                    mock.patch.object(os, "kill", side_effect=PermissionError("unexpected signal")):
                fixture.terminate_bound_process_group(
                    fixture.bind_new_process_group(process.pid), signal.SIGKILL)
            self.assertEqual(process.returncode, 0)
        finally:
            process.stdout.close()
            process.wait(timeout=2)
        live = fixture.popen(
            [sys.executable, "-I", "-S", "-u", "-c",
             "import time; print('ready'); time.sleep(30)"],
            stdout=subprocess.PIPE, start_new_session=True)
        try:
            self.assertEqual(live.stdout.readline(), b"ready\n")
            with mock.patch.object(os, "kill", side_effect=PermissionError("live child denied")):
                with self.assertRaisesRegex(PermissionError, "live child denied"):
                    fixture.terminate_bound_process_group(live, signal.SIGKILL)
            self.assertIsNone(live.poll())
        finally:
            live.kill()
            live.wait(timeout=2)
            live.stdout.close()

    def test_cleanup_defers_signals_and_closes_every_owned_handle(self):
        for checkpoint in ("terminate", "wait", "fsync"):
            for prior_failure in (False, True, "signal"):
                with self.subTest(checkpoint=checkpoint, prior_failure=prior_failure):
                    self.assert_cleanup_signals(checkpoint, prior_failure)

    def assert_cleanup_signals(self, checkpoint, prior_failure):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary).resolve()
            logs.chmod(0o700)
            check = module.Check("signal", ("/bin/sleep", "30"), True, 0.03, 128)
            prepared = SimpleNamespace(role="self", network_policy="deny", allow_keychain=False,
                                       target_argv=check.argv)
            processes, descriptors, received, group_calls = [], [], [], []
            fired = False
            real_popen, real_open, real_fsync = subprocess.Popen, os.open, os.fsync

            def interrupt(number, _frame):
                received.append(number)
                if len(received) == 1 or number == signal.SIGALRM:
                    raise module.VerificationError("interrupted " + str(number))

            def inject(where):
                nonlocal fired
                if where == checkpoint and not fired:
                    fired = True
                    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
                        os.kill(os.getpid(), number)

            def popen(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                processes.append(process)
                real_wait = process.wait

                def wait(*args, **kwargs):
                    inject("wait")
                    return real_wait(*args, **kwargs)

                process.wait = wait
                return process

            def opened(*args, **kwargs):
                descriptor = real_open(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor

            def fsync(descriptor):
                inject("fsync")
                return real_fsync(descriptor)

            def terminate(pid, number):
                group_calls.append(pid)
                inject("terminate")
                try:
                    os.killpg(pid, number)
                except ProcessLookupError:
                    pass
                return ()

            def bind(pid):
                if prior_failure == "signal":
                    os.kill(os.getpid(), signal.SIGTERM)
                if prior_failure:
                    raise module.VerificationError("first failure")
                return pid

            native = SimpleNamespace(
                ROLE_SELF_VERIFY="self", NETWORK_DENY_ALL="deny",
                confirm_contained_launch=lambda _prepared: SimpleNamespace(
                    argv=check.argv, executable="/bin/sleep", cwd=str(logs), environment={}),
                bind_new_process_group=bind, terminate_bound_process_group=terminate)
            old = {number: signal.signal(number, interrupt) for number in (
                signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGALRM)}
            started = time.monotonic()
            try:
                with mock.patch.object(module.subprocess, "Popen", side_effect=popen), \
                        mock.patch.object(module.os, "open", side_effect=opened), \
                        mock.patch.object(module.os, "fsync", side_effect=fsync):
                    expected = ("interrupted 15" if prior_failure == "signal" else
                                "first failure" if prior_failure else "interrupted")
                    with self.assertRaisesRegex(module.VerificationError, expected):
                        module.run_check(check, prepared, containment=native,
                                         log_directory=logs, remaining=0.03)
                self.assertLess(time.monotonic() - started, 3)
                if not prior_failure or checkpoint != "terminate":
                    self.assertTrue(fired)
                    self.assertTrue(received)
                for process in processes:
                    self.assertIsNotNone(process.poll())
                    self.assertTrue(process.stdout.closed and process.stderr.closed)
                for descriptor in descriptors:
                    with self.assertRaises(OSError):
                        os.fstat(descriptor)
            finally:
                for number, handler in old.items():
                    signal.signal(number, handler)
                for process in processes:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    process.stdout.close()
                    process.stderr.close()
                for descriptor in descriptors:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
            if prior_failure:
                self.assertFalse(group_calls)
                self.assertFalse(checkpoint == "terminate" and fired)

    def test_cleanup_signal_does_not_leave_a_descendant(self):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary).resolve()
            logs.chmod(0o700)
            program = ("import subprocess,time; "
                       "p=subprocess.Popen(['/bin/sleep','30']); "
                       "print(p.pid,flush=True); time.sleep(30)")
            argv = (sys.executable, "-I", "-S", "-B", "-c", program)
            check = module.Check("descendant", argv, True, 0.3, 128)
            prepared = SimpleNamespace(role="self", network_policy="deny", allow_keychain=False,
                                       target_argv=argv)
            fired = False

            def terminate(pid, number):
                nonlocal fired
                if not fired:
                    fired = True
                    os.kill(os.getpid(), signal.SIGTERM)
                try:
                    os.killpg(pid, number)
                except ProcessLookupError:
                    pass
                return ()

            native = SimpleNamespace(
                ROLE_SELF_VERIFY="self", NETWORK_DENY_ALL="deny",
                confirm_contained_launch=lambda _prepared: SimpleNamespace(
                    argv=argv, executable=sys.executable, cwd=str(logs), environment={}),
                bind_new_process_group=lambda pid: pid, terminate_bound_process_group=terminate)

            def interrupt(_number, _frame):
                raise module.VerificationError("interrupted")

            processes = []
            real_popen = subprocess.Popen

            def popen(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                processes.append(process)
                return process

            old = signal.signal(signal.SIGTERM, interrupt)
            try:
                with mock.patch.object(module.subprocess, "Popen", side_effect=popen), \
                        self.assertRaisesRegex(module.VerificationError, "interrupted"):
                    module.run_check(check, prepared, containment=native,
                                     log_directory=logs, remaining=0.3)
                descendant = int((logs / "descendant.stdout").read_text().strip())
                deadline = time.monotonic() + 2
                while True:
                    try:
                        os.kill(descendant, 0)
                    except ProcessLookupError:
                        break
                    self.assertLess(time.monotonic(), deadline, "descendant remained alive")
                    time.sleep(0.02)
                self.assertIsNotNone(processes[0].poll())
                self.assertTrue(processes[0].stdout.closed and processes[0].stderr.closed)
            finally:
                signal.signal(signal.SIGTERM, old)
                for process in processes:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    process.stdout.close()
                    process.stderr.close()

    def test_cleanup_failure_still_closes_other_handles(self):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary).resolve()
            logs.chmod(0o700)
            check = module.Check("close", ("/usr/bin/true",), True, 1, 128)
            prepared = SimpleNamespace(role="self", network_policy="deny", allow_keychain=False,
                                       target_argv=check.argv)
            native = SimpleNamespace(
                ROLE_SELF_VERIFY="self", NETWORK_DENY_ALL="deny",
                confirm_contained_launch=lambda _prepared: SimpleNamespace(
                    argv=check.argv, executable="/usr/bin/true", cwd=str(logs), environment={}),
                bind_new_process_group=lambda pid: pid,
                terminate_bound_process_group=lambda *_args: ())
            descriptors = []
            real_open = os.open

            def opened(*args, **kwargs):
                descriptor = real_open(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor

            with mock.patch.object(module.os, "open", side_effect=opened), \
                    mock.patch.object(module.os, "fsync", side_effect=OSError("fsync failure")):
                with self.assertRaisesRegex(OSError, "fsync failure"):
                    module.run_check(check, prepared, containment=native,
                                     log_directory=logs, remaining=1)
            for descriptor in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)

    @unittest.skipUnless(sys.platform == "darwin", "native containment requires macOS")
    def test_native_structured_shell_script_runs_inside_copy(self):
        native_spec = importlib.util.spec_from_file_location(
            "native_shell_verification", source.with_name("agy_dispatch_containment.py"))
        native = importlib.util.module_from_spec(native_spec)
        sys.modules[native_spec.name] = native
        native_spec.loader.exec_module(native)
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary).resolve()
            job.chmod(0o700)
            stage = job / "copy"
            stage.mkdir(mode=0o700)
            logs = job / "logs"
            logs.mkdir(mode=0o700)
            (stage / "check.sh").write_text('test "$1" = "-c" || exit 7\nprintf shell-ok\n')
            manifest = module.Manifest((module.Check("shell", ("/bin/sh", "check.sh", "-c"),
                                                     True, 5, 4096),), 5)
            result = module.run_checks(manifest, [], containment=native, job_directory=job,
                                       copy_directory=stage, log_directory=logs, remaining=5)
            self.assertEqual(result[0].outcome, "passed")
            self.assertEqual((logs / "shell.stdout").read_text(), "shell-ok")

    @unittest.skipUnless(sys.platform == "darwin", "native containment requires macOS")
    def test_native_check_cannot_change_candidate_or_read_private_sibling(self):
        native_path = source.with_name("agy_dispatch_containment.py")
        native_spec = importlib.util.spec_from_file_location("native_verification_fixture", native_path)
        native = importlib.util.module_from_spec(native_spec)
        sys.modules[native_spec.name] = native
        native_spec.loader.exec_module(native)
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory).resolve()
            job.chmod(0o700)
            stage = job / "copy"
            stage.mkdir(mode=0o700)
            logs = job / "logs"
            logs.mkdir(mode=0o700)
            sentinel = job / "candidate-private.txt"
            sentinel.write_text("unchanged")
            program = (
                "from pathlib import Path\n"
                "import os\n"
                "assert 'SECRET_SHOULD_NOT_PASS' not in os.environ\n"
                "p=Path(" + repr(str(sentinel)) + ")\n"
                "for action in (lambda:p.read_text(),lambda:p.write_text('bad')):\n"
                " try: action()\n"
                " except PermissionError: pass\n"
                " else: raise SystemExit(8)\n"
                "Path('generated.txt').write_text('copy-only')\n"
                "print('safe-check')\n"
            )
            qualified_root = Path("/Library/Developer/CommandLineTools")
            qualified_python = Path(os.path.realpath(qualified_root / "usr/bin/python3"))
            self.assertTrue(qualified_python.is_relative_to(qualified_root))
            argv = (str(qualified_python), "-I", "-S", "-B", "-c", program)
            check = module.Check("native", argv, True, 5, 4096)
            prepared = native.prepare_contained_launch(
                role=native.ROLE_SELF_VERIFY, network_policy=native.NETWORK_DENY_ALL,
                job_dir=job, attempt=1, stage_dir=stage,
                target_executable=argv[0], target_argv=argv,
                child_environment={"SECRET_SHOULD_NOT_PASS": "fixture-secret"},
            )
            result = module.run_check(check, prepared, containment=native,
                                      log_directory=logs, remaining=5)
            stderr = (logs / "native.stderr").read_text(encoding="utf-8", errors="replace")
            stderr = stderr.replace(str(job), "<test-root>")[:check.output_limit_bytes]
            self.assertEqual(
                result.outcome,
                "passed",
                f"outcome={result.outcome} exit={result.exit_code} "
                f"stdout_bytes={result.stdout_bytes} stderr_bytes={result.stderr_bytes} "
                f"stderr={stderr!r}",
            )
            self.assertEqual(sentinel.read_text(), "unchanged")
            self.assertEqual((stage / "generated.txt").read_text(), "copy-only")
            self.assertEqual((logs / "native.stdout").read_text(), "safe-check\n")


if __name__ == "__main__":
    unittest.main()
