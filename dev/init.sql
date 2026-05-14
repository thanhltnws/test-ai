-- AI Insight Hub — local dev schema
-- Auto-run by postgres container on first start (docker-entrypoint-initdb.d).
-- Keep in sync with docs/schema.md.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── core tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signals (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source           TEXT         NOT NULL,
    source_id        TEXT         NOT NULL,
    source_url       TEXT,
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
        WHERE conname = 'signals_funnel_stage_valid'
          AND conrelid = 'signals'::regclass
    ) THEN
        ALTER TABLE signals ADD CONSTRAINT signals_funnel_stage_valid
            CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'signals_source_record_unique'
          AND conrelid = 'signals'::regclass
    ) THEN
        ALTER TABLE signals ADD CONSTRAINT signals_source_record_unique
            UNIQUE (source, source_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS insights (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL
);

-- ── indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS signals_source_idx ON signals (source);
CREATE INDEX IF NOT EXISTS signals_funnel_stage_idx ON signals (funnel_stage);
CREATE INDEX IF NOT EXISTS signals_extracted_at_idx ON signals (extracted_at DESC);
CREATE INDEX IF NOT EXISTS signals_source_url_idx ON signals (source_url);
CREATE INDEX IF NOT EXISTS signals_icp_idx ON signals USING GIN (icp);
CREATE INDEX IF NOT EXISTS signals_pain_points_idx ON signals USING GIN (pain_points);

CREATE INDEX IF NOT EXISTS insights_computed_at_idx ON insights (computed_at DESC);
CREATE INDEX IF NOT EXISTS insights_period_period_start_result_type_idx
    ON insights (period, period_start DESC, result_type);

-- ── vector store ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signal_embeddings (
    signal_id      UUID         PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    embedding_text TEXT         NOT NULL,
    embedding      vector(1024) NOT NULL,
    metadata       JSONB
);

CREATE INDEX IF NOT EXISTS signal_embeddings_embedding_idx
    ON signal_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS signal_embeddings_metadata_idx
    ON signal_embeddings USING GIN (metadata);
