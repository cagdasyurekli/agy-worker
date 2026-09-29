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
    tier = None
    if command["selection_path"] is not None:
        selection = json.loads(Path(command["selection_path"]).read_bytes())
        if selection["selection_mode"] == "tier" and selection["selected_tier_source"] != "implicit-default":
            tier = selection["selected_tier"]
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
        notice_seconds=command["notice_seconds"], tier=tier, model=option("--model"), effort=option("--effort"),
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


def main() -> int:
    worker, *arguments = sys.argv[1:]
    task = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    values = {"--workdir", "--worktree", "--provider-scope", "--provider-isolation",
              "--workflow", "--mode", "--max-cycles", "--tier", "--model", "--effort",
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
