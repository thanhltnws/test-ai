"""
Batch compute Lambda — Feature 1 (Dashboard).

EventBridge triggers this daily. Queries Aurora (structured aggregates) and
Cloudflare Vectorize (semantic pattern context) in parallel, enriches a prompt
with both, then calls Gemini (dev) or Bedrock (prod) and appends a new row to
the recommendations table.

Local run:
    python backend/application/batch/handler.py
"""
import json
import os
import sys
# from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pg8000.dbapi
# import requests  # used by query_vectorize (disabled)
from dotenv import load_dotenv
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_batch_prompt

PERIOD       = "daily"
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

# Cached across Lambda invocations within the same container
_db_url_cache: str | None = None

# # Seed queries used to pull semantic pattern context from Vectorize
# _VECTOR_QUERIES = [
#     "customer pain points and challenges",
#     "sales objections and friction",
#     "product use cases and applications",
# ]


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


# ── vectorize queries (disabled) ───────────────────────────────────────────────

# def _embed(text: str, embed_url: str, headers: dict) -> list[float]:
#     resp = requests.post(embed_url, headers=headers, json={"text": [text]}, timeout=30)
#     resp.raise_for_status()
#     return resp.json()["result"]["data"][0]
#
#
# def _vector_query(vector: list[float], query_url: str, headers: dict) -> list[dict]:
#     resp = requests.post(
#         query_url,
#         headers=headers,
#         json={"vector": vector, "topK": 10, "returnMetadata": "all"},
#         timeout=30,
#     )
#     resp.raise_for_status()
#     return resp.json()["result"].get("matches", [])
#
#
# def query_vectorize() -> list[dict]:
#     account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
#     api_token  = os.environ.get("CLOUDFLARE_API_TOKEN")
#     index_name = os.environ.get("VECTORIZE_INDEX_NAME")
#     if not all([account_id, api_token, index_name]):
#         print("Vectorize skipped — creds not set")
#         return []
#
#     headers   = {"Authorization": f"Bearer {api_token}"}
#     embed_url = (
#         f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
#         f"/ai/run/@cf/baai/bge-m3"
#     )
#     query_url = (
#         f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
#         f"/vectorize/v2/indexes/{index_name}/query"
#     )
#
#     seen_ids: set[str] = set()
#     chunks: list[dict] = []
#
#     def fetch_one(query_text: str) -> list[dict]:
#         vector  = _embed(query_text, embed_url, headers)
#         matches = _vector_query(vector, query_url, headers)
#         results = []
#         for m in matches:
#             meta = m.get("metadata") or {}
#             uid  = meta.get("unified_id") or m["id"]
#             results.append({"uid": uid, "score": round(m["score"], 3), "meta": meta})
#         return results
#
#     try:
#         with ThreadPoolExecutor(max_workers=len(_VECTOR_QUERIES)) as ex:
#             futures = {ex.submit(fetch_one, q): q for q in _VECTOR_QUERIES}
#             for fut in as_completed(futures):
#                 for item in fut.result():
#                     if item["uid"] not in seen_ids:
#                         seen_ids.add(item["uid"])
#                         meta = item["meta"]
#                         chunks.append({
#                             "score":        item["score"],
#                             "source":       meta.get("source"),
#                             "source_url":   meta.get("source_url"),
#                             "funnel_stage": meta.get("funnel_stage"),
#                         })
#     except Exception as exc:
#         print(f"Vectorize error: {exc}")
#
#     chunks.sort(key=lambda x: x["score"], reverse=True)
#     return chunks


# ── llm calls ──────────────────────────────────────────────────────────────────

def _is_dev() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


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
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
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
        sql_ctx    = query_aurora(conn, period_start)
        vector_ctx: list[dict] = []  # Vectorize disabled

        # # Query Aurora and Vectorize in parallel
        # with ThreadPoolExecutor(max_workers=2) as ex:
        #     sql_fut    = ex.submit(query_aurora, conn, period_start)
        #     vector_fut = ex.submit(query_vectorize)
        #     sql_ctx    = sql_fut.result()
        #     vector_ctx = vector_fut.result()

        total = sql_ctx["summary"]["total_insights"]
        print(
            f"Aurora: {total} insights, avg_confidence={sql_ctx['summary']['avg_confidence']}"
        )
        # print(f"Vectorize: {len(vector_ctx)} semantic chunks")

        if total == 0:
            print("No insights in period window — skipping LLM call.")
            return {"statusCode": 200, "body": "no data"}

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
