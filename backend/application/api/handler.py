"""
API Lambda — GET /insights

Returns the latest pre-computed batch results from the insights table.
Each result_type (pain_points_summary, funnel_distribution, icp_narrative,
recommendations) is a key in the response payload.

Local run:
    python backend/application/api/handler.py
"""
import json
import os

import pg8000.dbapi
from dotenv import load_dotenv
from urllib.parse import urlparse


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


def get_insights(conn) -> dict:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT result_type, payload, period_start, computed_at
            FROM insights
            WHERE period_start = (SELECT MAX(period_start) FROM insights)
            ORDER BY result_type
            """
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()

    result: dict = {"period_start": None, "computed_at": None}
    for row in rows:
        result[row["result_type"]] = row["payload"]
        if result["period_start"] is None:
            result["period_start"] = str(row["period_start"])
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

    conn = _pg_connect()
    try:
        return _ok(get_insights(conn))
    finally:
        conn.close()


if __name__ == "__main__":
    print(json.dumps(handler({"rawPath": "/insights"}), indent=2))
