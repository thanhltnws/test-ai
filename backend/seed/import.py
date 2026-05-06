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
    """
    TODO: embed raw_text and upsert into Cloudflare Vectorize.

    For each record:
      - vector id : record["id"]          (matches insights.id)
      - text      : record["raw_text"]    (split into chunks if > 512 tokens)
      - metadata  : {source, source_url, funnel_stage, ingested_at}

    Requires in .env:
      CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, VECTORIZE_INDEX_NAME
    """
    pass


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
