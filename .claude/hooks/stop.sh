#!/usr/bin/env bash
# Stop hook — enforce HANDOFF.md freshness when the working tree is dirty.
#
# Fires when the main agent finishes responding. Blocks the stop (exit 2, stderr
# fed back to Claude) only when BOTH are true:
#   1. the git working tree has uncommitted changes, and
#   2. HANDOFF.md was not modified in the last 30 minutes.
# Clean tree, recent HANDOFF, non-repo, or a re-entrant stop all pass silently.

set -uo pipefail

INPUT="$(cat)"

# Loop guard: when Claude is already responding to a previous block, this field is
# true. Allow the stop so we never trap the session in an infinite block loop.
if printf '%s' "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# Non-repo or clean working tree → nothing to hand off → allow stop.
# (git status on a non-repo prints nothing to stdout, so the empty check covers
# both cases without a separate `git rev-parse` probe.)
if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  exit 0
fi

HANDOFF="$PROJECT_DIR/HANDOFF.md"

# HANDOFF.md exists and was touched within the last 30 minutes → allow stop.
if [ -f "$HANDOFF" ] && [ -n "$(find "$HANDOFF" -mmin -30 2>/dev/null)" ]; then
  exit 0
fi

# Dirty tree + stale/missing HANDOFF → block and tell Claude what to write.
cat >&2 <<'EOF'
[stop-hook] BLOCKED: uncommitted changes exist but HANDOFF.md was not updated in the last 30 minutes.

Update HANDOFF.md with the current state (follow the schema in HANDOFF.template.md),
then COMMIT it — or otherwise clean the working tree. Editing HANDOFF.md alone only
suppresses this for 30 minutes; while the tree stays dirty the block re-fires.
EOF
exit 2
