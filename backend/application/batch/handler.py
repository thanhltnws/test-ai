"""
Batch compute Lambda — Feature 1 (Dashboard).

EventBridge triggers this daily. Queries Aurora (structured aggregates) and
Aurora pgvector (semantic pattern context), enriches a prompt
with both, then calls Gemini (dev) or Bedrock (prod) and appends a new row to
the recommendations table.

Local run:
    python backend/application/batch/handler.py
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pg8000.dbapi
from dotenv import load_dotenv
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_batch_prompt

PERIOD       = "daily"
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# Cached across Lambda invocations within the same container
_db_url_cache: str | None = None

# Seed queries used to pull semantic pattern context from pgvector.
_VECTOR_QUERIES = [
    "customer pain points and challenges",
    "sales objections and friction",
    "product use cases and applications",
]

_VECTOR_TOP_K_PER_QUERY = 10


# ── db url ────────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    global _db_url_cache
    if _db_url_cache:
        return _db_url_cache

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        import boto3
        sm = boto3.client("secretsmanager")
        s = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
        _db_url_cache = (
            f"postgresql://{s['username']}:{s['password']}"
            f"@{s['host']}:{s.get('port', 5432)}/{s['dbname']}"
        )
    else:
        _db_url_cache = os.environ.get("DATABASE_URL", "")

    if not _db_url_cache:
        raise RuntimeError("Set DB_SECRET_ARN (AWS) or DATABASE_URL (local)")

    return _db_url_cache


def _pg_connect():
    u = urlparse(_get_db_url())
    return pg8000.dbapi.connect(
        host=u.hostname,
        database=u.path.lstrip("/"),
        user=u.username,
        password=u.password,
        port=u.port or 5432,
    )


# ── period window ──────────────────────────────────────────────────────────────

def get_period_start() -> date:
    return date.today()


# ── aurora queries ─────────────────────────────────────────────────────────────

def query_aurora(conn, period_start: date) -> dict:
    ctx: dict = {}
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*), AVG(confidence_score) FROM insights WHERE extracted_at >= %s",
            (period_start,),
        )
        row = cur.fetchone()
        ctx["summary"] = {
            "total_insights": row[0],
            "avg_confidence": round(float(row[1] or 0), 2),
        }

        cur.execute(
            """
            SELECT pain_point, COUNT(*) AS cnt
            FROM insights, unnest(pain_points) AS pain_point
            WHERE extracted_at >= %s AND pain_point <> ''
            GROUP BY pain_point
            ORDER BY cnt DESC
            LIMIT 20
            """,
            (period_start,),
        )
        ctx["top_pain_points"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT objection, COUNT(*) AS cnt
            FROM insights, unnest(objections) AS objection
            WHERE extracted_at >= %s AND objection <> ''
            GROUP BY objection
            ORDER BY cnt DESC
            LIMIT 15
            """,
            (period_start,),
        )
        ctx["top_objections"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT use_case, COUNT(*) AS cnt
            FROM insights, unnest(use_cases) AS use_case
            WHERE extracted_at >= %s AND use_case <> ''
            GROUP BY use_case
            ORDER BY cnt DESC
            LIMIT 15
            """,
            (period_start,),
        )
        ctx["top_use_cases"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT funnel_stage, COUNT(*) AS cnt
            FROM insights
            WHERE extracted_at >= %s AND funnel_stage IS NOT NULL
            GROUP BY funnel_stage
            ORDER BY cnt DESC
            """,
            (period_start,),
        )
        rows = cur.fetchall()
        total = sum(r[1] for r in rows)
        ctx["funnel_distribution"] = [
            {
                "stage": r[0],
                "count": r[1],
                "pct": round(r[1] / total * 100, 1) if total else 0,
            }
            for r in rows
        ]

        cur.execute(
            """
            SELECT
                icp->>'sector'       AS sector,
                icp->>'company_size' AS company_size,
                icp->>'deal_size'    AS deal_size,
                icp->>'region'       AS region,
                COUNT(*)             AS cnt
            FROM insights
            WHERE extracted_at >= %s AND icp IS NOT NULL
            GROUP BY sector, company_size, deal_size, region
            ORDER BY cnt DESC
            LIMIT 15
            """,
            (period_start,),
        )
        ctx["icp_breakdown"] = [
            {
                "sector": r[0],
                "company_size": r[1],
                "deal_size": r[2],
                "region": r[3],
                "count": r[4],
            }
            for r in cur.fetchall()
        ]

        return ctx
    finally:
        cur.close()


# pgvector queries

def _embed_gemini(texts: list[str]) -> list[list[float]]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    embeddings = []
    for text in texts:
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=1024,
            ),
        )
        embeddings.append(result.embeddings[0].values)
    return embeddings


def _embed_bedrock(texts: list[str]) -> list[list[float]]:
    import boto3

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    embeddings = []
    for text in texts:
        resp = client.invoke_model(
            modelId=os.environ.get(
                "BEDROCK_EMBEDDING_MODEL_ID", "apac.amazon.titan-embed-text-v2:0"
            ),
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
        )
        embeddings.append(json.loads(resp["body"].read())["embedding"])
    return embeddings


def _embed_queries(texts: list[str]) -> list[list[float]]:
    if _is_dev():
        print("Embeddings: Gemini (dev/local)")
        return _embed_gemini(texts)
    print("Embeddings: Bedrock (prod)")
    return _embed_bedrock(texts)


def query_pgvector(conn, period_start: date) -> list[dict]:
    try:
        query_vectors = _embed_queries(_VECTOR_QUERIES)
    except Exception as exc:
        print(f"pgvector embedding skipped: {exc}")
        return []

    seen_ids: set[str] = set()
    chunks: list[dict] = []
    cur = conn.cursor()
    try:
        for query_text, vector in zip(_VECTOR_QUERIES, query_vectors):
            cur.execute(
                """
                SELECT
                    e.insight_id,
                    i.source,
                    i.source_url,
                    i.funnel_stage,
                    e.embedding_text,
                    1 - (e.embedding <=> %s::vector) AS score
                FROM insight_embeddings e
                JOIN insights i ON i.id = e.insight_id
                WHERE i.extracted_at >= %s
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (str(vector), period_start, str(vector), _VECTOR_TOP_K_PER_QUERY),
            )
            for row in cur.fetchall():
                uid = str(row[0])
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                chunks.append({
                    "query": query_text,
                    "score": round(float(row[5]), 3),
                    "source": row[1],
                    "source_url": row[2],
                    "funnel_stage": row[3],
                    "embedding_text": row[4],
                })
    except Exception as exc:
        print(f"pgvector query skipped: {exc}")
        return []
    finally:
        cur.close()

    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks


# ── llm calls ──────────────────────────────────────────────────────────────────

def _is_dev() -> bool:
    env = (
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("ENV")
        or os.environ.get("STAGE")
        or ""
    ).strip().lower()
    if env:
        return env in {"local", "dev", "development", "test"}

    return not (
        os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("DB_SECRET_ARN")
    )


def _call_gemini(prompt_text: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt_text,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return resp.text


def _call_bedrock(prompt_text: str) -> str:
    import boto3

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt_text}],
    })
    resp = client.invoke_model(
        modelId=os.environ.get(
            "BEDROCK_MODEL_ID", "apac.anthropic.claude-3-haiku-20240307-v1:0"
        ),
        body=body,
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def call_llm(prompt_text: str) -> str:
    if _is_dev():
        print("LLM: Gemini (dev)")
        return _call_gemini(prompt_text)
    print("LLM: Bedrock (prod)")
    return _call_bedrock(prompt_text)


# ── response parsing ───────────────────────────────────────────────────────────

def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── write results ──────────────────────────────────────────────────────────────

RESULT_TYPES = [
    "pain_points_summary",
    "funnel_distribution",
    "icp_narrative",
    "recommendations",
]


def write_recommendations(
    conn, results: dict, period: str, period_start: date
) -> int:
    written = 0
    cur = conn.cursor()
    try:
        for rt in RESULT_TYPES:
            if rt not in results:
                continue
            cur.execute(
                """
                INSERT INTO recommendations (period, period_start, result_type, payload)
                VALUES (%s, %s, %s, %s)
                """,
                (period, period_start, rt, json.dumps(results[rt])),
            )
            written += 1
        conn.commit()
    finally:
        cur.close()
    return written


# ── lambda handler ─────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    load_dotenv()

    period_start = get_period_start()
    print(f"Period: {PERIOD}, period_start: {period_start}")

    conn = _pg_connect()
    try:
        sql_ctx = query_aurora(conn, period_start)

        total = sql_ctx["summary"]["total_insights"]
        print(
            f"Aurora: {total} insights, avg_confidence={sql_ctx['summary']['avg_confidence']}"
        )
        if total == 0:
            print("No insights in period window — skipping LLM call.")
            return {"statusCode": 200, "body": "no data"}

        vector_ctx = query_pgvector(conn, period_start)
        print(f"pgvector: {len(vector_ctx)} semantic chunks")

        prompt  = build_batch_prompt(sql_ctx, vector_ctx, PERIOD)
        raw     = call_llm(prompt)
        results = parse_json_response(raw)
        written = write_recommendations(conn, results, PERIOD, period_start)
        print(f"Wrote {written} recommendation rows for {period_start}.")

        return {
            "statusCode": 200,
            "body": json.dumps({"period_start": str(period_start), "written": written}),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    result = handler()
    print(json.dumps(result, indent=2))
