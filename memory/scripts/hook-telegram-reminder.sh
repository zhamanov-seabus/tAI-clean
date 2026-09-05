#!/bin/bash
# Claude Code UserPromptSubmit hook — Telegram delivery reminder.
# Injects a hard reminder on every inbound message so the daemon always routes
# its answer through the reply tool instead of emitting plain transcript text
# (which never reaches the user). Paired with the Stop safety net in
# hook-telegram-forward.py.
cat <<'EOF'
[Telegram daemon reminder] The user reads ONLY messages sent via the mcp__plugin_telegram_telegram__reply tool. Plain assistant/transcript text NEVER reaches their chat. Before ending this turn, send your actual answer through the reply tool. Reactions do not carry text.
EOF
exit 0
