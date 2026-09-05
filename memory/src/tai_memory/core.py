"""Core memory operations: sessions, tasks, facts, artifacts, recall.

All persistence ops write the Postgres row + memory_index + embedding inside a
single transaction. Dedupe is by content_hash UNIQUE on memory_index.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg.rows import dict_row

from . import db, embeddings

Kind = Literal["task", "fact", "artifact"]
RefTable = Literal["tasks", "facts", "artifacts"]


@dataclass
class RecallResult:
    kind: Kind
    similarity: float
    content: str
    metadata: dict[str, Any]


def _embed_and_index(cur, ref_table: RefTable, ref_id: UUID, text: str) -> UUID | None:
    """Insert into memory_index + embeddings if content_hash is new.

    Returns the new vector_id, or None if the text was already embedded (dedupe).
    Dedupe intentionally keeps the original ref binding — repeated identical
    content under a new ref reuses the existing vector without re-pointing.
    """
    h = embeddings.content_hash(text)
    cur.execute("SELECT vector_id FROM memory_index WHERE content_hash = %s", (h,))
    if cur.fetchone():
        return None

    vec = embeddings.embed_one(text, kind="passage")
    cur.execute(
        """
        INSERT INTO memory_index (postgres_ref_table, postgres_ref_id, content_hash)
        VALUES (%s, %s, %s)
        RETURNING vector_id
        """,
        (ref_table, ref_id, h),
    )
    vector_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO embeddings (vector_id, embedding) VALUES (%s, %s)",
        (vector_id, vec),
    )
    return vector_id


def start_session() -> UUID:
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO sessions DEFAULT VALUES RETURNING session_id")
        return cur.fetchone()[0]


# Marker the Stop hook used to write as a summary. Treated as "no real summary"
# so auto-close logic is free to overwrite it.
PLACEHOLDER_SUMMARY = "(auto-closed via Stop hook)"


def end_session(session_id: UUID, summary: str, *, overwrite: bool = True) -> None:
    """Close a session with a summary.

    With overwrite=True (explicit calls, e.g. memory_end_session) the summary is
    set unconditionally. With overwrite=False (the Stop hook) a real summary the
    model already set during the session is preserved — only a NULL or
    placeholder summary is replaced.
    """
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        if overwrite:
            cur.execute(
                """
                UPDATE sessions
                SET ended_at = now(), summary = %s, status = 'closed'
                WHERE session_id = %s
                """,
                (summary, session_id),
            )
        else:
            cur.execute(
                """
                UPDATE sessions
                SET ended_at = now(),
                    summary = CASE
                        WHEN summary IS NULL OR summary = %s THEN %s
                        ELSE summary
                    END,
                    status = 'closed'
                WHERE session_id = %s
                """,
                (PLACEHOLDER_SUMMARY, summary, session_id),
            )


def auto_close_session(session_id: UUID) -> str:
    """Close a session for the Stop hook without losing information.

    If the model already set a real summary during the session, it is kept
    untouched. Otherwise a summary is derived from the session's most recent
    task so the row carries real content instead of a static placeholder.
    Returns the summary the session ends up with.
    """
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT summary FROM sessions WHERE session_id = %s",
            (session_id,),
        )
        row = cur.fetchone()
        if row is None:
            return ""  # unknown session id — nothing to close

        existing = row[0]
        if existing and existing != PLACEHOLDER_SUMMARY:
            # A real summary is already in place; just ensure the row is closed.
            cur.execute(
                """
                UPDATE sessions
                SET ended_at = COALESCE(ended_at, now()), status = 'closed'
                WHERE session_id = %s
                """,
                (session_id,),
            )
            return existing

        # No meaningful summary — derive one from the latest task.
        cur.execute(
            """
            SELECT description, outcome FROM tasks
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        task = cur.fetchone()
        if task:
            description, outcome = task
            summary = f"(auto) {description}"
            if outcome:
                summary += f" — {outcome[:200]}"
        else:
            summary = PLACEHOLDER_SUMMARY

        cur.execute(
            """
            UPDATE sessions
            SET ended_at = now(), summary = %s, status = 'closed'
            WHERE session_id = %s
            """,
            (summary, session_id),
        )
        return summary


def persist_task(
    session_id: UUID,
    description: str,
    outcome: str | None = None,
    decisions_made: str | None = None,
) -> UUID:
    """Insert a task row + embed its full text for semantic recall."""
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (session_id, description, outcome, decisions_made)
            VALUES (%s, %s, %s, %s)
            RETURNING task_id
            """,
            (session_id, description, outcome, decisions_made),
        )
        task_id = cur.fetchone()[0]
        text = "\n".join(p for p in (description, outcome, decisions_made) if p)
        _embed_and_index(cur, "tasks", task_id, text)
        return task_id


def add_fact(
    content: str,
    source_task_id: UUID | None = None,
    confidence: float = 1.0,
) -> UUID:
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO facts (content, source_task_id, confidence)
            VALUES (%s, %s, %s)
            RETURNING fact_id
            """,
            (content, source_task_id, confidence),
        )
        fact_id = cur.fetchone()[0]
        _embed_and_index(cur, "facts", fact_id, content)
        return fact_id


def supersede_fact(
    old_fact_id: UUID,
    new_content: str,
    source_task_id: UUID | None = None,
) -> UUID:
    """Insert a new fact and mark the old one superseded by it."""
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO facts (content, source_task_id)
            VALUES (%s, %s)
            RETURNING fact_id
            """,
            (new_content, source_task_id),
        )
        new_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE facts SET superseded_by = %s WHERE fact_id = %s",
            (new_id, old_fact_id),
        )
        _embed_and_index(cur, "facts", new_id, new_content)
        return new_id


def add_artifact(task_id: UUID, type: str, content: str) -> UUID:
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO artifacts (task_id, type, content)
            VALUES (%s, %s, %s)
            RETURNING artifact_id
            """,
            (task_id, type, content),
        )
        artifact_id = cur.fetchone()[0]
        _embed_and_index(cur, "artifacts", artifact_id, content)
        return artifact_id


def recall(
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.4,
    kinds: list[RefTable] | None = None,
) -> list[RecallResult]:
    """Semantic + structured retrieval. Filters by similarity and superseded facts.

    Default min_similarity (0.4) is calibrated for paraphrase-multilingual-MiniLM,
    where related-but-not-paraphrase pairs typically score 0.3-0.7 and unrelated
    content scores near or below zero. Switch the default if you change models.
    """
    if kinds is None:
        kinds = ["tasks", "facts", "artifacts"]

    qvec = embeddings.embed_one(query, kind="query")
    pool = db.get_pool()

    with pool.connection() as conn, conn.cursor() as cur:
        # Over-fetch so superseded-fact and threshold filtering still gives top_k hits.
        cur.execute(
            """
            SELECT mi.postgres_ref_table,
                   mi.postgres_ref_id,
                   1 - (e.embedding <=> %s::vector) AS similarity
            FROM memory_index mi
            JOIN embeddings e USING (vector_id)
            WHERE mi.postgres_ref_table = ANY(%s)
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (qvec, kinds, qvec, top_k * 4),
        )
        candidates = cur.fetchall()

    results: list[RecallResult] = []
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        for ref_table, ref_id, similarity in candidates:
            if similarity < min_similarity:
                continue
            hit = _hydrate(cur, ref_table, ref_id, similarity)
            if hit is not None:
                results.append(hit)
            if len(results) >= top_k:
                break
    return results


def _hydrate(cur, ref_table: str, ref_id: UUID, similarity: float) -> RecallResult | None:
    if ref_table == "tasks":
        cur.execute("SELECT * FROM tasks WHERE task_id = %s", (ref_id,))
        row = cur.fetchone()
        if not row:
            return None
        content = row["description"]
        if row["outcome"]:
            content += f"\n\n{row['outcome']}"
        return RecallResult(
            kind="task",
            similarity=similarity,
            content=content,
            metadata={
                "task_id": str(row["task_id"]),
                "session_id": str(row["session_id"]),
                "created_at": _iso(row["created_at"]),
            },
        )

    if ref_table == "facts":
        cur.execute(
            "SELECT * FROM facts WHERE fact_id = %s AND superseded_by IS NULL",
            (ref_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return RecallResult(
            kind="fact",
            similarity=similarity,
            content=row["content"],
            metadata={
                "fact_id": str(row["fact_id"]),
                "confidence": row["confidence"],
                "created_at": _iso(row["created_at"]),
            },
        )

    if ref_table == "artifacts":
        cur.execute("SELECT * FROM artifacts WHERE artifact_id = %s", (ref_id,))
        row = cur.fetchone()
        if not row:
            return None
        return RecallResult(
            kind="artifact",
            similarity=similarity,
            content=row["content"],
            metadata={
                "artifact_id": str(row["artifact_id"]),
                "task_id": str(row["task_id"]),
                "type": row["type"],
                "created_at": _iso(row["created_at"]),
            },
        )

    return None


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None
