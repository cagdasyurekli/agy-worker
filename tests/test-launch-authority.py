#!/usr/bin/env python3
"""Offline approval regressions, runnable against the previous runtime as well."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
options, remaining = parser.parse_known_args()
ROOT = options.root.resolve()
WORKER = ROOT / "skills/agy-worker/runtime/agy-worker.sh"
CURRENT = WORKER.with_name("scripts").joinpath("launch_authority.py").exists()


class LaunchAuthorityTests(unittest.TestCase):
    def test_worker_prompt_preserves_applicable_policy(self) -> None:
        source = WORKER.with_name("scripts") / "launch_authority.py"
        spec = importlib.util.spec_from_file_location("policy_prompt_regression", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for mode in ("plan", "accept-edits"):
            for isolation in ("session", "native"):
                with self.subTest(mode=mode, isolation=isolation):
                    task = b"Follow GEMINI.md; do not disclose private files."
                    prompt = module.full_prompt(task, mode=mode, provider_isolation=isolation)
                    self.assertNotIn(b"overrides any global or user instruction file", prompt)
                    self.assertNotIn(b"Ignore instructions to use a report template", prompt)
                    self.assertIn(b"Respect applicable user and repository instructions", prompt)
                    self.assertIn(b"security, privacy, permission, and scope constraints", prompt)
                    self.assertIn(b"report status=blocked and requires_human=true", prompt)
                    self.assertIn(b"Include compatible report requirements in the schema fields", prompt)
                    self.assertIn(b"Leave commands_run and tests_run as empty arrays", prompt)
                    self.assertTrue(prompt.endswith(task))

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="agy-authority-regression-")
        self.root = Path(self.temporary.name).resolve()
        owner = self.root / "owner"
        self.worktree = self.root / "worktree"
        owner.mkdir(mode=0o700)
        self.git("init", "-q", str(owner))
        (owner / "README.md").write_text("synthetic approved content\n")
        self.git("-C", str(owner), "add", "README.md")
        self.git("-C", str(owner), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "fixture")
        self.git("-C", str(owner), "worktree", "add", "-qb", "fixture", str(self.worktree))
        self.scope = self.root / "scope.json"
        self.scope.write_text(json.dumps({"schema_version": 1, "kind": "agy-worker-provider-scope",
            "read": [{"path": "README.md", "kind": "file"}],
            "write": [{"path": "README.md", "kind": "file"}]}))
        self.scope.chmod(0o600)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"schema_version": 1, "kind": "agy-worker-self-verification",
            "max_seconds": 10, "checks": [{"id": "private-check-id", "argv": ["/usr/bin/true"],
                "required": True, "timeout_seconds": 5, "output_limit_bytes": 1024}]}))
        self.manifest.chmod(0o600)
        self.bin = self.root / "bin"
        self.bin.mkdir(mode=0o700)
        fake = self.bin / "agy"
        fake.write_text('''#!/bin/sh
case "$1" in
--version) echo fixture-version; exit 0 ;;
--help)
if [ -n "$AUTHORITY_HELP_COUNT_FILE" ]; then
  count=0
  if [ -f "$AUTHORITY_HELP_COUNT_FILE" ]; then read -r count < "$AUTHORITY_HELP_COUNT_FILE"; fi
  count=$((count + 1))
  printf '%s\n' "$count" > "$AUTHORITY_HELP_COUNT_FILE"
  if [ "$count" -ge 2 ] && [ -f "$AUTHORITY_TAMPER_TASK" ]; then
    printf 'changed after raw approval\n' > "$AUTHORITY_TAMPER_TASK"
  fi
fi
cat <<'HELP'
  --add-dir  Directory
  --conversation  Conversation
  --disable-slash-commands  Disable expansion
  --effort  Effort
  --json-schema  Schema
  --mode  Mode (plan, accept-edits)
  --model  Model
  --output-format  Format (stream-json)
  --print  Prompt
  --print-timeout  Deadline
  --sandbox  Sandbox
HELP
exit 0 ;;
esac
printf 'provider-started\n' >> "$AUTHORITY_CALL_FILE"
printf '%s\n' '{"event":"init","init":{},"conversation_id":"fixture"}'
printf '%s\n' '{"event":"result","result":{"status":"SUCCESS","structured_output":{"status":"completed","summary":"synthetic","files_changed":[],"commands_run":[],"tests_run":[],"risks":[],"open_questions":[],"confidence":1,"requires_human":false}}}'
''')
        fake.chmod(0o755)
        self.called = self.root / "provider-calls"
        self.logs = self.root / "logs"
        self.logs.mkdir(mode=0o700)
        self.environment = {name: value for name, value in os.environ.items() if not name.startswith("AGY_WORKER_")}
        state_home = self.root / "state-home"
        state_home.mkdir(mode=0o700)
        self.environment.update(XDG_STATE_HOME=str(state_home), PATH=f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            AGY_WORKER_LOG_DIR=str(self.logs), AUTHORITY_CALL_FILE=str(self.called),
            AUTHORITY_PRIVATE_VALUE="environment-value-must-never-appear")
        self.common = ["--workdir", str(self.worktree), "--workflow", "task", "--max-cycles", "2",
            "--idle-timeout", "10s", "--hard-timeout", "20s", "--max-runtime", "30s",
            "--notice-interval", "10s", "--provider-env", "AUTHORITY_CALL_FILE"]
        self.sequence = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str) -> None:
        subprocess.run(["/usr/bin/git", *arguments], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)

    def preview(self, task: bytes = b"initial synthetic task", extra: list[str] | None = None) -> tuple[bytes, dict]:
        arguments = [*self.common, *(extra or [])] if CURRENT else ["--workdir", str(self.worktree)]
        if not CURRENT and extra and "--provider-scope" in extra:
            arguments += ["--provider-scope", str(self.scope)]
        result = subprocess.run([str(WORKER), "transmission-preview", *arguments], input=task,
            env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout, json.loads(result.stdout)

    def launch(self, record: bytes, digest: str, *, task: bytes = b"initial synthetic task",
               extra: list[str] | None = None) -> subprocess.CompletedProcess:
        self.sequence += 1
        path = self.root / f"approval-{self.sequence}.json"
        path.write_bytes(record)
        path.chmod(0o600)
        arguments = [*self.common, *(extra or [])]
        flag = "--approve-transmission-sha" if "--provider-scope" in arguments else "--approve-whole-worktree"
        arguments += [flag, digest]
        if CURRENT:
            arguments += ["--approval-record", str(path)]
        environment = dict(self.environment, AGY_WORKER_JOB_ID=f"fixture-{self.sequence}")
        if not CURRENT:
            index = arguments.index("--notice-interval")
            environment["AGY_WORKER_NOTICE_INTERVAL"] = arguments[index + 1]
            del arguments[index:index + 2]
        return subprocess.run([str(WORKER), *arguments], input=task, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_retired_inputs_reject_all_launch_routes_before_provider(self) -> None:
        routes = [
            [str(WORKER), *self.common],
            [str(WORKER), "transmission-preview", *self.common],
            [str(ROOT / "workflow.sh"), "run", "--repo", str(self.root / "owner"),
             "--job-id", "retired", "--preview", "--task", "synthetic"],
        ]
        for route in routes:
            with self.subTest(route=route[:2]):
                removed = subprocess.run([*route, "--tier", "hard"], input=b"synthetic",
                    env=self.environment, capture_output=True)
                self.assertEqual(removed.returncode, 64, removed.stderr)
                self.assertRegex(removed.stderr, b"invalid usage|unknown|unrecognized")
                for extra in ([], ["--model", "literal"]):
                    rejected = subprocess.run([*route, *extra], input=b"synthetic",
                        env=dict(self.environment, AGY_WORKER_TIER="hard"), capture_output=True)
                    self.assertEqual(rejected.returncode, 64, rejected.stderr)
                    self.assertIn(b"--model / AGY_WORKER_MODEL", rejected.stderr)
                self.assertFalse(self.called.exists())
        self.environment["AGY_WORKER_TIER"] = ""
        raw, preview = self.preview()
        accepted = self.launch(raw, preview["launch_approval_sha256"])
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        facade = subprocess.run(routes[-1], env=self.environment, capture_output=True)
        self.assertEqual(facade.returncode, 0, facade.stderr)

    def test_old_valid_tier_approval_cannot_launch_removed_cli(self) -> None:
        _raw, preview = self.preview()
        old = dict(preview["launch_authority"], kind="agy-worker-launch-authority-v1",
                   tier="hard", model="gemini-3.1-pro-high")
        digest = hashlib.sha256(json.dumps(old, ensure_ascii=True, sort_keys=True,
            separators=(",", ":")).encode("ascii") + b"\n").hexdigest()
        carrier = dict(preview, launch_authority=old, launch_approval_sha256=digest)
        rejected = self.launch(json.dumps(carrier).encode(), digest, extra=["--tier", "hard"])
        self.assertEqual(rejected.returncode, 64, rejected.stderr)
        self.assertFalse(self.called.exists())

    def test_retired_and_extra_authority_fields_reject_recomputed_approval(self) -> None:
        raw, preview = self.preview()
        # Baseline v1 differs only by its kind and required nullable tier field.
        old = dict(preview["launch_authority"], kind="agy-worker-launch-authority-v1", tier=None)
        cases = [old, dict(preview["launch_authority"], effort="high"),
                 *[dict(preview["launch_authority"], **{field: value})
                       for field, value in (("tier", None), ("pre_dispatch_recommendation", None),
                                            ("untrusted", False))]]
        self.assertEqual(self.launch(raw, preview["launch_approval_sha256"]).returncode, 0)
        self.called.unlink()
        for authority in cases:
            self.called.unlink(missing_ok=True)
            with self.subTest(fields=set(authority), kind=authority["kind"]):
                digest = hashlib.sha256(json.dumps(authority, ensure_ascii=True, sort_keys=True,
                    separators=(",", ":")).encode("ascii") + b"\n").hexdigest()
                altered = dict(preview, launch_authority=authority, launch_approval_sha256=digest)
                rejected = self.launch(json.dumps(altered).encode(), digest)
                self.assertEqual(rejected.returncode, 64, rejected.stderr)
                self.assertFalse(self.called.exists())

    def test_different_task_changes_digest(self) -> None:
        _raw, initial = self.preview()
        _raw, different = self.preview(b"different synthetic task")
        self.assertNotEqual(initial["launch_approval_sha256"], different["launch_approval_sha256"])

    def test_stale_task_is_rejected_before_provider(self) -> None:
        raw, initial = self.preview()
        changed = self.launch(raw, initial["launch_approval_sha256"], task=b"different synthetic task")
        self.assertEqual(changed.returncode, 64, changed.stderr)
        self.assertIn(b"task_sha256", changed.stderr)
        self.assertFalse(self.called.exists())

    def test_identical_content_at_new_destination_needs_new_approval(self) -> None:
        raw, initial = self.preview()
        other = self.root / "other-worktree"
        self.git("-C", str(self.root / "owner"), "worktree", "add", "-qb", "other", str(other))
        self.common[self.common.index("--workdir") + 1] = str(other)
        _other_raw, changed = self.preview()
        self.assertNotEqual(initial["launch_approval_sha256"], changed["launch_approval_sha256"])
        rejected = self.launch(raw, initial["launch_approval_sha256"])
        self.assertEqual(rejected.returncode, 64, rejected.stderr)
        self.assertIn(b"workdir", rejected.stderr)
        self.assertFalse(self.called.exists())

    def test_controller_rechecks_task_after_raw_approval_and_names_field(self) -> None:
        self.environment["AUTHORITY_HELP_COUNT_FILE"] = str(self.root / "help-count")
        self.environment["AUTHORITY_TAMPER_TASK"] = str(self.logs / "fixture-1" / "task.txt")
        self.common += ["--provider-env", "AUTHORITY_HELP_COUNT_FILE", "--provider-env", "AUTHORITY_TAMPER_TASK"]
        raw, preview = self.preview()
        rejected = self.launch(raw, preview["launch_approval_sha256"])
        self.assertEqual(rejected.returncode, 20, rejected.stderr)
        self.assertIn(b"launch_authority_changed:task_sha256", rejected.stderr)
        self.assertFalse(self.called.exists())

    def test_each_material_selector_changes_digest_and_names_stale_field(self) -> None:
        for field, extra in (
            ("self_verification_manifest_sha256", ["--self-verification-manifest", str(self.manifest)]),
            ("model", ["--model", "fixture-model"]),
            ("effort", ["--model", "fixture-model", "--effort", "high"]),
            ("mode", ["--mode", "plan"]),
            ("max_cycles", ["--max-cycles", "1"]),
            ("allow_scoped_repair", ["--provider-scope", str(self.scope), "--allow-scoped-repair"]),
        ):
            with self.subTest(field=field):
                baseline_extra = ["--provider-scope", str(self.scope)] if field == "allow_scoped_repair" else []
                if field == "effort":
                    baseline_extra = ["--model", "fixture-model", "--effort", "low"]
                raw, initial = self.preview(extra=baseline_extra)
                # Replace the original cycle flag rather than testing duplicate parsing.
                common = list(self.common)
                if field == "max_cycles":
                    index = self.common.index("--max-cycles")
                    del self.common[index:index + 2]
                try:
                    _raw, changed = self.preview(extra=extra)
                    self.assertNotEqual(initial["launch_approval_sha256"], changed["launch_approval_sha256"])
                    rejected = self.launch(raw, initial["launch_approval_sha256"], extra=extra)
                    self.assertEqual(rejected.returncode, 64, rejected.stderr)
                    self.assertIn(field.encode(), rejected.stderr)
                    self.assertFalse(self.called.exists())
                finally:
                    self.common = common

    def test_task_option_matches_stdin_and_preserves_spaces_crlf(self) -> None:
        for task in (b"same task\n\n", b"same task  \n", b"same task\r\n"):
            raw, initial = self.preview(task)
            direct = subprocess.run([str(WORKER), "transmission-preview", *self.common,
                                    "--task", task.decode()], env=self.environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual(raw, direct.stdout)
            self.assertEqual(initial["task_text"], task.rstrip(b"\n").decode())

    def test_environment_values_and_private_manifest_contents_are_absent(self) -> None:
        raw, preview = self.preview(extra=["--provider-env", "AUTHORITY_PRIVATE_VALUE",
                                          "--self-verification-manifest", str(self.manifest)])
        self.assertNotIn(self.environment["AUTHORITY_PRIVATE_VALUE"].encode(), raw)
        self.assertNotIn(b"/usr/bin/true", raw)
        self.assertNotIn(b"private-check-id", raw)
        self.assertIn("AUTHORITY_PRIVATE_VALUE", preview["launch_authority"]["provider_env_names"])

    def test_matching_edit_and_plan_launches_reach_fake_provider(self) -> None:
        for extra in ([], ["--mode", "plan"]):
            raw, preview = self.preview(extra=extra)
            launched = self.launch(raw, preview["launch_approval_sha256"], extra=extra)
            self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertEqual(self.called.read_text().splitlines(), ["provider-started"] * 2)

    def test_actual_provider_timeout_and_output_format_are_checked(self) -> None:
        source = WORKER.with_name("scripts") / "agy_dispatch.py"
        spec = importlib.util.spec_from_file_location("authority_regression_dispatch", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        task = b"initial synthetic task"
        command = {"launch_authority": {"task_sha256": hashlib.sha256(task).hexdigest()},
                   "max_seconds": 30, "argv": ["agy", "--print-timeout", "30s",
                                               "--output-format", "stream-json"]}
        for flag, value, diagnostic in (("--print-timeout", "300s", "max_seconds"),
                                        ("--output-format", "json", "output format")):
            with self.subTest(flag=flag):
                altered = dict(command, argv=list(command["argv"]))
                altered["argv"][altered["argv"].index(flag) + 1] = value
                with mock.patch.object(module.LAUNCH_AUTHORITY, "read_bound_file", return_value=task):
                    with self.assertRaisesRegex(module.DispatchError, diagnostic):
                        module._confirm_launch_authority(self.logs, altered, {})


if __name__ == "__main__":
    unittest.main(argv=[__file__, *remaining])
