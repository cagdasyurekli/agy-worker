#!/usr/bin/env bash
# Repository-only tool; core workflow runtime remains in the skill package.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec /usr/bin/python3 -I -S -B "$SCRIPT_DIR/scripts/codex_usage_report.py" "$@"
