# AI Insight Hub

Internal demo. Aggregates customer insights from HubSpot, Jira, email, and ops notes into a unified store, then surfaces them through a dashboard and a natural-language chatbox.

```text
Data Sources → Ingestion (Lambda + S3) → Transform (Lambda ETL + Bedrock) → Aurora + Vectorize → Dashboard / Chatbox
```

---

## Stack

| Layer | Local dev | AWS deploy |
| --- | --- | --- |
| LLM | Gemini API (free) | Bedrock — Haiku (extract) · Sonnet (RAG, Case B) |
| Database | PostgreSQL | Aurora PostgreSQL Serverless v2 |
| Vector store | — | Cloudflare Vectorize |
| Functions | Python 3.12 | Lambda |
| Infra | — | CDK (TypeScript) |
| Frontend | Vite + React + Recharts | Amplify |

---

## Project structure

```text
ai-insight-hub/
│
├── docs/
│   ├── architecture.md       ← full system design
│   ├── schema.md             ← Aurora table definitions
│   └── decisions.md          ← ADRs — why we chose what
│
├── backend/
│   ├── ingestion/
│   │   ├── hubspot/          ← Lambda: poll HubSpot deals + call notes
│   │   └── jira/             ← Lambda: poll Jira tickets
│   │
│   ├── transform/
│   │   ├── lambda_etl/       ← Lambda: normalize schema, dedup, field map
│   │   └── bedrock_extract/  ← Lambda: AI extraction → unified table
│   │       ├── handler.py
│   │       └── prompt.py     ← prompt template (never inline in handler)
│   │
│   ├── application/
│   │   ├── batch/            ← Lambda: EventBridge-triggered dashboard compute
│   │   │   └── handler.py    ← Case A (aggregates) + Case B (ICP narrative)
│   │   └── rag/              ← Lambda: POST /chat RAG handler
│   │       ├── handler.py
│   │       └── prompt.py
│   │
│   └── seed/                 ← local dev only — not deployed
│       ├── generate.py       ← read raw/, call Gemini, output unified_seed.json
│       ├── import.py         ← import unified_seed.json → Aurora + Vectorize (stub)
│       ├── prompt.py
│       ├── requirements.txt
│       ├── raw/              ← source datasets, committed to git
│       │   ├── marketing/
│       │   │   └── marketing_lead_scoring/
│       │   ├── sales/
│       │   │   ├── sales_pipeline_crm/
│       │   │   └── sales_b2b_ict/
│       │   └── ops/
│       │       └── ofbiz_issues.json
│       └── data/
│           └── unified_seed.json   ← generated, gitignored
│
├── infra/                    ← CDK TypeScript
│   ├── bin/app.ts
│   └── lib/
│       ├── ingestion-stack.ts
│       ├── transform-stack.ts
│       └── application-stack.ts
│
├── frontend/                 ← React + Vite
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   └── Chat.tsx
│   │   └── components/
│   ├── package.json
│   └── amplify.yml
│
├── .env.example              ← copy to .env, fill in keys
├── .gitignore
└── requirements.txt          ← root-level deps for local scripts
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

### 3. Create the database

Create a local PostgreSQL database and run the DDL from [`docs/schema.md`](docs/schema.md).

```bash
createdb ai_insight_hub
# then paste the CREATE TABLE statements from docs/schema.md into psql
```

### 4. Generate and import seed data

```bash
# Generate ~28 records by calling Gemini on backend/seed/raw/
python backend/seed/generate.py

# Import into PostgreSQL
python backend/seed/import.py
```

`generate.py` accepts `--jira N` and `--crm N` to control sample sizes.

---

## Docs

| File | Contents |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Three-tier architecture, data flow, service list |
| [`docs/schema.md`](docs/schema.md) | `unified` and `table_c` table definitions, indexes, seed mappings |
| [`docs/decisions.md`](docs/decisions.md) | ADRs — Vectorize vs OpenSearch, fixed SQL vs Text-to-SQL, Gemini vs Bedrock, etc. |
