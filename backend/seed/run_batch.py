"""
Backfill insight builder for seed data.

Runs the same logic as the batch Lambda (handler.py) but iterates over
all historical periods covered by the seed data (Feb–May 2026) instead
of computing only the current period.

Usage:
    cd E:/works/programming/ai-insight-hub
    python backend/seed/run_batch.py
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import os
os.environ.setdefault("LLM_PROVIDER", "bedrock")

# Make batch handler importable
sys.path.insert(0, str(Path(__file__).parents[1] / "application" / "batch"))
sys.path.insert(0, str(Path(__file__).parents[1] / "application"))

from handler import (  # noqa: E402
    MARKETS,
    _pg_connect,
    query_aurora,
    query_pgvector,
    call_llm,
    parse_json_response,
    write_insights,
    _derive_embedding_text,
)
from prompt import build_batch_prompt  # noqa: E402


# ── period definitions ────────────────────────────────────────────────────────

def _get_data_range(conn) -> tuple[date, date]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT MIN(record_date), MAX(record_date) FROM signals WHERE record_date IS NOT NULL"
        )
        data_start, data_end = cur.fetchone()
        if data_start is None or data_end is None:
            raise RuntimeError("No records with record_date found in signals table")
        return data_start, data_end
    finally:
        cur.close()


def _weekly_periods(data_start: date, data_end: date) -> list[tuple[date, date]]:
    periods = []
    cursor = data_start - timedelta(days=data_start.weekday())
    while cursor <= data_end:
        periods.append((cursor, min(cursor + timedelta(days=6), data_end)))
        cursor += timedelta(weeks=1)
    return periods


def _monthly_periods(data_start: date, data_end: date) -> list[tuple[date, date]]:
    periods = []
    cursor = data_start.replace(day=1)
    while cursor <= data_end:
        year, month = cursor.year, cursor.month
        last_day = date(year, 12, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
        periods.append((cursor, min(last_day, data_end)))
        cursor = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return periods


def _quarterly_periods(data_start: date, data_end: date) -> list[tuple[date, date]]:
    quarters = []
    for year in range(data_start.year, data_end.year + 1):
        for q_start, q_end in [
            (date(year, 1, 1), date(year, 3, 31)),
            (date(year, 4, 1), date(year, 6, 30)),
            (date(year, 7, 1), date(year, 9, 30)),
            (date(year, 10, 1), date(year, 12, 31)),
        ]:
            if q_start <= data_end and q_end >= data_start:
                quarters.append((max(q_start, data_start), min(q_end, data_end)))
    return quarters


def _yearly_periods(data_start: date, data_end: date) -> list[tuple[date, date]]:
    return [
        (date(year, 1, 1), min(date(year, 12, 31), data_end))
        for year in range(data_start.year, data_end.year + 1)
        if date(year, 12, 31) >= data_start
    ]

EMBED_BATCH_SIZE = 96


COHERE_MAX_CHARS = 2048


def _embed_texts(texts: list[str]) -> list[list[float]]:
    import boto3
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "ap-southeast-1"),
    )
    truncated = [t[:COHERE_MAX_CHARS] for t in texts]
    resp = client.invoke_model(
        modelId=os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "cohere.embed-multilingual-v3"),
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"texts": truncated, "input_type": "search_document"}),
    )
    return json.loads(resp["body"].read())["embeddings"]


def _insert_insight_embeddings(conn, rows: list[tuple[str, str, str, dict]]) -> None:
    """rows: list of (insight_id, embedding_text, vector_str, metadata)"""
    cur = conn.cursor()
    try:
        for insight_id, emb_text, vector_str, metadata in rows:
            cur.execute(
                """
                INSERT INTO insight_embeddings (insight_id, embedding_text, embedding, metadata)
                VALUES (%s, %s, %s::vector, %s)
                ON CONFLICT (insight_id) DO UPDATE SET
                    embedding_text = EXCLUDED.embedding_text,
                    embedding      = EXCLUDED.embedding,
                    metadata       = EXCLUDED.metadata
                """,
                (insight_id, emb_text, vector_str, json.dumps(metadata)),
            )
        conn.commit()
    finally:
        cur.close()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    conn = _pg_connect()
    data_start, data_end = _get_data_range(conn)
    conn.close()

    granularities: dict[str, list[tuple[date, date]]] = {
        "weekly":    _weekly_periods(data_start, data_end),
        "monthly":   _monthly_periods(data_start, data_end),
        "quarterly": _quarterly_periods(data_start, data_end),
        "yearly":    _yearly_periods(data_start, data_end),
    }

    print(f"Data range from DB: {data_start} → {data_end}")
    total_periods = sum(len(v) for v in granularities.values())
    total_slices  = total_periods * len(MARKETS)
    print(f"Backfill plan: {total_periods} periods × {len(MARKETS)} markets = {total_slices} slices")
    for g, periods in granularities.items():
        print(f"  {g}: {len(periods)} period(s)")
    print(f"  markets: {[m or 'all' for m in MARKETS]}")
    print()

    conn = _pg_connect()
    total_written = 0

    # Collect all insight rows to embed after the main loop
    pending: list[dict] = []  # {id, result_type, payload, granularity, p_start, p_end, market}

    try:
        for market in MARKETS:
            mkt_label = market or "all"
            for granularity, periods in granularities.items():
                for p_start, p_end in periods:
                    label = f"[{granularity}/{mkt_label}] {p_start} → {p_end}"

                    sql_ctx = query_aurora(conn, p_start, p_end, market=market)
                    total   = sql_ctx["summary"]["total_signals"]
                    print(f"{label}  signals={total}", end="")

                    if total == 0:
                        print("  — skip (no data)")
                        continue

                    vector_ctx = query_pgvector(conn, p_start, p_end)
                    print(f"  semantic={len(vector_ctx)}", end="  ")

                    prompt  = build_batch_prompt(sql_ctx, vector_ctx, granularity, p_start, p_end, market=market)
                    raw     = call_llm(prompt)
                    results = parse_json_response(raw)
                    written_rows = write_insights(conn, results, granularity, p_start, p_end, market=market)
                    total_written += len(written_rows)
                    print(f"wrote {len(written_rows)} rows")

                    for row in written_rows:
                        row.update({"granularity": granularity, "p_start": p_start, "p_end": p_end, "market": market})
                        pending.append(row)

    finally:
        conn.close()

    print(f"\nDone — {total_written} rows written to insights.")

    # ── embed + insert insight_embeddings ─────────────────────────────────────
    if not pending:
        return

    to_embed = []
    for row in pending:
        emb_text = _derive_embedding_text(row["result_type"], row["payload"])
        if emb_text:
            to_embed.append((row["id"], emb_text, row))

    print(f"\nEmbedding {len(to_embed)} insight rows ({len(pending) - len(to_embed)} skipped — empty text)...")

    embed_rows: list[tuple[str, str, str, dict]] = []
    for start in range(0, len(to_embed), EMBED_BATCH_SIZE):
        batch = to_embed[start:start + EMBED_BATCH_SIZE]
        texts = [r[1] for r in batch]
        print(f"  Embedding batch {start // EMBED_BATCH_SIZE + 1}: {len(texts)} texts...")
        vectors = _embed_texts(texts)
        for (insight_id, emb_text, row), vec in zip(batch, vectors):
            metadata = {
                "period":       row["granularity"],
                "period_start": str(row["p_start"]),
                "period_end":   str(row["p_end"]),
                "result_type":  row["result_type"],
                "market":       row["market"],
            }
            embed_rows.append((insight_id, emb_text, str(vec), metadata))

    conn2 = _pg_connect()
    try:
        _insert_insight_embeddings(conn2, embed_rows)
    finally:
        conn2.close()

    print(f"Upserted {len(embed_rows)} embeddings into insight_embeddings.")


def embed_only() -> None:
    """Re-embed all existing insight rows into insight_embeddings. Use after a failed embedding step."""
    conn = _pg_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT i.id, i.result_type, i.payload, i.period, i.period_start, i.period_end, i.market
            FROM insights i
            LEFT JOIN insight_embeddings ie ON ie.insight_id = i.id
            WHERE ie.insight_id IS NULL
            ORDER BY i.computed_at
            """
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not rows:
        print("No un-embedded insight rows found.")
        return

    print(f"Found {len(rows)} insight rows without embeddings.")

    to_embed = []
    for r in rows:
        insight_id, result_type, payload, period, p_start, p_end, market = r
        emb_text = _derive_embedding_text(result_type, payload)
        if emb_text:
            to_embed.append((str(insight_id), emb_text, {
                "period": period, "period_start": str(p_start),
                "period_end": str(p_end), "result_type": result_type, "market": market,
            }))

    print(f"Embedding {len(to_embed)} rows ({len(rows) - len(to_embed)} skipped — empty text)...")

    embed_rows: list[tuple[str, str, str, dict]] = []
    for start in range(0, len(to_embed), EMBED_BATCH_SIZE):
        batch = to_embed[start:start + EMBED_BATCH_SIZE]
        texts = [r[1] for r in batch]
        print(f"  Batch {start // EMBED_BATCH_SIZE + 1}: {len(texts)} texts...")
        vectors = _embed_texts(texts)
        for (insight_id, emb_text, metadata), vec in zip(batch, vectors):
            embed_rows.append((insight_id, emb_text, str(vec), metadata))

    conn2 = _pg_connect()
    try:
        _insert_insight_embeddings(conn2, embed_rows)
    finally:
        conn2.close()

    print(f"Upserted {len(embed_rows)} embeddings into insight_embeddings.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed-only", action="store_true", help="Only embed existing insight rows, skip LLM batch")
    args = parser.parse_args()

    if args.embed_only:
        embed_only()
    else:
        main()
