"""
Lambda: read configured sources → write raw JSON files to S3.

Sources are defined in sources.json: [{name, file}]
  - name : used as the S3 path prefix (raw/{name}/...)
  - file : path to mock JSON relative to this file (local dev)

To add a new source: append one entry to sources.json.

S3 path: raw/{name}/{YYYY-MM-DD}/{HHmmss}.json

Environment variables:
    S3_BUCKET   target S3 bucket (required)
    AWS_REGION  (default: ap-southeast-1)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

_S3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-southeast-1"))
_BASE = Path(__file__).resolve().parent


def _load_sources() -> list[dict]:
    return json.loads((_BASE / "sources.json").read_text(encoding="utf-8"))


def _load_records(file_path: str) -> list[dict]:
    return json.loads((_BASE / file_path).read_text(encoding="utf-8"))


def _write_to_s3(bucket: str, name: str, records: list[dict]) -> str | None:
    if not records:
        return None

    now = datetime.now(timezone.utc)
    key = f"raw/{name}/{now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}.json"

    _S3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(records, ensure_ascii=False, default=str).encode(),
        ContentType="application/json",
    )

    return f"s3://{bucket}/{key}"


def handler(event: dict, context=None) -> dict:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET environment variable is required")

    sources = _load_sources()
    results = {}

    for source in sources:
        name = source["name"]
        records = _load_records(source["file"])
        uri = _write_to_s3(bucket, name, records)
        print(f"{name}: {len(records)} records → {uri}")
        results[name] = len(records)

    return {"status": "ok", **results}


if __name__ == "__main__":
    print(handler({}))
