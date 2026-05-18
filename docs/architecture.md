# AI Insight Hub — System Architecture

> Internal showcase / demo. Not production.

---

## Overview

AI Insight Hub aggregates customer insights scattered across HubSpot, Jira/Redmine, email, and manual notes into a signals store, then surfaces them through a dashboard and a natural-language chatbox.

```
Data Sources → Ingestion (Lambda + S3) → Transform (Lambda ETL + Bedrock) → Aurora + pgvector → Application (Dashboard + Chat)
```

---

## Tier 1 — Ingestion

All sources are pulled via **Lambda + API Gateway** on a schedule. Raw data is dumped as-is to S3 — no parsing at this stage.

| Source | Data captured |
|---|---|
| HubSpot | Deals, call notes |
| Twenty CRM | Contacts, pipeline stages |
| Jira / Redmine | Ticket descriptions |
| Outlook Email | Email body |
| Teams Transcript | Meeting and call transcripts |
| SharePoint | Documents, ops notes |
| Push form | Ops notes, call notes (manual fallback) |

S3 path convention: `raw/{source}/{date}/{timestamp}_{id}.json`

---

## Tier 2 — Transform

Two sequential steps.

### Step 1 — Lambda ETL

Normalize schema, rule-based dedup, field mapping for structured fields (deal stage, ticket status, form data). AWS Glue was rejected — Spark cluster is over-engineering at ~500 docs/month demo scale (ADR-002).

### Step 2 — Bedrock / Claude

Processes unstructured text (CRM note, email, Teams transcript, Jira/Redmine note). Two parallel outputs:

**Output A — Structured extraction → Aurora PostgreSQL `signals` table**

| Field | Description |
|---|---|
| `pain_points` | Customer pain points |
| `objections` | Sales objections raised |
| `use_cases` | Use cases mentioned |
| `icp` | Ideal Customer Profile signals |
| `funnel_stage` | Where the customer is in the funnel |
| `confidence_score` | Model confidence in the extraction |
| `source_url` | Link back to the originating Jira ticket or HubSpot deal |

`source_url` is optional — populated when the source has an external URL (CRM deal, Jira/Redmine ticket). NULL for sources with no deep link (email body, form submission, ops notes).

**Output B — Vector embedding → Aurora pgvector (`signal_embeddings`)**

`embedding_text` (AI-generated NL summary) is embedded and stored in `signal_embeddings` with `source_url` in metadata. Enables semantic search at the Application layer.

---

## Tier 3 — Application

Built on API Gateway + Lambda. Two independent features. Both enrich the Bedrock prompt using context from **Aurora** (structured) and **pgvector** (semantic) before generating a response.

### Feature 1 · Dashboard (batch)

EventBridge triggers `InsightsBuilderFn` (`ai-insight-hub-insights-builder`) daily.

```
EventBridge scheduler
  → InsightsBuilderFn (ai-insight-hub-insights-builder)
      → SQL query Aurora signals           (structured aggregates)
      → pgvector semantic search           (pattern context)
      → single prompt with both contexts
      → Bedrock / Claude  →  single JSON with 4 keys:
            pain_points_summary · funnel_distribution
            icp_narrative · recommendations
      → INSERT 4 rows into Aurora insights (one per result_type)
  → GET /insights
  → Frontend · Dashboard (charts, ICP cards, recommendations)
```

### Feature 2 · Chatbox (RAG)

User submits a free-text question. `ChatFn` (`ai-insight-hub-chat`) retrieves context from both stores, enriches the prompt, and returns the response.

```
POST /chat
  → ChatFn (ai-insight-hub-chat)
      → SQL query Aurora signals           (structured fields + source_url)
      → pgvector semantic search           (relevant chunks + source_url)
      → merge context → enrich prompt
  → Bedrock / Claude
  → JSON { answer, references }
  → Frontend · Chatbox (answer + chip links → Jira / HubSpot)
```

Fixed SQL is the primary Aurora query strategy. Text-to-SQL is last-resort fallback only.

---

## Services

| Tier | Service | Role |
|---|---|---|
| Ingestion | Lambda + API Gateway | Poll sources, dump raw to S3 |
| Ingestion | S3 | Raw landing zone |
| Transform | Lambda ETL | Schema normalize, dedup, field map |
| Transform | Bedrock / Claude | AI field extraction from unstructured text |
| Store | Aurora PostgreSQL | `signals` table (source of truth) + `insights` (pre-computed) |
| Store | Aurora pgvector | Vector index — `signal_embeddings` + source_url metadata |
| Application | EventBridge | Batch scheduler |
| Application | InsightsBuilderFn (`ai-insight-hub-insights-builder`) | Batch compute |
| Application | DashboardApiFn (`ai-insight-hub-dashboard-api`) | REST API — GET /insights |
| Application | ChatFn (`ai-insight-hub-chat`) | RAG handler — POST /chat |
| Application | Bedrock / Claude | Prompt enrichment, ICP narrative, recommendations, RAG answers |
| Application | API Gateway | REST API layer |
| Application | Vercel | Web frontend — React + Vite |

---

## Key Design Decisions

Service and tooling choices (Lambda polling vs AppFlow, Lambda ETL vs Glue, pgvector vs Vectorize, Gemini vs Bedrock, Recharts vs QuickSight, fixed SQL vs Text-to-SQL) are documented in [`decisions.md`](decisions.md).

The following decisions are architectural — not yet in decisions.md:

- **`source_url` in `signals` and pgvector metadata** — links back to the originating CRM/Jira/Redmine record when available; optional, NULL for sources without an external URL.
- **Two-layer idempotency in Transform Lambda** — S3 object tag `processed=true` is the file-level guard: on duplicate S3 events the tag is checked first and the Lambda returns early (Bedrock never called). `ON CONFLICT (source, source_id) DO UPDATE` in Aurora is the record-level guard: re-processing the same file overwrites existing rows with the latest extraction result rather than creating duplicates. The UPSERT semantics are intentional — re-running with an updated prompt or model produces better extractions that should replace the old ones.
- **Dual prompt enrichment** — both Feature 1 and Feature 2 enrich the Bedrock prompt with context from Aurora (structured) and pgvector (semantic) before generating output.
- **Feature 1 and Feature 2 are fully decoupled** — Dashboard reads pre-computed data (fast, stable). Chatbox runs real-time RAG (flexible, ad-hoc).
- **Embedding model must be consistent between write and query** — the model used to embed `embedding_text` when writing to `signal_embeddings` / `insight_embeddings` must be the same model used to embed the user question at query time in the Chat Lambda. Mixing models produces incorrect cosine similarity with no error or warning. Full rule and checklist in [`docs/chat_optimization.md`](chat_optimization.md).

---

## Known Gaps

- Text-to-SQL hallucination risk — no validation layer yet. Mitigate by prioritizing fixed SQL and logging generated queries.
- No data quality gate — Bedrock extraction output is not validated before INSERT. Schema validation in Lambda recommended before going beyond demo.
