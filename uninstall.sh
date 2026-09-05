#!/usr/bin/env bash
# tAI uninstaller. Stops the daemon, removes services, scripts, config and the
# tai-memory install. Use --purge to ALSO drop the Postgres data + Telegram token.
#
#   ./uninstall.sh            # remove daemon/services/scripts/config (keep DB data + token)
#   ./uninstall.sh --purge    # ALSO wipe memory DB volume + telegram token + agent defs
set -uo pipefail
HOME_DIR="${HOME}"
TAI_HOME="${TAI_HOME:-$HOME/tai}"
OS="$(uname -s)"
PURGE=0; for a in "$@"; do [ "$a" = "--purge" ] && PURGE=1; done
say(){ printf "\033[1;36m==>\033[0m %s\n" "$*"; }

say "Stopping the daemon..."
if [ "$OS" = Darwin ]; then
  launchctl bootout "gui/$(id -u)/com.claudet" 2>/dev/null || true
  launchctl bootout "gui/$(id -u)/com.claudet-watchdog" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.claudet.plist" "$HOME/Library/LaunchAgents/com.claudet-watchdog.plist"
else
  systemctl --user stop claudet claudet-watchdog.timer 2>/dev/null || true
  systemctl --user disable claudet claudet-watchdog.timer 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/claudet.service" \
        "$HOME/.config/systemd/user/claudet-watchdog.service" \
        "$HOME/.config/systemd/user/claudet-watchdog.timer"
  systemctl --user daemon-reload 2>/dev/null || true
fi
tmux -L claudet kill-server 2>/dev/null || true

say "Removing daemon scripts..."
rm -f "$HOME/.local/bin/claudet" "$HOME/.local/bin/claudet-launchd" \
      "$HOME/.local/bin/claudet-launchd-inner" "$HOME/.local/bin/claudet-watchdog" \
      "$HOME/.local/bin/claudet-notify" "$HOME/.local/bin/claudet-ctx-tokens"

say "Stopping Postgres container..."
if [ -f "$TAI_HOME/docker-compose.yml" ]; then
  if [ "$PURGE" = 1 ]; then ( cd "$TAI_HOME" && docker compose down -v 2>/dev/null || docker-compose down -v 2>/dev/null || true )
  else ( cd "$TAI_HOME" && docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true ); fi
fi

say "Removing tai-memory install ($TAI_HOME)..."
rm -rf "$TAI_HOME"

if [ "$PURGE" = 1 ]; then
  say "Purging Telegram token + agent defs..."
  rm -rf "$HOME/.claude/channels/telegram"
  rm -f "$HOME/.claude/agents/codex.md" "$HOME/.claude/agents/gemini.md"
fi

say "Done. (Claude Code CLI, Docker, and the Telegram plugin were left installed.)"
[ "$PURGE" = 0 ] && say "Kept: Postgres data volume + Telegram token. Re-run with --purge to wipe those too."
