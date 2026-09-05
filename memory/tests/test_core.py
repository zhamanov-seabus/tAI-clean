"""Core memory-ops tests: insert→embed→recall, dedupe, supersession, threshold.

Similarity thresholds are calibrated for paraphrase-multilingual-MiniLM-L12-v2:
related-but-not-paraphrase pairs ~0.3-0.7, unrelated pairs near or below 0.
"""

from tai_memory import core, db


def _row_count(table: str) -> int:
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]


def test_persist_task_and_recall_round_trip():
    sid = core.start_session()
    core.persist_task(
        sid,
        description="fix login bug where user could submit empty password",
        outcome="resolved by adding null check on password field before auth",
    )
    hits = core.recall("authentication problem with empty credentials", top_k=5, min_similarity=0.5)
    assert hits, "expected at least one hit for related auth query"
    assert hits[0].kind == "task"
    assert "login" in hits[0].content.lower()
    assert hits[0].similarity >= 0.5


def test_dedupe_same_content_one_vector():
    sid = core.start_session()
    text = "the database connection pool should have at least 1 minimum connection"
    core.persist_task(sid, description=text)
    core.persist_task(sid, description=text)
    assert _row_count("tasks") == 2
    assert _row_count("memory_index") == 1
    assert _row_count("embeddings") == 1


def test_supersede_old_fact_excluded_from_recall():
    f_old = core.add_fact("the owner prefers tabs over spaces for indentation")
    core.supersede_fact(f_old, "the owner prefers spaces over tabs for indentation")
    hits = core.recall("indentation preference", top_k=5, min_similarity=0.5)
    contents = [h.content for h in hits]
    assert any("spaces over tabs" in c for c in contents), "new fact should be returned"
    assert not any("tabs over spaces" in c for c in contents), "superseded fact should be filtered"


def test_threshold_filters_unrelated():
    sid = core.start_session()
    core.persist_task(sid, description="growing tomatoes in raised beds with mulch")
    hits = core.recall("kubernetes ingress controller TLS termination", top_k=5, min_similarity=0.5)
    assert hits == [], f"high threshold should reject unrelated content; got {hits}"


def test_recall_kinds_filter():
    sid = core.start_session()
    tid = core.persist_task(sid, description="configured the github actions CI pipeline for the project")
    core.add_fact("the project uses github actions for continuous integration", source_task_id=tid)

    query = "github actions CI"
    only_facts = core.recall(query, min_similarity=0.4, kinds=["facts"])
    only_tasks = core.recall(query, min_similarity=0.4, kinds=["tasks"])

    assert only_facts, "expected at least one fact hit"
    assert only_tasks, "expected at least one task hit"
    assert all(h.kind == "fact" for h in only_facts)
    assert all(h.kind == "task" for h in only_tasks)


def test_artifact_recall():
    sid = core.start_session()
    tid = core.persist_task(sid, description="set up local Postgres for development")
    core.add_artifact(
        tid,
        type="note",
        content="docker compose configuration file for running Postgres with pgvector",
    )
    hits = core.recall("postgres docker setup config", min_similarity=0.4, kinds=["artifacts"])
    assert hits, "expected artifact hit for related query"
    assert hits[0].kind == "artifact"


def test_session_lifecycle():
    sid = core.start_session()
    core.end_session(sid, summary="phase B verification — schema and migrations green")
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, summary, ended_at IS NOT NULL FROM sessions WHERE session_id = %s",
            (sid,),
        )
        status, summary, has_ended = cur.fetchone()
    assert status == "closed"
    assert "phase B" in summary
    assert has_ended is True


def _session_summary(sid):
    pool = db.get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status, summary FROM sessions WHERE session_id = %s", (sid,))
        return cur.fetchone()


def test_auto_close_preserves_real_summary():
    """The Stop hook must never clobber a summary the model set during the session."""
    sid = core.start_session()
    core.end_session(sid, summary="real summary the model wrote before exit")
    out = core.auto_close_session(sid)
    status, summary = _session_summary(sid)
    assert status == "closed"
    assert summary == "real summary the model wrote before exit"
    assert out == "real summary the model wrote before exit"


def test_auto_close_derives_summary_from_latest_task():
    """With no real summary, auto-close pulls content from the session's latest task."""
    sid = core.start_session()
    core.persist_task(sid, description="first thing", outcome="done first")
    core.persist_task(
        sid,
        description="ship the memory summary fix",
        outcome="patched end_session and the Stop hook",
    )
    core.auto_close_session(sid)
    status, summary = _session_summary(sid)
    assert status == "closed"
    assert "ship the memory summary fix" in summary
    assert "patched end_session" in summary
    assert summary != core.PLACEHOLDER_SUMMARY


def test_auto_close_placeholder_when_no_tasks():
    """A session with nothing recorded still closes, with the placeholder."""
    sid = core.start_session()
    core.auto_close_session(sid)
    status, summary = _session_summary(sid)
    assert status == "closed"
    assert summary == core.PLACEHOLDER_SUMMARY


def test_auto_close_overwrites_stale_placeholder():
    """A leftover placeholder summary is treated as 'no summary' and replaced."""
    sid = core.start_session()
    core.end_session(sid, summary=core.PLACEHOLDER_SUMMARY)
    core.persist_task(sid, description="late task after placeholder close")
    core.auto_close_session(sid)
    _, summary = _session_summary(sid)
    assert "late task after placeholder close" in summary


def test_end_session_no_overwrite_keeps_real_summary():
    sid = core.start_session()
    core.end_session(sid, summary="genuine summary")
    core.end_session(sid, summary=core.PLACEHOLDER_SUMMARY, overwrite=False)
    _, summary = _session_summary(sid)
    assert summary == "genuine summary"
