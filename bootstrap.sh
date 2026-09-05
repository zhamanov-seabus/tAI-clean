#!/usr/bin/env bash
# tAI one-line bootstrap.
#
#   curl -fsSL https://raw.githubusercontent.com/zhamanov-seabus/tAI-clean/main/bootstrap.sh | bash
#
# Installs the scriptable prerequisites, clones tAI, and runs install.sh with
# the zero-sudo Docker Postgres default. Two things can't be automated (auth +
# a secret) and are printed at the end: `claude` login and the Telegram token.

set -euo pipefail
say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

OS="$(uname -s)"
SRC_DIR="${TAI_SRC:-$HOME/tAI-clean}"
REPO_URL="https://github.com/zhamanov-seabus/tAI-clean.git"

say "tAI bootstrap on $OS"

# ---- package manager helper ----
pkg_install() {
  if [ "$OS" = "Darwin" ]; then
    have brew || { say "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; }
    brew install "$@"
  elif have apt-get; then sudo apt-get update -y && sudo apt-get install -y "$@"
  elif have dnf; then sudo dnf install -y "$@"
  elif have pacman; then sudo pacman -S --noconfirm "$@"
  else warn "No known package manager — install manually: $*"; fi
}

# ---- git ----
have git || pkg_install git

# ---- uv (Python) ----
have uv || { say "Installing uv..."; curl -fsSL https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }

# ---- tmux + expect (daemon needs them on macOS; harmless elsewhere) ----
have tmux   || pkg_install tmux
have expect || pkg_install expect

# ---- Docker + compose plugin (default Postgres backend) ----
if ! have docker; then
  if [ "$OS" = "Darwin" ]; then
    # Colima = a scriptable, GUI-less Docker runtime (no Docker Desktop license,
    # no admin GUI prompt). Fully automatable, unlike Docker Desktop.
    say "Installing Docker runtime (Colima — no GUI, scriptable)..."
    pkg_install colima docker docker-compose || warn "Install colima+docker manually (brew install colima docker docker-compose)."
  else
    say "Installing Docker engine..."; curl -fsSL https://get.docker.com | sh || warn "Install docker manually, then re-run."
  fi
fi
# macOS: make sure the Colima VM (docker daemon) is up.
if [ "$OS" = "Darwin" ] && have colima; then
  colima status >/dev/null 2>&1 || { say "Starting Colima VM..."; colima start; }
fi
# Ensure the compose v2 plugin exists (docker.io often ships without it).
if have docker && ! docker compose version >/dev/null 2>&1 && ! have docker-compose; then
  say "Installing docker compose plugin..."
  pkg_install docker-compose-v2 || pkg_install docker-compose-plugin || warn "Install 'docker compose' manually (apt: docker-compose-v2)."
fi
# On Linux, make sure the current user can talk to the daemon.
if [ "$OS" != "Darwin" ] && have docker && ! docker info >/dev/null 2>&1; then
  say "Enabling Docker daemon + adding you to the docker group..."
  sudo systemctl enable --now docker 2>/dev/null || true
  sudo usermod -aG docker "$USER" 2>/dev/null || true
  warn "Added you to the 'docker' group — you may need to log out/in (or run: newgrp docker) before Docker works without sudo."
fi

# ---- Claude Code CLI (the brain — install if missing) ----
if ! have claude; then
  warn "Claude Code CLI not found. Install it, then re-run this line:"
  warn "  https://claude.com/claude-code   (you'll log in once after install)"
fi

# ---- clone + install ----
if [ -d "$SRC_DIR/.git" ]; then say "Updating tAI in $SRC_DIR..."; git -C "$SRC_DIR" pull --ff-only || true
else say "Cloning tAI into $SRC_DIR..."; git clone "$REPO_URL" "$SRC_DIR"; fi

say "Running installer (Docker Postgres default)..."
bash "$SRC_DIR/install.sh"

cat <<EOF

✓ Bootstrap done. Two manual steps remain (auth + secret — can't be scripted):
  1. Run:  claude          (log in once)
  2. Add your Telegram bot token + chat id to  ~/.claude/channels/telegram/.env :
       TELEGRAM_BOT_TOKEN=123456:AA...
       TELEGRAM_CHAT_ID=<your numeric id from @userinfobot>
     (or run /telegram:configure + /telegram:access inside a claude session)
EOF
