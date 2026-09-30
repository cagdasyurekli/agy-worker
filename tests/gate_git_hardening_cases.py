#!/usr/bin/env python3
"""Offline gate boundaries; runnable against any checkout with --root OLD_SOURCE."""
from __future__ import annotations

import argparse
import hashlib
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

    def test_verifier_cannot_stage_other_bytes_then_restore_worktree(self):
        candidate = "candidate bytes\n"
        (self.repo / "tracked.txt").write_text(candidate)
        script = (
            "from pathlib import Path; import subprocess,sys; "
            "p=Path('tracked.txt'); p.write_text('malicious staged bytes\\n'); "
            "subprocess.run(['/usr/bin/git','add','tracked.txt'],check=True); "
            "p.write_text(sys.argv[1])"
        )
        result = self.gate((("tracked.txt", "modified"),), verifier=[
            sys.executable, "-I", "-S", "-B", "-c", script, candidate,
        ])
        self.assert_code(14, result)
        self.assertIn("verifier changed the Git index for", result.stderr)
        self.assertIn("tracked.txt", result.stderr)
        self.assertEqual((self.repo / "tracked.txt").read_text(), candidate)
        self.assertEqual(self.git("show", ":tracked.txt"), b"malicious staged bytes\n")

    def test_verifier_read_only_git_is_accepted(self):
        (self.repo / "tracked.txt").write_text("candidate bytes\n")
        self.assert_code(0, self.gate((("tracked.txt", "modified"),), verifier=[
            "/usr/bin/git", "status", "--short",
        ]))

    def test_pre_staged_candidate_is_accepted_when_verifier_only_reads(self):
        (self.repo / "tracked.txt").write_text("candidate bytes\n")
        self.git("add", "tracked.txt")
        self.assert_code(0, self.gate((("tracked.txt", "modified"),), verifier=[
            "/usr/bin/git", "status", "--short",
        ]))

    def test_assume_unchanged_cannot_hide_worktree_bytes(self):
        self.git("update-index", "--assume-unchanged", "tracked.txt")
        (self.repo / "tracked.txt").write_text("hidden bytes\n")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported Git index flags", result.stderr)

    def test_skip_worktree_cannot_hide_worktree_bytes(self):
        self.git("update-index", "--skip-worktree", "tracked.txt")
        (self.repo / "tracked.txt").write_text("hidden bytes\n")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported Git index flags", result.stderr)

    def test_verifier_cannot_detach_same_head_commit(self):
        (self.repo / "tracked.txt").write_text("candidate bytes\n")
        result = self.gate((("tracked.txt", "modified"),), verifier=[
            "/usr/bin/git", "checkout", "--detach", "-q",
        ])
        self.assert_code(14, result)
        self.assertIn("verifier changed Git HEAD or the current branch", result.stderr)

    def test_verifier_cannot_move_current_branch_ref(self):
        (self.repo / "tracked.txt").write_text("candidate bytes\n")
        result = self.gate((("tracked.txt", "modified"),), verifier=[
            "/usr/bin/git", "commit", "--allow-empty", "-qm", "verifier",
        ])
        self.assert_code(14, result)
        self.assertIn("verifier changed Git HEAD or the current branch", result.stderr)

    def test_bounded_index_probe_fails_closed_on_output_cap(self):
        script = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        code = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); import candidate_state as c; "
            "r=c._checked_git_reader(Path(sys.argv[2])); "
            "r(Path(sys.argv[2]),'ls-files','--stage','-z',max_output_bytes=1,timeout_seconds=0.5)"
        )
        result = subprocess.run([
            sys.executable, "-I", "-S", "-B", "-c", code,
            str(script.parent), str(self.repo),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bounded limit", result.stderr)

    def test_caller_path_cannot_select_git_executable(self):
        shadow_directory = self.directory / "shadow-bin"
        shadow_directory.mkdir()
        shadow = shadow_directory / "git"
        shadow.write_text(
            f'#!/bin/sh\nprintf "invoked\\n" >> "{self.marker}"\n'
            'exec /usr/bin/git "$@"\n'
        )
        shadow.chmod(0o700)
        (self.repo / "tracked.txt").write_text("changed\n")
        result = self.gate((("tracked.txt", "modified"),), environment={
            "PATH": str(shadow_directory) + os.pathsep + self.environment.get("PATH", ""),
        })
        self.assert_code(0, result)
        self.assertFalse(self.marker.exists(), "gate executed caller PATH Git")

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
from candidate_state import GIT_EXECUTABLE, candidate_state_digest
from job_lifecycle import GIT_EXECUTABLE as LIFECYCLE_GIT_EXECUTABLE, git
assert GIT_EXECUTABLE == LIFECYCLE_GIT_EXECUTABLE == "/usr/bin/git"
repo, base = Path(sys.argv[2]), sys.argv[3]
assert candidate_state_digest(repo, base) == candidate_state_digest(repo, base, git_reader=git)
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", command,
                                 str(scripts), str(self.repo), self.base],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)

    def test_digest_checks_effective_filters_once_per_invocation(self):
        scripts = ROOT / "skills/agy-worker/runtime/scripts"
        command = """
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from candidate_state import CandidateStateError, _git, candidate_state_digest
repo, base = Path(sys.argv[2]), sys.argv[3]
actual_run = subprocess.run
filter_checks = []
def counted_run(command, *args, **kwargs):
    if "config" in command and "--includes" in command:
        filter_checks.append(command)
    return actual_run(command, *args, **kwargs)
with patch("subprocess.run", side_effect=counted_run):
    candidate_state_digest(repo, base)
    assert len(filter_checks) == 1, len(filter_checks)
    _git(repo, "rev-parse", "--is-inside-work-tree")
    _git(repo, "rev-parse", "--is-inside-work-tree")
    assert len(filter_checks) == 3, len(filter_checks)
    actual_run(["/usr/bin/git", "-C", str(repo), "config", "filter.late.required", "false"], check=True)
    try:
        candidate_state_digest(repo, base)
    except CandidateStateError:
        pass
    else:
        raise AssertionError("new digest did not recheck effective filters")
    assert len(filter_checks) == 4, len(filter_checks)
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", command,
                                 str(scripts), str(self.repo), self.base],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)

    def test_candidate_digest_stays_within_git_process_budget(self):
        # Deterministic speed guard: the snapshot runs several times per gate, so
        # each extra Git process multiplies. Raise the ceiling only with a reason.
        scripts = ROOT / "skills/agy-worker/runtime/scripts"
        (self.repo / "tracked.txt").write_text("candidate\n")
        command = """
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
git_processes = []
class CountingPopen(subprocess.Popen):
    def __init__(self, args, *rest, **kwargs):
        if args and str(args[0]).endswith("/git"):
            git_processes.append(args)
        super().__init__(args, *rest, **kwargs)
subprocess.Popen = CountingPopen
from candidate_state import candidate_state_digest
candidate_state_digest(Path(sys.argv[2]), sys.argv[3])
print(len(git_processes))
"""
        result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", command,
                                 str(scripts), str(self.repo), self.base],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)
        self.assertLessEqual(int(result.stdout.strip()), 10, result.stdout)

    def test_base_preflight_rejects_extra_git_action(self):
        helper = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        result = subprocess.run([
            sys.executable, "-I", "-S", "-B", str(helper),
            "--repo", str(self.repo), "--base", self.base,
            "--verify-base", "--git", "rev-parse", "HEAD",
        ], env=self.environment, capture_output=True, text=True)
        self.assert_code(64, result)

    def test_verifier_chmod_names_tracked_mode_change(self):
        result = self.gate(verifier=[sys.executable, "-I", "-S", "-B", "-c",
                                     "import os,sys; os.chmod(sys.argv[1], 0o755)",
                                     str(self.repo / "tracked.txt")])
        self.assert_code(14, result)
        self.assertIn('"tracked.txt" (mode changed 0644 to 0755)', result.stderr)

    def test_verifier_content_change_names_tracked_path(self):
        (self.repo / "tracked.txt").write_text("before verifier\n")
        result = self.gate((("tracked.txt", "modified"),), verifier=[
            sys.executable, "-I", "-S", "-B", "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('after verifier\\n')",
            str(self.repo / "tracked.txt"),
        ])
        self.assert_code(14, result)
        self.assertIn('"tracked.txt" (content or Git index changed)', result.stderr)

    def test_verifier_same_payload_kind_change_names_tracked_path(self):
        tracked = self.repo / "tracked.txt"
        tracked.chmod(0o755)
        self.commit()
        script = ("import os,sys; p=sys.argv[1]; "
                  "os.unlink(p); os.symlink('original\\n', p)")
        result = self.gate(verifier=[sys.executable, "-I", "-S", "-B", "-c",
                                     script, str(tracked)])
        self.assert_code(14, result)
        self.assertIn('"tracked.txt" (kind changed)', result.stderr)

    def test_diagnostic_walk_does_not_follow_symlink_or_enter_git(self):
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("private content\n")
        (self.repo / "linked").symlink_to(outside, target_is_directory=True)
        helper = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(helper),
                                 "--repo", str(self.repo), "--facts"],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)
        facts = json.loads(result.stdout)
        self.assertTrue(facts["complete"])
        self.assertIn("linked", [item[0] for item in facts["items"]])
        self.assertFalse(any(item[0].startswith(".git/") for item in facts["items"]))
        self.assertNotIn("private.txt", result.stdout)
        self.assertNotIn("private content", result.stdout)

    def test_bundled_facts_preserve_canonical_digest(self):
        helper = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        command = [sys.executable, "-I", "-S", "-B", str(helper),
                   "--repo", str(self.repo), "--base", self.base]
        digest = subprocess.run(command, env=self.environment, capture_output=True,
                                text=True, check=True).stdout.strip()
        bundled = subprocess.run([*command, "--digest-facts"], env=self.environment,
                                 capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(bundled[0], digest)
        self.assertTrue(json.loads(bundled[1])["complete"])

    def test_diagnostic_mode_and_payload_are_unambiguous(self):
        # Without the separator, mode 44 + b"4x" and mode 444 + b"x" collide.
        helper = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(helper),
                                 "--repo", str(self.repo), "--facts"],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)
        fact = next(item for item in json.loads(result.stdout)["items"]
                    if item[0] == "tracked.txt")
        expected = hashlib.sha256(str(fact[2]).encode("ascii") + b"\0"
                                  + b"original\n" + b"file").hexdigest()
        self.assertEqual(fact[3], expected)

    def test_diagnostic_content_limit_is_incomplete(self):
        (self.repo / "large.dat").write_bytes(b"x" * (8 * 1024 * 1024 + 1))
        helper = ROOT / "skills/agy-worker/runtime/scripts/candidate_state.py"
        result = subprocess.run([sys.executable, "-I", "-S", "-B", str(helper),
                                 "--repo", str(self.repo), "--facts"],
                                env=self.environment, capture_output=True, text=True)
        self.assert_code(0, result)
        self.assertEqual(json.loads(result.stdout), {"complete": False, "items": []})

    def test_diagnostic_path_limit_uses_generic_mutation_message(self):
        script = ("from pathlib import Path; import sys; "
                  "root=Path(sys.argv[1]); "
                  "[(root / f'bulk-{i:03d}').write_text('x') for i in range(65)]")
        result = self.gate(verifier=[sys.executable, "-I", "-S", "-B", "-c",
                                     script, str(self.repo)])
        self.assert_code(14, result)
        self.assertIn("path diagnostics incomplete", result.stderr)
        self.assertNotIn("new path", result.stderr)

    def test_direct_envelope_control_drift_after_verification_is_rejected(self):
        if options.mode != "direct":
            self.skipTest("receipt mode uses an immutable envelope snapshot")
        envelope = self.directory / "envelope.json"
        script = ("import json,sys; from pathlib import Path; "
                  "p=Path(sys.argv[1]); value=json.loads(p.read_text()); "
                  "value['status']='blocked'; p.write_text(json.dumps(value))")
        result = self.gate(verifier=[sys.executable, "-I", "-S", "-B", "-c",
                                     script, str(envelope)])
        self.assert_code(10, result)
        self.assertNotIn("Traceback", result.stderr)

    def test_direct_envelope_type_drift_fails_without_traceback(self):
        if options.mode != "direct":
            self.skipTest("receipt mode uses an immutable envelope snapshot")
        envelope = self.directory / "envelope.json"
        script = ("import json,sys; from pathlib import Path; "
                  "p=Path(sys.argv[1]); value=json.loads(p.read_text()); "
                  "value['requires_human']='yes'; p.write_text(json.dumps(value))")
        result = self.gate(verifier=[sys.executable, "-I", "-S", "-B", "-c",
                                     script, str(envelope)])
        self.assert_code(10, result)
        self.assertIn("cannot establish scope", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *unittest_arguments], verbosity=2)
