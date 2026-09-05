#!/bin/bash
# Claude Code Stop hook — closes the tai-memory session opened at SessionStart.
# Uses auto-close-session, which preserves a real summary the model set during
# the session and otherwise derives one from the session's latest task. It
# never clobbers real content with a static placeholder.
set -e

PROJECT_ROOT="__TAI_HOME__"
TAI_MEM="$PROJECT_ROOT/.venv/bin/tai-mem"
SESSION_FILE="$PROJECT_ROOT/.tai-mem-current-session"

[[ -f "$SESSION_FILE" ]] || exit 0
SID=$(cat "$SESSION_FILE")

if [[ -x "$TAI_MEM" && -n "$SID" ]]; then
    "$TAI_MEM" auto-close-session "$SID" 2>/dev/null || true
fi

rm -f "$SESSION_FILE"
