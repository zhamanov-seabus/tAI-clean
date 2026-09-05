"""MCP server exposing memory.* tools to Claude Code over stdio."""

from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

from . import core, db

mcp = FastMCP("tai-memory")


@mcp.tool()
def memory_recall(
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.4,
    kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Semantic + structured retrieval over past tasks, facts, and artifacts.

    Args:
        query: Natural-language query — embedded and compared via cosine similarity.
        top_k: Maximum number of hydrated results.
        min_similarity: Cosine threshold (0-1). 0.4 is calibrated for the local
            multilingual model; raise for stricter recall, lower to cast a wider net.
        kinds: Restrict to a subset of ['tasks','facts','artifacts']. None = all.
    """
    results = core.recall(
        query,
        top_k=top_k,
        min_similarity=min_similarity,
        kinds=kinds,  # type: ignore[arg-type]
    )
    return [
        {
            "kind": r.kind,
            "similarity": r.similarity,
            "content": r.content,
            "metadata": r.metadata,
        }
        for r in results
    ]


@mcp.tool()
def memory_start_session() -> str:
    """Open a new memory session. Returns the session_id (UUID string)."""
    return str(core.start_session())


@mcp.tool()
def memory_end_session(session_id: str, summary: str) -> str:
    """Close a session and persist its summary."""
    core.end_session(UUID(session_id), summary)
    return "ok"


@mcp.tool()
def memory_persist_task(
    session_id: str,
    description: str,
    outcome: str | None = None,
    decisions_made: str | None = None,
) -> str:
    """Record a completed task and embed its full text for future recall.

    Returns the task_id. Use this at task end to capture what was done, what
    the outcome was, and what decisions were made along the way.
    """
    return str(core.persist_task(UUID(session_id), description, outcome, decisions_made))


@mcp.tool()
def memory_add_fact(
    content: str,
    source_task_id: str | None = None,
    confidence: float = 1.0,
) -> str:
    """Store a learned fact (preference, constraint, project info). Returns fact_id."""
    return str(
        core.add_fact(
            content,
            UUID(source_task_id) if source_task_id else None,
            confidence,
        )
    )


@mcp.tool()
def memory_supersede_fact(
    old_fact_id: str,
    new_content: str,
    source_task_id: str | None = None,
) -> str:
    """Replace an obsolete fact. Old fact stays in DB but is filtered from recall."""
    return str(
        core.supersede_fact(
            UUID(old_fact_id),
            new_content,
            UUID(source_task_id) if source_task_id else None,
        )
    )


@mcp.tool()
def memory_add_artifact(task_id: str, type: str, content: str) -> str:
    """Attach an artifact (code, doc, plan, note) to a task. Returns artifact_id."""
    return str(core.add_artifact(UUID(task_id), type, content))


@mcp.tool()
def memory_recent_sessions(limit: int = 5) -> list[dict[str, Any]]:
    """List the most recent sessions with their summaries."""
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT session_id, started_at, ended_at, summary, status
            FROM sessions ORDER BY started_at DESC LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "session_id": str(r["session_id"]),
            "started_at": r["started_at"].isoformat(),
            "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None,
            "summary": r["summary"],
            "status": r["status"],
        }
        for r in rows
    ]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
