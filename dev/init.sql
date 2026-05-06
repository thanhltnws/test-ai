-- AI Insight Hub — local dev schema
-- Auto-run by postgres container on first start (docker-entrypoint-initdb.d).
-- Keep in sync with docs/schema.md.

-- ── core tables ───────────────────────────────────────────────────────────────

CREATE TABLE insights (
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

ALTER TABLE insights ADD CONSTRAINT insights_source_url_nonempty
    CHECK (source_url IS NOT NULL AND source_url <> '');

ALTER TABLE insights ADD CONSTRAINT insights_funnel_stage_valid
    CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));

ALTER TABLE insights ADD CONSTRAINT insights_source_record_unique
    UNIQUE (source, source_id);

CREATE TABLE recommendations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL
);

-- ── indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX ON insights (source);
CREATE INDEX ON insights (funnel_stage);
CREATE INDEX ON insights (extracted_at DESC);
CREATE INDEX ON insights (source_url);
CREATE INDEX ON insights USING GIN (icp);
CREATE INDEX ON insights USING GIN (pain_points);

CREATE INDEX ON recommendations (computed_at DESC);
CREATE INDEX ON recommendations (period, period_start DESC, result_type);
