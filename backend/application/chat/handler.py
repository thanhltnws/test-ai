"""
Chat Lambda — Feature 2 (Chatbox / RAG).

Nhận câu hỏi free-text từ end user qua POST /chat, truy vấn Aurora (structured
signals) và pgvector (semantic chunks), merge context, gọi Gemini (dev) hoặc
Bedrock Claude Sonnet (prod),
trả về { answer, references }.

Local run:
    python backend/application/chat/handler.py
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import pg8000.dbapi
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from common.auth import auth_error, cors_headers, error_response, is_options_request, options_response
from prompt import build_chat_prompt

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
_VECTOR_TOP_K = 8
_MAX_QUESTION_CHARS = 2000

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
        cur.execute("SELECT COUNT(*), AVG(confidence_score) FROM signals")
        row = cur.fetchone()
        ctx["total_signals"] = row[0]
        ctx["avg_confidence"] = round(float(row[1] or 0), 2)

        cur.execute(
            """
            SELECT pain_point, COUNT(*) AS cnt
            FROM signals, unnest(pain_points) AS pain_point
            WHERE pain_point <> ''
            GROUP BY pain_point
            ORDER BY cnt DESC LIMIT 15
            """
        )
        ctx["top_pain_points"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT use_case, COUNT(*) AS cnt
            FROM signals, unnest(use_cases) AS use_case
            WHERE use_case <> ''
            GROUP BY use_case
            ORDER BY cnt DESC LIMIT 10
            """
        )
        ctx["top_use_cases"] = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute(
            """
            SELECT funnel_stage, COUNT(*) AS cnt
            FROM signals
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
                FROM signals
                WHERE {conditions}
                ORDER BY confidence_score DESC LIMIT 8
                """,
                params,
            )
            ctx["relevant_signals"] = [
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
            ctx["relevant_signals"] = []

        return ctx
    finally:
        cur.close()


# ── pgvector query ─────────────────────────────────────────────────────────────

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
    if _llm_provider() == "gemini":
        return _embed_gemini(texts)
    return _embed_bedrock(texts)


def query_pgvector(conn, question: str) -> list[dict]:
    try:
        question_vector = _embed_queries([question])[0]
    except Exception as exc:
        print(f"pgvector embedding skipped: {exc}")
        return []

    cur = conn.cursor()
    try:
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
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (str(question_vector), str(question_vector), _VECTOR_TOP_K),
        )
        return [
            {
                "signal_id": str(r[0]),
                "score": round(float(r[5]), 3),
                "source": r[1],
                "source_url": r[2],
                "funnel_stage": r[3],
                "embedding_text": r[4],
            }
            for r in cur.fetchall()
        ]
    except Exception as exc:
        print(f"pgvector query skipped: {exc}")
        return []
    finally:
        cur.close()


# ── llm calls ──────────────────────────────────────────────────────────────────

def _llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "bedrock").strip().lower()


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
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt_text}],
    })
    resp = client.invoke_model(
        modelId=os.environ.get(
            "BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"
        ),
        body=body,
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def call_llm(prompt_text: str) -> str:
    if _llm_provider() == "gemini":
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


# ── lambda handler ─────────────────────────────────────────────────────────────

def lambda_handler(event=None, context=None):
    load_dotenv()
    event = event or {}

    if is_options_request(event):
        return options_response()

    auth_failure = auth_error(event)
    if auth_failure:
        return auth_failure

    # Parse request body
    try:
        body = json.loads(event.get("body") or "{}")
        question = (body.get("question") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        return error_response(400, "Invalid JSON body")

    if not question:
        return error_response(400, "Field 'question' is required and must not be empty")
    if len(question) > _MAX_QUESTION_CHARS:
        return error_response(413, f"Question is too long. Max {_MAX_QUESTION_CHARS} characters.")

    print(f"Question: {question!r}")

    conn = _pg_connect()
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_sql    = ex.submit(query_aurora, conn, question)
            f_vector = ex.submit(query_pgvector, conn, question)
        sql_ctx    = f_sql.result()
        vector_ctx = f_vector.result()

        print(
            f"Aurora: {sql_ctx['total_signals']} total signals, "
            f"{len(sql_ctx['relevant_signals'])} keyword-matched rows"
        )
        print(f"pgvector: {len(vector_ctx)} semantic chunks")

        prompt = build_chat_prompt(question, sql_ctx, vector_ctx)
        raw = call_llm(prompt)
        result = parse_json_response(raw)

        # Ensure required keys are present
        answer = result.get("answer", "")
        references = result.get("references", [])[:5]

        return {
            "statusCode": 200,
            "headers": cors_headers(),
            "body": json.dumps(
                {"answer": answer, "references": references},
                ensure_ascii=False,
            ),
        }

    except Exception as exc:
        print(f"Error: {exc}")
        return error_response(500, str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What are the main software pain points?"
    result = lambda_handler(
        {"body": json.dumps({"question": question})},
        None,
    )
    print(json.dumps(json.loads(result["body"]), indent=2, ensure_ascii=False))
