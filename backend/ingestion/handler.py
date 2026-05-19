"""
Ingestion demo Lambda — serves the Ingestion UI screen.

Endpoints (Lambda Function URL, method + path routed internally):
    GET  /ingestion           → list mock files with metadata (alias: /ingestion/files)
    GET  /ingestion/preview   → return raw records of a mock file (?file_id=...)
    GET  /ingestion/logs      → fetch recent CloudWatch logs of Transform Lambda (?since=ISO8601)
    POST /ingestion/trigger   → push one mock file to S3 (AWS) or run transform directly (local dev)

Local dev (DATABASE_URL set, no DB_SECRET_ARN):
    trigger runs the transform pipeline synchronously using Gemini for LLM extraction.

AWS mode (DB_SECRET_ARN set):
    trigger pushes the file to S3; the S3 ObjectCreated event fires Transform Lambda asynchronously.

Environment variables:
    S3_BUCKET             target S3 bucket (AWS mode)
    DB_SECRET_ARN         Secrets Manager ARN for Aurora (AWS mode)
    DATABASE_URL          local dev PG connection string
    AWS_REGION            (default: ap-southeast-1)
    GEMINI_API_KEY        required in local dev mode
    TRANSFORM_LOG_GROUP   CloudWatch log group (default: /aws/lambda/ai-insight-hub-transform)
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_HERE = Path(__file__).resolve().parent
_MOCK_BASE_DIR = _HERE
_MOCK_SOURCES_PATH = _MOCK_BASE_DIR / "mock_sources.json"

# ── DB helpers ────────────────────────────────────────────────────────────────

_DB_CONN = None


def _get_conn():
    global _DB_CONN
    if _DB_CONN is not None:
        try:
            cur = _DB_CONN.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return _DB_CONN
        except Exception:
            _DB_CONN = None

    import pg8000.dbapi

    secret_arn = os.environ.get("DB_SECRET_ARN")
    if secret_arn:
        import boto3
        sm = boto3.client("secretsmanager")
        secret_str = sm.get_secret_value(SecretId=secret_arn)["SecretString"]
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


# ── Mock file helpers ─────────────────────────────────────────────────────────

def _load_sources() -> list[dict]:
    return json.loads(_MOCK_SOURCES_PATH.read_text(encoding="utf-8"))


def _source_path(file_rel: str) -> Path:
    return _MOCK_BASE_DIR / file_rel


# ── Trigger helpers ───────────────────────────────────────────────────────────

def _trigger_aws(source_id: str, source_name: str, file_path: Path) -> dict:
    import boto3
    bucket = os.environ["S3_BUCKET"]
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))

    records = json.loads(file_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    s3_key = f"raw/{source_name}/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}_{source_id}.json"

    s3.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=json.dumps(records, ensure_ascii=False, default=str).encode(),
        ContentType="application/json",
    )
    return {
        "mode": "aws",
        "s3_uri": f"s3://{bucket}/{s3_key}",
        "record_count": len(records),
        "note": "Transform Lambda will fire automatically via S3 ObjectCreated event.",
    }


def _trigger_local(source_id: str, source_name: str, file_path: Path) -> dict:
    """Local dev: import transform pipeline functions and run them directly."""
    _TRANSFORM_DIR = str(_HERE.parent / "transform")
    if _TRANSFORM_DIR not in sys.path:
        sys.path.insert(0, _TRANSFORM_DIR)

    from handler import (  # type: ignore[import]
        normalize,
        extract_and_merge,
        _insert_signals,
        _embed_rows,
        _insert_embeddings,
    )

    records = json.loads(file_path.read_text(encoding="utf-8"))
    fake_key = f"raw/{source_name}/2026-05-18/{source_id}.json"
    ingested_at = datetime.now(timezone.utc)
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    normalized = normalize(records, fake_key, ingested_at)
    if not normalized:
        return {"mode": "local", "upserted": 0, "vectors": 0, "note": "No usable records after normalization."}

    rows = extract_and_merge(normalized, source_name, model_id)
    upserted, id_map = _insert_signals(rows)
    vectors = _embed_rows(rows)
    vec_upserted = _insert_embeddings(rows, id_map, vectors)

    return {
        "mode": "local",
        "upserted": upserted,
        "vectors": vec_upserted,
        "record_count": len(records),
        "note": f"{upserted} signals and {vec_upserted} embeddings written to local DB.",
    }


# ── CORS + response helpers ───────────────────────────────────────────────────

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def _ok(body: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **_CORS_HEADERS},
        "body": json.dumps(body, default=str),
    }


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **_CORS_HEADERS},
        "body": json.dumps({"error": message}),
    }


# ── Route handlers ────────────────────────────────────────────────────────────

def _handle_list() -> dict:
    sources = _load_sources()
    return _ok({"files": sources})


def _handle_preview(file_id: str) -> dict:
    if not file_id:
        return _err("file_id is required")
    sources = _load_sources()
    entry = next((s for s in sources if s["id"] == file_id), None)
    if not entry:
        return _err(f"Unknown file_id: {file_id}")
    file_path = _source_path(entry["file"])
    if not file_path.exists():
        return _err(f"Mock file not found: {entry['file']}")
    records = json.loads(file_path.read_text(encoding="utf-8"))
    return _ok({"file_id": file_id, "source": entry["source"], "label": entry["label"], "records": records})


def _handle_trigger(body: dict) -> dict:
    file_id = body.get("file_id", "").strip()
    if not file_id:
        return _err("file_id is required")

    sources = _load_sources()
    entry = next((s for s in sources if s["id"] == file_id), None)
    if not entry:
        return _err(f"Unknown file_id: {file_id}")

    file_path = _source_path(entry["file"])
    if not file_path.exists():
        return _err(f"Mock file not found: {entry['file']}")

    is_aws = bool(os.environ.get("DB_SECRET_ARN"))
    try:
        if is_aws:
            result = _trigger_aws(entry["id"], entry["source"], file_path)
        else:
            result = _trigger_local(entry["id"], entry["source"], file_path)
    except Exception as exc:
        return _err(f"Trigger failed: {exc}", status=500)

    return _ok({"file_id": file_id, "source": entry["source"], **result})


# ── Lambda entry point ────────────────────────────────────────────────────────

def handler(event: dict, context=None) -> dict:
    req = event.get("requestContext", {}).get("http", {})
    method = req.get("method", event.get("httpMethod", "GET")).upper()
    path = req.get("path", event.get("path", "/ingestion")).rstrip("/") or "/ingestion"
    query = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _CORS_HEADERS, "body": ""}

    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        raw_body = base64.b64decode(raw_body).decode()
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        body = {}

    if method == "GET" and path in ("/ingestion", "/ingestion/files"):
        return _handle_list()
    if method == "GET" and path == "/ingestion/preview":
        return _handle_preview(query.get("file_id", "").strip())
    if method == "POST" and path == "/ingestion/trigger":
        return _handle_trigger(body)

    return _err(f"Not found: {method} {path}", status=404)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "trigger", "preview"])
    parser.add_argument("--file-id", default="hubspot_01")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    if args.action == "list":
        res = _handle_list()
    elif args.action == "preview":
        res = _handle_preview(args.file_id)
    else:
        res = _handle_trigger({"file_id": args.file_id})

    print(json.dumps(json.loads(res["body"]), indent=2, ensure_ascii=False))
