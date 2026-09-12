#!/usr/bin/env bash
# Stop-hook gate. Exit 2 => Claude is NOT allowed to stop; stderr becomes the reason.
# Deterministic on purpose: a prompt-hook asking "are you done?" cannot verify a build.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Loop guard: never block more than twice in a row for the same failure.
GUARD="${TMPDIR:-/tmp}/stylelab-gate-$(basename "$PWD")"
COUNT=$(cat "$GUARD" 2>/dev/null || echo 0)
if [ "$COUNT" -ge 2 ]; then echo 0 > "$GUARD"; exit 0; fi

# Nothing to gate until the web app exists.
[ -f apps/web/package.json ] || exit 0

FAIL=""
pnpm --filter web typecheck >/tmp/gate-tsc.log 2>&1 || FAIL="typecheck"
[ -z "$FAIL" ] && { pnpm --filter web lint >/tmp/gate-lint.log 2>&1 || FAIL="lint"; }

if [ -n "$FAIL" ]; then
  echo $((COUNT+1)) > "$GUARD"
  echo "Phase gate failed: $FAIL is broken. Fix it before ending the turn." >&2
  tail -30 "/tmp/gate-${FAIL/typecheck/tsc}.log" >&2
  exit 2
fi

echo 0 > "$GUARD"
exit 0
