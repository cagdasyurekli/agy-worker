"""Check the public host, approval, and lifecycle claims as one contract."""

from pathlib import Path
import contextlib
import importlib.util
import io
import re
import shlex
import sys


root = Path(sys.argv[1])


def read(name: str) -> str:
    return (root / name).read_text(encoding="utf-8")


skill = read("skills/agy-worker/SKILL.md")
lifecycle = read("skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md")
security = read("skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md")
troubleshooting = read("skills/agy-worker/references/TROUBLESHOOTING.md")
project = read("docs/PROJECT_WORKFLOW.md")
installation = read("docs/INSTALLATION.md")
usage = read("docs/USAGE.md")
def quick_path_contract(text: str) -> bool:
    """The Quick path must be one ordered cycle whose flags the real CLIs accept."""
    heading = text.find("Quick path")
    blocks = re.findall(r"```bash\n(.*?)```", text[heading:], re.S) if heading >= 0 else []
    if not blocks or "#verification-v2" not in text[heading:]:
        return False
    lines = [ln for ln in blocks[0].replace("\\\n", " ").splitlines() if not ln.lstrip().startswith("#")]
    calls = []
    for ln in lines:
        match = re.search(r'"\$PIPELINE/(workflow\.sh|agy-worker\.sh)"\s+(.*)', ln)
        if match:
            argv = shlex.split(match.group(2).split(") ||")[0])
            calls.append((match.group(1), argv[: argv.index(">")] if ">" in argv else argv))
    seq = [(s, argv[0], set(argv)) for s, argv in calls]
    expected = [
        ("workflow.sh", "run", {"--preview"}),
        ("workflow.sh", "run", {"--approve-transmission-sha"}),
        ("workflow.sh", "status", {"--repo", "--job-id"}),
        ("agy-worker.sh", "verification-copy", {"--job-id", "--state", "--destination"}),
        ("workflow.sh", "verify-finalize", {"--approve-dispatch-sha", "--verification-json"}),
    ]
    if len(seq) != len(expected) or any(
        s != es or c != ec or not flags >= ef for (s, c, flags), (es, ec, ef) in zip(seq, expected)
    ):
        return False
    if "--preview" in seq[1][2] or "--state" in seq[2][2]:
        return False
    scripts = root / "skills/agy-worker/runtime/scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("workflow_quick_path", scripts / "workflow.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parser = module.build_parser()
    for script, argv in calls:
        if script == "agy-worker.sh":
            usage = (root / "skills/agy-worker/runtime/agy-worker.sh").read_text(encoding="utf-8")
            if not all(flag in usage for flag in argv if flag.startswith("--")):
                return False
            continue
        try:  # parse_args rejects unknown flags, missing required ones and bad choices
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(argv)
        except SystemExit:
            return False
    return True


checks = {
    "approval request discloses fixed delegation overhead": (
        "fixed agy overhead can make direct work faster" in skill
        and "let the user choose" in skill
        and "### When delegation is worth it" in usage
        and "Do not claim time or token savings" in usage
    ),
    "approval digest distinguishes whole and scoped bindings": (
        "full file mode bits, symlink target hashes" in skill
        and "scoped mode rejects symlinks and does" in skill
        and "not bind full POSIX permissions" in skill
        and "The human approves one `launch_approval_sha256` over canonical" in skill
        and "SHA values bind that decision" not in skill
        and "One `launch_approval_sha256` binds the full launch authority" in project
        and "Preview the\nexact task and all launch options" in skill
    ),
    "headless Claude dispatch lifetime": (
        "in non-interactive `claude -p` or SDK runs, dispatch in the foreground" in skill
        and "never end the turn while a job runs" in skill
        and "headless session exit cancels background work" in lifecycle
    ),
    "mandatory Git-neutral finalization": (
        "When `status` offers finalization for a bound candidate, `verify-finalize` records the"
        in skill
        and "driver's result without a Git change and is the facade's required closure step"
        in skill
        and "to finish every job" not in skill
    ),
    "private approval checklist covers excluded settings": (
        "The exact task text (not the shorter public-safe launch notice)" in lifecycle
        and "workflow/edit" in lifecycle
        and "retry/time budget" in lifecycle
        and "exact scope policy and preview digest" in lifecycle
        and "provider isolation mode and native grant profile" in lifecycle
        and "`--allow-scoped-repair`" in lifecycle
        and "each manifest check's exact `argv`, ID, required/optional flag" in lifecycle
        and "manifest's total time limit" in lifecycle
        and "Each `--provider-env` and `--verify-env` name" in lifecycle
        and "out of\nthe provider preview and prompt" in lifecycle
    ),
    "facade-created worktree and sorted scope quick path": (
        'run --preview --repo "$TARGET" --job-id "$JOB_ID" --provider-scope "$SCOPE"'
        in skill
        and "entries sorted by path" in skill
        and "the facade creates the branch-backed disposable worktree" in lifecycle
    ),
    "quick path is one ordered cycle with flags the real CLIs accept": (
        quick_path_contract(skill)
    ),
    "nested Seatbelt host prerequisite": (
        "Codex `workspace-write`" in security
        and "sandbox_apply: Operation not permitted" in troubleshooting
        and "keep the requested" in installation
    ),
    "supported Claude Code label and headless note": (
        "OpenAI Codex CLI and Claude Code." in skill
        and "Claude Code host operation was live-tested with synthetic jobs" in read("docs/MARKETPLACE.md")
        and "keep headless sessions active until dispatch completes" in read(".claude-plugin/plugin.json")
        and all(
            "experimental: pending live verification" not in read(name)
            for name in (
                "README.md", "docs/INSTALLATION.md", "docs/MARKETPLACE.md",
                "docs/REPO_MAP.md", "docs/ROADMAP.md", "skills/agy-worker/README.md",
                "skills/agy-worker/SKILL.md",
                "skills/agy-worker/references/SECURITY_AND_COMPATIBILITY.md",
                "skills/agy-worker/references/PROJECT_LIFECYCLE_AND_VERIFICATION.md",
            )
        )
    ),
}
failed = [label for label, passed in checks.items() if not passed]
for label in failed:
    print(f"FAIL: {label}", file=sys.stderr)
if failed:
    raise SystemExit(1)
print(f"ok: {len(checks)} public host and approval claim checks")
