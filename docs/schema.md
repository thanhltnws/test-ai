# AI Insight Hub — Database Schema

Aurora PostgreSQL Serverless v2. Local dev: PostgreSQL via psycopg2.

---

## Tables

### `unified`

Core table. One row per insight extracted by AI from a source record.

```sql
CREATE TABLE unified (
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

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Surrogate key |
| `source` | TEXT | `hubspot` · `jira` · `crm` · `email` · `form` |
| `source_id` | TEXT | Original record ID in source system |
| `source_url` | TEXT | **Mandatory.** Deep link to originating record — HubSpot deal URL, Jira ticket URL, etc. INSERT rejected if NULL or empty. |
| `raw_text` | TEXT | Original unstructured text passed to Bedrock/Gemini |
| `pain_points` | TEXT[] | Extracted customer pain points |
| `objections` | TEXT[] | Sales objections raised |
| `use_cases` | TEXT[] | Use cases mentioned |
| `icp` | JSONB | ICP signals — see structure below |
| `funnel_stage` | TEXT | `awareness` · `consideration` · `negotiation` · `won` · `lost` |
| `confidence_score` | NUMERIC(3,2) | 0.00–1.00, model self-reported confidence |
| `ingested_at` | TIMESTAMPTZ | When raw record arrived in S3 |
| `extracted_at` | TIMESTAMPTZ | When AI extraction completed |

#### `icp` JSONB structure

```json
{
  "sector": "fintech",
  "company_size": "50-200",
  "deal_size": "large",
  "region": "Southeast Asia"
}
```

| Field | Example values |
|---|---|
| `sector` | `fintech` · `logistics` · `retail` · `healthcare` · `manufacturing` |
| `company_size` | `1-10` · `11-50` · `50-200` · `200-1000` · `1000+` |
| `deal_size` | `small` · `medium` · `large` |
| `region` | `Vietnam` · `Southeast Asia` · `International` |

```sql
-- Reject INSERT without source_url at DB level
ALTER TABLE unified ADD CONSTRAINT unified_source_url_nonempty
    CHECK (source_url IS NOT NULL AND source_url <> '');

-- Enforce valid funnel stages
ALTER TABLE unified ADD CONSTRAINT unified_funnel_stage_valid
    CHECK (funnel_stage IN ('awareness', 'consideration', 'negotiation', 'won', 'lost'));

-- Dedup: one AI extraction per source record
ALTER TABLE unified ADD CONSTRAINT unified_source_record_unique
    UNIQUE (source, source_id);
```

---

### `table_c`

Pre-computed batch results from Feature 1 (Dashboard). Written by the EventBridge-triggered Lambda, read by `GET /insights/summary`.

```sql
CREATE TABLE table_c (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    period       TEXT        NOT NULL,
    period_start DATE        NOT NULL,
    result_type  TEXT        NOT NULL,
    payload      JSONB       NOT NULL
);
```

| Column | Type | Notes |
|---|---|---|
| `period` | TEXT | `daily` · `weekly` |
| `period_start` | DATE | Start of the compute window |
| `result_type` | TEXT | `pain_points_summary` · `funnel_distribution` · `icp_narrative` · `recommendations` |
| `payload` | JSONB | Full Bedrock response for this result type |

```sql
-- Prevent duplicate runs for the same window
ALTER TABLE table_c ADD CONSTRAINT table_c_period_unique
    UNIQUE (period, period_start, result_type);
```

---

### Seed / Staging Tables (Demo)

Imported directly from `seed-data/` — bypasses Tier 1 & 2.

#### `crm_accounts`

```sql
CREATE TABLE crm_accounts (
    account          TEXT PRIMARY KEY,
    sector           TEXT,
    year_established INT,
    revenue          TEXT,
    employees        INT,
    office_location  TEXT,
    subsidiary_of    TEXT
);
```

#### `crm_products`

```sql
CREATE TABLE crm_products (
    product     TEXT PRIMARY KEY,
    series      TEXT,
    sales_price NUMERIC(12,2)
);
```

#### `crm_sales_teams`

```sql
CREATE TABLE crm_sales_teams (
    sales_agent     TEXT PRIMARY KEY,
    manager         TEXT,
    regional_office TEXT
);
```

#### `crm_sales_pipeline`

```sql
CREATE TABLE crm_sales_pipeline (
    opportunity_id TEXT    PRIMARY KEY,
    sales_agent    TEXT    REFERENCES crm_sales_teams(sales_agent),
    product        TEXT    REFERENCES crm_products(product),
    account        TEXT    REFERENCES crm_accounts(account),
    deal_stage     TEXT,
    engage_date    DATE,
    close_date     DATE,
    close_value    NUMERIC(12,2)
);
```

Deal stages in seed data: `Prospecting` · `Engaging` · `Won` · `Lost`

#### `ict_customers`

From `seed-data/sales_b2b_ict/b2b_ict_customer_dataset.csv`.

```sql
CREATE TABLE ict_customers (
    customer_id              TEXT    PRIMARY KEY,
    industry                 TEXT,
    company_size             TEXT,
    first_purchase_date      DATE,
    last_renewal_date        DATE,
    total_projects           INT,
    total_vendors            INT,
    total_spend              NUMERIC(14,2),
    services_provided        TEXT,
    delivery_effort_days     INT,
    support_contract_hours   INT,
    support_hours_used       INT,
    customer_satisfaction    NUMERIC(3,1),
    is_upsell_opportunity    BOOLEAN,
    churn_risk               TEXT,
    contract_renewed         BOOLEAN
);
```

#### `marketing_leads`

From `seed-data/marketing_lead_scoring/`.

```sql
CREATE TABLE marketing_leads (
    lead_id          TEXT    PRIMARY KEY,
    lead_origin      TEXT,
    lead_source      TEXT,
    do_not_email     BOOLEAN,
    do_not_call      BOOLEAN,
    converted        BOOLEAN,
    occupation       TEXT,
    country          TEXT,
    visited_page     TEXT,
    last_activity    TEXT,
    lead_score       NUMERIC(5,2),
    lead_quality     TEXT
);
```

> Column names mapped from raw CSV headers. Adjust if actual CSV schema differs.

---

## Seed Data → `unified` Mapping

When transforming seed data into `unified` rows, apply the following mappings:

### `crm_sales_pipeline.deal_stage` → `unified.funnel_stage`

| Source value | `funnel_stage` |
|---|---|
| `Prospecting` | `awareness` |
| `Engaging` | `consideration` |
| `Won` | `won` |
| `Lost` | `lost` |

> `negotiation` has no direct equivalent in CRM seed data — populated from Jira/OFBiz issues where applicable.

### Source → `unified.source`

| Seed table / file | `source` value |
|---|---|
| `crm_sales_pipeline` | `crm` |
| `ict_customers` | `crm` |
| `marketing_leads` | `hubspot` |
| `ofbiz_issues.json` | `jira` |

### `source_url` convention for seed data

| Source | Format |
|---|---|
| `jira` | `https://issues.apache.org/jira/browse/{issue_key}` |
| `crm` | `https://demo.twentycrm.io/objects/opportunities/{opportunity_id}` |
| `hubspot` | `https://app.hubspot.com/contacts/demo/deals/{lead_id}` |

---

## Indexes

```sql
-- unified: common filter and join patterns
CREATE INDEX ON unified (source);
CREATE INDEX ON unified (funnel_stage);
CREATE INDEX ON unified (extracted_at DESC);
CREATE INDEX ON unified (source_url);
CREATE INDEX ON unified USING GIN (icp);          -- JSONB field queries
CREATE INDEX ON unified USING GIN (pain_points);  -- array contains queries

-- table_c: dashboard fetch pattern
CREATE INDEX ON table_c (period, period_start DESC, result_type);
```

---

## Cloudflare Vectorize (companion vector store)

Not PostgreSQL — documented here for completeness.

Each vector entry mirrors a row in `unified`:

| Metadata field | Maps to |
|---|---|
| `unified_id` | `unified.id` |
| `source` | `unified.source` |
| `source_url` | `unified.source_url` — **mandatory** |
| `funnel_stage` | `unified.funnel_stage` |
| `extracted_at` | `unified.extracted_at` |

Text chunk embedded: `raw_text` (split by sentence if > 512 tokens).

---

## Seed Data Import Order

For demo: skip Tier 1 & Tier 2. Import in this order to respect foreign key dependencies:

```
1. crm_accounts
2. crm_products
3. crm_sales_teams
4. crm_sales_pipeline        ← depends on 1, 2, 3
5. ict_customers
6. marketing_leads
7. unified                   ← populated via AI extraction on ofbiz_issues.json + crm_sales_pipeline
```

`ofbiz_issues.json` is the primary source for populating `unified` in the demo. Each Jira issue maps to one `unified` row; the AI extraction step runs locally using Gemini.