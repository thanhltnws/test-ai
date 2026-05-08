# AI Insight Hub — Database Schema

Aurora PostgreSQL Serverless v2. Local dev: PostgreSQL via psycopg2.

---

## Tables

### `insights`

Core table. One row per insight extracted by AI from a source record.

```sql
CREATE TABLE insights (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source           TEXT        NOT NULL,
    source_id        TEXT        NOT NULL,
    source_url       TEXT        NOT NULL,
    raw_text         TEXT,
    pain_points      TEXT[],
    objections       TEXT[],
    use_cases        TEXT[],
    icp              JSONB,
    funnel_stage     TEXT,
    confidence_score NUMERIC(3,2) CHECK (confidence_score BETWEEN 0 AND 1),
    ingested_at      TIMESTAMPTZ,
    extracted_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column             | Type         | Notes                                                                                                                      |
| ------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `id`               | UUID         | Surrogate key                                                                                                              |
| `source`           | TEXT         | `hubspot` · `jira` · `crm` · `email` · `form`                                                                              |
| `source_id`        | TEXT         | Original record ID in source system                                                                                        |
| `source_url`       | TEXT         | **Mandatory.** Deep link to originating record — HubSpot deal URL, Jira ticket URL, etc. INSERT rejected if NULL or empty. |
| `raw_text`         | TEXT         | Original unstructured text passed to Bedrock/Gemini                                                                        |
| `pain_points`      | TEXT[]       | Extracted customer pain points                                                                                             |
| `objections`       | TEXT[]       | Sales objections raised                                                                                                    |
| `use_cases`        | TEXT[]       | Use cases mentioned                                                                                                        |
| `icp`              | JSONB        | ICP signals — see structure below                                                                                          |
| `funnel_stage`     | TEXT         | `awareness` · `consideration` · `negotiation` · `won` · `lost`                                                             |
| `confidence_score` | NUMERIC(3,2) | 0.00–1.00, model self-reported confidence                                                                                  |
| `ingested_at`      | TIMESTAMPTZ  | When raw record arrived in S3                                                                                              |
| `extracted_at`     | TIMESTAMPTZ  | When AI extraction completed                                                                                               |

#### `icp` JSONB structure

```json
{
  "sector": "fintech",
  "company_size": "50-200",
  "deal_size": "large",
  "region": "Southeast Asia"
}
```

| Field          | Example values                                                      |
| -------------- | ------------------------------------------------------------------- |
| `sector`       | `fintech` · `logistics` · `retail` · `healthcare` · `manufacturing` |
| `company_size` | `1-10` · `11-50` · `50-200` · `200-1000` · `1000+`                  |
| `deal_size`    | `small` · `medium` · `large`                                        |
| `region`       | `Vietnam` · `Southeast Asia` · `International`                      |

```sql
-- Reject INSERT without source_url at DB level
ALTER TABLE insights ADD CONSTRAINT insights_source_url_nonempty
    CHECK (source_url IS NOT NULL AND source_url <> '');

-- Enforce valid funnel stages
ALTER TABLE insights ADD CONSTRAINT insights_funnel_stage_valid
    CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));

-- Dedup: one AI extraction per source record
ALTER TABLE insights ADD CONSTRAINT insights_source_record_unique
    UNIQUE (source, source_id);
```

---

### `recommendations`

Pre-computed batch results from Feature 1 (Dashboard). Written by the EventBridge-triggered Lambda, read by `GET /insights/summary`.

```sql
CREATE TABLE recommendations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL
);
```

| Column         | Type  | Notes                                                                               |
| -------------- | ----- | ----------------------------------------------------------------------------------- |
| `period`       | TEXT  | `daily`                                                                             |
| `period_start` | DATE  | Start of the compute window                                                         |
| `result_type`  | TEXT  | `pain_points_summary` · `funnel_distribution` · `icp_narrative` · `recommendations` |
| `payload`      | JSONB | Full Bedrock response for this result type                                          |

---

## Indexes

```sql
-- insights: common filter and join patterns
CREATE INDEX ON insights (source);
CREATE INDEX ON insights (funnel_stage);
CREATE INDEX ON insights (extracted_at DESC);
CREATE INDEX ON insights (source_url);
CREATE INDEX ON insights USING GIN (icp);          -- JSONB field queries
CREATE INDEX ON insights USING GIN (pain_points);  -- array contains queries

-- recommendations: each day appends new rows, query by recency
CREATE INDEX ON recommendations (computed_at DESC);
CREATE INDEX ON recommendations (period, period_start DESC, result_type);
```

---

### `insight_chunks`

pgvector store co-located with PostgreSQL. One row per text chunk of `insights.raw_text`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE insight_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insight_id  UUID NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    chunk_index INT  NOT NULL,
    chunk_text  TEXT,
    embedding   vector(1024),
    UNIQUE (insight_id, chunk_index)
);

CREATE INDEX ON insight_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
```

| Column        | Type         | Notes                                         |
| ------------- | ------------ | --------------------------------------------- |
| `insight_id`  | UUID         | FK → `insights.id`                            |
| `chunk_index` | INT          | 0-based chunk order within the source record  |
| `chunk_text`  | TEXT         | ~512-token slice of `raw_text` (≈ 2048 chars) |
| `embedding`   | vector(1024) | Gemini `text-embedding-004` output            |

Embedding model: Gemini `text-embedding-004` (768 dims) via `GEMINI_API_KEY`.
