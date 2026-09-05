"""Postgres connection pool + migration runner."""

import atexit
from pathlib import Path

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from .config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

EXPECTED_TABLES = ("sessions", "tasks", "artifacts", "facts", "memory_index", "embeddings")
REQUIRED_EXTENSIONS = ("vector", "pgcrypto")

_pool: ConnectionPool | None = None


def _configure_conn(conn) -> None:
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(
            s.postgres_url,
            min_size=1,
            max_size=4,
            open=True,
            configure=_configure_conn,
        )
        atexit.register(close_pool)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def apply_migrations() -> list[str]:
    """Apply pending migrations from MIGRATIONS_DIR. Returns names of newly applied files."""
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

    applied: list[str] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
            if cur.fetchone():
                continue
            cur.execute(f.read_text())
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        applied.append(version)
    return applied


def installed_extensions() -> set[str]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension")
        return {row[0] for row in cur.fetchall()}


def existing_tables() -> set[str]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = current_schema()
            """
        )
        return {row[0] for row in cur.fetchall()}


def has_index(name: str) -> bool:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (name,))
        return cur.fetchone() is not None


def vector_column_dim() -> int | None:
    """Return the declared dimension of embeddings.embedding, or None if absent."""
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'embeddings'::regclass AND attname = 'embedding'
            """
        )
        row = cur.fetchone()
        if not row or row[0] in (None, -1):
            return None
        return int(row[0])
