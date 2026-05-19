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
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pg8000.dbapi
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from common.auth import auth_error, cors_headers, error_response, is_options_request, options_response
from prompt import build_chat_prompt

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
BEDROCK_INTENT_MODEL = "global.anthropic.claude-haiku-4-5-20251001"
_VECTOR_TOP_K  = 8
_INSIGHT_TOP_K = 4
_MAX_QUESTION_CHARS = 2000

_db_url_cache: str | None = None

_sessions: dict[str, list[dict]] = {}
_SESSION_WINDOW = 6


# ── session history ────────────────────────────────────────────────────────────

def _get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])[-_SESSION_WINDOW:]


def _append_history(session_id: str, role: str, content: str) -> None:
    _sessions.setdefault(session_id, []).append({"role": role, "content": content})


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
        # local only
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


# ── period helper ──────────────────────────────────────────────────────────────

def _default_period_start(period: str, today: date) -> date:
    from datetime import timedelta
    if period == "weekly":
        return today - timedelta(days=today.weekday())
    if period == "monthly":
        return today.replace(day=1)
    if period == "quarterly":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_month, day=1)
    if period == "yearly":
        return today.replace(month=1, day=1)
    return today - timedelta(days=today.weekday())


# ── embeddings ─────────────────────────────────────────────────────────────────

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


# ── intent detection ───────────────────────────────────────────────────────────

_INTENT_SCHEMA = '{"market": null|"vietnam"|"japan"|"korea"|"international", "sector": null|string, "period": "weekly"|"monthly"|"quarterly"|"yearly", "period_start": null|"YYYY-MM-DD", "use_latest": false|true, "result_type": null|"pain_points_summary"|"funnel_distribution"|"icp_narrative"|"recommendations", "funnel_stage": null|"awareness"|"consideration"|"negotiation"|"won"|"lost", "needs_citations": false|true, "out_of_scope": false|true}'

_INTENT_PROMPT = """\
Extract search intent from the user question below. Return ONLY valid JSON matching this schema:
{schema}

Rules:
- market: null if not mentioned
- sector: null if not mentioned; industry/domain string if clearly stated (e.g. "fintech", "healthcare")
- period: "weekly" if not mentioned
- period_start: null means "compute from today"; ISO date for specific period ("Q1 2026" → "2026-01-01", "tháng 3 2026" → "2026-03-01", "2026" → "2026-01-01")
- use_latest: true ONLY for "gần đây", "mới nhất", "latest", "most recent"
- result_type: null if not clearly one of the four types
- funnel_stage: null if not mentioned; one of the enum values if the question is about a specific stage
- needs_citations: true if user asks for specific sources, examples, or evidence
- out_of_scope: true if question is completely unrelated to B2B sales, customer signals, or internal platform data

Question: {question}"""


def _intent_defaults() -> dict:
    return {
        "market": None,
        "sector": None,
        "period": "weekly",
        "period_start": None,
        "use_latest": False,
        "result_type": None,
        "funnel_stage": None,
        "needs_citations": False,
        "out_of_scope": False,
    }


def _call_gemini_small(prompt_text: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt_text,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return resp.text


def _call_bedrock_small(prompt_text: str) -> str:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt_text}],
    })
    resp = client.invoke_model(modelId=BEDROCK_INTENT_MODEL, body=body)
    return json.loads(resp["body"].read())["content"][0]["text"]


def detect_intent(question: str) -> dict:
    prompt_text = _INTENT_PROMPT.format(schema=_INTENT_SCHEMA, question=question)
    try:
        if _llm_provider() == "gemini":
            raw = _call_gemini_small(prompt_text)
        else:
            raw = _call_bedrock_small(prompt_text)
        intent = parse_json_response(raw)
        defaults = _intent_defaults()
        defaults.update({k: intent[k] for k in defaults if k in intent})
        return defaults
    except Exception as exc:
        print(f"[intent] parse error: {exc} — using defaults")
        return _intent_defaults()


# ── follow-up rewrite ──────────────────────────────────────────────────────────

def rewrite_question(question: str, history: list[dict]) -> str:
    if not history:
        return question
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
    prompt_text = (
        f"Given this conversation history:\n{history_text}\n\n"
        f"Rewrite the following follow-up question as a fully standalone question "
        f"(no pronouns referencing prior turns). Return ONLY the rewritten question, no explanation.\n\n"
        f"Follow-up: {question}"
    )
    try:
        if _llm_provider() == "gemini":
            return _call_gemini_small(prompt_text).strip()
        return _call_bedrock_small(prompt_text).strip()
    except Exception as exc:
        print(f"[rewrite] error: {exc} — using original")
        return question


# ── db queries ─────────────────────────────────────────────────────────────────

def _count_signals(conn) -> int:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM signals")
        return cur.fetchone()[0]
    finally:
        cur.close()


def query_signal_embeddings(conn, question_vector: list[float], intent: dict) -> list[dict]:
    cur = conn.cursor()
    try:
        where_clauses = []
        where_params = []
        if intent.get("market"):
            where_clauses.append("s.market = %s")
            where_params.append(intent["market"])
        if intent.get("sector"):
            where_clauses.append("s.sector = %s")
            where_params.append(intent["sector"])
        if intent.get("funnel_stage"):
            where_clauses.append("s.funnel_stage = %s")
            where_params.append(intent["funnel_stage"])

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cur.execute(
            f"""
            SELECT
                e.signal_id,
                s.source,
                s.source_url,
                s.funnel_stage,
                e.embedding_text,
                1 - (e.embedding <=> %s::vector) AS score
            FROM signal_embeddings e
            JOIN signals s ON s.id = e.signal_id
            {where}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (str(question_vector), *where_params, str(question_vector), _VECTOR_TOP_K),
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
        print(f"signal_embeddings query skipped: {exc}")
        return []
    finally:
        cur.close()


def query_insight_embeddings(conn, question_vector: list[float], intent: dict) -> list[dict]:
    cur = conn.cursor()
    try:
        where_clauses = []
        where_params = []

        if intent.get("use_latest"):
            where_clauses.append("i.computed_at = (SELECT MAX(computed_at) FROM insights)")
        else:
            period_start_val = intent.get("period_start")
            if period_start_val:
                ps = date.fromisoformat(period_start_val)
            else:
                ps = _default_period_start(intent["period"], date.today())
            where_clauses.append("i.period = %s")
            where_params.append(intent["period"])
            where_clauses.append("i.period_start = %s")
            where_params.append(ps)

        if intent.get("market"):
            where_clauses.append("i.market = %s")
            where_params.append(intent["market"])

        if intent.get("result_type"):
            where_clauses.append("i.result_type = %s")
            where_params.append(intent["result_type"])

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cur.execute(
            f"""
            SELECT
                ie.insight_id,
                i.result_type,
                i.period,
                i.market,
                ie.embedding_text,
                1 - (ie.embedding <=> %s::vector) AS score
            FROM insight_embeddings ie
            JOIN insights i ON i.id = ie.insight_id
            {where}
            ORDER BY ie.embedding <=> %s::vector
            LIMIT %s
            """,
            (str(question_vector), *where_params, str(question_vector), _INSIGHT_TOP_K),
        )
        return [
            {
                "insight_id": str(r[0]),
                "result_type": r[1],
                "period": r[2],
                "market": r[3],
                "embedding_text": r[4],
                "score": round(float(r[5]), 3),
            }
            for r in cur.fetchall()
        ]
    except Exception as exc:
        print(f"insight_embeddings query skipped: {exc}")
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
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"}),
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

    try:
        body = json.loads(event.get("body") or "{}")
        question = (body.get("question") or "").strip()
        session_id = (body.get("session_id") or "").strip() or None
    except (json.JSONDecodeError, AttributeError):
        return error_response(400, "Invalid JSON body")

    if not question:
        return error_response(400, "Field 'question' is required and must not be empty")
    if len(question) > _MAX_QUESTION_CHARS:
        return error_response(413, f"Question is too long. Max {_MAX_QUESTION_CHARS} characters.")

    import time
    print(f"\n{'='*60}")
    print(f"[chat] question: {question!r}")
    print(f"[chat] session_id: {session_id!r}  provider: {_llm_provider()}")

    history = _get_history(session_id) if session_id else []
    standalone = rewrite_question(question, history) if history else question

    conn = _pg_connect()
    try:
        t0 = time.perf_counter()

        with ThreadPoolExecutor(max_workers=2) as ex:
            f_intent = ex.submit(detect_intent, standalone)
            f_embed  = ex.submit(_embed_queries, [standalone])
        intent          = f_intent.result()
        question_vector = f_embed.result()[0]
        t_intent_embed  = time.perf_counter() - t0
        print(f"[intent]   {intent}")
        print(f"[timing]   intent+embed={t_intent_embed*1000:.0f}ms")

        if intent.get("out_of_scope"):
            return {
                "statusCode": 200,
                "headers": cors_headers(),
                "body": json.dumps(
                    {
                        "answer": "Câu hỏi này nằm ngoài phạm vi của hệ thống. Tôi chỉ có thể hỗ trợ các câu hỏi liên quan đến tín hiệu khách hàng, insights bán hàng, và dữ liệu nội bộ của nền tảng.",
                        "references": [],
                    },
                    ensure_ascii=False,
                ),
            }

        t1 = time.perf_counter()
        conn2 = _pg_connect()
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_count   = ex.submit(_count_signals, conn)
                f_insight = ex.submit(query_insight_embeddings, conn2, question_vector, intent)
            total_signals = f_count.result()
            insight_ctx   = f_insight.result()
        finally:
            conn2.close()
        t_phase1 = time.perf_counter() - t1
        print(f"[phase1]   total_signals={total_signals}  insight_chunks={len(insight_ctx)}")
        print(f"[timing]   phase1={t_phase1*1000:.0f}ms")

        if total_signals == 0:
            return {
                "statusCode": 200,
                "headers": cors_headers(),
                "body": json.dumps(
                    {
                        "answer": "Hệ thống chưa có dữ liệu tín hiệu nào. Vui lòng chạy pipeline ingestion trước.",
                        "references": [],
                    },
                    ensure_ascii=False,
                ),
            }

        top_insight_score = insight_ctx[0]["score"] if insight_ctx else 0.0
        insight_low = top_insight_score < 0.5

        signal_ctx: list[dict] = []
        if intent.get("needs_citations") or insight_low:
            t2 = time.perf_counter()
            signal_ctx = query_signal_embeddings(conn, question_vector, intent)
            t_phase2 = time.perf_counter() - t2
            print(f"[phase2]   signal_chunks={len(signal_ctx)}  scores={[c['score'] for c in signal_ctx]}")
            print(f"[timing]   phase2={t_phase2*1000:.0f}ms")

        prompt = build_chat_prompt(standalone, insight_ctx, signal_ctx, history, insight_low)

        t3 = time.perf_counter()
        raw = call_llm(prompt)
        t_llm = time.perf_counter() - t3

        result = parse_json_response(raw)

        answer     = result.get("answer", "")
        references = result.get("references", [])[:5]

        t_total = time.perf_counter() - t0
        print(f"[timing]   llm={t_llm*1000:.0f}ms  total={t_total*1000:.0f}ms")
        print(f"[refs]     {len(references)} reference(s) returned")
        print(f"{'='*60}\n")

        if session_id:
            _append_history(session_id, "user", question)
            _append_history(session_id, "assistant", answer)

        return {
            "statusCode": 200,
            "headers": cors_headers(),
            "body": json.dumps(
                {"answer": answer, "references": references},
                ensure_ascii=False,
            ),
        }

    except Exception as exc:
        print(f"[error] {exc}")
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
