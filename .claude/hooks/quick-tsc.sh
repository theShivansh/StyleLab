#!/usr/bin/env bash
# Async background typecheck after TS edits. Never blocks; surfaces nothing on success.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -f apps/web/package.json ] || exit 0
pnpm --filter web typecheck >/dev/null 2>&1
exit 0
