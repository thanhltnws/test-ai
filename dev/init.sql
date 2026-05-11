-- AI Insight Hub — local dev schema
-- Auto-run by postgres container on first start (docker-entrypoint-initdb.d).
-- Keep in sync with docs/schema.md.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── core tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insights (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source           TEXT         NOT NULL,
    source_id        TEXT         NOT NULL,
    source_url       TEXT         NOT NULL,
    raw_text         TEXT,
    pain_points      TEXT[],
    objections       TEXT[],
    use_cases        TEXT[],
    icp              JSONB,
    funnel_stage     TEXT,
    confidence_score NUMERIC(3,2) CHECK (confidence_score BETWEEN 0 AND 1),
    embedding_text   TEXT,
    ingested_at      TIMESTAMPTZ,
    extracted_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'insights_source_url_nonempty'
          AND conrelid = 'insights'::regclass
    ) THEN
        ALTER TABLE insights ADD CONSTRAINT insights_source_url_nonempty
            CHECK (source_url IS NOT NULL AND source_url <> '');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'insights_funnel_stage_valid'
          AND conrelid = 'insights'::regclass
    ) THEN
        ALTER TABLE insights ADD CONSTRAINT insights_funnel_stage_valid
            CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'insights_source_record_unique'
          AND conrelid = 'insights'::regclass
    ) THEN
        ALTER TABLE insights ADD CONSTRAINT insights_source_record_unique
            UNIQUE (source, source_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS recommendations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL
);

-- ── indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS insights_source_idx ON insights (source);
CREATE INDEX IF NOT EXISTS insights_funnel_stage_idx ON insights (funnel_stage);
CREATE INDEX IF NOT EXISTS insights_extracted_at_idx ON insights (extracted_at DESC);
CREATE INDEX IF NOT EXISTS insights_source_url_idx ON insights (source_url);
CREATE INDEX IF NOT EXISTS insights_icp_idx ON insights USING GIN (icp);
CREATE INDEX IF NOT EXISTS insights_pain_points_idx ON insights USING GIN (pain_points);

CREATE INDEX IF NOT EXISTS recommendations_computed_at_idx ON recommendations (computed_at DESC);
CREATE INDEX IF NOT EXISTS recommendations_period_period_start_result_type_idx
    ON recommendations (period, period_start DESC, result_type);

-- ── vector store ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insight_embeddings (
    insight_id     UUID         PRIMARY KEY REFERENCES insights(id) ON DELETE CASCADE,
    embedding_text TEXT         NOT NULL,
    embedding      vector(1024) NOT NULL,
    metadata       JSONB
);

CREATE INDEX IF NOT EXISTS insight_embeddings_embedding_idx
    ON insight_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS insight_embeddings_metadata_idx
    ON insight_embeddings USING GIN (metadata);
