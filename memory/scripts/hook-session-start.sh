#!/bin/bash
# Claude Code SessionStart hook — opens a tai-memory session and stashes its ID.
set -e

PROJECT_ROOT="__TAI_HOME__"
TAI_MEM="$PROJECT_ROOT/.venv/bin/tai-mem"
SESSION_FILE="$PROJECT_ROOT/.tai-mem-current-session"

if [[ ! -x "$TAI_MEM" ]]; then
    echo "tai-mem not found at $TAI_MEM — skipping SessionStart hook" >&2
    exit 0
fi

SID=$("$TAI_MEM" start-session 2>/dev/null) || exit 0
echo "$SID" > "$SESSION_FILE"

# When running as the always-on Telegram daemon (CLAUDET_DAEMON=1 set in the
# launchd plist), ping the owner that a fresh session is live. This makes every
# restart visible instead of silent. Plain dev sessions don't set the flag,
# so they stay quiet.
if [[ "${CLAUDET_DAEMON:-}" == "1" ]]; then
    NOTIFY="__HOME__/.local/bin/claudet-notify"
    if [[ -x "$NOTIFY" ]]; then
        TS=$(date "+%H:%M %d.%m")
        "$NOTIFY" "🟢 Снова онлайн ($TS). Новая сессия поднята — если писал в последние минуты, повтори, я мог не увидеть." &
    fi
fi
