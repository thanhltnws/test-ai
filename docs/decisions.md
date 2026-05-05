# AI Insight Hub — Architecture Decision Records

> Documents finalized technical decisions. Do not re-open without clear justification.

---

## ADR-001 · Lambda polling instead of AppFlow

**Status:** Accepted

**Context:**
The ingestion layer needs to pull data from HubSpot, Jira, Email, and Push form on a schedule.

**Decision:**
Use custom Lambda polling for all sources. AppFlow remains in the architecture diagram but is not implemented.

**Reason:**
AppFlow is overkill for demo scale. Custom Lambda covers all sources, is easier to debug, and easier to explain during a demo.

**Rejected:**
- AppFlow — pre-built connectors exist but add configuration complexity not worth it at this scale.

---

## ADR-002 · Lambda ETL instead of AWS Glue

**Status:** Accepted

**Context:**
The transform layer needs to normalize schema, deduplicate, and map fields for structured data before passing to Bedrock extraction.

**Decision:**
Use Lambda ETL instead of Glue ETL.

**Reason:**
AWS Glue runs on a Spark cluster designed for big data. At ~500 docs/month demo scale, a Lambda function reading S3 and normalizing JSON is sufficient — simpler and easier to debug.

**Rejected:**
- AWS Glue — ~$3.65/month, over-engineering for this scale. Re-evaluate if moving to production.

---

## ADR-003 · Call Bedrock directly, no Comprehend or Macie pre-filter

**Status:** Accepted

**Context:**
Consider whether to pre-filter text before passing to Bedrock extraction — to reduce token cost (Comprehend) or strip PII (Macie).

**Decision:**
Call Bedrock directly. No Comprehend or Macie in the pipeline.

**Reason:**
Intended data sources (HubSpot deals, Jira tickets, internal email) do not contain sensitive PII requiring filtering. Adding Comprehend or Macie increases complexity without clear benefit at demo scope.

**Rejected:**
- Comprehend pre-filter — can be added later to reduce token cost at production scale.
- Macie PII detection — not necessary given current data sources.

---

## ADR-004 · Cloudflare Vectorize instead of Aurora pgvector or OpenSearch

**Status:** Accepted

**Context:**
Need a vector store for semantic search to support the RAG chatbox.

**Decision:**
Use Cloudflare Vectorize. Aurora stores structured fields only — pgvector extension not enabled.

**Reason:**
Vectorize is a purpose-built vector DB with a free tier suited for demo scale. pgvector on Aurora adds coupling between the structured store and vector store. OpenSearch costs ~$25+/month and is overkill for demo scope.

**Rejected:**
- Aurora pgvector — simpler infra but creates coupling between structured and vector stores.
- OpenSearch — powerful but over-engineering and costly.
- Qdrant / Weaviate / Pinecone — unnecessary when Vectorize is sufficient and free.

---

## ADR-005 · Gemini API for local dev, Bedrock for AWS deploy

**Status:** Accepted

**Context:**
Need an LLM for local development and testing before deploying to AWS.

**Decision:**
Use Gemini API (free tier) during local dev. Switch to Bedrock on AWS deploy — only the endpoint and credentials change, logic remains identical.

**Rejected:**
- Groq — free tier but less stable long-term than Gemini.
- Ollama — runs locally but requires 16GB+ RAM; risk of spending 2 days on setup is too high given the 3-week timeline.

---

## ADR-006 · Vectorize semantic search as primary RAG strategy, SQL as secondary

**Status:** Accepted

**Context:**
The RAG chatbox needs to retrieve context from the data store to enrich the prompt before calling Bedrock. Two options: Text-to-SQL on Aurora, or semantic search on Vectorize.

**Decision:**
Vectorize semantic search is primary. SQL query on Aurora is secondary — fixed SQL only, no Text-to-SQL. Both contexts are merged to enrich the prompt.

**Reason:**
Text-to-SQL hallucinates on ambiguous questions — silent failure: no crash, but wrong results returned. Vectorize similarity search does not carry this risk. SQL is still needed for structured fields (funnel_stage, icp) but only with pre-defined fixed queries.

**Rejected:**
- Text-to-SQL as primary — hallucination risk too high with no validation layer at demo scope.

---

## ADR-007 · Seed data to unblock development; full pipeline shown in demo

**Status:** Accepted

**Context:**
Backend and frontend development requires data in Aurora and Vectorize before the ingestion pipeline is complete. The ingestion pipeline is still being built and must be demonstrated end-to-end during the actual demo.

**Decision:**
Pre-seed Aurora and Vectorize with ~20–30 realistic records (HubSpot deals, Jira tickets, call notes) sourced from public datasets. This unblocks backend API and frontend UI development immediately. The seed data is for development only — the live demo will run the complete pipeline (Tier 1 ingestion → Tier 2 transform → Aurora/Vectorize) against real or prepared source records.

**Reason:**
Without seed data, backend and frontend work are blocked on the ingestion pipeline. Seeding decouples development tracks and allows parallel progress. The demo still shows the full end-to-end flow — seed data does not replace it.

**Rejected:**

- Waiting for real ingestion pipeline before starting backend/frontend — creates a sequential dependency that wastes time in a 3-week timeline.

---

## ADR-008 · Recharts instead of QuickSight

**Status:** Accepted

**Context:**
The dashboard needs to display charts (top pain points, funnel distribution, ICP cards).

**Decision:**
Render charts directly in the React frontend using Recharts.

**Reason:**
Recharts is sufficient for demo charts with no additional service required. QuickSight costs ~$18/month per author and adds an unnecessary dependency.

**Rejected:**
- QuickSight — powerful for BI but overkill and costly for demo scope.