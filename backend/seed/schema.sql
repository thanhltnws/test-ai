-- AI Insight Hub — local dev schema
-- Run once before import.py: psql $DATABASE_URL -f backend/seed/schema.sql

CREATE TABLE IF NOT EXISTS unified (
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
    ingested_at      TIMESTAMPTZ,
    extracted_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

ALTER TABLE unified DROP CONSTRAINT IF EXISTS unified_source_url_nonempty;
ALTER TABLE unified ADD CONSTRAINT unified_source_url_nonempty
    CHECK (source_url IS NOT NULL AND source_url <> '');

ALTER TABLE unified DROP CONSTRAINT IF EXISTS unified_funnel_stage_valid;
ALTER TABLE unified ADD CONSTRAINT unified_funnel_stage_valid
    CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));

ALTER TABLE unified DROP CONSTRAINT IF EXISTS unified_source_record_unique;
ALTER TABLE unified ADD CONSTRAINT unified_source_record_unique
    UNIQUE (source, source_id);

CREATE INDEX IF NOT EXISTS unified_source_idx       ON unified (source);
CREATE INDEX IF NOT EXISTS unified_funnel_idx       ON unified (funnel_stage);
CREATE INDEX IF NOT EXISTS unified_extracted_idx    ON unified (extracted_at DESC);
CREATE INDEX IF NOT EXISTS unified_source_url_idx   ON unified (source_url);
CREATE INDEX IF NOT EXISTS unified_icp_gin_idx      ON unified USING GIN (icp);
CREATE INDEX IF NOT EXISTS unified_pain_points_idx  ON unified USING GIN (pain_points);
