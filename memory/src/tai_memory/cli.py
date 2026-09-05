"""tai-mem command-line interface."""

import sys
from uuid import UUID

import click
from psycopg.rows import dict_row

from . import core, db
from .config import get_settings


@click.group()
def main() -> None:
    """tai-mem — manage Claude Code's persistent memory."""


# ------------------------------------------------------------------ schema ops


@main.command()
def init() -> None:
    """Apply pending migrations against POSTGRES_URL."""
    try:
        applied = db.apply_migrations()
    except Exception as e:
        click.secho(f"init failed: {e}", fg="red", err=True)
        sys.exit(1)
    if not applied:
        click.echo("No pending migrations.")
        return
    for v in applied:
        click.secho(f"applied {v}", fg="green")


@main.command()
def doctor() -> None:
    """Health-check DB connection, extensions, tables, indexes, and config."""
    ok = True

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal ok
        mark, color = ("✓", "green") if condition else ("✗", "red")
        click.secho(f"  {mark} {label}", fg=color, nl=False)
        click.echo(f"  ({detail})" if detail else "")
        if not condition:
            ok = False

    click.echo("config:")
    try:
        s = get_settings()
        check("POSTGRES_URL set", bool(s.postgres_url))
        check(f"EMBEDDING_MODEL={s.embedding_model}", bool(s.embedding_model))
        col_dim = db.vector_column_dim()
        dim_ok = col_dim is not None and col_dim == s.embedding_dim
        check(
            f"EMBEDDING_DIM={s.embedding_dim}",
            dim_ok,
            f"schema column is vector({col_dim})" if not dim_ok and col_dim else "matches schema",
        )
    except Exception as e:
        click.secho(f"  ✗ failed to load settings: {e}", fg="red")
        sys.exit(1)

    click.echo("\ndatabase:")
    try:
        exts = db.installed_extensions()
        for ext in db.REQUIRED_EXTENSIONS:
            check(f"extension {ext} installed", ext in exts)

        tables = db.existing_tables()
        missing = [t for t in db.EXPECTED_TABLES if t not in tables]
        check(
            f"tables ({len(db.EXPECTED_TABLES)}/{len(db.EXPECTED_TABLES)})",
            not missing,
            f"missing: {', '.join(missing)}" if missing else "all present",
        )

        has_ivfflat = db.has_index("idx_embeddings_cosine")
        check("ivfflat index on embeddings", has_ivfflat, "" if has_ivfflat else "run `tai-mem init`")
    except Exception as e:
        click.secho(f"  ✗ db check failed: {e}", fg="red")
        ok = False

    click.echo()
    if ok:
        click.secho("all green.", fg="green", bold=True)
    else:
        click.secho("issues above.", fg="red", bold=True)
        sys.exit(1)


# ------------------------------------------------------------------ recall


@main.command()
@click.argument("query")
@click.option("-k", "--top-k", default=5, type=int, help="Maximum results.")
@click.option("-t", "--threshold", default=0.4, type=float, help="Min cosine similarity.")
@click.option(
    "--kind",
    "kinds",
    multiple=True,
    type=click.Choice(["tasks", "facts", "artifacts"]),
    help="Restrict to one or more record kinds (repeatable).",
)
def recall(query: str, top_k: int, threshold: float, kinds: tuple[str, ...]) -> None:
    """Semantic + structured retrieval. Prints hydrated rows above similarity threshold."""
    hits = core.recall(query, top_k=top_k, min_similarity=threshold, kinds=list(kinds) or None)
    if not hits:
        click.secho("(no hits)", fg="yellow")
        return
    for h in hits:
        click.secho(f"[{h.kind}] sim={h.similarity:.3f}", fg="cyan")
        for line in h.content.splitlines() or [""]:
            click.echo(f"  {line}")
        click.secho(f"  meta: {h.metadata}", fg="bright_black")
        click.echo()


# ------------------------------------------------------------------ sessions


@main.command()
@click.option("-n", "--limit", default=10, type=int, help="How many sessions to list.")
def sessions(limit: int) -> None:
    """List recent sessions."""
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT session_id, started_at, ended_at, status, summary
            FROM sessions ORDER BY started_at DESC LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    if not rows:
        click.secho("(no sessions)", fg="yellow")
        return
    for r in rows:
        status_color = {"closed": "green", "active": "yellow", "abandoned": "red"}.get(r["status"], "white")
        click.secho(
            f"{r['session_id']}  {r['started_at']:%Y-%m-%d %H:%M}  ", nl=False
        )
        click.secho(f"[{r['status']}]", fg=status_color, nl=False)
        click.echo(f"  {r['summary'] or '(no summary)'}")


@main.group()
def session() -> None:
    """Per-session inspection."""


@session.command("show")
@click.argument("session_id")
def session_show(session_id: str) -> None:
    """Show tasks (and counts) for a session."""
    sid = UUID(session_id)
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM sessions WHERE session_id = %s", (sid,))
        s = cur.fetchone()
        if not s:
            click.secho("session not found", fg="red")
            sys.exit(1)
        cur.execute("SELECT * FROM tasks WHERE session_id = %s ORDER BY created_at", (sid,))
        tasks = cur.fetchall()

    click.secho(f"session {s['session_id']}", fg="cyan", bold=True)
    click.echo(f"  started: {s['started_at']}")
    click.echo(f"  ended:   {s['ended_at'] or '(open)'}")
    click.echo(f"  status:  {s['status']}")
    click.echo(f"  summary: {s['summary'] or '(none)'}")
    click.echo(f"\ntasks ({len(tasks)}):")
    for t in tasks:
        click.echo(f"  - [{t['task_id']}] {t['description'][:80]}")


@main.command()
@click.argument("session_id")
@click.argument("summary")
def end_session(session_id: str, summary: str) -> None:
    """Close a session with a summary."""
    core.end_session(UUID(session_id), summary)
    click.secho("session closed.", fg="green")


@main.command()
@click.argument("session_id")
def auto_close_session(session_id: str) -> None:
    """Close a session for the Stop hook.

    Preserves a real summary if one was set during the session, otherwise
    derives one from the session's latest task. Never clobbers real content.
    """
    summary = core.auto_close_session(UUID(session_id))
    click.echo(summary or "(no session)")


@main.command()
def start_session() -> None:
    """Open a new session and print its ID."""
    sid = core.start_session()
    click.echo(str(sid))


# ------------------------------------------------------------------ tasks


@main.group()
def task() -> None:
    """Manage tasks."""


@task.command("add")
@click.argument("session_id")
@click.argument("description")
@click.option("--outcome", default=None)
@click.option("--decisions", "decisions_made", default=None)
def task_add(session_id: str, description: str, outcome: str | None, decisions_made: str | None) -> None:
    """Persist a task into SESSION_ID."""
    tid = core.persist_task(UUID(session_id), description, outcome, decisions_made)
    click.echo(str(tid))


# ------------------------------------------------------------------ artifacts


@main.group()
def artifact() -> None:
    """Manage artifacts."""


@artifact.command("add")
@click.argument("task_id")
@click.argument("type")
@click.argument("content")
def artifact_add(task_id: str, type: str, content: str) -> None:
    """Attach an artifact to TASK_ID."""
    aid = core.add_artifact(UUID(task_id), type, content)
    click.echo(str(aid))


# ------------------------------------------------------------------ facts


@main.group()
def fact() -> None:
    """Manage facts."""


@fact.command("add")
@click.argument("content")
@click.option("--confidence", default=1.0, type=float)
def fact_add(content: str, confidence: float) -> None:
    """Insert a new fact."""
    fid = core.add_fact(content, confidence=confidence)
    click.echo(str(fid))


@fact.command("supersede")
@click.argument("old_fact_id")
@click.argument("new_content")
def fact_supersede(old_fact_id: str, new_content: str) -> None:
    """Replace OLD_FACT_ID with NEW_CONTENT."""
    new_id = core.supersede_fact(UUID(old_fact_id), new_content)
    click.echo(str(new_id))


@main.command()
@click.option("--active/--all", default=True, help="Only currently-active (default) or every fact.")
def facts(active: bool) -> None:
    """List facts."""
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        sql = (
            "SELECT fact_id, content, confidence, created_at, superseded_by "
            "FROM facts "
        )
        if active:
            sql += "WHERE superseded_by IS NULL "
        sql += "ORDER BY created_at DESC"
        cur.execute(sql)
        rows = cur.fetchall()
    if not rows:
        click.secho("(no facts)", fg="yellow")
        return
    for r in rows:
        marker = "✓" if r["superseded_by"] is None else "×"
        color = "green" if r["superseded_by"] is None else "bright_black"
        click.secho(f"  {marker} ", fg=color, nl=False)
        click.echo(f"[{r['fact_id']}] {r['content']}")


# ------------------------------------------------------------------ entrypoint


if __name__ == "__main__":
    main()
