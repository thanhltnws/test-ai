# AI Insight Hub — System Architecture

> Internal showcase / demo. Not production.

---

## Overview

AI Insight Hub aggregates customer insights scattered across HubSpot, Jira/Redmine, email, and manual notes into a insights store, then surfaces them through a dashboard and a natural-language chatbox.

```
Data Sources → Ingestion (Lambda + S3) → Transform (Glue + Bedrock) → Aurora + Vectorize → Application (Feature 1 + Feature 2)
```

---

## Tier 1 — Ingestion

All sources are pulled via **Lambda + API Gateway** on a schedule. Raw data is dumped as-is to S3 — no parsing at this stage.

| Source | Data captured |
|---|---|
| HubSpot | Deals, call notes |
| CRM | Contacts, pipeline stages |
| Jira / Redmine | Ticket descriptions |
| Email (Gmail / Outlook API) | Email body |
| Push form | Ops notes, call notes (manual fallback) |

S3 path convention: `raw/{source}/{date}/{timestamp}_{id}.json`

---

## Tier 2 — Transform

Two sequential steps.

### Step 1 — AWS Glue ETL

Normalize schema, rule-based dedup, field mapping for structured fields (deal stage, ticket status, form data).

### Step 2 — Bedrock / Claude

Processes unstructured text (call notes, email body, ops notes). Two parallel outputs:

**Output A — Structured extraction → Aurora PostgreSQL `insights` table**

| Field | Description |
|---|---|
| `pain_points` | Customer pain points |
| `objections` | Sales objections raised |
| `use_cases` | Use cases mentioned |
| `icp` | Ideal Customer Profile signals |
| `funnel_stage` | Where the customer is in the funnel |
| `confidence_score` | Model confidence in the extraction |
| `source_url` | Link back to the originating Jira ticket or HubSpot deal |

`source_url` is mandatory — every row in `insights` must have it. Reject any INSERT missing this field.

**Output B — Vector embedding → Cloudflare Vectorize**

Raw text chunks are embedded and stored in Vectorize with `source_url` in metadata. Enables semantic search at the Application layer.

---

## Tier 3 — Application

Built on API Gateway + Lambda. Two independent features. Both enrich the Bedrock prompt using context from **Aurora** (structured) and **Vectorize** (semantic) before generating a response.

### Feature 1 · Dashboard (batch)

EventBridge triggers Lambda daily or weekly.

```
EventBridge scheduler
  → Lambda batch compute
      → SQL query Aurora insights          (structured aggregates)
      → Vectorize semantic search         (pattern context)
      → enrich prompt with both contexts
      → Bedrock / Claude
          Case A → top pain points, funnel distribution
          Case B → ICP narrative, action recommendations for Sales & Marketing
  → Aurora recommendations (pre-computed results)
  → GET /insights/summary
  → Frontend · Dashboard (charts, ICP cards, recommendations)
```

### Feature 2 · Chatbox (RAG)

User submits a free-text question. Lambda retrieves context from both stores, enriches the prompt, and streams the response back.

```
POST /chat
  → Lambda RAG
      → SQL query Aurora insights          (structured fields + source_url)
      → Vectorize semantic search         (relevant raw chunks + source_url)
      → merge context → enrich prompt
  → Bedrock / Claude
  → streaming JSON { answer, references }
  → Frontend · Chatbox (answer + chip links → Jira / HubSpot)
```

Fixed SQL is the primary Aurora query strategy. Text-to-SQL is last-resort fallback only.

---

## Services

| Tier | Service | Role |
|---|---|---|
| Ingestion | Lambda + API Gateway | Poll sources, dump raw to S3 |
| Ingestion | S3 | Raw landing zone |
| Transform | AWS Glue ETL | Schema normalize, dedup, field map |
| Transform | Bedrock / Claude | AI field extraction from unstructured text |
| Store | Aurora PostgreSQL | `insights` table (source of truth) + `recommendations` (pre-computed) |
| Store | Cloudflare Vectorize | Vector index — raw text chunks + source_url metadata |
| Store | ElastiCache Redis | API response cache |
| Application | EventBridge | Batch scheduler |
| Application | Lambda | Batch compute + RAG handler |
| Application | Bedrock / Claude | Prompt enrichment, ICP narrative, recommendations, RAG answers |
| Application | API Gateway | REST API layer |
| Application | Amplify | Web frontend — React + Vite + Recharts |

---

## Key Design Decisions

- **`source_url` is mandatory in `insights` and Vectorize metadata** — every response in both features links back to the exact Jira ticket or HubSpot deal that produced the insight.
- **Dual prompt enrichment** — both Feature 1 and Feature 2 enrich Bedrock prompt with context from Aurora (structured) and Vectorize (semantic) before generating output.
- **Feature 1 and Feature 2 are fully decoupled** — Dashboard reads pre-computed data (fast, stable). Chatbox runs real-time RAG (flexible, ad-hoc).
- **Fixed SQL is primary for Aurora queries** — Text-to-SQL deferred as fallback only, due to hallucination risk on complex queries.
- **Bedrock called directly, no Comprehend pre-filter** — simpler for demo scope. Comprehend can be added later to reduce token cost.
- **No ingestion pipeline for demo** — seed data imported directly into Aurora and Vectorize, bypassing Tier 1 and Tier 2 entirely.

---

## Known Gaps

- External customer workspaces (Jira, Slack) lose access when a project ends — ingestion must capture data before access is revoked.
- OpenSearch and Titan Embeddings deferred — Cloudflare Vectorize covers semantic search needs for demo scope.
- Kinesis real-time stream deferred — batch ingestion is sufficient for demo.
- Text-to-SQL hallucination risk — no validation layer yet. Mitigate by prioritizing fixed SQL and logging generated queries.
- No data quality gate — Bedrock extraction output is not validated before INSERT. Schema validation in Lambda recommended before going beyond demo.