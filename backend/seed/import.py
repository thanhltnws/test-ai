"""
Import backend/seed/data/insights_seed.json into Aurora PostgreSQL + pgvector.

Usage:
    python backend/seed/import.py
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import json
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

_HERE     = Path(__file__).parent
DATA_PATH = _HERE / "data" / "insights_seed.json"

# Chunking is intentionally disabled for now: embedding_text is expected to be
# a short natural-language summary. Keep this here in case summaries become
# long enough to split later.
# _CHUNK_SIZE = 2048   # ~512 tokens


# ── db connection ─────────────────────────────────────────────────────────────

def get_db_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg2.connect(url)


# ── postgres ──────────────────────────────────────────────────────────────────

def insert_insights(records: list[dict]) -> None:
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO insights (
                            id, source, source_id, source_url, raw_text,
                            pain_points, objections, use_cases,
                            icp, funnel_stage, confidence_score, embedding_text,
                            ingested_at, extracted_at
                        )
                        VALUES (%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s, %s,%s)
                        ON CONFLICT (source, source_id) DO UPDATE SET
                            raw_text         = EXCLUDED.raw_text,
                            pain_points      = EXCLUDED.pain_points,
                            objections       = EXCLUDED.objections,
                            use_cases        = EXCLUDED.use_cases,
                            icp              = EXCLUDED.icp,
                            funnel_stage     = EXCLUDED.funnel_stage,
                            confidence_score = EXCLUDED.confidence_score,
                            embedding_text   = EXCLUDED.embedding_text,
                            extracted_at     = EXCLUDED.extracted_at,
                            source_id        = EXCLUDED.source_id
                        RETURNING id
                        """,
                        (
                            rec["id"],
                            rec["source"],
                            rec["source_id"],
                            rec["source_url"],
                            rec.get("raw_text"),
                            rec.get("pain_points") or [],
                            rec.get("objections") or [],
                            rec.get("use_cases") or [],
                            psycopg2.extras.Json(rec.get("icp") or {}),
                            rec.get("funnel_stage"),
                            rec.get("confidence_score"),
                            str(rec.get("embedding_text") or "").strip(),
                            rec.get("ingested_at"),
                            datetime.now(timezone.utc),
                        ),
                    )
                    # sync rec["id"] with the actual DB id (handles conflict case)
                    rec["id"] = str(cur.fetchone()[0])
        print(f"Imported {len(records)} records into insights.")
    finally:
        conn.close()


# ── pgvector ──────────────────────────────────────────────────────────────────

# def _split_chunks(text: str) -> list[str]:
#     text = text or ""
#     return [text[i:i + _CHUNK_SIZE] for i in range(0, max(len(text), 1), _CHUNK_SIZE)]


def _embed_bedrock(texts: list[str]) -> list[list[float]]:
    import boto3
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    embeddings = []
    for text in texts:
        resp = client.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
        )
        embeddings.append(json.loads(resp["body"].read())["embedding"])
    return embeddings


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
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=1024,
            ),
        )
        embeddings.append(result.embeddings[0].values)
    return embeddings


def _embed_cloudflare(texts: list[str]) -> list[list[float]]:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts"
        f"/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/ai/run/@cf/baai/bge-m3"
    )
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
        json={"text": texts},
    )
    if not resp.ok:
        raise RuntimeError(f"Cloudflare embed {resp.status_code}: {resp.text}")
    return resp.json()["result"]["data"]


def _get_embedding_provider() -> str:
    provider = os.environ.get("EMBEDDING_PROVIDER", "").strip().lower()
    if provider not in {"bedrock", "gemini", "cloudflare"}:
        raise RuntimeError(
            "Set EMBEDDING_PROVIDER in .env to one of: bedrock, gemini, cloudflare. "
            "Use EMBEDDING_PROVIDER=gemini for local dev."
        )
    return provider


def _embed_batch(texts: list[str]) -> list[list[float]]:
    provider = _get_embedding_provider()
    if provider == "gemini":
        return _embed_gemini(texts)
    elif provider == "cloudflare":
        return _embed_cloudflare(texts)
    return _embed_bedrock(texts)


def insert_embeddings(records: list[dict]) -> None:
    provider = _get_embedding_provider()
    print(f"Embedding provider: {provider}")

    # Build one vector row per insight from embedding_text only. raw_text is a
    # flattened source record and intentionally not used for semantic search.
    embedding_rows: list[tuple[str, str, dict]] = []
    skipped = 0
    for rec in records:
        embedding_text = str(rec.get("embedding_text") or "").strip()
        if not embedding_text:
            skipped += 1
            continue

        metadata = {
            "source":           rec["source"],
            "funnel_stage":     rec.get("funnel_stage"),
            "source_url":       rec.get("source_url"),
        }
        embedding_rows.append((rec["id"], embedding_text, metadata))

    # batch size: Bedrock/Gemini are per-call so 100 is fine; Cloudflare supports native batch
    embeddings: list[list[float]] = []
    for start in range(0, len(embedding_rows), 100):
        batch = [r[1] for r in embedding_rows[start:start + 100]]
        embeddings.extend(_embed_batch(batch))

    # upsert into insight_embeddings
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                empty_ids = [
                    rec["id"]
                    for rec in records
                    if not str(rec.get("embedding_text") or "").strip()
                ]
                if empty_ids:
                    cur.execute(
                        "DELETE FROM insight_embeddings WHERE insight_id = ANY(%s::uuid[])",
                        (empty_ids,),
                    )

                for (insight_id, embedding_text, metadata), values in zip(embedding_rows, embeddings):
                    cur.execute(
                        """
                        INSERT INTO insight_embeddings (insight_id, embedding_text, embedding, metadata)
                        VALUES (%s, %s, %s::vector, %s)
                        ON CONFLICT (insight_id) DO UPDATE SET
                            embedding_text = EXCLUDED.embedding_text,
                            embedding      = EXCLUDED.embedding,
                            metadata       = EXCLUDED.metadata
                        """,
                        (insight_id, embedding_text, str(values), psycopg2.extras.Json(metadata)),
                    )
        print(f"Upserted {len(embedding_rows)} embeddings into insight_embeddings; skipped {skipped} records.")
    finally:
        conn.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)

    # Assign stable UUIDs once — same id used by both postgres and pgvector
    for rec in records:
        if "id" not in rec:
            rec["id"] = str(uuid.uuid4())

    print(f"Loaded {len(records)} records from {DATA_PATH}")
    insert_insights(records)
    insert_embeddings(records)


if __name__ == "__main__":
    main()
