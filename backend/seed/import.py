"""
Import backend/seed/data/insights_seed.json into Aurora PostgreSQL.
Vectorize import is stubbed — to be implemented.

Usage:
    python backend/seed/import.py
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

_HERE     = Path(__file__).parent
DATA_PATH = _HERE / "data" / "insights_seed.json"


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
                            extracted_at     = EXCLUDED.extracted_at
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
        print(f"Imported {len(records)} records into insights.")
    finally:
        conn.close()


# ── vectorize (stub) ──────────────────────────────────────────────────────────

def import_to_vectorize(records: list[dict]) -> None:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token  = os.environ.get("CLOUDFLARE_API_TOKEN")
    index_name = os.environ.get("VECTORIZE_INDEX_NAME")
    if not all([account_id, api_token, index_name]):
        print("Vectorize skipped — CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN / VECTORIZE_INDEX_NAME not set")
        return

    headers    = {"Authorization": f"Bearer {api_token}"}
    embed_url  = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/baai/bge-m3"
    upsert_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/vectorize/v2/indexes/{index_name}/upsert"

    # ~512-token chunks (≈ 2048 chars)
    def chunks(text: str) -> list[str]:
        text = text or ""
        return [text[i:i + 2048] for i in range(0, max(len(text), 1), 2048)]

    texts, metas = [], []
    for rec in records:
        for i, chunk in enumerate(chunks(rec.get("raw_text") or "")):
            texts.append(chunk)
            metas.append({
                "vector_id":    rec["id"] if i == 0 else f"{rec['id']}_{i}",
                "unified_id":   rec["id"],
                "source":       rec["source"],
                "source_url":   rec["source_url"],
                "funnel_stage": rec.get("funnel_stage"),
                "ingested_at":  rec.get("ingested_at"),
            })

    # embed in batches of 100
    vectors = []
    for start in range(0, len(texts), 100):
        resp = requests.post(
            embed_url,
            headers=headers,
            json={"text": texts[start:start + 100]},
        )
        if not resp.ok:
            raise RuntimeError(f"Embed API {resp.status_code}: {resp.text}")
        for meta, values in zip(metas[start:start + 100], resp.json()["result"]["data"]):
            vectors.append({"id": meta.pop("vector_id"), "values": values, "metadata": meta})

    # upsert in batches of 1000
    upsert_headers = {**headers, "Content-Type": "application/x-ndjson"}
    total = 0
    for start in range(0, len(vectors), 1000):
        batch  = vectors[start:start + 1000]
        ndjson = "\n".join(json.dumps(v) for v in batch)
        resp = requests.post(upsert_url, headers=upsert_headers, data=ndjson.encode())
        if not resp.ok:
            raise RuntimeError(f"Vectorize upsert {resp.status_code}: {resp.text}")
        total += len(batch)

    print(f"Upserted {total} vectors into Vectorize index '{index_name}'.")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)

    # Assign stable UUIDs once — same id used by both postgres and vectorize
    for rec in records:
        if "id" not in rec:
            rec["id"] = str(uuid.uuid4())

    print(f"Loaded {len(records)} records from {DATA_PATH}")
    import_to_postgres(records)
    import_to_vectorize(records)


if __name__ == "__main__":
    main()
