#!/usr/bin/env python3
"""Offline approval regressions, runnable against the previous runtime as well."""

from __future__ import annotations

import argparse
import contextlib
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

EXPECTED_POLICY = """NON-INTERACTIVE RUN:
- Respect applicable user and repository instructions (for example GEMINI.md),
  including security, privacy, permission, and scope constraints.
- If a security, privacy, permission, or scope constraint conflicts with this task
  or output contract, or a missing answer is needed to satisfy it,
  report status=blocked and requires_human=true; explain in open_questions.
  Do not bypass the constraint or assume required authorization.
- Constraints on secrets, data destinations, destructive actions, and required
  permission to act are protected; do not treat them as routine conversation.
- Nobody can answer questions during this run. Do not ask; put assumptions,
  blockers, and questions in the result as the output contract requires.
- This run's contract governs routine conversational questions and response
  formatting. If no protected constraint needs the answer, record an unanswered
  question in open_questions and a safe assumption in summary, then continue.
- Stay within the task's scope and allowed paths. Do not add CI, hooks, linters,
  formatters, type checkers, dependencies, or refactors the task did not ask for.
- Include compatible report requirements in the schema fields; use this
  contract's format when a report template is incompatible.

"""

PREVIOUS_POLICY = """NON-INTERACTIVE RUN:
- Respect applicable user and repository instructions (for example GEMINI.md),
  including security, privacy, permission, and scope constraints.
- If those instructions conflict with this task or output contract, or require
  clarification, report status=blocked and requires_human=true; explain the
  conflict in open_questions. Do not bypass the constraint.
- Nobody can answer questions during this run. Do not ask; put assumptions,
  blockers, and questions in the result as the output contract requires.
- Stay within the task's scope and allowed paths. Do not add CI, hooks, linters,
  formatters, type checkers, dependencies, or refactors the task did not ask for.
- Include compatible report requirements in the schema fields; report incompatible
  requirements as a conflict rather than silently discarding them.

"""

EXPECTED_OUTPUT_CONTRACT = """OUTPUT CONTRACT — non-negotiable:
- Your FINAL response must be a single JSON object matching the enforced schema.
- Do NOT write your answer to a file, artifact, or brain document.
- Do NOT reply "see the artifact" or reference an external document.
- Follow the FILE-TOOL ROOT instruction for the files_changed reference point.
  Report net created, modified, or deleted paths; omit transient touches.
- __WORKSPACE_DIRECTIVE__ Do NOT run shell or terminal tools or tests.
  __PROVIDER_EXECUTION_NOTE__ The driver's environment is the only trusted execution
  context. Leave commands_run and tests_run as empty arrays.
- If a permission gate, missing tool, or ambiguity blocks you: set
  status="blocked", requires_human=true, and explain in open_questions.
  Do not silently work around it.

TASK FOLLOWS:
"""


def dispatch_module():
    source = WORKER.with_name("scripts") / "agy_dispatch.py"
    spec = importlib.util.spec_from_file_location("config_regression_dispatch", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def authority_module():
    source = WORKER.with_name("scripts") / "launch_authority.py"
    spec = importlib.util.spec_from_file_location("policy_prompt_regression", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LaunchAuthorityTests(unittest.TestCase):
    def test_timeout_units_are_actionable_without_changing_grammar(self) -> None:
        module = authority_module()
        message = "timeout must be a positive integer with s, m or h (for example 30m)"
        for value, expected in (("1s", 1), ("30m", 1800), ("168h", 604800)):
            self.assertEqual(module.duration(value), expected)
        for value in ("300", "0s", "01m", "-1s", "1.5h", "1S", " 1s", "1s "):
            with self.subTest(value=value), self.assertRaises(module.LaunchAuthorityError) as caught:
                module.duration(value)
            self.assertEqual(str(caught.exception), message)
        with self.assertRaisesRegex(module.LaunchAuthorityError, "timeout exceeds limit"):
            module.duration("169h")
        for flag in ("--idle-timeout", "--hard-timeout", "--max-runtime"):
            with self.subTest(flag=flag):
                arguments = list(self.common)
                arguments[arguments.index(flag) + 1] = "300"
                result = subprocess.run(
                    [str(WORKER), "transmission-preview", *arguments],
                    input=b"bounded task", env=self.environment, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 20, result.stderr)
                self.assertIn(message.encode(), result.stderr)
                self.assertFalse(self.called.exists())

    def test_selection_entrypoints_reject_auto_mode_before_effects(self) -> None:
        # Selection has no mode input; ambiguous model prefixes fail before probing AGY.
        for selector in (ROOT / "model-selection.sh", WORKER.with_name("model-selection.sh")):
            for arguments in (["--mode", "auto"], ["--mode=auto"]):
                with self.subTest(selector=selector, arguments=arguments):
                    result = subprocess.run([str(selector), *arguments], input=b"",
                        env=self.environment, capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 64, result.stderr)
                    self.assertIn(b"ambiguous option", result.stderr)
                    self.assertFalse(self.called.exists())

    def test_worker_entrypoints_reject_auto_mode_before_effects(self) -> None:
        for worker in (ROOT / "agy-worker.sh", WORKER):
            for arguments in (["--mode", "auto"], ["--mode=auto"]):
                with self.subTest(worker=worker, arguments=arguments):
                    result = subprocess.run([str(worker), *arguments, "--task", "bounded task"],
                        input=b"", env=self.environment, capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 64, result.stderr)
                    self.assertFalse(self.called.exists())
                    self.assertEqual(list(self.logs.iterdir()), [])

    def test_preview_entrypoints_reject_auto_mode_before_effects(self) -> None:
        for worker in (ROOT / "agy-worker.sh", WORKER):
            for arguments in (["--mode", "auto"], ["--mode=auto"]):
                with self.subTest(worker=worker, arguments=arguments):
                    result = subprocess.run([str(worker), "transmission-preview", *self.common,
                                             *arguments], input=b"bounded task",
                        env=self.environment, capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 64, result.stderr)
                    self.assertIn(b"invalid choice: 'auto'", result.stderr)
                    self.assertFalse(self.called.exists())
                    self.assertEqual(list(self.logs.iterdir()), [])

    def test_prompt_render_rejects_auto_mode(self) -> None:
        module = authority_module()
        with self.assertRaisesRegex(module.LaunchAuthorityError, "mode is invalid"):
            module.full_prompt(b"bounded task", mode="auto", provider_isolation="session")
        result = subprocess.run([sys.executable, "-I", "-S", "-B",
            str(WORKER.with_name("scripts") / "launch_authority.py"), "render", "auto", "session", ""],
            input=b"bounded task", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_launch_authority_record_rejects_auto_mode(self) -> None:
        _raw, preview = self.preview()
        authority = {**preview["launch_authority"], "mode": "auto"}
        module = authority_module()
        with self.assertRaisesRegex(module.LaunchAuthorityError, "workflow is invalid"):
            module.approval_sha256(authority)

    def test_worker_prompt_preserves_applicable_policy(self) -> None:
        module = authority_module()
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
                    self.assertIn(EXPECTED_POLICY.encode(), prompt)
                    self.assertNotIn(b"If those instructions conflict", prompt)
                    self.assertNotIn(b"requirements as a conflict rather than silently discarding", prompt)
                    self.assertTrue(prompt.endswith(task))

    def test_worker_preamble_exact_policy_and_output_contract(self) -> None:
        preamble = authority_module()._PREAMBLE
        prefix, policy_and_output = preamble.split("NON-INTERACTIVE RUN:", 1)
        policy, output = policy_and_output.split("OUTPUT CONTRACT", 1)
        self.assertEqual("OUTPUT CONTRACT" + output, EXPECTED_OUTPUT_CONTRACT)
        self.assertEqual(prefix, "You are a bounded worker. Another agent (the driver) will independently verify\n"
            "everything you claim, so inaccurate self-reporting is worse than admitting failure.\n\n"
            "__SELF_VERIFICATION_CHECK_REQUESTS__\n")
        self.assertEqual("NON-INTERACTIVE RUN:" + policy, EXPECTED_POLICY)
        self.assertEqual(preamble.count(EXPECTED_POLICY), 1)
        self.assertEqual(hashlib.sha256(preamble.encode()).hexdigest(),
                         "0ca4fda6892e644546d4625d3bfea7e4ef1b62d4e5966b595842db028d6da5bc")

    def test_prompt_render_preview_parity(self) -> None:
        module = authority_module()
        source = WORKER.with_name("scripts") / "launch_authority.py"
        for task in (b"normal synthetic task\n\n", "Çağdaş: résumé\r\nsecond line  \r\n\n".encode()):
            for mode in ("plan", "accept-edits"):
                for isolation in ("session", "native"):
                    with self.subTest(task=task, mode=mode, isolation=isolation):
                        prompt = module.full_prompt(task.rstrip(b"\n"), mode=mode,
                                                    provider_isolation=isolation)
                        rendered = subprocess.run(["/usr/bin/python3", "-I", "-S", "-B", str(source),
                            "render", mode, isolation, ""], input=task, capture_output=True)
                        self.assertEqual(rendered.returncode, 0, rendered.stderr)
                        self.assertEqual(rendered.stdout, prompt)
                        _raw, preview = self.preview(task, extra=["--mode", mode,
                            "--provider-isolation", isolation, "--provider-scope", str(self.scope)])
                        self.assertEqual(preview["launch_authority"]["full_prompt_sha256"],
                                         hashlib.sha256(prompt).hexdigest())
                        self.assertFalse(self.called.exists())

    def test_previous_preamble_approval_is_rejected_before_provider(self) -> None:
        module = authority_module()
        task = b"initial synthetic task"
        _raw, preview = self.preview(task)
        # Reconstruct exactly the previous policy, keeping the fixed prefix and output contract.
        prefix, rest = module._PREAMBLE.split("NON-INTERACTIVE RUN:", 1)
        suffix = "OUTPUT CONTRACT" + rest.split("OUTPUT CONTRACT", 1)[1]
        with mock.patch.object(module, "_PREAMBLE", prefix + PREVIOUS_POLICY + suffix):
            old_prompt = module.full_prompt(task, mode="accept-edits", provider_isolation="session")
        old_authority = dict(preview["launch_authority"],
                             full_prompt_sha256=hashlib.sha256(old_prompt).hexdigest())
        old_digest = module.approval_sha256(old_authority)
        old_record = dict(preview, launch_authority=old_authority, launch_approval_sha256=old_digest)
        rejected = self.launch(json.dumps(old_record).encode(), old_digest, task=task)
        self.assertEqual(rejected.returncode, 64, rejected.stderr)
        self.assertIn(b"full_prompt_sha256", rejected.stderr)
        self.assertFalse(self.called.exists())
        self.assertNotEqual(old_authority["full_prompt_sha256"], preview["launch_authority"]["full_prompt_sha256"])
        self.assertNotEqual(old_digest, preview["launch_approval_sha256"])
        self.assertEqual({key: value for key, value in old_authority.items() if key != "full_prompt_sha256"},
                         {key: value for key, value in preview["launch_authority"].items()
                          if key != "full_prompt_sha256"})

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

    def config_path(self, relative: str, *, directory: bool = False) -> Path:
        target = self.worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if directory:
            target.mkdir()
        else:
            target.write_text('{"private-payload":"must-not-be-diagnosed"}')
        return target

    def config_preview(self, extra: list[str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(WORKER), "transmission-preview", *self.common, *(extra or [])],
            input=b"initial synthetic task", env=self.environment, capture_output=True, check=False)

    def assert_config_rejected(self, result: subprocess.CompletedProcess, path: str) -> None:
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"executable provider configuration", result.stderr)
        self.assertIn(path.encode("unicode_escape").lower(), result.stderr.lower())
        self.assertIn(b"use scoped mode excluding .agents/ configuration", result.stderr)
        self.assertNotIn(b"must-not-be-diagnosed", result.stderr)
        self.assertFalse(self.called.exists())

    def select_config(self, path: str, kind: str) -> list[str]:
        self.scope.write_text(json.dumps({"schema_version": 1, "kind": "agy-worker-provider-scope",
            "read": [{"path": path, "kind": kind}], "write": []}))
        return ["--provider-scope", str(self.scope)]

    def test_workspace_config_preview_rejects_reserved_nodes_and_aliases(self) -> None:
        paths = [f".agents/{leaf}.json" for leaf in
                 ("mcp_config", "hooks", "skills", "rules", "agents", "plugins")]
        paths += ["src/.agents/mcp_config.json", ".AGENTS/MCP_CONFIG.JSON",
                  ".agents/plugins/example/mcp_config.json", ".agents/plugins/example/plugin.json",
                  ".agents/plugins/example/.antigravity-plugin/plugin.json",
                  ".agents/plugins/example/.gemini-plugin/plugin.json"]
        for relative in paths:
            with self.subTest(path=relative):
                target = self.config_path(relative)
                target.write_text("{}")
                try:
                    self.assert_config_rejected(self.config_preview(), relative)
                finally:
                    target.unlink()
    def test_workspace_config_preview_rejects_reserved_directory_and_special_node(self) -> None:
        directory = self.config_path(".agents/hooks.json", directory=True)
        self.assert_config_rejected(self.config_preview(), ".agents/hooks.json")
        directory.rmdir()
        special = self.worktree / ".agents/hooks.json"
        os.mkfifo(special)
        self.assert_config_rejected(self.config_preview(), ".agents/hooks.json")
        special.unlink()
    def test_workspace_config_preview_rejects_loader_aliases(self) -> None:
        aliases = [("nested/.agents", "../safe"), (".agents/mcp_config.json", "../safe/note"),
                   (".agents/plugins", "../safe"), (".agents/plugins/example", "../../safe")]
        (self.worktree / "safe").mkdir()
        (self.worktree / "safe/note").write_text("ordinary text")
        # Remove the empty ordinary directories from earlier cases first.
        import shutil
        if (self.worktree / ".agents").exists():
            shutil.rmtree(self.worktree / ".agents")
        for relative, destination in aliases:
            with self.subTest(alias=relative):
                target = self.worktree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(destination)
                try:
                    self.assert_config_rejected(self.config_preview(), relative)
                finally:
                    target.unlink()

    def test_workspace_config_diagnostic_is_escaped_bounded_and_content_free(self) -> None:
        relative = "/".join(["segment" * 15] * 5) + "/line\nname/.agents/mcp_config.json"
        self.config_path(relative)
        result = self.config_preview()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"executable provider configuration", result.stderr)
        self.assertIn(b"\\nname/.agents/mcp_config.json", result.stderr)
        self.assertNotIn(b"must-not-be-diagnosed", result.stderr)
        self.assertEqual(result.stderr.count(b"\n"), 1)
        self.assertLessEqual(len(result.stderr), 768)

    def test_workspace_config_scoped_preview_rejects_file_tree_and_nested_selection(self) -> None:
        for relative, selected, kind in ((".agents/mcp_config.json", ".agents/mcp_config.json", "file"),
                (".agents/mcp_config.json", ".agents", "tree"),
                ("src/.agents/hooks.json", "src", "tree")):
            target = self.config_path(relative)
            try:
                for isolation in ("session", "native"):
                    with self.subTest(path=relative, kind=kind, isolation=isolation):
                        extra = self.select_config(selected, kind) + ["--provider-isolation", isolation]
                        self.assert_config_rejected(self.config_preview(extra), relative)
            finally:
                target.unlink()

    def test_workspace_config_scoped_symlink_diagnostic_precedes_generic_rejection(self) -> None:
        (self.worktree / "safe").mkdir()
        (self.worktree / ".agents").symlink_to("safe")
        extra = self.select_config(".agents", "tree")
        self.assert_config_rejected(self.config_preview(extra), ".agents")

    def test_workspace_markdown_agents_preview_rejects_documented_forms(self) -> None:
        for relative in (".agents/agents/example.md", ".agents/agents/example/agent.md",
                         "src/.agents/agents/example.md", "src/.agents/agents/example/agent.md"):
            target = self.config_path(relative)
            try:
                for isolation in ("session", "native"):
                    for selection in (None, (relative, "file"), (relative.split("/")[0], "tree")):
                        if isolation == "native" and selection is None:
                            continue  # Native isolation requires scoped staging.
                        with self.subTest(path=relative, isolation=isolation, selection=selection):
                            extra = ["--provider-isolation", isolation]
                            if selection is not None:
                                extra += self.select_config(*selection)
                            self.assert_config_rejected(self.config_preview(extra), relative)
            finally:
                target.unlink()

    def test_workspace_markdown_agents_normalization_is_type_independent(self) -> None:
        module = dispatch_module().WORKTREE
        for relative in (".AGENTS/AGENTS/EXAMPLE.MD", ".AGENTS/AGENTS/Example/AGENT.MD",
                         "src/.agents/agents/cafe\u0301.md", ".agents/agents/cafe\u0301/agent.md"):
            for symlink in (False, True):
                with self.subTest(path=relative, symlink=symlink):
                    with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                        module._check_provider_config_node(relative, symlink=symlink)

    def test_workspace_markdown_agents_preview_rejects_loader_aliases_and_reserved_types(self) -> None:
        (self.worktree / "safe").mkdir()
        for relative in (".agents/agents", ".agents/agents/example",
                         ".agents/agents/example.md", ".agents/agents/example/agent.md"):
            with self.subTest(alias=relative):
                target = self.worktree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(self.worktree / "safe")
                try:
                    self.assert_config_rejected(self.config_preview(), relative)
                    extra = self.select_config(".agents", "tree")
                    self.assert_config_rejected(self.config_preview(extra), relative)
                finally:
                    target.unlink()
        for relative in (".agents/agents/example.md", ".agents/agents/example/agent.md"):
            with self.subTest(reserved_type=relative):
                target = self.config_path(relative, directory=True)
                self.assert_config_rejected(self.config_preview(), relative)
                target.rmdir()
                os.mkfifo(target)
                self.assert_config_rejected(self.config_preview(), relative)
                target.unlink()

    def test_workspace_config_plain_content_and_unselected_config_remain_allowed(self) -> None:
        for path in (".agents/skills/example/SKILL.md", ".agents/rules/example.md",
                     ".agents/plugins/marketplace.json", "config/mcp_config.json", "GEMINI.md",
                     ".agents/agents/README.txt", ".agents/agents/example/notes.md",
                     ".agents/agents/example/deep/agent.md", "notes/.agents/ordinary.md"):
            self.config_path(path)
        internal_link = self.worktree / ".agents/rules/internal-link.md"
        internal_link.symlink_to("../../README.md")
        self.preview()
        internal_link.unlink()
        self.config_path(".agents/mcp_config.json")
        self.config_path(".agents/agents/unselected.md")
        self.config_path(".agents/agents/unselected/agent.md")
        for isolation in ("session", "native"):
            with self.subTest(isolation=isolation):
                _raw, preview = self.preview(extra=["--provider-scope", str(self.scope),
                                                   "--provider-isolation", isolation])
                self.assertEqual([entry["path"] for entry in preview["selected_content_manifest"]], ["README.md"])
        raw, preview = self.preview(extra=["--provider-scope", str(self.scope)])
        launched = self.launch(raw, preview["launch_approval_sha256"],
                               extra=["--provider-scope", str(self.scope)])
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertFalse((self.logs / "fixture-1/stage-001/.agents").exists())

    def test_workspace_config_ordinary_regular_loader_containers_remain_allowed(self) -> None:
        for relative in (".agents", ".agents/plugins", ".agents/agents"):
            with self.subTest(path=relative):
                target = self.config_path(relative)
                raw, preview = self.preview()
                launched = self.launch(raw, preview["launch_approval_sha256"])
                self.assertEqual(launched.returncode, 0, launched.stderr)
                target.unlink()
        self.assertEqual(self.called.read_text().splitlines(), ["provider-started"] * 3)

    def test_workspace_config_whole_disposable_git_file_stops_ancestor_probe(self) -> None:
        self.assertTrue((self.worktree / ".git").is_file())
        outside = self.root / ".agents/mcp_config.json"
        outside.parent.mkdir()
        outside.write_text("{}")
        raw, preview = self.preview()
        result = self.launch(raw, preview["launch_approval_sha256"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.called.exists())

    def test_workspace_config_every_whole_launch_origin_rechecks_without_extra_tree_walk(self) -> None:
        module = dispatch_module()
        for origin, conversation in (("initial", None), ("resume", "same"),
                ("conversation-continue", "same"), ("fresh-attempt", None)):
            with self.subTest(origin=origin):
                raw, _preview = self.preview()
                self.assertTrue(raw)
                target = self.config_path(".agents/mcp_config.json")
                stderr = self.root / "config-stderr"
                with stderr.open("wb") as handle, contextlib.ExitStack() as stack:
                    binding = module._ControllerBinding(state={"attempt_origin": origin,
                        "conversation_id": conversation, "provider_scope_path": None},
                        command={"schema_version": 16, "workdir": str(self.worktree), "base_commit": None,
                                 "provider_isolation": "session"})
                    launch = module._ScopedLaunch(argv=["agy"])
                    streams = module._ControllerStreams(self.root / "stream", stderr, self.root / "envelope",
                                                         stderr_fd=handle.fileno())
                    for name in ("_reprobe_direct_selection", "_bound_worktree_baseline",
                                 "_confirm_whole_controller_approval", "_confirm_launch_authority", "_bind_workspace_prompt"):
                        stack.enter_context(mock.patch.object(module, name))
                    spawn = stack.enter_context(mock.patch.object(module, "_spawn_controller_provider"))
                    walker = stack.enter_context(mock.patch.object(module.WORKTREE.os, "scandir",
                                                   wraps=module.WORKTREE.os.scandir))
                    outcome = module._ControllerOutcome()
                    module._launch_controller_provider(self.logs, binding, module._ProviderExecution(),
                                                        streams, launch, outcome)
                    self.assertFalse(spawn.called, f"provider launch bypass: {origin}")
                    self.assertEqual(outcome.reason, "status_unavailable")
                    # Existing launch boundary visits root and .agents exactly once.
                    self.assertLessEqual(walker.call_count, 2)
                self.assertIn(b"executable provider configuration", stderr.read_bytes())
                self.assertIn(b".agents/mcp_config.json", stderr.read_bytes())
                target.unlink()

    def test_workspace_config_final_spawn_checks_actual_ancestors_and_late_mutations(self) -> None:
        module = dispatch_module()
        stage = self.logs / "stage"
        stage.mkdir()
        (stage / ".agents").mkdir()
        # The session's ambient HOME is trusted only as an ancestor, never as cwd.
        home = self.root / "ambient-home"
        home.mkdir()
        (home / ".agents").mkdir()
        (home / ".agents/hooks.json").write_text("{}")
        (home / "safe-stage").mkdir()
        safe_agents = self.root / "safe-agents"
        safe_agents.mkdir()
        loader = stage / ".agents/plugins/marketplace.json"
        cases = [(stage, self.logs / ".agents/hooks.json", None),
                 (stage, self.logs / ".agents/hooks.json", str(self.logs)),
                 (stage, stage / ".agents", None),
                 (stage, stage / ".agents/mcp_config.json", None),
                 (home, None, str(home)),
                 (stage, loader, None)]
        for cwd, introduced, ambient_home in cases:
            with self.subTest(cwd=cwd, introduced=introduced), contextlib.ExitStack() as stack:
                if introduced == loader:
                    loader.parent.mkdir(exist_ok=True)
                    loader.write_text("{}")
                state = {"attempt": 1, "controller_pid": os.getpid(), "status": "queued",
                         "source_checkout_guard": {}, "cancel_requested": False, "hard_seconds": 30, "max_seconds": 30, "provider_elapsed_seconds": 0}
                binding = module._ControllerBinding(state=state, command={"provider_env": [], "max_seconds": 30,
                                                                         "child_umask": "022", "workdir": str(self.worktree)})
                execution = module._ProviderExecution(source_guard_expected={})
                launch = module._ScopedLaunch(argv=["agy", "--print", "task"], expected_print="task",
                                              launch_cwd=str(cwd))
                # A known safe directory is replaced during slow source preparation.
                if hasattr(launch, "provider_config_paths"):
                    launch.provider_config_paths = {".agents": "directory"}
                    if introduced == loader:
                        launch.provider_config_paths.update({".agents/plugins": "directory",
                            ".agents/plugins/marketplace.json": "file"})
                def prepare(*_args, introduced=introduced):
                    if introduced is not None:
                        introduced.parent.mkdir(exist_ok=True)
                        if introduced == loader:
                            introduced.unlink()
                            introduced.symlink_to(safe_agents)
                        elif introduced.is_dir():
                            introduced.rmdir()
                            introduced.symlink_to(safe_agents)
                        else:
                            introduced.write_text("must-not-be-diagnosed")
                    return {"status": "unchanged"}
                stack.enter_context(mock.patch.object(module, "_prepare_controller_source", side_effect=prepare))
                stack.enter_context(mock.patch.object(module, "state_lock", return_value=contextlib.nullcontext()))
                stack.enter_context(mock.patch.object(module, "load_state", return_value=(state, b"", "sha")))
                stack.enter_context(mock.patch.object(module, "_transition_locked", side_effect=lambda _job, current, raw, _updates: (current, raw, "sha")))
                stack.enter_context(mock.patch.object(module, "_provider_environment", return_value={}))
                stack.enter_context(mock.patch.dict(os.environ, {"HOME": ambient_home or str(home)}))
                popen = stack.enter_context(mock.patch.object(module.subprocess, "Popen",
                    side_effect=AssertionError("provider Popen reached before configuration rejection")))
                with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                    module._spawn_controller_provider(self.logs, binding, execution,
                        module._ControllerStreams(self.root / "stream", self.root / "stderr", self.root / "envelope"),
                        launch, module._ControllerOutcome())
                popen.assert_not_called()
                self.assertIsNone(execution.started_mono)
                if introduced is not None:
                    was_link = introduced.is_symlink()
                    introduced.unlink()
                    if was_link and introduced != loader:
                        introduced.mkdir()
        # Existing spawn entrypoint accepts trusted ambient HOME and safe siblings.
        # Exercise its final probe via the same preparation, with Popen stopped by a sentinel.
        (self.root / "sibling").mkdir()
        (self.root / "sibling/.agents").mkdir()
        (self.root / "sibling/.agents/hooks.json").write_text("{}")
        for safe_cwd in (home / "safe-stage", stage):
            state = {"attempt": 1, "controller_pid": os.getpid(), "status": "queued", "source_checkout_guard": {},
                     "cancel_requested": False, "hard_seconds": 30, "max_seconds": 30, "provider_elapsed_seconds": 0}
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(module, "_prepare_controller_source", return_value={"status": "unchanged"}))
                stack.enter_context(mock.patch.object(module, "state_lock", return_value=contextlib.nullcontext()))
                stack.enter_context(mock.patch.object(module, "load_state", return_value=(state, b"", "sha")))
                stack.enter_context(mock.patch.object(module, "_transition_locked", side_effect=lambda _job, current, raw, _updates: (current, raw, "sha")))
                stack.enter_context(mock.patch.object(module, "_provider_environment", return_value={}))
                stack.enter_context(mock.patch.dict(os.environ, {"HOME": str(home)}))
                popen = stack.enter_context(mock.patch.object(module.subprocess, "Popen", side_effect=RuntimeError("safe spawn reached")))
                stack.enter_context(mock.patch.object(module.WORKTREE.os, "scandir",
                    side_effect=AssertionError("extra directory enumeration before Popen")))
                safe_launch = module._ScopedLaunch(argv=["agy", "--print", "task"],
                    expected_print="task", launch_cwd=str(safe_cwd))
                if hasattr(safe_launch, "provider_config_paths"):
                    safe_launch.provider_config_paths = {".agents": "directory"}
                with self.assertRaisesRegex(RuntimeError, "safe spawn reached"):
                    module._spawn_controller_provider(self.logs, module._ControllerBinding(state=state,
                        command={"provider_env": [], "max_seconds": 30, "child_umask": "022", "workdir": str(self.worktree)}), module._ProviderExecution(source_guard_expected={}),
                        module._ControllerStreams(self.root / "stream", self.root / "stderr", self.root / "envelope"),
                        safe_launch,
                        module._ControllerOutcome())
                popen.assert_called_once()

    def test_workspace_markdown_agents_final_spawn_rejects_cwd_ancestors_and_late_additions(self) -> None:
        module = dispatch_module()
        stage = self.logs / "agent-stage"
        stage.mkdir()
        (self.root / ".git").write_text("stop without reading marker contents")
        for relative in (".agents/agents/example.md", ".agents/agents/example/agent.md"):
            for location in ("cwd", "ancestor", "known", "late"):
                with self.subTest(path=relative, location=location), contextlib.ExitStack() as stack:
                    base = self.logs if location == "ancestor" else stage
                    if location == "known":
                        base = stage / "nested"
                    target = base / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if location not in ("known", "late"):
                        target.write_text("must-not-be-diagnosed")
                    state = {"attempt": 1, "controller_pid": os.getpid(), "status": "queued",
                             "source_checkout_guard": {}, "cancel_requested": False,
                             "hard_seconds": 30, "max_seconds": 30, "provider_elapsed_seconds": 0}
                    def prepare(*_args, location=location, target=target):
                        if location in ("known", "late"):
                            target.write_text("must-not-be-diagnosed")
                        return {"status": "unchanged"}
                    stack.enter_context(mock.patch.object(module, "_prepare_controller_source", side_effect=prepare))
                    stack.enter_context(mock.patch.object(module, "state_lock", return_value=contextlib.nullcontext()))
                    stack.enter_context(mock.patch.object(module, "load_state", return_value=(state, b"", "sha")))
                    stack.enter_context(mock.patch.object(module, "_transition_locked", side_effect=lambda _job, current, raw, _updates: (current, raw, "sha")))
                    stack.enter_context(mock.patch.object(module, "_provider_environment", return_value={}))
                    popen = stack.enter_context(mock.patch.object(module.subprocess, "Popen",
                        side_effect=AssertionError("provider Popen reached before Markdown agent rejection")))
                    launch = module._ScopedLaunch(argv=["agy", "--print", "task"],
                        expected_print="task", launch_cwd=str(stage))
                    if location == "known":
                        launch.provider_config_paths = {"nested/.agents": "directory"}
                    try:
                        with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                            module._spawn_controller_provider(self.logs, module._ControllerBinding(state=state,
                                command={"provider_env": [], "max_seconds": 30, "child_umask": "022",
                                         "workdir": str(self.worktree)}),
                                module._ProviderExecution(source_guard_expected={}),
                                module._ControllerStreams(self.root / "stream", self.root / "stderr", self.root / "envelope"),
                                launch, module._ControllerOutcome())
                        popen.assert_not_called()
                    finally:
                        target.unlink()

    def test_workspace_markdown_agents_final_scan_is_shallow_bounded_and_no_follow(self) -> None:
        module = dispatch_module().WORKTREE
        stage = self.logs / "agent-scan-stage"
        loader = stage / ".agents/agents"
        package = loader / "example"
        package.mkdir(parents=True)
        (stage / ".git").write_text("stop")
        (package / "notes.md").write_text("ordinary content")
        deep = package / "deep"
        deep.mkdir()
        (deep / "agent.md").write_text("outside documented shallow loader")
        real_scandir = module.os.scandir
        with mock.patch.object(module.os, "scandir", wraps=real_scandir) as scanned:
            module._recheck_provider_configuration(str(stage), {}, ambient_home=None)
            self.assertEqual([Path(call.args[0]) for call in scanned.call_args_list], [loader, package])
        with mock.patch.object(module, "MAX_BOUNDARY_ENTRIES", 1):
            with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                module._recheck_provider_configuration(str(stage), {}, ambient_home=None)
        elapsed = [0.0]
        @contextlib.contextmanager
        def expired_scan(path):
            with real_scandir(path) as scanned:
                elapsed[0] = module.READABLE_MANIFEST_SCAN_SECONDS + 1
                yield scanned
        with mock.patch.object(module.os, "scandir", side_effect=expired_scan), mock.patch.object(
                module.time, "monotonic", side_effect=lambda: elapsed[0]):
            with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                module._recheck_provider_configuration(str(stage), {}, ambient_home=None)
        alias = loader / "alias"
        alias.symlink_to(deep)
        with mock.patch.object(module.os, "scandir", wraps=real_scandir) as scanned:
            with self.assertRaisesRegex(module.DispatchError, "executable provider configuration.*alias"):
                module._recheck_provider_configuration(str(stage), {}, ambient_home=None)
            self.assertNotIn(alias, [Path(call.args[0]) for call in scanned.call_args_list])

    def test_workspace_config_ancestor_plugin_regular_entries_obey_deadline(self) -> None:
        module = dispatch_module()
        stage = self.logs / "deadline-stage"
        stage.mkdir()
        plugins = self.logs / ".agents/plugins"
        plugins.mkdir(parents=True)
        (plugins / "marketplace.json").write_text("{}")
        (self.logs / ".git").write_text("marker contents must not be parsed")
        state = {"attempt": 1, "controller_pid": os.getpid(), "status": "queued",
                 "source_checkout_guard": {}, "cancel_requested": False, "hard_seconds": 30, "max_seconds": 30}
        elapsed = [0.0]
        real_scandir = module.WORKTREE.os.scandir
        @contextlib.contextmanager
        def late_regular_entries(path):
            self.assertEqual(Path(path), plugins)
            with real_scandir(path) as scanned:
                elapsed[0] = module.WORKTREE.READABLE_MANIFEST_SCAN_SECONDS + 1
                yield scanned
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(module, "_prepare_controller_source", return_value={"status": "unchanged"}))
            stack.enter_context(mock.patch.object(module, "state_lock", return_value=contextlib.nullcontext()))
            stack.enter_context(mock.patch.object(module, "load_state", return_value=(state, b"", "sha")))
            stack.enter_context(mock.patch.object(module, "_transition_locked", side_effect=lambda _job, current, raw, _updates: (current, raw, "sha")))
            stack.enter_context(mock.patch.object(module, "_provider_environment", return_value={}))
            stack.enter_context(mock.patch.object(module.WORKTREE.os, "scandir", side_effect=late_regular_entries))
            stack.enter_context(mock.patch.object(module.WORKTREE.time, "monotonic", side_effect=lambda: elapsed[0]))
            popen = stack.enter_context(mock.patch.object(module.subprocess, "Popen",
                side_effect=AssertionError("provider Popen reached after configuration deadline")))
            with self.assertRaisesRegex(module.DispatchError, "executable provider configuration"):
                module._spawn_controller_provider(self.logs, module._ControllerBinding(state=state,
                    command={"provider_env": [], "child_umask": "022", "workdir": str(self.worktree)}),
                    module._ProviderExecution(source_guard_expected={}),
                    module._ControllerStreams(self.root / "stream", self.root / "stderr", self.root / "envelope"),
                    module._ScopedLaunch(argv=["agy", "--print", "task"], expected_print="task", launch_cwd=str(stage)),
                    module._ControllerOutcome())
            popen.assert_not_called()

    def test_provider_configuration_selected_classification_obeys_deadline(self) -> None:
        module = dispatch_module()
        entries = [{"kind": "file", "path": "README.md"}]
        scope = {"read": [{"kind": "file", "path": "unselected.md"}]}
        with mock.patch.object(module.WORKTREE.time, "monotonic", side_effect=[
            0.0, module.WORKTREE.READABLE_MANIFEST_SCAN_SECONDS + 1,
        ]):
            with self.assertRaisesRegex(module.DispatchError, "executable provider configuration.*README.md"):
                module.WORKTREE._check_provider_config_entries(entries, scope=scope)

    def copy_config_candidate_for_verification(self):
        module = dispatch_module()
        config = self.config_path(".agents/mcp_config.json")
        raw = json.dumps({"schema_version": 1, "kind": "agy-worker-provider-scope",
            "read": [{"path": ".agents", "kind": "tree"}, {"path": "README.md", "kind": "file"}],
            "write": [{"path": ".agents", "kind": "tree"}]}).encode()
        self.scope.write_bytes(raw)
        scope = module._parse_provider_scope(raw)
        selected = module._build_selected_content_manifest(self.worktree, scope)
        command = {"workdir": str(self.worktree), "provider_scope_path": str(self.scope),
                   "provider_scope_sha256": module.digest(raw),
                   "provider_scope_identity": list(module._identity(self.scope.stat()))}
        state = {"selected_content_sha256": module._selected_content_digest(selected),
                 "selected_file_count": sum(entry["kind"] == "file" for entry in selected),
                 "selected_tree_count": sum(entry["kind"] == "directory" for entry in selected)}
        destination = self.root / "verification-copy"
        with mock.patch.object(module, "_bound_current_candidate") as bound, mock.patch.object(
                module.subprocess, "Popen", side_effect=AssertionError("verification copy started a provider")) as popen:
            try:
                module.SELF_VERIFICATION._copy_candidate(module.VERIFICATION_API, self.logs,
                                                         command, state, destination)
            except module.DispatchError as exc:
                self.fail(f"legitimate scoped verification copy was rejected: {exc}")
            popen.assert_not_called()
            bound.assert_called_once_with(self.logs, state)
        self.assertEqual((destination / ".agents/mcp_config.json").read_bytes(), config.read_bytes())
        self.assertEqual((destination / "README.md").read_bytes(), (self.worktree / "README.md").read_bytes())
        copied = module._build_selected_content_manifest(destination, scope, is_stage=True)
        self.assertEqual(module._selected_content_digest(copied), state["selected_content_sha256"])
        return module

    def test_workspace_config_scoped_verification_copy_remains_allowed(self) -> None:
        self.copy_config_candidate_for_verification()

    def test_workspace_config_next_launch_rejects_verified_candidate(self) -> None:
        module = self.copy_config_candidate_for_verification()
        stderr = self.root / "verified-candidate-stderr"
        with stderr.open("wb") as handle, contextlib.ExitStack() as stack:
            binding = module._ControllerBinding(state={"attempt_origin": "resume",
                "conversation_id": "same", "provider_scope_path": None},
                command={"schema_version": 16, "workdir": str(self.worktree), "base_commit": None,
                         "provider_isolation": "session"})
            for name in ("_reprobe_direct_selection", "_bound_worktree_baseline",
                         "_confirm_whole_controller_approval", "_confirm_launch_authority", "_bind_workspace_prompt"):
                stack.enter_context(mock.patch.object(module, name))
            spawn = stack.enter_context(mock.patch.object(module, "_spawn_controller_provider"))
            streams = module._ControllerStreams(self.root / "stream", stderr, self.root / "envelope",
                                                 stderr_fd=handle.fileno())
            outcome = module._ControllerOutcome()
            module._launch_controller_provider(self.logs, binding, module._ProviderExecution(), streams,
                                                module._ScopedLaunch(argv=["agy"]), outcome)
            self.assertFalse(spawn.called, "provider launch accepted executable configuration from the verified candidate")
            self.assertEqual(outcome.reason, "status_unavailable")
        self.assertIn(b"executable provider configuration", stderr.read_bytes())
        self.assertIn(b".agents/mcp_config.json", stderr.read_bytes())

    def test_workspace_config_worker_created_candidate_remains_inspectable(self) -> None:
        module = dispatch_module()
        stage = self.root / "post-provider-stage"
        stage.mkdir(mode=0o700)
        (stage / ".agents").mkdir(mode=0o700)
        (stage / ".agents/mcp_config.json").write_text("{}")
        scope = {"schema_version": 1, "kind": "agy-worker-provider-scope",
                 "read": [{"path": ".agents", "kind": "tree"}],
                 "write": [{"path": ".agents", "kind": "tree"}]}
        manifest = module.WORKTREE._build_selected_content_manifest(stage, scope, is_stage=True)
        self.assertIn(".agents/mcp_config.json", [entry["path"] for entry in manifest])
        mutations, _digest = module.WORKTREE._scan_stage_mutations(stage, scope, [])
        self.assertIn(".agents/mcp_config.json", [entry["path"] for entry in mutations])

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
