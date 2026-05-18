-- AI Insight Hub — local dev schema
-- Auto-run by postgres container on first start (docker-entrypoint-initdb.d).
-- Keep in sync with docs/schema.md.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── core tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signals (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source         TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    source_url     TEXT,
    pain_points    TEXT[],
    objections     TEXT[],
    use_cases      TEXT[],
    deal_size      TEXT         CHECK (deal_size      IN ('small', 'medium', 'large')),
    client_type    TEXT         CHECK (client_type    IN ('individual', 'startup', 'corporate')),
    tech_maturity  TEXT         CHECK (tech_maturity  IN ('non-tech', 'semi-tech', 'technical')),
    market         TEXT         CHECK (market         IN ('vietnam', 'japan', 'korea', 'international')),
    sector         TEXT,
    funnel_stage   TEXT         CHECK (funnel_stage   IN ('awareness', 'consideration', 'negotiation', 'won', 'lost')),
    embedding_text TEXT,
    record_date    DATE,
    ingested_at    TIMESTAMPTZ,
    extracted_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT signals_source_record_unique UNIQUE (source, source_id)
);

CREATE TABLE IF NOT EXISTS insights (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    period_end   DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    market       TEXT,
    payload      JSONB       NOT NULL
);

-- ── indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS signals_market_idx          ON signals (market);
CREATE INDEX IF NOT EXISTS signals_sector_idx          ON signals (sector);
CREATE INDEX IF NOT EXISTS signals_market_sector_idx   ON signals (market, sector);
CREATE INDEX IF NOT EXISTS signals_funnel_stage_idx    ON signals (funnel_stage);
CREATE INDEX IF NOT EXISTS signals_source_idx          ON signals (source);
CREATE INDEX IF NOT EXISTS signals_extracted_at_idx    ON signals (extracted_at DESC);
CREATE INDEX IF NOT EXISTS signals_deal_size_idx       ON signals (deal_size);
CREATE INDEX IF NOT EXISTS signals_client_type_idx     ON signals (client_type);
CREATE INDEX IF NOT EXISTS signals_tech_maturity_idx   ON signals (tech_maturity);
CREATE INDEX IF NOT EXISTS signals_pain_points_idx     ON signals USING GIN (pain_points);

CREATE INDEX IF NOT EXISTS insights_period_slice_idx   ON insights (period, period_start, result_type, market);
CREATE INDEX IF NOT EXISTS insights_computed_at_idx    ON insights (computed_at DESC);

-- ── vector stores ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signal_embeddings (
    signal_id      UUID         PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    embedding_text TEXT         NOT NULL,
    embedding      vector(1024) NOT NULL,
    embedded_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    metadata       JSONB
);

CREATE INDEX IF NOT EXISTS signal_embeddings_embedding_idx ON signal_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS signal_embeddings_metadata_idx  ON signal_embeddings USING GIN  (metadata);

CREATE TABLE IF NOT EXISTS insight_embeddings (
    insight_id     UUID         PRIMARY KEY REFERENCES insights(id) ON DELETE CASCADE,
    embedding_text TEXT         NOT NULL,
    embedding      vector(1024) NOT NULL,
    embedded_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    metadata       JSONB
);

CREATE INDEX IF NOT EXISTS insight_embeddings_embedding_idx ON insight_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS insight_embeddings_metadata_idx  ON insight_embeddings USING GIN  (metadata);
