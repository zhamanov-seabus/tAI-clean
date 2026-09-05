-- 002_indexes.sql — supporting indexes.
-- ivfflat lists is tuned for small corpora (<1k rows); bump when the dataset grows.

CREATE INDEX IF NOT EXISTS idx_tasks_session
    ON tasks(session_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_task
    ON artifacts(task_id);

-- Partial index covering only currently-active facts.
CREATE INDEX IF NOT EXISTS idx_facts_active
    ON facts(created_at)
    WHERE superseded_by IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_ref
    ON memory_index(postgres_ref_table, postgres_ref_id);

CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
    ON embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
