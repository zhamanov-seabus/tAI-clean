"""Smoke tests for the MCP server module: tools registered, callable end-to-end."""

import asyncio

from tai_memory import mcp_server


def test_mcp_server_has_expected_tools():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "memory_recall",
        "memory_start_session",
        "memory_end_session",
        "memory_persist_task",
        "memory_add_fact",
        "memory_supersede_fact",
        "memory_add_artifact",
        "memory_recent_sessions",
    }
    missing = expected - names
    assert not missing, f"missing MCP tools: {missing}"


def test_mcp_recall_round_trip():
    sid = mcp_server.memory_start_session()
    mcp_server.memory_persist_task(
        session_id=sid,
        description="set up the local Postgres database",
        outcome="created the tai role and tai_memory db with pgvector enabled",
    )
    hits = mcp_server.memory_recall(query="setting up the postgres database locally")
    assert hits, "expected at least one hit"
    assert hits[0]["kind"] == "task"
    assert "postgres" in hits[0]["content"].lower()
