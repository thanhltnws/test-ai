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
from common.auth import cors_headers, error_response, is_options_request, options_response
from prompt import build_chat_prompt, build_intent_prompt, intent_defaults

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
BEDROCK_INTENT_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
_VECTOR_TOP_K  = 8
_INSIGHT_TOP_K = 4
_MAX_QUESTION_CHARS = 2000

_db_url_cache: str | None = None

_sessions: dict[str, list[dict]] = {}
_SESSION_WINDOW = 12


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


def _default_period_end(period: str, period_start: date) -> date:
    from datetime import timedelta
    if period == "weekly":
        return period_start + timedelta(days=6)
    if period == "monthly":
        if period_start.month == 12:
            return period_start.replace(day=31)
        return period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
    if period == "quarterly":
        end_month = period_start.month + 2
        if end_month >= 12:
            return date(period_start.year, 12, 31)
        return date(period_start.year, end_month + 1, 1) - timedelta(days=1)
    if period == "yearly":
        return period_start.replace(month=12, day=31)
    return period_start + timedelta(days=6)


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
    prompt_text = build_intent_prompt(question, date.today().isoformat())
    try:
        if _llm_provider() == "gemini":
            raw = _call_gemini_small(prompt_text)
        else:
            raw = _call_bedrock_small(prompt_text)
        intent = parse_json_response(raw)
        defaults = intent_defaults()
        defaults.update({k: intent[k] for k in defaults if k in intent})
        return defaults
    except Exception as exc:
        print(f"[intent] parse error: {exc} — using defaults")
        return intent_defaults()


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

def query_signal_embeddings(conn, question_vector: list[float], intent: dict, top_k: int = _VECTOR_TOP_K) -> list[dict]:
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
        if intent.get("use_latest"):
            ps = date.today().replace(day=1)
            pe = date.today()
        else:
            period_start_val = intent.get("period_start")
            ps = date.fromisoformat(period_start_val) if period_start_val else _default_period_start(intent["period"], date.today())
            pe = _default_period_end(intent["period"], ps)
        where_clauses.append("COALESCE(s.record_date, s.extracted_at::date) >= %s AND COALESCE(s.record_date, s.extracted_at::date) <= %s")
        where_params.extend([ps, pe])

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        cur.execute(
            f"""
            SELECT
                e.signal_id,
                s.source,
                s.source_url,
                s.funnel_stage,
                e.embedding_text,
                1 - (e.embedding <=> %s::vector) AS score,
                s.pain_points,
                s.objections,
                s.use_cases,
                s.deal_size,
                s.client_type,
                s.tech_maturity,
                s.market,
                s.sector
            FROM signal_embeddings e
            JOIN signals s ON s.id = e.signal_id
            {where}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (str(question_vector), *where_params, str(question_vector), top_k),
        )
        return [
            {
                "signal_id": str(r[0]),
                "source": r[1],
                "source_url": r[2],
                "funnel_stage": r[3],
                "embedding_text": r[4],
                "score": round(float(r[5]), 3),
                "pain_points": r[6] or [],
                "objections": r[7] or [],
                "use_cases": r[8] or [],
                "deal_size": r[9],
                "client_type": r[10],
                "tech_maturity": r[11],
                "market": r[12],
                "sector": r[13],
            }
            for r in cur.fetchall()
        ]
    except Exception as exc:
        print(f"signal_embeddings query skipped: {exc}")
        return []
    finally:
        cur.close()


def query_insights_structured(conn, intent: dict) -> list[dict]:
    """Structured retrieval: query insights directly by period/market/result_type.
    Period filter always applied — intent LLM defaults period to 'monthly' when not mentioned.
    Returns score=1.0 (exact match)."""
    cur = conn.cursor()
    try:
        where_clauses = []
        where_params = []

        if intent.get("use_latest"):
            ps = date.today().replace(day=1)
            pe = date.today()
            where_clauses.append("i.period_start <= %s AND i.period_end >= %s")
            where_params.extend([pe, ps])
        else:
            period_start_val = intent.get("period_start")
            anchor = date.fromisoformat(period_start_val) if period_start_val else _default_period_start(intent["period"], date.today())
            where_clauses.append("i.period = %s")
            where_params.append(intent["period"])
            where_clauses.append("i.period_start <= %s AND i.period_end >= %s")
            where_params.extend([anchor, anchor])

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
                i.id,
                i.result_type,
                i.period,
                i.market,
                ie.embedding_text
            FROM insights i
            LEFT JOIN insight_embeddings ie ON ie.insight_id = i.id
            {where}
            ORDER BY i.computed_at DESC
            LIMIT %s
            """,
            (*where_params, _INSIGHT_TOP_K),
        )
        return [
            {
                "insight_id": str(r[0]),
                "result_type": r[1],
                "period": r[2],
                "market": r[3],
                "embedding_text": r[4],
                "score": 1.0,
            }
            for r in cur.fetchall()
        ]
    except Exception as exc:
        print(f"insights structured query skipped: {exc}")
        return []
    finally:
        cur.close()


def query_insight_embeddings(conn, question_vector: list[float], intent: dict) -> list[dict]:
    cur = conn.cursor()
    try:
        where_clauses = []
        where_params = []

        if intent.get("use_latest"):
            ps = date.today().replace(day=1)
            pe = date.today()
            where_clauses.append("i.period_start <= %s AND i.period_end >= %s")
            where_params.extend([pe, ps])
        else:
            period_start_val = intent.get("period_start")
            if period_start_val:
                anchor = date.fromisoformat(period_start_val)
            else:
                anchor = _default_period_start(intent["period"], date.today())
            where_clauses.append("i.period = %s")
            where_params.append(intent["period"])
            # range overlap: find the insight window that contains the anchor date
            # avoids off-by-1 errors when intent model returns a date within the correct week
            where_clauses.append("i.period_start <= %s AND i.period_end >= %s")
            where_params.extend([anchor, anchor])

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
        modelId=os.environ.get("BEDROCK_CHAT_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
        body=body,
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def call_llm(prompt_text: str) -> str:
    if _llm_provider() == "gemini":
        return _call_gemini(prompt_text)
    return _call_bedrock(prompt_text)


# ── response parsing ───────────────────────────────────────────────────────────

def parse_json_response(text: str) -> dict:
    from json_repair import repair_json
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(repair_json(text.strip()))


# ── lambda handler ─────────────────────────────────────────────────────────────

def lambda_handler(event=None, context=None):
    load_dotenv()
    event = event or {}

    if is_options_request(event):
        return options_response()



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
    provider = _llm_provider()
    intent_model = BEDROCK_INTENT_MODEL if provider == "bedrock" else f"gemini/{GEMINI_MODEL}"
    answer_model = os.environ.get("BEDROCK_CHAT_MODEL_ID", "global.anthropic.claude-sonnet-4-6") if provider == "bedrock" else f"gemini/{GEMINI_MODEL}"

    print(f"\n{'='*60}")
    print(f"[chat]         question: {question!r}")
    print(f"[chat]         session_id: {session_id!r}  provider: {provider}")

    history = _get_history(session_id) if session_id else []
    if history:
        standalone = rewrite_question(question, history)
        if standalone != question:
            print(f"[rewrite]      {question!r} → {standalone!r}")
    else:
        standalone = question

    conn = _pg_connect()
    try:
        t0 = time.perf_counter()

        # parallel: intent detection (LLM call) + embedding
        print(f"[llm/intent]   calling {intent_model} + embed in parallel …")
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_intent = ex.submit(detect_intent, standalone)
            f_embed  = ex.submit(_embed_queries, [standalone])
        intent          = f_intent.result()
        question_vector = f_embed.result()[0]
        t_intent_embed  = time.perf_counter() - t0
        print(f"[intent]       {intent}")
        print(f"[timing]       intent+embed={t_intent_embed*1000:.0f}ms")

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

        # 3-flow routing — primary discriminator: question type, not period
        t1 = time.perf_counter()
        result_type_known = bool(intent.get("result_type"))
        question_type     = intent.get("question_type")  # "summary" | None

        if result_type_known:
            # Flow A: question maps to a known dashboard output → SQL on insights
            flow = "A"
            insight_ctx = query_insights_structured(conn, intent)
            if not insight_ctx:
                print("[routing]      flow=A structured 0 rows — fallback semantic insight")
                insight_ctx = query_insight_embeddings(conn, question_vector, intent)
                flow = "A-fallback"
            signal_ctx = query_signal_embeddings(conn, question_vector, intent, top_k=3)

        elif question_type == "summary":
            # Flow B: summary / trend → insight_embeddings primary
            flow = "B"
            insight_ctx = query_insight_embeddings(conn, question_vector, intent)
            signal_top_k = _VECTOR_TOP_K if intent.get("needs_citations") else 3
            signal_ctx  = query_signal_embeddings(conn, question_vector, intent, top_k=signal_top_k)

        else:
            # Flow C: open / ambiguous / other — default fallback → signal_embeddings
            flow = "C"
            insight_ctx = []
            signal_ctx  = query_signal_embeddings(conn, question_vector, intent, top_k=_VECTOR_TOP_K)

        t_retrieval = time.perf_counter() - t1
        print(f"[routing]      flow={flow}  insight_chunks={len(insight_ctx)}  signal_chunks={len(signal_ctx)}")
        print(f"[timing]       retrieval={t_retrieval*1000:.0f}ms")

        prompt = build_chat_prompt(standalone, insight_ctx, signal_ctx, history, flow=flow)

        # LLM answer generation
        print(f"[llm/answer]   calling {answer_model} …")
        t3 = time.perf_counter()
        raw = call_llm(prompt)
        t_llm = time.perf_counter() - t3

        try:
            result = parse_json_response(raw)
        except (json.JSONDecodeError, ValueError):
            result = {"answer": raw, "references": []}

        answer     = result.get("answer", "")
        references = result.get("references", [])[:5]

        t_total = time.perf_counter() - t0
        print(f"[timing]       llm={t_llm*1000:.0f}ms  total={t_total*1000:.0f}ms")
        print(f"[refs]         {len(references)} reference(s) returned")
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
