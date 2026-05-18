"""
Import backend/seed/data/signals_seed.json into Aurora PostgreSQL + pgvector.

Usage:
    python backend/seed/import.py
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

_HERE = Path(__file__).parent
DATA_PATH = _HERE / "data" / "signals_seed.json"

CLOUDFLARE_BATCH_SIZE = 50
BEDROCK_BATCH_SIZE = 96
DEFAULT_BATCH_SIZE = 100


# ── db connection ─────────────────────────────────────────────────────────────

def get_db_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set in .env")
    return psycopg2.connect(url)


# ── postgres ──────────────────────────────────────────────────────────────────

def insert_signals(records: list[dict]) -> None:
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO signals (
                            id, source, source_id, source_url, raw_text,
                            pain_points, objections, use_cases,
                            icp, market, sector, funnel_stage,
                            confidence_score, embedding_text,
                            record_date, ingested_at, extracted_at
                        )
                        VALUES (%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s, %s,%s, %s,%s,%s)
                        ON CONFLICT (source, source_id) DO UPDATE SET
                            raw_text         = EXCLUDED.raw_text,
                            pain_points      = EXCLUDED.pain_points,
                            objections       = EXCLUDED.objections,
                            use_cases        = EXCLUDED.use_cases,
                            icp              = EXCLUDED.icp,
                            market           = EXCLUDED.market,
                            sector           = EXCLUDED.sector,
                            funnel_stage     = EXCLUDED.funnel_stage,
                            confidence_score = EXCLUDED.confidence_score,
                            embedding_text   = EXCLUDED.embedding_text,
                            record_date      = EXCLUDED.record_date,
                            extracted_at     = EXCLUDED.extracted_at
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
                            rec.get("market"),
                            rec.get("sector"),
                            rec.get("funnel_stage"),
                            rec.get("confidence_score"),
                            str(rec.get("embedding_text") or "").strip(),
                            rec.get("record_date"),
                            rec.get("ingested_at"),
                            datetime.now(timezone.utc),
                        ),
                    )
                    rec["id"] = str(cur.fetchone()[0])

        print(f"Imported {len(records)} records into signals.")
    finally:
        conn.close()


# ── embedding providers ───────────────────────────────────────────────────────

def _embed_bedrock(texts: list[str]) -> list[list[float]]:
    import boto3

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
    )
    resp = client.invoke_model(
        modelId=os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "cohere.embed-multilingual-v3"),
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "texts": texts,
            "input_type": "search_document",
        }),
    )
    return json.loads(resp["body"].read())["embeddings"]


_EMBED_DELAY_S = 0.7


def _embed_gemini(texts: list[str]) -> list[list[float]]:
    import re as _re
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    embeddings = []

    for idx, text in enumerate(texts):
        for attempt in range(4):
            try:
                result = client.models.embed_content(
                    model=os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=1024,
                    ),
                )
                embeddings.append(result.embeddings[0].values)
                break

            except Exception as exc:
                msg = str(exc)

                if attempt == 3 or "429" not in msg:
                    raise

                wait = 65
                m = _re.search(r"retry in ([\d.]+)s", msg)
                if m:
                    wait = int(float(m.group(1))) + 5

                print(f"429 rate limit ({idx + 1}/{len(texts)}), waiting {wait}s...")
                time.sleep(wait)

        if idx < len(texts) - 1:
            time.sleep(_EMBED_DELAY_S)

    return embeddings


def _embed_cloudflare(texts: list[str]) -> list[list[float]]:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{os.environ['CLOUDFLARE_ACCOUNT_ID']}"
        f"/ai/run/@cf/baai/bge-m3"
    )

    for attempt in range(4):
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}",
                "Content-Type": "application/json",
            },
            json={"text": texts},
            timeout=60,
        )

        if resp.ok:
            data = resp.json()
            embeddings = data["result"]["data"]

            if len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Cloudflare returned {len(embeddings)} embeddings "
                    f"for {len(texts)} texts"
                )

            return embeddings

        if resp.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
            raise RuntimeError(f"Cloudflare embed {resp.status_code}: {resp.text}")

        wait = 2 ** attempt
        print(f"Cloudflare temporary error {resp.status_code}, retrying in {wait}s...")
        time.sleep(wait)

    raise RuntimeError("Cloudflare embedding failed unexpectedly")


def _get_embedding_provider() -> str:
    provider = os.environ.get("SEED_EMBEDDING_PROVIDER", "").strip().lower()

    if provider not in {"bedrock", "gemini", "cloudflare"}:
        raise RuntimeError(
            "Set SEED_EMBEDDING_PROVIDER in .env to one of: "
            "bedrock, gemini, cloudflare"
        )

    return provider


def _embed_batch(texts: list[str]) -> list[list[float]]:
    provider = _get_embedding_provider()

    if provider == "gemini":
        return _embed_gemini(texts)

    if provider == "cloudflare":
        return _embed_cloudflare(texts)

    return _embed_bedrock(texts)


# ── pgvector ──────────────────────────────────────────────────────────────────

def insert_embeddings(records: list[dict]) -> None:
    provider = _get_embedding_provider()
    print(f"Embedding provider: {provider}")

    embedding_rows: list[tuple[str, str, dict]] = []
    skipped = 0

    for rec in records:
        embedding_text = str(rec.get("embedding_text") or "").strip()

        if not embedding_text:
            skipped += 1
            continue

        metadata = {
            "source": rec["source"],
            "funnel_stage": rec.get("funnel_stage"),
            "market": rec.get("market"),
            "sector": rec.get("sector"),
            "source_url": rec.get("source_url"),
        }

        embedding_rows.append((rec["id"], embedding_text, metadata))

    batch_size = CLOUDFLARE_BATCH_SIZE if provider == "cloudflare" else BEDROCK_BATCH_SIZE

    embeddings: list[list[float]] = []

    for start in range(0, len(embedding_rows), batch_size):
        batch_rows = embedding_rows[start:start + batch_size]
        batch_texts = [r[1] for r in batch_rows]

        print(
            f"Embedding batch {start // batch_size + 1}: "
            f"{len(batch_texts)} texts..."
        )

        batch_embeddings = _embed_batch(batch_texts)

        if batch_embeddings:
            print(f"Embedding dimension: {len(batch_embeddings[0])}")

        embeddings.extend(batch_embeddings)

    if len(embeddings) != len(embedding_rows):
        raise RuntimeError(
            f"Embedding count mismatch: {len(embeddings)} embeddings "
            f"for {len(embedding_rows)} rows"
        )

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
                        "DELETE FROM signal_embeddings WHERE signal_id = ANY(%s::uuid[])",
                        (empty_ids,),
                    )

                for (signal_id, embedding_text, metadata), values in zip(
                    embedding_rows,
                    embeddings,
                ):
                    cur.execute(
                        """
                        INSERT INTO signal_embeddings (
                            signal_id, embedding_text, embedding, metadata
                        )
                        VALUES (%s, %s, %s::vector, %s)
                        ON CONFLICT (signal_id) DO UPDATE SET
                            embedding_text = EXCLUDED.embedding_text,
                            embedding      = EXCLUDED.embedding,
                            metadata       = EXCLUDED.metadata
                        """,
                        (
                            signal_id,
                            embedding_text,
                            str(values),
                            psycopg2.extras.Json(metadata),
                        ),
                    )

        print(
            f"Upserted {len(embedding_rows)} embeddings into signal_embeddings; "
            f"skipped {skipped} records."
        )

    finally:
        conn.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    with open(DATA_PATH, encoding="utf-8") as f:
        records = json.load(f)

    for rec in records:
        if "id" not in rec:
            rec["id"] = str(uuid.uuid4())

    print(f"Loaded {len(records)} records from {DATA_PATH}")

    insert_signals(records)
    insert_embeddings(records)


if __name__ == "__main__":
    main()