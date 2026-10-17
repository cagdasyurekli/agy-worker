#!/usr/bin/env python3
"""Approve the exact synthetic launch used by existing provider-mechanism fixtures.

Authority rejection regressions invoke the runtime directly. This adapter only
constructs the current record for older mechanism tests' synthetic task/settings.
An explicitly supplied stale scoped content digest remains stale. Dedicated
whole-worktree stale/missing-approval cases opt out with AGY_TEST_SKIP_WHOLE_APPROVAL.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import Any


def bind_command(module: Any, command: dict[str, Any], *, bind_content: bool = True) -> dict[str, Any]:
    """Construct a complete synthetic authority for controller mechanism tests."""
    launch = module.LAUNCH_AUTHORITY
    argv = command["argv"]

    def option(name: str) -> str | None:
        return argv[argv.index(name) + 1] if name in argv else None

    task, _text = launch.normalize_task((option("--print") or "fixture task").encode())
    mode = option("--mode") or ("plan" if command["workflow"] in {"legacy", "explore"} else "accept-edits")
    if "--mode" not in argv:
        argv[1:1] = ["--mode", mode]
    if "--print-timeout" not in argv:
        argv[1:1] = ["--print-timeout", f'{command["max_seconds"]}s']
    if "--output-format" not in argv:
        argv[1:1] = ["--output-format", "stream-json"]
    block = ""
    manifest_sha = None
    if command["self_verification_manifest_path"]:
        raw = Path(command["self_verification_manifest_path"]).read_bytes()
        manifest = module.SELF_VERIFICATION.parse_manifest(raw)
        manifest_sha = module.digest(raw)
        block = launch.verification_request_block(
            [check.identifier for check in manifest.checks if check.required],
            [check.identifier for check in manifest.checks if not check.required])
    prompt = launch.full_prompt(task, mode=mode, provider_isolation=command["provider_isolation"],
                                verification_block=block)
    if command["stage_file"]:
        path = Path(command["stage_file"])
        path.write_bytes(prompt)
        argv[argv.index("--print") + 1] = launch.STAGED_INSTRUCTION.format(stage_file=str(path))
    else:
        argv[argv.index("--print") + 1] = prompt.decode()
    root = Path(command["workdir"])
    readable = module._scan_readable_worktree(str(root)) if bind_content else []
    scoped = command["provider_scope_path"] is not None
    policy_sha = selected_sha = whole_sha = None
    if scoped and bind_content:
        scope = module._parse_provider_scope(Path(command["provider_scope_path"]).read_bytes())
        policy_sha = module._canonical_digest(scope)
        selected_sha = module._selected_content_digest(module._build_selected_content_manifest(str(root), scope))
    elif not scoped and bind_content:
        whole_sha = module.WORKTREE.whole_worktree_content_manifest(str(root))["manifest_sha256"]
        command["whole_worktree_content_sha256"] = whole_sha
    add_dirs = [Path(argv[index + 1]).resolve().relative_to(root.resolve()).as_posix()
                for index, item in enumerate(argv) if item == "--add-dir"
                and (not command["stage_dir"] or Path(argv[index + 1]).resolve() != Path(command["stage_dir"]).resolve())]
    authority = launch.build_authority(
        content={"manifest_sha256": module._manifest_digest(readable), "policy_sha256": policy_sha,
                 "selected_content_sha256": selected_sha, "content_manifest_sha256": whole_sha,
                 "provider_isolation": command["provider_isolation"],
                 "native_grant_profile": command["native_grant_profile"]},
        task=task, prompt=prompt, workflow=command["workflow"], mode=mode,
        max_cycles=command["max_cycles"], idle_seconds=command["idle_seconds"],
        hard_seconds=command["hard_seconds"], max_seconds=command["max_seconds"],
        notice_seconds=command["notice_seconds"], model=option("--model"), effort=option("--effort"),
        allow_scoped_repair=command["allow_scoped_repair"], self_verification_manifest_sha256=manifest_sha,
        provider_env_names=command["provider_env"],
        allow_slash_commands=mode == "accept-edits" and "--disable-slash-commands" not in argv,
        add_dirs=sorted(set(add_dirs)), provider_schema_sha256=(module.digest(Path(option("--json-schema")).read_bytes())
                                                              if option("--json-schema") else "0" * 64),
        base_commit=command["base_commit"], workdir=str(root.resolve()))
    command["launch_authority"] = authority
    command["launch_approval_sha256"] = launch.approval_sha256(authority)
    if scoped or bind_content:
        command["approved_transmission_sha256" if scoped else "approved_whole_worktree_sha256"] = command["launch_approval_sha256"]
    return command


def retain_prompt(job: Path, command: dict[str, Any]) -> None:
    """Retain the synthetic initial task/prompt without replacing tampered bytes."""
    if "launch_authority" not in command:
        return
    if (job / "task.txt").exists() and (job / "full-prompt.txt").exists():
        return
    argv = command["argv"]
    prompt = (Path(command["stage_file"]).read_bytes() if command["stage_file"]
              else argv[argv.index("--print") + 1].encode())
    task = prompt.split(b"TASK FOLLOWS:\n\n", 1)[1]
    for name, raw in (("task.txt", task), ("full-prompt.txt", prompt)):
        path = job / name
        if not path.exists():
            path.write_bytes(raw)
            path.chmod(0o600)


def foreground_signal_fixture(root: Path, temporary: Path) -> None:
    """Signal only after the fake provider's real descendant announces setup."""
    import importlib.util
    import selectors
    import time

    source = root / "skills/agy-worker/runtime/scripts/agy_dispatch.py"
    spec = importlib.util.spec_from_file_location("foreground_fixture_dispatch", source)
    assert spec is not None and spec.loader is not None
    dispatch = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = dispatch
    spec.loader.exec_module(dispatch)
    containment = dispatch.CONTAINMENT
    native = sys.platform == "darwin"
    # This is a fatal diagnostic guard, not a readiness/latency assertion:
    # two version/help passes, source proof, startup handshake, provider cap.
    diagnostic_seconds = 2 * (
        dispatch.MODEL_SELECTION.VERSION_TIMEOUT_SECONDS
        + dispatch.MODEL_SELECTION.HELP_TIMEOUT_SECONDS
    ) + dispatch.CANDIDATE_STATE.SOURCE_CHECKOUT_SECONDS + 5 + 4

    def bind_group(pid: int):
        if native:
            return containment.bind_new_process_group(pid)
        assert os.getpgid(pid) == os.getsid(pid) == pid
        return subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "pid=,ppid=,pgid=,sid=,uid=,lstart="],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        ).stdout.strip()

    def nonrunnable(pid: int) -> bool:
        observed = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "stat="],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )
        if observed.returncode == 0 and observed.stdout.strip():
            return observed.stdout.strip().startswith("Z")
        # A lookup/permission error is not evidence that a process disappeared.
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        raise AssertionError(f"process state unavailable: {pid}: {observed.stderr}")

    def quiet(pid: int) -> bool:
        if native:
            members = containment._process_group_members(pid)
        else:
            observed = subprocess.run(
                ["/bin/ps", "-A", "-o", "pid=,pgid="],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
            )
            members = tuple(int(line.split()[0]) for line in observed.stdout.splitlines()
                            if len(line.split()) == 2 and int(line.split()[1]) == pid)
        return all(nonrunnable(member) for member in members)

    def settle(pid: int) -> bool:
        deadline = time.monotonic() + dispatch.TERM_GRACE
        while not quiet(pid):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True

    for suffix, mode, expected in (
        ("", "heartbeat-forever", 143),
        ("-unready", "idle", dispatch.EXIT_BY_REASON["idle_timeout"]),
        ("-crash", "result", dispatch.EXIT_BY_REASON["agy_failed_unclassified"]),
    ):
        name = "foreground-signal" + suffix
        event_path = temporary / (name + ".ready-fifo")
        os.mkfifo(event_path, 0o600)
        event_fd = os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
        side_effect = temporary / (name + ".side-effect")
        pid_file = temporary / (name + ".child-pid")
        group_file = temporary / (name + ".provider-pgid")
        release_file = temporary / (name + ".binding-release")
        provider_environment = {
            "FAKE_MODEL_FILE": str(temporary / (name + ".model")),
            "FAKE_PROMPT_FILE": str(temporary / (name + ".prompt")),
            "FAKE_DIRS_FILE": str(temporary / (name + ".dirs")),
            "FAKE_ARGV_FILE": str(temporary / (name + ".argv")),
            "FAKE_STAGE_RESULT_FILE": str(temporary / (name + ".stage-result")),
            "FAKE_CALLS_FILE": str(temporary / (name + ".calls")),
            "FAKE_WORKER_CALLS_FILE": str(temporary / (name + ".worker-calls")),
            "FAKE_VERSION_MODE": "ready", "FAKE_DISPATCH_MODE": mode,
            "FAKE_EXIT_CODE": "23" if suffix == "-crash" else "0",
            "FAKE_SIDE_EFFECT_FILE": str(side_effect),
            "FAKE_PROBE_READY_FILE": str(event_path),
            "FAKE_PROBE_PGID_FILE": str(group_file),
            "FAKE_PROBE_RELEASE_FILE": str(release_file),
            "FAKE_CHILD_PID_FILE": str(pid_file),
        }
        environment = dict(os.environ, **provider_environment)
        environment.update(
            PATH=str(temporary / "bin") + os.pathsep + os.environ["PATH"],
            AGY_WORKER_LOG_DIR=str(temporary / "logs"),
            AGY_WORKER_JOB_ID=name, AGY_WORKER_MODE="accept-edits",
        )
        arguments = [sys.executable, "-I", "-S", "-B", str(root / "tests/launch_fixture.py"),
                     str(root / "agy-worker.sh"), "--workdir", str(temporary / "repo"),
                     "--idle-timeout", "2s", "--hard-timeout", "4s", "--max-runtime", "4s"]
        for variable in provider_environment:
            arguments += ["--provider-env", variable]
        observation: dict[str, Any] = {"case": name, "ready": False, "signal_test_term_sent": False}
        groups = {}
        wrapper = None
        state_path = temporary / "logs" / name / dispatch.STATE_NAME
        try:
            with (temporary / (name + ".out")).open("wb") as output, \
                    (temporary / (name + ".err")).open("wb") as errors:
                wrapper = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=output,
                                           stderr=errors, env=environment, start_new_session=True)
                groups[wrapper.pid] = bind_group(wrapper.pid)
                assert wrapper.stdin is not None
                wrapper.stdin.write(b"foreground signal ownership\n")
                wrapper.stdin.close()
                deadline = time.monotonic() + diagnostic_seconds
                payload = bytearray()
                with selectors.DefaultSelector() as selector:
                    selector.register(event_fd, selectors.EVENT_READ)
                    while wrapper.poll() is None and not observation["ready"]:
                        remaining = deadline - time.monotonic()
                        assert remaining > 0, "foreground setup event diagnostic timeout"
                        if selector.select(min(0.1, remaining)):
                            payload.extend(os.read(event_fd, 128))
                            assert len(payload) <= 128, "invalid descendant readiness event"
                        while b"\n" in payload:
                            line, _, payload = payload.partition(b"\n")
                            event, first, second = line.decode("ascii").split()
                            provider_pid = int(first)
                            assert int(group_file.read_text()) == provider_pid
                            if event == "started":
                                assert not release_file.exists()
                                controller_pid = int(second)
                                current, _, _ = dispatch.read_state_snapshot(state_path.parent)
                                assert current["controller_pid"] == controller_pid
                                provider = bind_group(provider_pid)
                                controller = bind_group(controller_pid)
                                if native:
                                    worker = containment.capture_process_identity(controller.parent_pid)
                                    assert provider.parent_pid == controller.pid
                                    assert worker.parent_pid == wrapper.pid
                                    assert worker.process_group == worker.session_id == wrapper.pid
                                    assert worker.uid == provider.uid == controller.uid == os.getuid()
                                    assert (controller.start_seconds, controller.start_microseconds) >= (
                                        groups[wrapper.pid].start_seconds, groups[wrapper.pid].start_microseconds)
                                    observation["provider_identity"] = vars(provider)
                                    observation["controller_identity"] = vars(controller)
                                    observation["worker_identity"] = vars(worker)
                                else:
                                    worker_pid = int(controller.split()[1])
                                    worker = subprocess.run(
                                        ["/bin/ps", "-p", str(worker_pid), "-o", "ppid="],
                                        stdout=subprocess.PIPE, text=True, check=True,
                                    )
                                    assert int(provider.split()[1]) == controller_pid
                                    assert int(worker.stdout) == wrapper.pid
                                    assert os.getpgid(worker_pid) == os.getsid(worker_pid) == wrapper.pid
                                groups.update({provider_pid: provider, controller_pid: controller})
                                observation["bound_before_release"] = True
                                release_file.touch()
                            else:
                                assert event == "ready" and mode == "heartbeat-forever"
                                assert observation.get("bound_before_release")
                                child_pid = int(second)
                                assert int(pid_file.read_text()) == child_pid
                                assert os.getpgid(child_pid) == os.getsid(child_pid) == provider_pid
                                assert not nonrunnable(provider_pid) and not nonrunnable(child_pid)
                                if native:
                                    descendant = containment.capture_process_identity(child_pid)
                                    assert descendant.parent_pid == provider_pid
                                    assert descendant.uid == provider.uid
                                    observation["descendant_identity"] = vars(descendant)
                                observation.update(ready=True, provider_pid=provider_pid, child_pid=child_pid)
                                wrapper.send_signal(signal.SIGTERM)
                                observation["signal_test_term_sent"] = True
                rc = wrapper.wait(timeout=diagnostic_seconds)
            observation["wrapper_exit"] = rc
            terminal, _, _ = dispatch.load_state(state_path.parent)
            observation["terminal"] = {key: terminal[key] for key in (
                "status", "reason", "exit_code", "progress_count", "elapsed_seconds",
            )}
            assert rc == expected, observation
            assert observation.get("bound_before_release"), observation
            if mode == "heartbeat-forever":
                assert observation["ready"] and observation["signal_test_term_sent"], observation
                assert (terminal["status"], terminal["reason"], terminal["exit_code"]) == (
                    "cancelled", "interrupted", 143,
                ), observation
                assert settle(provider_pid) and nonrunnable(child_pid), "live descendant after signal"
                observation["quiescent_before_cleanup"] = True
                assert not side_effect.exists(), "late descendant side effect"
            else:
                assert not observation["ready"] and not observation["signal_test_term_sent"], observation
                assert terminal["status"] == "failed" and terminal["exit_code"] == expected, observation
                assert terminal["reason"] == ("idle_timeout" if mode == "idle" else "agy_failed_unclassified")
            assert terminal["controller_pid"] is None and not terminal["candidate_recognized"]
        finally:
            cleanup_errors = []
            try:
                # Preserve leaked-group evidence before any rescue operation.
                observation["groups_before_cleanup"] = {pid: settle(pid) for pid in groups}
            except Exception as exc:
                cleanup_errors.append(repr(exc))
            for pid, identity in reversed(tuple(groups.items())):
                try:
                    for number in (signal.SIGTERM, signal.SIGKILL):
                        if quiet(pid):
                            break
                        if native:
                            containment.terminate_bound_process_group(identity, number)
                        else:
                            assert bind_group(pid) == identity
                            os.killpg(pid, number)
                        if settle(pid):
                            break
                    assert settle(pid), f"fixture left runnable group {pid}"
                except Exception as exc:
                    cleanup_errors.append(repr(exc))
            try:
                if wrapper is not None:
                    wrapper.wait(timeout=dispatch.TERM_GRACE + 1)
            except Exception as exc:
                cleanup_errors.append(repr(exc))
            finally:
                os.close(event_fd)
            observation["cleanup_errors"] = cleanup_errors
            (temporary / (name + ".observation.json")).write_text(json.dumps(observation) + "\n")
            print("foreground observation: " + json.dumps(observation), flush=True)
            assert not cleanup_errors, observation
            assert all(observation["groups_before_cleanup"].values()), observation



def main() -> int:
    worker, *arguments = sys.argv[1:]
    task = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    values = {"--workdir", "--worktree", "--provider-scope", "--provider-isolation",
              "--workflow", "--mode", "--max-cycles", "--model", "--effort",
              "--idle-timeout", "--hard-timeout", "--max-runtime", "--notice-interval",
              "--self-verification-manifest", "--provider-env", "--add-dir", "--base-commit"}
    switches = {"--allow-scoped-repair", "--allow-slash-commands"}
    preview_args = []
    remaining = iter(arguments)
    supplied = None
    supplied_flag = None
    for argument in remaining:
        if argument in values:
            value = next(remaining, "")
            if argument in {"--workdir", "--worktree", "--provider-scope", "--self-verification-manifest", "--add-dir"}:
                value = str(Path(value).resolve())
            preview_args += [argument, value]
        elif argument in switches:
            preview_args.append(argument)
        elif argument in {"--approve-transmission-sha", "--approve-whole-worktree"}:
            supplied_flag, supplied = argument, next(remaining, "")
    preview = subprocess.run([worker, "transmission-preview", *preview_args], input=task,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if preview.returncode and b"verification manifest" in preview.stderr:
        # An unsafe-manifest mechanism test needs a valid baseline record to
        # reach the raw manifest validator. It grants no verification authority.
        baseline = list(preview_args)
        index = baseline.index("--self-verification-manifest")
        del baseline[index:index + 2]
        preview = subprocess.run([worker, "transmission-preview", *baseline], input=task,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if preview.returncode:
        sys.stderr.buffer.write(preview.stderr)
        return run_worker([worker, *arguments], task)
    value = json.loads(preview.stdout)
    scoped = "--provider-scope" in arguments
    if scoped and supplied_flag is None:
        return run_worker([worker, *arguments], task)
    # Older scoped mechanism fixtures carry the content digest. Convert only
    # when it exactly matches the current synthetic content; preserve drift.
    if supplied_flag and ((not scoped and os.environ.get("AGY_TEST_SKIP_WHOLE_APPROVAL") == "1")
                          or (scoped and supplied != value["transmission_sha256"])):
        approved = supplied
    else:
        approved = value["launch_approval_sha256"]
    with tempfile.TemporaryDirectory(prefix="agy-launch-fixture-") as directory:
        record = Path(directory).resolve() / "preview.json"
        record.write_bytes(preview.stdout)
        record.chmod(0o600)
        clean = []
        remaining = iter(arguments)
        for argument in remaining:
            if argument in {"--approve-transmission-sha", "--approve-whole-worktree"}:
                next(remaining, None)
            else:
                clean.append(argument)
        # A missing-approval test retains its intentional boundary.
        if os.environ.get("AGY_TEST_SKIP_WHOLE_APPROVAL") == "1" and not scoped and supplied_flag is None:
            return run_worker([worker, *clean], task)
        approval_flag = "--approve-transmission-sha" if scoped else "--approve-whole-worktree"
        return run_worker([worker, *clean, approval_flag, approved,
                           "--approval-record", str(record)], task)


def run_worker(arguments: list[str], task: bytes) -> int:
    """Keep the synthetic adapter transparent to foreground signal tests."""
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE)
    signals = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)
    previous = {number: signal.getsignal(number) for number in signals}

    def forward(number: int, _frame: Any) -> None:
        process.send_signal(number)

    try:
        for number in signals:
            signal.signal(number, forward)
        process.communicate(task)
        return process.returncode if process.returncode >= 0 else 128 - process.returncode
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
