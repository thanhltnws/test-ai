"""
API Lambda — GET /insights

Returns pre-computed batch results from the insights table.
Supports time-range filtering via ?period= and ?date= query params.

Query params
------------
period  weekly | monthly | quarterly | yearly   (omit → latest across all)
date    Period reference — see README.md for accepted formats per period type.
        (omit → latest for the given period type)

Examples
--------
GET /insights                              # latest row, any period
GET /insights?period=monthly               # latest monthly snapshot
GET /insights?period=monthly&date=2026-05  # May 2026
GET /insights?period=weekly&date=2026-W20  # ISO week 20 of 2026
GET /insights?period=quarterly&date=2026-Q1
GET /insights?period=yearly&date=2026

Local run:
    python backend/application/api/handler.py
"""
import json
import os
from datetime import date, timedelta

import pg8000.dbapi
from dotenv import load_dotenv
from urllib.parse import urlparse


VALID_PERIODS = {"weekly", "monthly", "quarterly", "yearly"}

_db_url_cache: str | None = None


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


def _parse_period_start(period: str, date_str: str) -> date:
    """Resolve any ISO date to the canonical period_start for the given period type.

    date_str must be a valid ISO date: YYYY-MM-DD.
    Pass any date that falls within the desired period — the backend snaps it
    to the correct period_start automatically.

      weekly    "2026-05-14"  →  2026-05-11  (Monday of that week)
      monthly   "2026-05-14"  →  2026-05-01
      quarterly "2026-05-14"  →  2026-04-01  (Q2 starts Apr 1)
      yearly    "2026-05-14"  →  2026-01-01

    Raises ValueError on invalid date string.
    """
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid date '{date_str}'. Use ISO format YYYY-MM-DD, "
            "e.g. '2026-05-01'."
        )

    if period == "weekly":
        return d - timedelta(days=d.weekday())
    if period == "monthly":
        return d.replace(day=1)
    if period == "quarterly":
        return d.replace(month=((d.month - 1) // 3) * 3 + 1, day=1)
    if period == "yearly":
        return d.replace(month=1, day=1)

    raise ValueError(f"Unsupported period: {period}")


def get_insights(
    conn,
    period: str | None = None,
    date_str: str | None = None,
) -> dict:
    """Query the insights table with optional period/date filtering.

    Behaviour matrix:
      period=None, date=None  → latest snapshot across all period types
      period=X,    date=None  → latest snapshot for period type X
      period=X,    date=Y     → snapshot whose period_start matches Y
    """
    cur = conn.cursor()
    try:
        if period is None:
            cur.execute(
                """
                SELECT result_type, payload, period, period_start, period_end, computed_at
                FROM   insights
                WHERE  computed_at = (SELECT MAX(computed_at) FROM insights)
                ORDER  BY result_type
                """
            )
        elif date_str is None:
            cur.execute(
                """
                SELECT result_type, payload, period, period_start, period_end, computed_at
                FROM   insights
                WHERE  period = %s
                  AND  computed_at = (
                           SELECT MAX(computed_at) FROM insights WHERE period = %s
                       )
                ORDER  BY result_type
                """,
                (period, period),
            )
        else:
            period_start = _parse_period_start(period, date_str)
            cur.execute(
                """
                SELECT result_type, payload, period, period_start, period_end, computed_at
                FROM   insights
                WHERE  period = %s AND period_start = %s
                ORDER  BY result_type
                """,
                (period, period_start),
            )

        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()

    result: dict = {
        "period": None,
        "period_start": None,
        "period_end": None,
        "computed_at": None,
    }
    for row in rows:
        result[row["result_type"]] = row["payload"]
        if result["period_start"] is None:
            result["period"] = row["period"]
            result["period_start"] = str(row["period_start"])
            result["period_end"] = str(row["period_end"])
            result["computed_at"] = row["computed_at"].isoformat()

    return result


def _ok(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _err(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def handler(event=None, context=None):
    load_dotenv()

    path = (event or {}).get("rawPath", "/insights")

    if path != "/insights":
        return _err(404, f"Unknown path: {path}")

    params = (event or {}).get("queryStringParameters") or {}
    period = params.get("period") or None      # treat empty string as absent
    date_str = params.get("date") or None      # treat empty string as absent

    if period is not None and period not in VALID_PERIODS:
        return _err(
            400,
            f"Invalid period '{period}'. Valid values: {', '.join(sorted(VALID_PERIODS))}",
        )

    if date_str is not None and period is None:
        return _err(400, "'date' requires 'period' to be specified")

    conn = _pg_connect()
    try:
        try:
            return _ok(get_insights(conn, period=period, date_str=date_str))
        except ValueError as exc:
            return _err(400, str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Usage: python handler.py [period] [date]
    # e.g.:  python handler.py monthly 2026-05
    argv = sys.argv[1:]
    params: dict = {}
    if argv:
        params["period"] = argv[0]
    if len(argv) > 1:
        params["date"] = argv[1]
    print(json.dumps(handler({"rawPath": "/insights", "queryStringParameters": params}), indent=2))
