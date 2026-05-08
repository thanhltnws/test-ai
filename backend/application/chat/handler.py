"""
Chat Lambda — Feature 2 (Chatbox / RAG).

Nhận câu hỏi free-text từ end user qua POST /chat, truy vấn Aurora (structured
insights) và pgvector (semantic chunks — comment out, chờ bảng insight_embedding
được tạo), merge context, gọi Gemini (dev) hoặc Bedrock Claude Sonnet (prod),
trả về { answer, references }.

Local run:
    python backend/application/chat/handler.py
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pg8000.dbapi
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_chat_prompt

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

_STOP_WORDS = {
    "what", "are", "the", "is", "in", "of", "for", "and", "to", "a", "an",
    "how", "why", "which", "that", "this", "do", "does", "was", "were",
    "have", "has", "had", "by", "on", "at", "from", "with", "about",
    "our", "my", "your", "their", "we", "i", "you", "they", "it",
    "top", "most", "main", "key", "list", "show", "me", "give", "tell",
}

_db_url_cache: str | None = None


# ── db connection ──────────────────────────────────────────────────────────────

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


# ── aurora query ───────────────────────────────────────────────────────────────

def _extract_keywords(question: str) -> list[str]:
    words = question.lower().split()
    return [w.strip("?,!.'\"") for w in words if w.strip("?,!.'\"") not in _STOP_WORDS and len(w) > 2]


def query_aurora(conn, question: str) -> dict:
    ctx: dict = {}
    cur = conn.cursor()
    try:
        # 1. Background aggregates — always included regardless of question
        cur.execute("SELECT COUNT(*), AVG(confidence_score) FROM insights")
        row = cur.fetchone()
        ctx["total_insights"] = row[0]
        ctx["avg_confidence"] = round(float(row[1] or 0), 2)

        cur.execute(
            """
            SELECT pain_point, COUNT(*) AS cnt
            FROM insights, unnest(pain_points) AS pain_point
            WHERE pain_point <> ''
            GROUP BY pain_point
            ORDER BY cnt DESC LIMIT 15
            """
        )
        ctx["top_pain_points"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT use_case, COUNT(*) AS cnt
            FROM insights, unnest(use_cases) AS use_case
            WHERE use_case <> ''
            GROUP BY use_case
            ORDER BY cnt DESC LIMIT 10
            """
        )
        ctx["top_use_cases"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT funnel_stage, COUNT(*) AS cnt
            FROM insights
            WHERE funnel_stage IS NOT NULL
            GROUP BY funnel_stage
            ORDER BY cnt DESC
            """
        )
        rows = cur.fetchall()
        total = sum(r[1] for r in rows)
        ctx["funnel_distribution"] = [
            {"stage": r[0], "count": r[1], "pct": round(r[1] / total * 100, 1) if total else 0}
            for r in rows
        ]

        # 2. Keyword-matched rows — fixed SQL, no text-to-SQL
        keywords = _extract_keywords(question)
        if keywords:
            conditions = " OR ".join(["raw_text ILIKE %s"] * len(keywords))
            params = [f"%{kw}%" for kw in keywords]
            cur.execute(
                f"""
                SELECT source_url, pain_points, use_cases, funnel_stage, confidence_score
                FROM insights
                WHERE {conditions}
                ORDER BY confidence_score DESC LIMIT 8
                """,
                params,
            )
            ctx["relevant_insights"] = [
                {
                    "source_url": r[0],
                    "pain_points": r[1],
                    "use_cases": r[2],
                    "funnel_stage": r[3],
                    "confidence_score": float(r[4]) if r[4] is not None else None,
                }
                for r in cur.fetchall()
            ]
        else:
            ctx["relevant_insights"] = []

        return ctx
    finally:
        cur.close()


# ── pgvector query (comment out — bảng insight_embedding chưa được tạo) ────────

# def _embed_question(question: str) -> list[float]:
#     """
#     Embed câu hỏi để query pgvector.
#     Embedding model sẽ được chốt khi tạo bảng insight_embedding.
#     """
#     raise NotImplementedError("Chưa chốt embedding model")
#
#
# def query_pgvector(conn, question: str) -> list[dict]:
#     """
#     Semantic search trên bảng insight_embedding (pgvector).
#     Bảng dự kiến:
#
#       CREATE TABLE insight_embedding (
#           id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#           insights_id  UUID REFERENCES insights(id),
#           chunk_text   TEXT NOT NULL,
#           embedding    vector(768),   -- chiều phụ thuộc embedding model
#           chunk_index  INT DEFAULT 0
#       );
#       CREATE INDEX ON insight_embedding USING ivfflat (embedding vector_cosine_ops);
#
#     Uncomment khi:
#       1. Bảng insight_embedding đã được tạo và đã seed dữ liệu.
#       2. Embedding model đã được chốt và _embed_question() đã được implement.
#     """
#     question_vec = _embed_question(question)
#     cur = conn.cursor()
#     try:
#         cur.execute(
#             """
#             SELECT ie.chunk_text, i.source_url, i.funnel_stage,
#                    1 - (ie.embedding <=> %s::vector) AS score
#             FROM insight_embedding ie
#             JOIN insights i ON ie.insights_id = i.id
#             ORDER BY ie.embedding <=> %s::vector
#             LIMIT 8
#             """,
#             (question_vec, question_vec),
#         )
#         return [
#             {
#                 "chunk_text": r[0],
#                 "source_url": r[1],
#                 "funnel_stage": r[2],
#                 "score": round(float(r[3]), 3),
#             }
#             for r in cur.fetchall()
#         ]
#     finally:
#         cur.close()


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
        "max_tokens": 2048,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt_text}],
    })
    resp = client.invoke_model(
        modelId=os.environ.get(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
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


# ── helpers ────────────────────────────────────────────────────────────────────

def _cors_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _error(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": _cors_headers(),
        "body": json.dumps({"error": message}),
    }


# ── lambda handler ─────────────────────────────────────────────────────────────

def lambda_handler(event=None, context=None):
    load_dotenv()

    # Parse request body
    try:
        body = json.loads(event.get("body") or "{}")
        question = (body.get("question") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        return _error(400, "Invalid JSON body")

    if not question:
        return _error(400, "Field 'question' is required and must not be empty")

    print(f"Question: {question!r}")

    conn = _pg_connect()
    try:
        sql_ctx = query_aurora(conn, question)
        vector_ctx: list[dict] = []  # pgvector disabled — insight_embedding table not yet created
        # vector_ctx = query_pgvector(conn, question)

        print(
            f"Aurora: {sql_ctx['total_insights']} total insights, "
            f"{len(sql_ctx['relevant_insights'])} keyword-matched rows"
        )

        prompt = build_chat_prompt(question, sql_ctx, vector_ctx)
        raw = call_llm(prompt)
        result = parse_json_response(raw)

        # Ensure required keys are present
        answer = result.get("answer", "")
        references = result.get("references", [])[:5]

        return {
            "statusCode": 200,
            "headers": _cors_headers(),
            "body": json.dumps(
                {"answer": answer, "references": references},
                ensure_ascii=False,
            ),
        }

    except Exception as exc:
        print(f"Error: {exc}")
        return _error(500, str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What are the top pain points in fintech?"
    result = lambda_handler(
        {"body": json.dumps({"question": question})},
        None,
    )
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
