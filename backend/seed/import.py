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

_CHUNK_SIZE = 2048   # ~512 tokens


# ── db connection ─────────────────────────────────────────────────────────────

def get_db_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg2.connect(url)


# ── postgres ──────────────────────────────────────────────────────────────────

def import_to_postgres(records: list[dict]) -> None:
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
                            icp, funnel_stage, confidence_score,
                            ingested_at, extracted_at
                        )
                        VALUES (%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s)
                        ON CONFLICT (source, source_id) DO UPDATE SET
                            raw_text         = EXCLUDED.raw_text,
                            pain_points      = EXCLUDED.pain_points,
                            objections       = EXCLUDED.objections,
                            use_cases        = EXCLUDED.use_cases,
                            icp              = EXCLUDED.icp,
                            funnel_stage     = EXCLUDED.funnel_stage,
                            confidence_score = EXCLUDED.confidence_score,
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

def _split_chunks(text: str) -> list[str]:
    text = text or ""
    return [text[i:i + _CHUNK_SIZE] for i in range(0, max(len(text), 1), _CHUNK_SIZE)]


def _embed_batch(texts: list[str], account_id: str, api_token: str) -> list[list[float]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/baai/bge-m3"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_token}"},
        json={"text": texts},
    )
    if not resp.ok:
        raise RuntimeError(f"Cloudflare embed {resp.status_code}: {resp.text}")
    return resp.json()["result"]["data"]


def import_to_pgvector(records: list[dict]) -> None:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token  = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not all([account_id, api_token]):
        print("pgvector skipped — CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set")
        return

    # build flat list of (insight_id, chunk_index, chunk_text, metadata)
    chunks: list[tuple[str, int, str, dict]] = []
    for rec in records:
        metadata = {
            "source":           rec["source"],
            "funnel_stage":     rec.get("funnel_stage"),
        }
        for i, text in enumerate(_split_chunks(rec.get("raw_text") or "")):
            chunks.append((rec["id"], i, text, metadata))

    # embed in batches of 100
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), 100):
        batch = [c[2] for c in chunks[start:start + 100]]
        embeddings.extend(_embed_batch(batch, account_id, api_token))

    # upsert into insight_chunks
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for (insight_id, chunk_index, chunk_text, metadata), values in zip(chunks, embeddings):
                    cur.execute(
                        """
                        INSERT INTO insight_chunks (insight_id, chunk_index, chunk_text, embedding, metadata)
                        VALUES (%s, %s, %s, %s::vector, %s)
                        ON CONFLICT (insight_id, chunk_index) DO UPDATE SET
                            chunk_text = EXCLUDED.chunk_text,
                            embedding  = EXCLUDED.embedding,
                            metadata   = EXCLUDED.metadata
                        """,
                        (insight_id, chunk_index, chunk_text, str(values), psycopg2.extras.Json(metadata)),
                    )
        print(f"Upserted {len(chunks)} chunks into insight_chunks.")
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
    import_to_postgres(records)
    import_to_pgvector(records)


if __name__ == "__main__":
    main()
