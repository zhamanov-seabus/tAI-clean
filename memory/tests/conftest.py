"""Test fixtures.

CRITICAL: the suite TRUNCATEs every table. It must NEVER run against the
production database. Two guarantees enforce this:

  1. Tests are routed to a dedicated test database — TEST_POSTGRES_URL if set,
     otherwise the production database name with a "_test" suffix.
  2. A safety fuse refuses to touch any database whose name does not end in
     "_test". If the routing is ever wrong, the suite errors instead of wiping
     real memory.

One-time setup of the test database (the `tai` role is not a superuser, so a
superuser must create the extensions once):

    createdb tai_memory_test
    psql -d tai_memory_test -c "CREATE EXTENSION IF NOT EXISTS vector; \
                                CREATE EXTENSION IF NOT EXISTS pgcrypto;"
    psql -d tai_memory_test -c "ALTER SCHEMA public OWNER TO tai;"
"""

import os
from urllib.parse import urlsplit, urlunsplit

import pytest

from tai_memory import config, db

TEST_DB_SUFFIX = "_test"


def _db_name(url: str) -> str:
    return urlsplit(url).path.lstrip("/")


def _derive_test_url() -> str:
    """The database URL the suite is allowed to use."""
    explicit = os.environ.get("TEST_POSTGRES_URL")
    if explicit:
        return explicit
    base = config.get_settings().postgres_url
    parts = urlsplit(base)
    name = _db_name(base)
    if name.endswith(TEST_DB_SUFFIX):
        return base
    test_name = f"{name}{TEST_DB_SUFFIX}"
    return urlunsplit((parts.scheme, parts.netloc, f"/{test_name}", parts.query, parts.fragment))


def _assert_is_test_db(url: str) -> None:
    """Safety fuse: never let destructive fixtures run against a non-test DB."""
    name = _db_name(url)
    if not name.endswith(TEST_DB_SUFFIX):
        raise RuntimeError(
            f"Refusing to run the destructive test suite against database {name!r}: "
            f"its name must end with {TEST_DB_SUFFIX!r}. "
            "Set TEST_POSTGRES_URL to a dedicated test database."
        )


@pytest.fixture(scope="session", autouse=True)
def _route_to_test_db():
    """Point the app's pool at the test database for the whole session."""
    url = _derive_test_url()
    _assert_is_test_db(url)

    # Redirect every db.get_pool() consumer (core, cli, mcp) at the test DB.
    db.close_pool()
    config.get_settings().postgres_url = url
    db.close_pool()

    try:
        db.apply_migrations()
    except Exception as exc:  # pragma: no cover - setup failure path
        raise RuntimeError(
            f"Could not prepare test database {_db_name(url)!r} ({exc}). "
            "Create it once: createdb tai_memory_test && "
            'psql -d tai_memory_test -c "CREATE EXTENSION IF NOT EXISTS vector; '
            'CREATE EXTENSION IF NOT EXISTS pgcrypto;" && '
            'psql -d tai_memory_test -c "ALTER SCHEMA public OWNER TO tai;"'
        ) from exc

    yield
    db.close_pool()


@pytest.fixture(autouse=True)
def reset_tables():
    # Defense in depth: re-check the fuse before every truncate.
    _assert_is_test_db(config.get_settings().postgres_url)
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE sessions, tasks, artifacts, facts, memory_index, embeddings "
            "RESTART IDENTITY CASCADE"
        )
    yield
