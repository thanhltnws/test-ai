# AI Insight Hub

Internal demo. Aggregates customer insights from CRM, email, call transcripts, and ops notes into a unified store, then surfaces them through a dashboard and a natural-language chatbox.

```text
Data Sources → Ingestion (Lambda + S3) → Transform (Lambda + Bedrock) → Aurora + pgvector → Dashboard / Chatbox.
```

---

## Docs

| File | Contents |
| --- | --- |
| [`docs/break_problem.md`](docs/break_problem.md) | Problem analysis — why this system exists |
| [`docs/architecture.md`](docs/architecture.md) | Three-tier architecture, data flow, service list |
| [`docs/decisions.md`](docs/decisions.md) | ADRs — why we chose what |
| [`docs/scope.md`](docs/scope.md) | Scope, limitations, prerequisites |
| [`docs/faq.md`](docs/faq.md) | Technical Q&A — design decisions explained |
| [`docs/schema.md`](docs/schema.md) | Table definitions, indexes |

---

## Stack

| Layer | Local dev | AWS deploy |
| --- | --- | --- |
| LLM | Gemini API (free) | Bedrock — Haiku (extract) · Sonnet (RAG, batch) |
| Embeddings | Gemini Embedding | Bedrock — Cohere embed-multilingual-v3 |
| Database | PostgreSQL + pgvector | Aurora PostgreSQL Serverless v2 + pgvector |
| Functions | Python 3.12 | Lambda |
| Infra | — | CDK (TypeScript) |
| Frontend | React + Vercel |

---

## Project structure

```text
ai-insight-hub/
│
├── docs/                         ← see table above
│
├── backend/
│   ├── ingestion/
│   │   └── handler.py            ← Lambda: load from data sources → S3 raw/
│   │
│   ├── transform/
│   │   ├── handler.py            ← Lambda: S3 ObjectCreated → LLM extract → Aurora signals
│   │   └── prompt.py
│   │
│   ├── application/
│   │   ├── batch/                ← Lambda: EventBridge → aggregate signals → insights table
│   │   │   ├── handler.py
│   │   │   └── prompt.py
│   │   ├── chat/                 ← Lambda: POST /chat — dual-context RAG
│   │   │   ├── handler.py
│   │   │   └── prompt.py
│   │   ├── api/                  ← Lambda: GET /insights — dashboard data
│   │   │   └── handler.py
│   │   └── common/
│   │       └── auth.py
│   │
│   └── seed/                     ← local dev only — not deployed
│       ├── generate.py           ← read raw/, call Gemini, output signals_seed.json
│       ├── import.py             ← import signals_seed.json → Aurora + pgvector
│       ├── prompt.py
│       └── data/
│           ├── raw/              ← 6 source JSON files, committed to git
│           └── signals_seed.json ← generated, gitignored
│
├── infra/                        ← CDK TypeScript
│   ├── bin/app.ts
│   └── lib/
│       └── application-stack.ts
│
├── frontend/                     ← React + Vite
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   └── Chat.tsx
│   │   └── api/
│   │       └── lambdas.ts
│   └── package.json
│
├── dev/
│   ├── docker-compose.yml        ← PostgreSQL 17 + pgvector
│   └── init.sql                  ← DDL: signals, insights, signal_embeddings, insight_embeddings
│
├── .env.example                  ← copy to .env, fill in keys
├── .gitignore
└── requirements.txt              ← root-level deps for local scripts
```

---

## Getting started

### 1. Clone and configure

```bash
git clone <repo-url>
cd ai-insight-hub
cp .env.example .env
# Fill in GEMINI_API_KEY and DATABASE_URL in .env
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start the local database

Requires Docker. Starts a PostgreSQL 17 container with pgvector and runs the schema DDL automatically on first boot.

```bash
docker compose -f dev/docker-compose.yml up -d
```

Add to `.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_insight_hub
```

To wipe and recreate the database from scratch: `docker compose -f dev/docker-compose.yml down -v && docker compose -f dev/docker-compose.yml up -d`

### 4. Generate and import seed data

Set providers in `.env` before running:

```env
SEED_LLM_PROVIDER=gemini          # gemini (default) or bedrock
SEED_EMBEDDING_PROVIDER=gemini    # gemini, bedrock, or cloudflare
```

The raw source files in `backend/seed/data/raw/` contain mock data covering February — mid-May 2026.

There are three ways to get data into the local database — pick the one that fits:

#### Option A — Use the existing `signals_seed.json`

The repo may already have a generated file. Just import it directly:

```bash
python backend/seed/import.py
```

#### Option B — Regenerate `signals_seed.json` from raw sources

Re-runs extraction on the 6 files in `backend/seed/data/raw/` via LLM, then imports:

```bash
python backend/seed/generate.py
python backend/seed/import.py
```

#### Option C — Use your own raw data

Edit or replace files in `backend/seed/data/raw/`, then run Option B above.

### 5. Backfill batch insights for seed data

Populates the `insights` table across all historical periods in the seed data (weekly/monthly/quarterly/yearly × all markets). Required for the dashboard to have data to display.

> **Note:** the time range is hardcoded in `run_batch.py` to match the default `signals_seed.json` (Feb–Jun 2026). If you generated your own seed data, update `DATA_START` and `DATA_END` in that file to match your data before running.

```bash
python backend/seed/run_batch.py
```

If the LLM step completes but embedding fails mid-run, re-run with `--embed-only` to skip re-calling the LLM:

```bash
python backend/seed/run_batch.py --embed-only
```

---

## Running each component locally

```bash
python backend/application/batch/handler.py       # batch Lambda
python backend/application/api/handler.py         # GET /insights
python backend/application/chat/handler.py        # POST /chat
```

To test the Transform Lambda locally via SAM:

```bash
# Update events/s3_transform.json with a valid S3 key first
sam build && sam local invoke TransformFunction -e events/s3_transform.json
```

---
