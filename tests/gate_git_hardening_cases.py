#!/usr/bin/env python3
"""Offline gate boundaries; runnable against any checkout with --root OLD_SOURCE."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--mode", choices=("direct", "receipt"), required=True)
options, unittest_arguments = parser.parse_known_args()
ROOT = options.root.resolve()


class GateGitHardening(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gate-git-hardening-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.environment = {k: v for k, v in os.environ.items()
                            if not k.startswith("GIT_")}
        self.environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        (self.repo / "tracked.txt").write_text("original\n")
        (self.repo / ".gitignore").write_text("ignored.tmp\n")
        self.commit()
        self.marker = self.directory / "executed"
        self.receipt_number = 0

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              env=self.environment, capture_output=True, check=True).stdout

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def gate(self, changes=(), *policy, environment=None, verifier=None):
        self.receipt_number += 1
        envelope = self.directory / "envelope.json"
        envelope.write_text(json.dumps({
            "status": "completed", "summary": "fixture",
            "files_changed": [{"path": p, "change": k} for p, k in changes],
            "commands_run": [], "tests_run": [], "risks": [],
            "open_questions": [], "confidence": 1, "requires_human": False,
        }))
        command = [str(ROOT / ("qa-gate.sh" if options.mode == "direct" else "verify-job.sh"))]
        receipt = self.directory / f"receipt-{self.receipt_number}.json"
        if options.mode == "receipt":
            command += ["--receipt", str(receipt)]
        command += ["--repo", str(self.repo), "--base", self.base,
                    "--envelope", str(envelope), "--verify-argv",
                    json.dumps(verifier or ["/usr/bin/true"], separators=(",", ":")), *policy]
        result = subprocess.run(command, env={**self.environment, **(environment or {})},
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0 and receipt.exists():
            value = json.loads(receipt.read_text())
            self.assertNotEqual(value["verdict"], "gate-passed")
            self.assertNotEqual(value["gate_outcome"], "gate-passed")
        return result

    def assert_code(self, expected, result):
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def monitor(self):
        hook = self.directory / "monitor.sh"
        hook.write_text(f'#!/bin/sh\ntouch "{self.marker}"\nprintf "tok\\0"\n')
        hook.chmod(0o700)
        self.git("config", "core.fsmonitor", str(hook))
        self.git("config", "core.fsmonitorHookVersion", "2")
        self.git("update-index", "--fsmonitor")
        self.git("status", "--porcelain")
        self.git("status", "--porcelain")
        self.marker.unlink(missing_ok=True)

    def test_lying_fsmonitor_cannot_hide_undeclared_edit(self):
        self.monitor()
        time.sleep(1)
        (self.repo / "tracked.txt").write_text("TAMPERED\n")
        # No Git reads between the stale-index setup and the gate under test.
        self.assert_code(10, self.gate())
        self.assertFalse(self.marker.exists(), "gate executed fsmonitor")

    def test_fsmonitor_is_neutralized_without_rejecting_clean_repository(self):
        self.monitor()
        self.assert_code(0, self.gate())
        self.assertFalse(self.marker.exists(), "gate executed fsmonitor")

    def test_caller_git_variables_cannot_steer_reads(self):
        (self.repo / "tracked.txt").write_text("changed\n")
        for environment in (
            {"GIT_DIR": str(self.directory / "missing")},
            {"GIT_WORK_TREE": str(self.directory)},
            {"GIT_INDEX_FILE": str(self.directory / "missing-index")},
            {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"},
            {"GIT_CONFIG_PARAMETERS": "'core.bare=true'"},
        ):
            with self.subTest(environment=next(iter(environment))):
                self.assert_code(0, self.gate((("tracked.txt", "modified"),), environment=environment))

    def test_caller_git_directory_cannot_hide_edit_in_another_repository(self):
        other = self.directory / "other"
        shutil.copytree(self.repo, other)
        (self.repo / "tracked.txt").write_text("changed\n")
        self.assert_code(10, self.gate(environment={
            "GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}))

    def test_clean_filter_is_rejected_without_execution(self):
        (self.repo / ".gitattributes").write_text("tracked.txt filter=untrusted\n")
        self.commit()
        hook = self.directory / "filter.sh"
        hook.write_text(f'#!/bin/sh\ntouch "{self.marker}"\ncat >/dev/null\nprintf "original\\n"\n')
        hook.chmod(0o700)
        self.git("config", "filter.untrusted.clean", str(hook))
        (self.repo / "tracked.txt").write_text("tampered content\n")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content-filter configuration", result.stderr)
        self.assertNotIn(str(hook), result.stderr)
        self.assertFalse(self.marker.exists(), "gate executed clean filter")

    def test_process_filter_is_rejected_without_execution(self):
        (self.repo / ".gitattributes").write_text("tracked.txt filter=untrusted\n")
        self.commit()
        hook = self.directory / "process.sh"
        hook.write_text(f'#!/bin/sh\ntouch "{self.marker}"\nexit 1\n')
        hook.chmod(0o700)
        self.git("config", "filter.untrusted.process", str(hook))
        (self.repo / "tracked.txt").write_text("tampered content\n")
        result = self.gate((("tracked.txt", "modified"),))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content-filter configuration", result.stderr)
        self.assertFalse(self.marker.exists(), "gate executed process filter")

    def test_verifier_added_filter_fails_closed_without_execution(self):
        (self.repo / ".gitattributes").write_text("tracked.txt filter=untrusted\n")
        self.commit()
        hook = self.directory / "late-filter.sh"
        hook.write_text(f'#!/bin/sh\ntouch "{self.marker}"\ncat\n')
        hook.chmod(0o700)
        (self.repo / "tracked.txt").write_text("changed\n")
        script = (
            "from pathlib import Path; import sys; "
            "p=Path(sys.argv[1]); p.write_text(p.read_text()+sys.argv[2]); "
            "q=Path(sys.argv[3]); q.write_text('changed after verification\\n')"
        )
        result = self.gate((("tracked.txt", "modified"),), verifier=[
            sys.executable, "-I", "-S", "-B", "-c", script,
            str(self.repo / ".git/config"),
            f'\n[filter "untrusted"]\n clean = {hook}\n',
            str(self.repo / "tracked.txt"),
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content-filter configuration", result.stderr)
        self.assertFalse(self.marker.exists(), "snapshot executed verifier-added filter")

    def test_true_required_definition_is_rejected(self):
        self.git("config", "filter.untrusted.required", "true")
        self.assertNotEqual(self.gate().returncode, 0)

    def test_empty_clean_definition_is_rejected(self):
        self.git("config", "filter.untrusted.clean", "")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content-filter configuration", result.stderr)

    def test_empty_process_definition_is_rejected(self):
        self.git("config", "filter.untrusted.process", "")
        self.assertNotEqual(self.gate().returncode, 0)

    def test_false_required_definition_is_rejected(self):
        self.git("config", "filter.untrusted.required", "false")
        self.assertNotEqual(self.gate().returncode, 0)

    def test_included_mixed_case_filter_is_rejected(self):
        config = self.directory / "included.config"
        config.write_text('[FiLtEr "MixedCase"]\n ClEaN = PRIVATE-VALUE\n')
        self.git("config", "include.path", str(config))
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("content-filter configuration", result.stderr)
        self.assertNotIn("PRIVATE-VALUE", result.stderr)

    def test_conditional_include_filter_is_rejected(self):
        config = self.directory / "conditional.config"
        config.write_text('[filter "driver"]\n required = false\n')
        self.git("config", f"includeIf.gitdir:{self.repo}/.git.path", str(config))
        self.assertNotEqual(self.gate().returncode, 0)

    def test_worktree_filter_configuration_is_rejected(self):
        self.git("config", "extensions.worktreeConfig", "true")
        self.git("config", "--worktree", "filter.driver.process", "")
        self.assertNotEqual(self.gate().returncode, 0)

    def test_global_configuration_is_ignored(self):
        config = self.directory / "global.config"
        config.write_text('[core]\n bare = true\n[filter "driver"]\n required = false\n')
        self.assert_code(0, self.gate(environment={"GIT_CONFIG_GLOBAL": str(config)}))

    def test_external_diff_and_textconv_do_not_execute(self):
        (self.repo / ".gitattributes").write_text("tracked.txt diff=untrusted\n")
        self.commit()
        hook = self.directory / "diff.sh"
        hook.write_text(f'#!/bin/sh\ntouch "{self.marker}"\nexit 0\n')
        hook.chmod(0o700)
        self.git("config", "diff.external", str(hook))
        self.git("config", "diff.untrusted.textconv", str(hook))
        (self.repo / "tracked.txt").write_text("changed\n")
        self.assert_code(0, self.gate((("tracked.txt", "modified"),)))
        self.assertFalse(self.marker.exists())

    def test_normal_staged_unstaged_untracked_and_ignored_changes(self):
        (self.repo / "tracked.txt").write_text("staged\n")
        self.git("add", "tracked.txt")
        (self.repo / "tracked.txt").write_text("unstaged\n")
        (self.repo / "new.txt").write_text("new\n")
        (self.repo / "ignored.tmp").write_text("ignored\n")
        self.assert_code(0, self.gate((("tracked.txt", "modified"),
                                     ("new.txt", "created"), ("ignored.tmp", "created")),
                                    "--only", "**"))

    def path_case(self, path, pattern, expected, flag="--only"):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("new\n")
        changes = ((path, "created"),) if flag == "--only" else ()
        self.assert_code(expected, self.gate(changes, flag, pattern))

    def test_star_cannot_cross_segments(self):
        self.path_case("src/a/b.py", "src/*.py", 10)

    def test_question_mark_cannot_cross_segments(self):
        self.path_case("src/a/b.py", "src/a?b.py", 10)

    def test_allow_cannot_cross_segments(self):
        self.path_case("a/b/secret.log", "*.log", 10, "--allow")

    def test_globstar_matches_zero_segments(self):
        self.path_case("src/x.py", "src/**/*.py", 0)

    def test_globstar_matches_multiple_segments(self):
        self.path_case("src/a/b.py", "src/**/*.py", 0)

    def test_globstar_alone_matches_everything(self):
        self.path_case("src/a/b.py", "**", 0)

    def test_documented_tests_glob(self):
        self.path_case("tests/deep/case.py", "tests/**", 0)

    def test_allow_globstar_matches_zero_segments(self):
        self.path_case("result.log", "**/*.log", 0, "--allow")

    def test_candidate_digest_matches_lifecycle_with_color_config(self):
        self.git("config", "color.ui", "always")
        (self.repo / "tracked.txt").write_text("changed\n")
        scripts = ROOT / "skills/agy-worker/runtime/scripts"
        command = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from candidate_state import candidate_state_digest
from job_lifecycle import git
repo, base = Path(sys.argv[2]), sys.argv[3]
assert candidate_state_digest(repo, base) == candidate_state_digest(repo, base, git_reader=git)
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", command,
                                 str(scripts), str(self.repo), self.base],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *unittest_arguments], verbosity=2)
