# tAI

An **always-on personal AI agent** you reach over Telegram. It is Claude Code
running as a supervised daemon, with a two-layer persistent memory
(Postgres + pgvector, local embeddings) and cross-vendor review (Codex + Gemini).

Give it a task in Telegram from anywhere; it plans, executes, remembers across
sessions, and reports back — text or voice.

> **Note on the "brain":** the reasoning engine is **Claude Code** (Anthropic's
> CLI) plus the official Telegram plugin. Those are installed on your machine by
> you and are **not** redistributed here. This repo is the *wrapper*: the daemon,
> the memory system, config templates, cross-vendor agents, and an installer.

---

## What's in here

```
daemon/      always-on supervisor scripts (launchd/tmux keepalive, watchdog, notify)
launchd/     macOS LaunchAgent plist template
systemd/     Linux systemd (user) unit template
memory/      tai-memory package (Postgres + pgvector, MCP server, CLI, migrations)
config/      CLAUDE.md / .mcp.json / settings.json templates
agents/      7 subagent definitions — codex, gemini, cover-designer, dxf-draftsman,
             psychologist, islamic-finance-advisor, ca-startup-strategist
tools/       key-free image generation via Gemini web (headless Chrome, no API key)
install.sh   wires it all together (macOS + Linux)
```

## Prerequisites

- **Claude Code CLI** — https://claude.com/claude-code (authenticate once)
- **uv** — Python package manager (https://astral.sh/uv)
- **PostgreSQL 17** with the `vector` (pgvector) + `pgcrypto` extensions
- **git**
- macOS only: **tmux**, **expect**
- A **Telegram bot token** (from @BotFather)
- Optional: **Codex CLI** + **Gemini CLI** for cross-vendor review

## Install (one line)

```sh
curl -fsSL https://raw.githubusercontent.com/zhamanov-seabus/tAI-clean/main/bootstrap.sh | bash
```

This installs the scriptable prerequisites (git, uv, tmux/expect, Docker), clones
the repo, and runs `install.sh` with the **zero-sudo Docker Postgres** default
(a pgvector container on port 5544 — no local Postgres admin needed).

Then two manual steps (auth + a secret — can't be scripted):
1. `claude` — log in once.
2. Add your Telegram bot token + chat id to `~/.claude/channels/telegram/.env`
   (or run `/telegram:configure` + `/telegram:access` in a session):
   ```
   TELEGRAM_BOT_TOKEN=123456:AA...
   TELEGRAM_CHAT_ID=<your numeric id from @userinfobot>
   ```

Finally edit `$TAI_HOME/CLAUDE.md` (identity, project context).

### Manual / advanced

```sh
git clone https://github.com/zhamanov-seabus/tAI-clean.git && cd tAI-clean
./install.sh                 # Docker Postgres (default, no sudo)
./install.sh --system-pg     # use a local Postgres on :5432 instead
TAI_HOME=~/tai ./install.sh  # custom install location
```

The installer installs tai-memory (DB + migrations), drops the parametrized
daemon scripts into `~/.local/bin`, writes config into `$TAI_HOME`, installs the
Codex/Gemini agent defs, and loads the service + watchdog (launchd on macOS,
systemd on Linux).

## Memory (tai-memory)

Durable state in Postgres; semantic recall via pgvector; embeddings run locally
(`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, EN+RU, no API key). Exposed
over MCP: `memory_recall`, `memory_persist_task`, `memory_add_fact`,
`memory_supersede_fact`, `memory_recent_sessions`, and more. See `memory/README.md`.

## Cross-vendor review

The `codex` and `gemini` subagents give you second- and third-opinion critique
from other model vendors alongside Claude — useful for adversarial review of
plans, code, and documents. Requires the respective CLIs installed.

## Security notes

- Secrets never live in this repo. `.env`, the Telegram token
  (`~/.claude/channels/telegram/access.json`), and local session state are
  git-ignored / stored outside the tree.
- The daemon runs with your user privileges — keep the box trusted.

## License

Wrapper code: choose your license. Claude Code, the Telegram plugin, Codex, and
Gemini are separate products under their own terms.
