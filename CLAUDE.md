# CLAUDE.md

## Project

Internal demo — AI Insight Hub. Aggregates customer insights from HubSpot, Jira, email, and ops notes into a unified store, surfaces them via dashboard and RAG chatbox.

See `docs/architecture.md` for full system design.
<!-- See `docs/schema.md` for table definitions.
See `docs/decisions.md` for ADRs. -->

## Stack

| Layer | Local dev | AWS deploy |
|---|---|---|
| LLM | Gemini API (free) | Bedrock — Haiku (extract) · Sonnet (RAG, Case B) |
| DB | PostgreSQL + DBeaver | Aurora PostgreSQL Serverless v2 |
| Infra | — | CDK (TypeScript) |
| Functions | Python 3.12 + venv | Python Lambda |
| Frontend | Vite + React + Recharts | Amplify |

Gemini → Bedrock: swap endpoint + key only, logic unchanged.

## Conventions

- Prompts always in `prompt.py`, never inline in `handler.py`
- Each Lambda is self-contained with its own `requirements.txt`
- Pipeline outputs JSON — never generate raw SQL strings
- `source_url` is mandatory in every `unified` row — reject INSERT without it

## Data situation

No real sources yet. Use seed data in `backend/seed/data/` (20–30 mock records).
Import directly into Aurora — skip ingestion pipeline entirely for demo.

## Do not re-suggest

- OpenSearch / Titan Embeddings
- Kinesis
- QuickSight
- Comprehend pre-filter
- Text-to-SQL as primary RAG strategy — fixed SQL only, Text-to-SQL as fallback