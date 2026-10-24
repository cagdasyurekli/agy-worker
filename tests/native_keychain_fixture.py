#!/usr/bin/env python3
"""Copy the skill and point its dedicated-Keychain seams at a synthetic file.

Offline suites cannot depend on the developer's real ``agy-worker-provider`` keychain.
The copy keeps every other byte of the runtime; a ``<keychain>.locked`` marker file
makes the copied lock probe report a locked keychain. Usage: DESTINATION KEYCHAIN_PATH.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH_LINE = '    return owner_home / "Library" / "Keychains" / DEDICATED_KEYCHAIN_NAME\n'
PROBE_LINE = "def _keychain_is_unlocked(path: str) -> bool:\n"


def build(destination: Path, keychain: Path) -> Path:
    """Return the patched skill copy's ``runtime/agy-worker.sh``."""
    shutil.copytree(
        ROOT / "skills" / "agy-worker", destination,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    module = destination / "runtime" / "scripts" / "agy_dispatch_containment.py"
    text = module.read_text(encoding="utf-8")
    if text.count(PATH_LINE) != 1 or text.count(PROBE_LINE) != 1:
        raise SystemExit("native keychain fixture seams changed")
    text = text.replace(PATH_LINE, f"    return Path({str(keychain)!r})\n")
    text = text.replace(
        PROBE_LINE, PROBE_LINE + '    return not os.path.exists(path + ".locked")\n',
    )
    module.write_text(text, encoding="utf-8")
    return destination / "runtime" / "agy-worker.sh"


if __name__ == "__main__":
    print(build(Path(sys.argv[1]), Path(sys.argv[2])))
