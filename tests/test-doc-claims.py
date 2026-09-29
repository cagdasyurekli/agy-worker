"""Check the public host, approval, and lifecycle claims as one contract."""

from pathlib import Path
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
checks = {
    "approval digest distinguishes whole and scoped bindings": (
        "full file mode bits, symlink target hashes" in skill
        and "scoped mode rejects symlinks and does" in skill
        and "not bind full POSIX permissions" in skill
        and "Neither digest binds task text" in skill
        and "SHA values bind that decision" not in skill
        and "Neither approval digest binds task text" in project
        and "Show the exact task" in skill
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
