-- 001_init.sql — base schema for tai-memory.
-- Extensions (vector, pgcrypto) are installed in setup as superuser; not in this migration.

CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'closed', 'abandoned'))
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    description     TEXT NOT NULL,
    outcome         TEXT,
    decisions_made  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    type         TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content         TEXT NOT NULL,
    source_task_id  UUID REFERENCES tasks(task_id) ON DELETE SET NULL,
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    superseded_by   UUID REFERENCES facts(fact_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Source-of-truth pointer for vectors. Dedupe via content_hash UNIQUE.
CREATE TABLE IF NOT EXISTS memory_index (
    vector_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    postgres_ref_table  TEXT NOT NULL CHECK (postgres_ref_table IN ('tasks', 'facts', 'artifacts')),
    postgres_ref_id     UUID NOT NULL,
    content_hash        TEXT NOT NULL UNIQUE,
    embedded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    version             INT  NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS embeddings (
    vector_id  UUID PRIMARY KEY REFERENCES memory_index(vector_id) ON DELETE CASCADE,
    embedding  vector(384) NOT NULL
);
