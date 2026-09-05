# tai-memory

Two-layer persistent memory for Claude Code. PostgreSQL (source of truth) + pgvector (semantic recall), exposed via an MCP server and a `tai-mem` CLI.

## Stack

- Python 3.12+ (uv-managed)
- PostgreSQL with `pgvector`
- **Local** embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  via `fastembed` — **384-dim, no API key** (downloaded + cached on first use,
  ~120 MB). Multilingual (EN + RU). The `vector(384)` columns in the schema match this.
- MCP server + Click CLI

> The top-level `install.sh` wires all of this up automatically. This README is
> for running tai-memory standalone / understanding the pieces.

## Setup (Docker Postgres — default)

```bash
docker compose up -d       # pgvector container: role tai / db tai_memory on :5544
cp .env.example .env
# .env POSTGRES_URL should point at the container:
#   POSTGRES_URL=postgresql://tai:tai@localhost:5544/tai_memory
uv sync
for m in migrations/*.sql; do docker compose exec -T postgres psql -U tai -d tai_memory < "$m"; done
uv run tai-mem doctor      # health check (config + schema)
```

No API key, no sudo. Embeddings run locally.

## Setup (system Postgres — alternative)

```bash
# e.g. macOS Homebrew:
brew install postgresql@17 pgvector && brew services start postgresql@17
createuser tai; createdb tai_memory -O tai
psql -d tai_memory -c "CREATE EXTENSION vector; CREATE EXTENSION pgcrypto;"
# POSTGRES_URL=postgresql://tai:tai@localhost:5432/tai_memory  in .env
uv sync
for m in migrations/*.sql; do psql -d tai_memory -f "$m"; done
uv run tai-mem doctor
```

## Common commands

```bash
uv run tai-mem recall "query"        # semantic + structured retrieval
uv run tai-mem sessions              # recent sessions
uv run tai-mem facts --active        # non-superseded facts
uv run tai-mem doctor                # health check
```

## Layout

```
src/tai_memory/   # package: db, embeddings, core ops, MCP server, CLI
migrations/       # SQL migrations (001_init.sql, 002_indexes.sql)
tests/            # pytest suite
docker-compose.yml  # alternative containerized Postgres
```

See [CLAUDE.md](CLAUDE.md) for the full architecture and operating instructions.
