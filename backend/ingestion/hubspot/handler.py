"""
Lambda: read HubSpot mock data → write raw JSON files to S3.

Reads deals.json and calls.json from the mock/ directory, flattens to
HubSpot API shape, and writes two S3 files that trigger the transform Lambda.

S3 path: raw/hubspot/{YYYY-MM-DD}/{HHmmss}_{type}.json

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

# Load .env file
load_dotenv()

_S3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION", "ap-southeast-1")
)

MOCK_DIR = Path(__file__).resolve().parent / "mock"


def _load(filename: str) -> list[dict]:
    return json.loads((MOCK_DIR / filename).read_text(encoding="utf-8"))


def _flatten_deals(records: list[dict]) -> list[dict]:
    return [
        {
            "id": r["id"],
            "url": f"https://app.hubspot.com/contacts/deals/{r['id']}",
            **r.get("properties", {}),
        }
        for r in records
    ]


def _flatten_calls(records: list[dict]) -> list[dict]:
    return [
        {
            "id": r["id"],
            "url": f"https://app.hubspot.com/contacts/calls/{r['id']}",
            "call_notes": r.get("properties", {}).get("hs_call_body", ""),
            **r.get("properties", {}),
        }
        for r in records
    ]


def _write_to_s3(bucket: str, records: list[dict], record_type: str) -> str | None:
    if not records:
        return None

    now = datetime.now(timezone.utc)

    key = (
        f"raw/hubspot/"
        f"{now.strftime('%Y-%m-%d')}/"
        f"{now.strftime('%H%M%S')}_{record_type}.json"
    )

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

    deals = _flatten_deals(_load("deals.json"))
    calls = _flatten_calls(_load("calls.json"))

    deal_uri = _write_to_s3(bucket, deals, "deals")
    call_uri = _write_to_s3(bucket, calls, "calls")

    print(
        f"HubSpot: "
        f"{len(deals)} deals → {deal_uri} | "
        f"{len(calls)} calls → {call_uri}"
    )

    return {
        "status": "ok",
        "deals": len(deals),
        "calls": len(calls),
    }


# Run locally
if __name__ == "__main__":
    result = handler({})
    print(result)