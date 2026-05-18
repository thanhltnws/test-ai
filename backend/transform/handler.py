"""
Lambda: S3 ObjectCreated (raw/) → normalize → Bedrock extract → Aurora signals

Triggered by S3 event on raw/{source}/{date}/{timestamp}.json

Idempotency: S3 object tag "processed=true" is set after a successful run.
On retry or duplicate event, Lambda checks the tag first and returns early —
Bedrock is never called again for the same file.
Aurora INSERT uses ON CONFLICT (source, source_id) DO UPDATE — re-extracted records overwrite existing rows.

Environment variables:
    DB_SECRET_ARN      Secrets Manager ARN for Aurora credentials (required)
    BEDROCK_MODEL_ID   (default: apac.anthropic.claude-haiku-4-5-20251001-v1:0)
    AWS_REGION         (default: ap-southeast-1)
"""
import hashlib
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import instructor
import pg8000.dbapi
from urllib.parse import urlparse
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt import build_extract_prompt, build_retry_prompt

load_dotenv()

DEFAULT_MODEL_ID  = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_BATCH_CHARS   = 150_000
MAX_BATCH_RECORDS = 40
API_DELAY_S       = 1.0
MIN_ROW_TEXT_LEN  = 10
RETRY_CONFIDENCE_THRESHOLD = 0.4   # retry extractions below this score
RETRY_MIN_TEXT_LEN         = 150   # skip retry if raw text is genuinely sparse

_S3  = boto3.client("s3")
_SM  = boto3.client("secretsmanager")
_BEDROCK = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))

_DB_CONN = None


# ── Pydantic output schema ────────────────────────────────────────────────────

_VALID_STAGES        = {"awareness", "consideration", "negotiation", "won", "lost"}
_VALID_SECTORS       = {"fintech", "logistics", "retail", "healthcare", "manufacturing",
                        "software", "education", "ict", "other"}
_VALID_COMPANY_SIZES = {"1-10", "11-50", "50-200", "200-1000", "1000+"}
_VALID_DEAL_SIZES    = {"small", "medium", "large"}
_VALID_MARKETS       = {"international", "korea", "japan"}


class _ICP(BaseModel):
    sector:       str = "other"
    company_size: str = "50-200"
    deal_size:    str = "medium"
    region:       str = "Southeast Asia"

    @field_validator("sector")
    @classmethod
    def _v_sector(cls, v: str) -> str:
        return v if v in _VALID_SECTORS else "other"

    @field_validator("company_size")
    @classmethod
    def _v_company_size(cls, v: str) -> str:
        return v if v in _VALID_COMPANY_SIZES else "50-200"

    @field_validator("deal_size")
    @classmethod
    def _v_deal_size(cls, v: str) -> str:
        return v if v in _VALID_DEAL_SIZES else "medium"


class _Extraction(BaseModel):
    pain_points:      list[str] = Field(default_factory=list)
    objections:       list[str] = Field(default_factory=list)
    use_cases:        list[str] = Field(default_factory=list)
    icp:              _ICP      = Field(default_factory=_ICP)
    funnel_stage:     str       = "consideration"
    confidence_score: float     = 0.5
    source_id:        str       = ""
    embedding_text:   str       = ""
    record_date:      str | None = None
    market:           str       = "international"

    @field_validator("funnel_stage")
    @classmethod
    def _v_funnel_stage(cls, v: str) -> str:
        return v if v in _VALID_STAGES else "consideration"

    @field_validator("confidence_score")
    @classmethod
    def _v_confidence_score(cls, v: float) -> float:
        return round(max(0.0, min(1.0, float(v))), 2)

    @field_validator("market")
    @classmethod
    def _v_market(cls, v: str) -> str:
        return v if v in _VALID_MARKETS else "international"


class _ExtractionBatch(BaseModel):
    records: list[_Extraction] = []


# ── S3 tag helpers ───────────────────────────────────────────────────────────

def _is_processed(bucket: str, s3_key: str) -> bool:
    resp = _S3.get_object_tagging(Bucket=bucket, Key=s3_key)
    return any(t["Key"] == "processed" and t["Value"] == "true" for t in resp.get("TagSet", []))


def _mark_processed(bucket: str, s3_key: str) -> None:
    _S3.put_object_tagging(
        Bucket=bucket,
        Key=s3_key,
        Tagging={"TagSet": [{"Key": "processed", "Value": "true"}]},
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    global _DB_CONN
    if _DB_CONN is None:
        secret_arn = os.environ.get("DB_SECRET_ARN")
        if secret_arn:
            secret_str = _SM.get_secret_value(SecretId=secret_arn)["SecretString"]
            creds = json.loads(secret_str)
            _DB_CONN = pg8000.dbapi.connect(
                host=creds["host"],
                port=creds.get("port", 5432),
                database=creds.get("dbname", "ai_insight_hub"),
                user=creds["username"],
                password=creds["password"],
            )
        else:
            db_url = os.environ.get("DATABASE_URL")
            if not db_url:
                raise RuntimeError("Set DB_SECRET_ARN (AWS) or DATABASE_URL (local dev)")
            u = urlparse(db_url)
            _DB_CONN = pg8000.dbapi.connect(
                host=u.hostname,
                port=u.port or 5432,
                database=u.path.lstrip("/"),
                user=u.username,
                password=u.password,
            )
        _DB_CONN.autocommit = False
    return _DB_CONN


def _insert_signals(rows: list[dict]) -> tuple[int, dict[str, str]]:
    """Upsert into Aurora signals. Returns (upserted_count, {pre_assigned_id: actual_db_id}).
    RETURNING id captures the real UUID on both insert and conflict-update paths so the
    embedding step can use the correct FK regardless of which path was taken.
    """
    conn = _get_conn()
    upserted = 0
    id_map: dict[str, str] = {}  # pre-assigned row["id"] → actual DB id
    cur = conn.cursor()
    try:
        for row in rows:
            cur.execute(
                """
                INSERT INTO signals (
                    id, source, source_id, source_url, raw_text,
                    pain_points, objections, use_cases, icp,
                    funnel_stage, confidence_score, embedding_text,
                    record_date, market, sector, ingested_at, extracted_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, source_id) DO UPDATE SET
                    source_url       = EXCLUDED.source_url,
                    raw_text         = EXCLUDED.raw_text,
                    pain_points      = EXCLUDED.pain_points,
                    objections       = EXCLUDED.objections,
                    use_cases        = EXCLUDED.use_cases,
                    icp              = EXCLUDED.icp,
                    funnel_stage     = EXCLUDED.funnel_stage,
                    confidence_score = EXCLUDED.confidence_score,
                    embedding_text   = EXCLUDED.embedding_text,
                    record_date      = EXCLUDED.record_date,
                    market           = EXCLUDED.market,
                    sector           = EXCLUDED.sector,
                    extracted_at     = EXCLUDED.extracted_at
                RETURNING id
                """,
                (
                    row["id"],
                    row["source"],
                    row["source_id"],
                    row["source_url"],
                    row["raw_text"],
                    row.get("pain_points") or [],
                    row.get("objections") or [],
                    row.get("use_cases") or [],
                    json.dumps(row.get("icp") or {}),
                    row.get("funnel_stage"),
                    row.get("confidence_score"),
                    str(row.get("embedding_text") or "").strip() or None,
                    row.get("record_date") or None,
                    row.get("market") or "international",
                    row.get("sector") or "other",
                    row.get("ingested_at"),
                    datetime.now(timezone.utc),
                ),
            )
            result = cur.fetchone()
            if result:
                upserted += 1
                id_map[row["id"]] = str(result[0])
        conn.commit()
    finally:
        cur.close()
    return upserted, id_map


# ── embed helpers ────────────────────────────────────────────────────────────

_GEMINI_CLIENT = None
_GEMINI_EXTRACT_CLIENT = None


def _embed_bedrock(text: str) -> list[float]:
    model_id = os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "cohere.embed-multilingual-v3")
    resp = _BEDROCK.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"texts": [text], "input_type": "search_document"}),
    )
    return json.loads(resp["body"].read())["embeddings"][0]


def _embed_gemini(text: str) -> list[float]:
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        from google import genai
        _GEMINI_CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    result = _GEMINI_CLIENT.models.embed_content(
        model="models/gemini-embedding-001",
        contents=text,
        config={"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": 1024},
    )
    return result.embeddings[0].values


def _embed_text(text: str) -> list[float]:
    if os.environ.get("DB_SECRET_ARN"):
        return _embed_bedrock(text)
    return _embed_gemini(text)


def _gemini_extract_client():
    global _GEMINI_EXTRACT_CLIENT
    if _GEMINI_EXTRACT_CLIENT is None:
        from google import genai
        _GEMINI_EXTRACT_CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _GEMINI_EXTRACT_CLIENT


def _embed_rows(rows: list[dict]) -> dict[str, list[float]]:
    """Embed all rows with embedding_text. Returns {row_id: vector}. No DB access."""
    result: dict[str, list[float]] = {}
    for row in rows:
        if not row.get("embedding_text"):
            continue
        try:
            result[row["id"]] = _embed_text(row["embedding_text"])
        except Exception as exc:
            print(f"  EMBED FAIL {row['source_id']}: {exc}")
    return result


def _insert_embeddings(
    rows: list[dict],
    id_map: dict[str, str],
    vectors: dict[str, list[float]],
) -> int:
    """Upsert signal_embeddings for rows that landed in Aurora.

    id_map maps the pre-assigned row["id"] → actual DB id returned by RETURNING, so
    this correctly handles both the fresh-insert and conflict-update Aurora paths.
    Rows with empty embedding_text have their embedding deleted (keeps vectors in sync).
    """
    id_to_row = {row["id"]: row for row in rows}

    embedding_rows: list[tuple[str, str, dict, list[float]]] = []
    empty_db_ids: list[str] = []

    for pre_id, db_id in id_map.items():
        row = id_to_row.get(pre_id)
        if not row:
            continue
        embedding_text = str(row.get("embedding_text") or "").strip()
        if not embedding_text or pre_id not in vectors:
            empty_db_ids.append(db_id)
            continue
        metadata = {
            "source":       row["source"],
            "funnel_stage": row.get("funnel_stage"),
            "source_url":   row.get("source_url"),
            "market":       row.get("market"),
            "sector":       row.get("sector"),
        }
        embedding_rows.append((db_id, embedding_text, metadata, vectors[pre_id]))

    if not embedding_rows and not empty_db_ids:
        return 0

    conn = _get_conn()
    inserted = 0
    cur = conn.cursor()
    try:
        if empty_db_ids:
            cur.execute(
                "DELETE FROM signal_embeddings WHERE signal_id = ANY(%s::uuid[])",
                (empty_db_ids,),
            )
        for db_id, embedding_text, metadata, vector in embedding_rows:
            cur.execute(
                """
                INSERT INTO signal_embeddings (signal_id, embedding_text, embedding, metadata)
                VALUES (%s, %s, %s::vector, %s::jsonb)
                ON CONFLICT (signal_id) DO UPDATE SET
                    embedding_text = EXCLUDED.embedding_text,
                    embedding      = EXCLUDED.embedding,
                    metadata       = EXCLUDED.metadata
                """,
                (db_id, embedding_text, str(vector), json.dumps(metadata)),
            )
            if cur.rowcount:
                inserted += 1
        conn.commit()
    finally:
        cur.close()
    return inserted


# ── Normalize (ETL) ───────────────────────────────────────────────────────────

def _source_from_key(s3_key: str) -> str:
    parts = s3_key.split("/")
    return parts[1] if len(parts) > 1 else "unknown"


def _row_to_text(rec: dict) -> str:
    """Dump all record fields as readable text. No source-specific logic — Bedrock handles variance."""
    lines = []
    for key, val in rec.items():
        if isinstance(val, str) and val.strip():
            lines.append(f"{key}: {val}")
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.strip():
                    lines.append(f"{key}: {item}")
                elif isinstance(item, dict):
                    text = " ".join(str(v) for v in item.values() if isinstance(v, str) and v.strip())
                    if text:
                        lines.append(f"{key}: {text}")
        elif isinstance(val, dict):
            text = " ".join(str(v) for v in val.values() if isinstance(v, str) and v.strip())
            if text:
                lines.append(f"{key}: {text}")
    return "\n".join(lines).strip()


_DATE_FALLBACK_FIELDS = (
    "closedate", "close_date", "createdAt", "created_at", "createdate",
    "created_on", "updated_on", "date", "timestamp", "receivedDateTime",
    "sentDateTime", "meetingDate", "due_date", "modified",
)


def _fallback_date_from_raw(rec: dict) -> str | None:
    for field in _DATE_FALLBACK_FIELDS:
        val = rec.get(field)
        if not val:
            continue
        try:
            return date.fromisoformat(str(val).strip()[:10]).isoformat()
        except (ValueError, TypeError):
            pass
    return None


def _has_signal(row: dict) -> bool:
    return bool(
        row.get("embedding_text")
        or row.get("pain_points")
        or row.get("use_cases")
        or row.get("objections")
    )


def normalize(raw_records: list[dict], s3_key: str, ingested_at: datetime, bucket: str = "") -> list[dict]:
    source = _source_from_key(s3_key)
    base_url = f"s3://{bucket}/{s3_key}" if bucket else s3_key
    seen, out = set(), []
    global_idx = 0
    for rec in raw_records:
        text = _row_to_text(rec)
        if len(text) < MIN_ROW_TEXT_LEN:
            continue
        h = hashlib.sha1(text.encode()).hexdigest()[:12]
        if h in seen:
            continue
        seen.add(h)

        source_url = rec.get("url") or rec.get("source_url") or f"{base_url}#{global_idx}"

        out.append({
            "source":         source,
            "source_id":      str(rec.get("id") or rec.get("key") or rec.get("deal_id") or h),
            "source_url":     source_url,
            "raw_text":       text,
            "ingested_at":    ingested_at,  # when the file arrived in S3, from S3 event eventTime
            "_date_fallback": _fallback_date_from_raw(rec),
        })
        global_idx += 1
    return out


# ── Bedrock extraction ────────────────────────────────────────────────────────

def _bedrock_client() -> Any:
    return instructor.from_bedrock(_BEDROCK, mode=instructor.Mode.BEDROCK_TOOLS)


def _make_batches(records: list[dict]) -> list[list[dict]]:
    batches, current, cur_chars = [], [], 0
    for rec in records:
        n = len(rec["raw_text"])
        if current and (cur_chars + n > MAX_BATCH_CHARS or len(current) >= MAX_BATCH_RECORDS):
            batches.append(current)
            current, cur_chars = [], 0
        current.append(rec)
        cur_chars += n
    if current:
        batches.append(current)
    return batches


def _extract_batch(
    records: list[dict], prompt: str, client: Any, model_id: str, use_gemini: bool = False
) -> list[_Extraction]:
    if use_gemini:
        from google.genai import types as genai_types
        schema = json.dumps(_ExtractionBatch.model_json_schema())
        response = client.models.generate_content(
            model=os.environ.get("LOCAL_GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
            contents=f"{prompt}\n\nRespond ONLY with valid JSON matching this schema:\n{schema}",
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ExtractionBatch,
            ),
        )
        result = _ExtractionBatch.model_validate_json(response.text)
    else:
        result = client.messages.create(
            model=model_id,
            max_tokens=4096,
            response_model=_ExtractionBatch,
            max_retries=2,
            messages=[{"role": "user", "content": prompt}],
        )
    extractions = result.records
    while len(extractions) < len(records):
        extractions.append(_Extraction())
    return extractions


def _do_retry(
    batch: list[dict],
    extractions: list[_Extraction],
    source: str,
    client: Any,
    model_id: str,
    use_gemini: bool,
) -> list[_Extraction]:
    retry_idx = [
        i for i, (rec, ext) in enumerate(zip(batch, extractions))
        if ext.confidence_score < RETRY_CONFIDENCE_THRESHOLD
        and len(rec["raw_text"]) >= RETRY_MIN_TEXT_LEN
    ]
    if not retry_idx:
        return extractions

    retry_records = [batch[i] for i in retry_idx]
    retry_texts   = [r["raw_text"] for r in retry_records]
    retry_prompt  = build_retry_prompt(retry_texts, source)
    retry_exts    = _extract_batch(retry_records, retry_prompt, client, model_id, use_gemini)

    improved = 0
    for i, new_ext in zip(retry_idx, retry_exts):
        if new_ext.confidence_score > extractions[i].confidence_score:
            extractions[i] = new_ext
            improved += 1
    print(f"  retry: {improved}/{len(retry_idx)} low-confidence extractions improved")
    return extractions


def extract_and_merge(normalized: list[dict], source: str, model_id: str) -> list[dict]:
    use_gemini = not bool(os.environ.get("DB_SECRET_ARN"))
    client  = _gemini_extract_client() if use_gemini else _bedrock_client()
    batches = _make_batches(normalized)
    results = []

    for i, batch in enumerate(batches, 1):
        try:
            texts = [r["raw_text"] for r in batch]
            prompt = build_extract_prompt(texts, source, context_content="")
            extractions = _extract_batch(batch, prompt, client, model_id, use_gemini=use_gemini)
            extractions = _do_retry(batch, extractions, source, client, model_id, use_gemini)
            for rec, ext in zip(batch, extractions):
                results.append({
                    "id":               str(uuid.uuid4()),
                    "source":           rec["source"],
                    "source_id":        ext.source_id or rec["source_id"],
                    "source_url":       rec["source_url"],
                    "raw_text":         rec["raw_text"],
                    "pain_points":      ext.pain_points,
                    "objections":       ext.objections,
                    "use_cases":        ext.use_cases,
                    "icp":              ext.icp.model_dump(),
                    "funnel_stage":     ext.funnel_stage,
                    "confidence_score": ext.confidence_score,
                    "embedding_text":   ext.embedding_text,
                    "record_date":      ext.record_date or rec.get("_date_fallback") or None,
                    "market":           ext.market,
                    "sector":           ext.icp.sector,  # denormalized from icp for direct querying
                    "ingested_at":      rec["ingested_at"],  # from S3 eventTime, per-record
                })
            print(f"  batch {i}/{len(batches)} OK ({len(batch)} records)")
        except Exception as exc:
            print(f"  batch {i}/{len(batches)} FAILED: {exc}")
        if i < len(batches):
            time.sleep(API_DELAY_S)

    before = len(results)
    results = [r for r in results if _has_signal(r)]
    dropped = before - len(results)
    if dropped:
        print(f"  noise filter: dropped {dropped}/{before} records with no signal")
    return results


# ── Lambda entry point ────────────────────────────────────────────────────────

def handler(event: dict, context=None) -> dict:
    model_id      = os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
    total_inserted = 0

    for record in event.get("Records", []):
        bucket     = record["s3"]["bucket"]["name"]
        s3_key     = record["s3"]["object"]["key"]
        # eventTime is when the object landed in S3 — this is ingested_at per schema definition
        ingested_at = datetime.fromisoformat(record["eventTime"].replace("Z", "+00:00"))

        if not s3_key.startswith("raw/"):
            print(f"SKIP non-raw key: {s3_key}")
            continue

        if _is_processed(bucket, s3_key):
            print(f"SKIP already processed: {s3_key}")
            continue

        try:
            body = _S3.get_object(Bucket=bucket, Key=s3_key)["Body"].read()
            raw_records = json.loads(body)
            if isinstance(raw_records, dict):
                raw_records = [raw_records]

            source     = _source_from_key(s3_key)
            normalized = normalize(raw_records, s3_key, ingested_at, bucket=bucket)

            if not normalized:
                print(f"SKIP no usable records in {s3_key}")
                continue

            rows = extract_and_merge(normalized, source, model_id)

            # Aurora INSERT and embedding API calls run concurrently.
            # _embed_rows does no DB access, so sharing the global conn is safe.
            with ThreadPoolExecutor(max_workers=2) as ex:
                aurora_fut = ex.submit(_insert_signals, rows)
                embed_fut  = ex.submit(_embed_rows, rows)

            upserted, id_map = aurora_fut.result()
            vectors          = embed_fut.result()

            vec_upserted = _insert_embeddings(rows, id_map, vectors)
            if upserted > 0:
                _mark_processed(bucket, s3_key)
            print(
                f"OK {s3_key}: {upserted}/{len(rows)} signals upserted, "
                f"{vec_upserted} vectors upserted"
            )
            total_inserted += upserted

        except Exception as exc:
            print(f"ERROR {s3_key}: {exc}")
            raise

    return {"status": "ok", "inserted": total_inserted}
