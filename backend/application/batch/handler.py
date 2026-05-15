"""
Batch compute Lambda — Feature 1 (Dashboard).

EventBridge triggers this daily. For each granularity (weekly, monthly,
quarterly, yearly) it decides whether to run based on the current date,
queries Aurora + pgvector for that period window, calls the LLM, and
appends new rows to the insights table (append-only, never overrides).

Local run:
    python backend/application/batch/handler.py
"""
import calendar
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pg8000.dbapi
from dotenv import load_dotenv
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from common.auth import auth_error, is_options_request, options_response
from prompt import build_batch_prompt

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

RESULT_TYPES = [
    "pain_points_summary",
    "funnel_distribution",
    "icp_narrative",
    "recommendations",
]

# Cached across Lambda invocations within the same container
_db_url_cache: str | None = None

_VECTOR_QUERIES = [
    "customer pain points and challenges",
    "sales objections and friction",
    "product use cases and applications",
]

_VECTOR_TOP_K_PER_QUERY = 10


# ── db ────────────────────────────────────────────────────────────────────────
# TODO: extract _get_db_url + _pg_connect to common/db.py — identical copy exists in chat/handler.py

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


# ── granularity schedule ──────────────────────────────────────────────────────

def _period_start(granularity: str, today: date) -> date:
    if granularity == "weekly":
        return today - timedelta(days=today.weekday())
    if granularity == "monthly":
        return today.replace(day=1)
    if granularity == "quarterly":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_month, day=1)
    if granularity == "yearly":
        return today.replace(month=1, day=1)
    raise ValueError(f"Unknown granularity: {granularity}")


def _is_last_day_of_quarter(d: date) -> bool:
    return (d.month, d.day) in {(3, 31), (6, 30), (9, 30), (12, 31)}


def _should_run(granularity: str, today: date) -> bool:
    if granularity in ("weekly", "monthly"):
        return True
    if granularity == "quarterly":
        # every Monday, plus the last day of each quarter for a clean final snapshot
        return today.weekday() == 0 or _is_last_day_of_quarter(today)
    if granularity == "yearly":
        # 1st of each month, plus Dec 31 for the year-end snapshot
        return today.day == 1 or (today.month == 12 and today.day == 31)
    return False


# ── aurora queries ─────────────────────────────────────────────────────────────

def query_aurora(conn, period_start: date, period_end: date) -> dict:
    ctx: dict = {}
    cur = conn.cursor()
    try:
        # COALESCE: use record_date when available, fall back to extracted_at date
        date_filter = "COALESCE(record_date, extracted_at::date) BETWEEN %s AND %s"

        cur.execute(
            f"SELECT COUNT(*), AVG(confidence_score) FROM signals WHERE {date_filter}",
            (period_start, period_end),
        )
        row = cur.fetchone()
        ctx["summary"] = {
            "total_signals": row[0],
            "avg_confidence": round(float(row[1] or 0), 2),
        }

        cur.execute(
            f"""
            SELECT pain_point, COUNT(*) AS cnt
            FROM signals, unnest(pain_points) AS pain_point
            WHERE pain_point <> '' AND {date_filter}
            GROUP BY pain_point
            ORDER BY cnt DESC
            """,
            (period_start, period_end),
        )
        ctx["top_pain_points"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT objection, COUNT(*) AS cnt
            FROM signals, unnest(objections) AS objection
            WHERE objection <> '' AND {date_filter}
            GROUP BY objection
            ORDER BY cnt DESC
            """,
            (period_start, period_end),
        )
        ctx["top_objections"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT use_case, COUNT(*) AS cnt
            FROM signals, unnest(use_cases) AS use_case
            WHERE use_case <> '' AND {date_filter}
            GROUP BY use_case
            ORDER BY cnt DESC
            """,
            (period_start, period_end),
        )
        ctx["top_use_cases"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT funnel_stage, COUNT(*) AS cnt
            FROM signals
            WHERE funnel_stage IS NOT NULL AND {date_filter}
            GROUP BY funnel_stage
            ORDER BY cnt DESC
            """,
            (period_start, period_end),
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
            f"""
            SELECT
                icp->>'sector'       AS sector,
                icp->>'company_size' AS company_size,
                icp->>'deal_size'    AS deal_size,
                icp->>'region'       AS region,
                COUNT(*)             AS cnt
            FROM signals
            WHERE icp IS NOT NULL AND {date_filter}
            GROUP BY sector, company_size, deal_size, region
            ORDER BY cnt DESC
            """,
            (period_start, period_end),
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


# ── pgvector queries ───────────────────────────────────────────────────────────

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

    client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    model_id = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "cohere.embed-multilingual-v3")
    embeddings = []
    for text in texts:
        resp = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"texts": [text], "input_type": "search_query", "embedding_types": ["float"]}),
        )
        embeddings.append(json.loads(resp["body"].read())["embeddings"]["float"][0])
    return embeddings


def _embed_queries(texts: list[str]) -> list[list[float]]:
    if _is_dev():
        return _embed_gemini(texts)
    return _embed_bedrock(texts)


def query_pgvector(conn, period_start: date, period_end: date) -> list[dict]:
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
                    e.signal_id,
                    i.source,
                    i.source_url,
                    i.funnel_stage,
                    e.embedding_text,
                    1 - (e.embedding <=> %s::vector) AS score
                FROM signal_embeddings e
                JOIN signals i ON i.id = e.signal_id
                WHERE COALESCE(i.record_date, i.extracted_at::date) BETWEEN %s AND %s
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (str(vector), period_start, period_end, str(vector), _VECTOR_TOP_K_PER_QUERY),
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
        "max_tokens": 8192,
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
        return _call_gemini(prompt_text)
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

def write_insights(
    conn, results: dict, granularity: str, period_start: date, period_end: date
) -> int:
    written = 0
    cur = conn.cursor()
    try:
        for rt in RESULT_TYPES:
            if rt not in results:
                continue
            cur.execute(
                """
                INSERT INTO insights (period, period_start, period_end, result_type, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (granularity, period_start, period_end, rt, json.dumps(results[rt])),
            )
            written += 1
        conn.commit()
    finally:
        cur.close()
    return written


# ── lambda handler ─────────────────────────────────────────────────────────────

def handler(event=None, context=None):
    load_dotenv()
    event = event or {}

    if is_options_request(event):
        return options_response()

    auth_failure = auth_error(event, allow_non_http=True)
    if auth_failure:
        return auth_failure

    today = date.today()
    granularities = ["weekly", "monthly", "quarterly", "yearly"]

    conn = _pg_connect()
    summary = {}
    try:
        for granularity in granularities:
            if not _should_run(granularity, today):
                print(f"[{granularity}] skipped (not due today)")
                continue

            period_start = _period_start(granularity, today)
            period_end   = today
            print(f"[{granularity}] period {period_start} → {period_end}")

            sql_ctx = query_aurora(conn, period_start, period_end)
            total = sql_ctx["summary"]["total_signals"]
            print(f"[{granularity}] {total} signals, avg_confidence={sql_ctx['summary']['avg_confidence']}")

            if total == 0:
                print(f"[{granularity}] no signals in window — skipping LLM call")
                summary[granularity] = {"written": 0, "skipped": "no data"}
                continue

            vector_ctx = query_pgvector(conn, period_start, period_end)
            print(f"[{granularity}] {len(vector_ctx)} semantic chunks")

            prompt  = build_batch_prompt(sql_ctx, vector_ctx, granularity, period_start, period_end)
            raw     = call_llm(prompt)
            results = parse_json_response(raw)
            written = write_insights(conn, results, granularity, period_start, period_end)
            print(f"[{granularity}] wrote {written} insight rows")
            summary[granularity] = {"written": written, "period_start": str(period_start)}

    finally:
        conn.close()

    return {
        "statusCode": 200,
        "body": json.dumps({"date": str(today), "granularities": summary}),
    }


if __name__ == "__main__":
    result = handler()
    print(json.dumps(result, indent=2))
