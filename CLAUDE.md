# CLAUDE.md

## Project

Internal demo — AI Insight Hub. Aggregates customer insights from CRM note, email, Teams transcript, Jira/Redmine note into a insights store, surfaces them via dashboard and RAG chatbox.

See `docs/break_problem.md` for problem analysis.
See `docs/architecture.md` for full system design.
See `docs/schema.md` for table definitions.
See `docs/decisions.md` for ADRs.
See `docs/scope.md` for scope, limitations, prerequisites.
See `docs/faq.md` for technical Q&A.

## Stack

| Layer | Local dev | AWS deploy |
|---|---|---|
| LLM | Gemini API (free) | Bedrock — Haiku (extract) · Sonnet (RAG, batch) |
| Embeddings | Gemini Embedding | Bedrock — Cohere embed-multilingual-v3 |
| DB | PostgreSQL + pgvector | Aurora PostgreSQL Serverless v2 + pgvector |
| Infra | — | CDK (TypeScript) |
| Functions | Python 3.12 + venv | Python Lambda |
| Frontend | React + Vercel |

Gemini → Bedrock: swap endpoint + key only, logic unchanged.

## Conventions

- Prompts always in `prompt.py`, never inline in `handler.py`
- Each Lambda is self-contained with its own `requirements.txt`
- Pipeline outputs JSON — never generate raw SQL strings
- `source_url` is optional — populated when the source has an external URL (CRM, Jira, Redmine); NULL is valid for email, form, and ops note sources

## Data situation

No real sources yet. Mock data in `backend/seed/data/raw/` (6 source files, ~1000 raw records, Feb–Jun 2026).

Seed workflow:
1. `generate.py` — LLM extraction → `signals_seed.json`
2. `import.py` — load into Aurora (signals) + pgvector (embeddings)
3. `run_batch.py` — backfill insights across all historical periods
