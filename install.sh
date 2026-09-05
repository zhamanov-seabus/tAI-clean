#!/usr/bin/env bash
# tAI installer — sets up the always-on Claude Code + Telegram daemon,
# the tai-memory system, and cross-vendor (Codex/Gemini) agent definitions.
#
# Usage:  ./install.sh            (interactive)
#         TAI_HOME=~/tai ./install.sh
#
# This does the mechanical wiring. Three things you must do yourself (printed
# at the end): (1) authenticate Claude Code, (2) set the Telegram bot token,
# (3) optionally install the Codex/Gemini CLIs.

set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${HOME}"
TAI_HOME="${TAI_HOME:-$HOME/tai}"
BIN="$HOME/.local/bin"
AGENTS_DIR="$HOME/.claude/agents"
# Postgres backend: "docker" (default, zero-sudo pgvector container on :5544)
# or "system" (local Postgres on :5432, needs admin). Override: --system-pg
PG_MODE="${PG_MODE:-docker}"
DEPS="${DEPS:-1}"        # auto-install prerequisites unless --no-deps
for a in "$@"; do case "$a" in
  --system-pg) PG_MODE="system" ;;
  --docker-pg) PG_MODE="docker" ;;
  --no-deps)   DEPS=0 ;;
esac; done
DC() { if docker compose version >/dev/null 2>&1; then docker compose "$@"; else docker-compose "$@"; fi; }
pkg_install() {
  if [ "$OS" = "Darwin" ]; then
    have brew || { say "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null || true)"; }
    brew install "$@"
  elif have apt-get; then sudo apt-get update -y && sudo apt-get install -y "$@"
  elif have dnf; then sudo dnf install -y "$@"
  elif have pacman; then sudo pacman -S --noconfirm "$@"
  else warn "No known package manager — install manually: $*"; fi
}

say() { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
# Claude Code stores per-project state at ~/.claude/projects/<cwd with / -> ->.
PROJ_DIR="$HOME_DIR/.claude/projects/$(printf '%s' "${TAI_HOME%/}" | sed 's#/#-#g')"
TMUX_BIN="$(command -v tmux || echo tmux)"
subst() { sed "s#__TAI_HOME__#${TAI_HOME}#g; s#__PROJ_DIR__#${PROJ_DIR}#g; s#__TMUX_BIN__#${TMUX_BIN}#g; s#__HOME__#${HOME_DIR}#g" "$1"; }

OS="$(uname -s)"
say "OS: $OS   |   TAI_HOME: $TAI_HOME"

# ---------- 0. Auto-install prerequisites (skip with --no-deps) ----------
if [ "$DEPS" = "1" ]; then
  say "Installing prerequisites (use --no-deps to skip)..."
  have git || pkg_install git
  have uv  || { say "Installing uv..."; curl -fsSL https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
  have tmux   || pkg_install tmux
  have expect || pkg_install expect
  # node/npm power the optional key-free image tools (Gemini web). Best-effort.
  have node   || pkg_install nodejs npm || warn "node not installed — image tools will be inactive."
  if [ "$PG_MODE" = "docker" ] && ! have docker; then
    if [ "$OS" = "Darwin" ]; then
      say "Installing Docker runtime (Colima — no GUI, scriptable)..."
      pkg_install colima docker docker-compose || warn "Install colima+docker manually."
    else
      say "Installing Docker engine..."; curl -fsSL https://get.docker.com | sh || warn "Install docker manually."
    fi
  fi
  # compose plugin if missing (Linux docker.io often ships without it)
  if [ "$PG_MODE" = "docker" ] && have docker && ! docker compose version >/dev/null 2>&1 && ! have docker-compose; then
    pkg_install docker-compose-v2 || pkg_install docker-compose-plugin || warn "Install 'docker compose' manually."
  fi
  # macOS: bring up the Colima VM
  if [ "$OS" = "Darwin" ] && have colima; then colima status >/dev/null 2>&1 || { say "Starting Colima..."; colima start; }; fi
  # Linux: ensure daemon + docker group
  if [ "$OS" != "Darwin" ] && [ "$PG_MODE" = "docker" ] && have docker && ! docker info >/dev/null 2>&1; then
    sudo systemctl enable --now docker 2>/dev/null || true
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    warn "Added you to 'docker' group — you may need to re-login (or: newgrp docker)."
  fi
  TMUX_BIN="$(command -v tmux || echo tmux)"   # recompute now that tmux is installed
fi

# ---------- 1. Prerequisites ----------
say "Checking prerequisites..."
MISSING=()
have claude || MISSING+=("claude (Claude Code CLI — install from claude.com/claude-code)")
have uv     || MISSING+=("uv (Python package manager — astral.sh/uv)")
have git    || MISSING+=("git")
if [ "$PG_MODE" = "docker" ]; then
  if ! have docker; then
    MISSING+=("docker (Docker Desktop / docker engine — for the pgvector container)")
  elif ! docker compose version >/dev/null 2>&1 && ! have docker-compose; then
    MISSING+=("docker compose v2 (Linux: sudo apt install docker-compose-v2  /  or Docker Desktop)")
  elif ! docker info >/dev/null 2>&1; then
    MISSING+=("docker daemon not reachable — start it (sudo systemctl start docker) and ensure your user is in the 'docker' group (sudo usermod -aG docker \$USER; re-login). Or use --system-pg.")
  fi
else
  have psql   || MISSING+=("postgresql@17 (brew install postgresql@17  /  apt install postgresql)")
fi
if [ "$OS" = "Darwin" ]; then
  have tmux   || MISSING+=("tmux (brew install tmux)")
  have expect || MISSING+=("expect (brew install expect)")
fi
if [ ${#MISSING[@]} -gt 0 ]; then
  warn "Missing prerequisites:"; printf '   - %s\n' "${MISSING[@]}"
  warn "Install them and re-run."; exit 1
fi
say "All prerequisites present."

# ---------- 2. tai-memory ----------
say "Installing tai-memory into $TAI_HOME ..."
mkdir -p "$TAI_HOME"
cp -R "$REPO/memory/." "$TAI_HOME/"
# Substitute path placeholders in the installed hook scripts.
for h in "$TAI_HOME"/scripts/*; do
  [ -f "$h" ] && { subst "$h" > "$h.tmp" && mv "$h.tmp" "$h" && chmod +x "$h"; }
done
[ -f "$TAI_HOME/.env" ] || cp "$TAI_HOME/.env.example" "$TAI_HOME/.env"
( cd "$TAI_HOME" && uv sync )

if [ "$PG_MODE" = "docker" ]; then
  # --- Zero-sudo pgvector container (docker-compose.yml ships it on :5544) ---
  say "Starting pgvector container (docker, port 5544)..."
  ( cd "$TAI_HOME" && DC up -d )
  # Point .env at the container.
  sed -i.bak "s#^POSTGRES_URL=.*#POSTGRES_URL=postgresql://tai:tai@localhost:5544/tai_memory#" "$TAI_HOME/.env" && rm -f "$TAI_HOME/.env.bak"
  say "Waiting for Postgres to be healthy..."
  for i in $(seq 1 30); do
    ( cd "$TAI_HOME" && DC exec -T postgres pg_isready -U tai -d tai_memory >/dev/null 2>&1 ) && break
    sleep 2
  done
  say "Applying migrations..."
  ( cd "$TAI_HOME" && DC exec -T postgres psql -U tai -d tai_memory -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null 2>&1 ) || warn "extension step: check container"
  for m in "$TAI_HOME"/migrations/*.sql; do
    ( cd "$TAI_HOME" && DC exec -T postgres psql -U tai -d tai_memory ) < "$m" >/dev/null 2>&1 || true
  done
else
  # --- System Postgres on :5432 (needs local admin) ---
  say "Checking Postgres is running..."
  psql -h localhost -d postgres -c "SELECT 1" >/dev/null 2>&1 || {
    warn "Postgres not responding on localhost:5432. Start it (macOS: brew services start postgresql@17; Linux: sudo systemctl start postgresql) or use the default Docker mode (drop --system-pg)."
    exit 1
  }
  say "Setting up Postgres role/db (idempotent)..."
  createuser tai 2>/dev/null || true
  createdb  tai_memory -O tai 2>/dev/null || true
  psql -d tai_memory -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null || \
    warn "Could not enable extensions — install pgvector, then re-run."
  for m in "$TAI_HOME"/migrations/*.sql; do psql -d tai_memory -f "$m" 2>/dev/null || true; done
fi
( cd "$TAI_HOME" && uv run tai-mem doctor ) || warn "tai-mem doctor reported issues — check .env / Postgres."

# ---------- 3. Daemon scripts ----------
say "Installing daemon scripts into $BIN ..."
mkdir -p "$BIN"
for f in "$REPO"/daemon/*; do
  out="$BIN/$(basename "$f")"
  subst "$f" > "$out"; chmod +x "$out"
done

# ---------- 4. Config ----------
say "Installing config..."
mkdir -p "$TAI_HOME/.claude"
subst "$REPO/config/mcp.json.template" > "$TAI_HOME/.mcp.json"
subst "$REPO/config/claude-settings.json.template" > "$TAI_HOME/.claude/settings.json"
if [ ! -f "$TAI_HOME/CLAUDE.md" ]; then
  subst "$REPO/config/CLAUDE.md.template" > "$TAI_HOME/CLAUDE.md"
  warn "Edit $TAI_HOME/CLAUDE.md — fill in <OWNER_NAME>, project context, etc."
fi
# Pre-create the Telegram channel dir + .env skeleton so setup never hits "no such dir".
mkdir -p "$HOME/.claude/channels/telegram"
TG_ENV="$HOME/.claude/channels/telegram/.env"
if [ ! -f "$TG_ENV" ]; then
  printf 'TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\n' > "$TG_ENV"; chmod 600 "$TG_ENV"
fi

# ---------- 5. Subagent definitions ----------
say "Installing subagent definitions into $AGENTS_DIR ..."
mkdir -p "$AGENTS_DIR"
# Don't clobber existing agent defs (a co-resident Claude Code setup may have its own).
for f in "$REPO"/agents/*.md; do
  a="$(basename "$f")"
  if [ -e "$AGENTS_DIR/$a" ]; then warn "kept existing $AGENTS_DIR/$a (not overwritten)";
  else cp "$f" "$AGENTS_DIR/" 2>/dev/null || true; fi
done

# ---------- 5b. Image tools (key-free Gemini image generation) ----------
# Optional capability: drive Gemini on the web (headless Chrome) to make images
# without an API key. Skipped gracefully if node/npm are absent.
say "Installing image tools into $HOME/.tai-browser ..."
TB="$HOME/.tai-browser"
mkdir -p "$TB"
cp "$REPO"/tools/*.mjs "$REPO"/tools/start-chrome.sh "$REPO"/tools/package.json "$REPO"/tools/README.md "$TB/" 2>/dev/null || true
chmod +x "$TB/start-chrome.sh" 2>/dev/null || true
if have node && have npm; then
  ( cd "$TB" && npm install --silent >/dev/null 2>&1 ) && say "  image tools ready (playwright-core installed)" \
    || warn "  npm install for image tools failed — run 'cd $TB && npm install' later."
else
  warn "  node/npm not found — image tools copied but inactive. Install node, then 'cd $TB && npm install'."
fi

# ---------- 6. Service ----------
# NOTE: we install the service definitions but DO NOT start the daemon here.
# Starting before `claude` is logged in + the Telegram token is set would just
# crash-loop. The user runs `claudet setup` then `claudet up` when ready.
if [ "$OS" = "Darwin" ]; then
  say "Installing launchd service definitions (not started yet)..."
  subst "$REPO/launchd/com.claudet.plist.template" > "$HOME/Library/LaunchAgents/com.claudet.plist"
  subst "$REPO/launchd/com.claudet-watchdog.plist.template" > "$HOME/Library/LaunchAgents/com.claudet-watchdog.plist"
else
  say "Installing systemd (user) service definitions (not started yet)..."
  mkdir -p "$HOME/.config/systemd/user"
  subst "$REPO/systemd/claudet.service.template" > "$HOME/.config/systemd/user/claudet.service"
  subst "$REPO/systemd/claudet-watchdog.service.template" > "$HOME/.config/systemd/user/claudet-watchdog.service"
  subst "$REPO/systemd/claudet-watchdog.timer.template" > "$HOME/.config/systemd/user/claudet-watchdog.timer"
  systemctl --user daemon-reload 2>/dev/null || true
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

# ---------- Manual steps ----------
cat <<EOF

✓ tAI wiring complete. Finish with these steps (in order):

  1. claude                         # log in once (if not already)
  2. In that claude session:        /plugin   → install 'telegram' from claude-plugins-official
  3. claudet setup                  # enter bot token (@BotFather) + chat id (@userinfobot)
  4. In a claude session:           /telegram:configure   then   /telegram:access  (approve your chat)
  5. claudet up                     # start the daemon
  6. claudet doctor                 # verify everything is green

Anytime:  claudet {doctor|up|down|status|logs|attach}
Edit $TAI_HOME/CLAUDE.md for your identity/project (fill <OWNER_NAME>).

Optional — key-free image generation via Gemini (web):
  Tools are in $HOME/.tai-browser (see its README.md). One-time: log into your
  Google account in the browser profile, then:
    node $HOME/.tai-browser/gemini-image.mjs "Generate an image: ..." /tmp/out.png
EOF
