"""
Backfill insight builder for seed data.

Runs the same logic as the batch Lambda (handler.py) but iterates over
all historical periods covered by the seed data (Feb–May 2026) instead
of computing only the current period.

Usage:
    cd E:/works/programming/ai-insight-hub
    python backend/seed/run_batch.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Force Bedrock — override _is_dev() detection before importing handler
import os
os.environ.setdefault("APP_ENV", "production")

# Make batch handler importable
sys.path.insert(0, str(Path(__file__).parents[1] / "application" / "batch"))
sys.path.insert(0, str(Path(__file__).parents[1] / "application"))

from handler import (  # noqa: E402
    _pg_connect,
    query_aurora,
    query_pgvector,
    call_llm,
    parse_json_response,
    write_insights,
)
from prompt import build_batch_prompt  # noqa: E402


# ── period definitions ────────────────────────────────────────────────────────

DATA_START = date(2026, 3, 1)   # first meaningful spike in seed data
DATA_END   = date(2026, 5, 16)  # last date in seed data


def _weekly_periods() -> list[tuple[date, date]]:
    """Every Mon–Sun week that overlaps with seed data range."""
    periods = []
    # Start from Monday of the week containing DATA_START
    cursor = DATA_START - timedelta(days=DATA_START.weekday())
    while cursor <= DATA_END:
        p_start = cursor
        p_end   = min(cursor + timedelta(days=6), DATA_END)
        periods.append((p_start, p_end))
        cursor += timedelta(weeks=1)
    return periods


def _monthly_periods() -> list[tuple[date, date]]:
    """Each calendar month that overlaps with seed data range."""
    periods = []
    cursor = DATA_START.replace(day=1)
    while cursor <= DATA_END:
        year, month = cursor.year, cursor.month
        if month == 12:
            last_day = date(year, 12, 31)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        p_end = min(last_day, DATA_END)
        periods.append((cursor, p_end))
        if month == 12:
            cursor = date(year + 1, 1, 1)
        else:
            cursor = date(year, month + 1, 1)
    return periods


def _quarterly_periods() -> list[tuple[date, date]]:
    """Each calendar quarter that overlaps with seed data range."""
    quarters = [
        (date(2026, 1, 1),  date(2026, 3, 31)),
        (date(2026, 4, 1),  date(2026, 6, 30)),
    ]
    return [
        (max(p_start, DATA_START), min(p_end, DATA_END))
        for p_start, p_end in quarters
        if p_start <= DATA_END and p_end >= DATA_START
    ]


def _yearly_periods() -> list[tuple[date, date]]:
    return [(date(2026, 1, 1), DATA_END)]


GRANULARITIES: dict[str, list[tuple[date, date]]] = {
    "weekly":    _weekly_periods(),
    "monthly":   _monthly_periods(),
    "quarterly": _quarterly_periods(),
    "yearly":    _yearly_periods(),
}


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    total_periods = sum(len(v) for v in GRANULARITIES.values())
    print(f"Backfill plan: {total_periods} periods")
    for g, periods in GRANULARITIES.items():
        print(f"  {g}: {len(periods)} period(s)")
    print()

    conn = _pg_connect()
    total_written = 0

    try:
        for granularity, periods in GRANULARITIES.items():
            for p_start, p_end in periods:
                label = f"[{granularity}] {p_start} → {p_end}"

                sql_ctx = query_aurora(conn, p_start, p_end)
                total   = sql_ctx["summary"]["total_signals"]
                print(f"{label}  signals={total}", end="")

                if total == 0:
                    print("  — skip (no data)")
                    continue

                vector_ctx = query_pgvector(conn, p_start, p_end)
                print(f"  semantic={len(vector_ctx)}", end="  ")

                prompt  = build_batch_prompt(sql_ctx, vector_ctx, granularity, p_start, p_end)
                raw     = call_llm(prompt)
                results = parse_json_response(raw)
                written = write_insights(conn, results, granularity, p_start, p_end)
                total_written += written
                print(f"wrote {written} rows")

    finally:
        conn.close()

    print(f"\nDone — {total_written} rows written to insights.")


if __name__ == "__main__":
    main()
