"""
Lambda: read Jira mock data → write raw JSON file to S3.

Reads issues.json from the mock/ directory, flattens from Jira API shape,
and writes one S3 file that triggers the transform Lambda.

S3 path: raw/jira/{YYYY-MM-DD}/{HHmmss}_issues.json

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

BASE_URL = "https://newwave.atlassian.net"


def _load() -> list[dict]:
    return json.loads(
        (MOCK_DIR / "issues.json").read_text(encoding="utf-8")
    )


def _flatten(issues: list[dict]) -> list[dict]:
    out = []

    for issue in issues:
        fields = issue.get("fields", {})

        comments = [
            {
                "author": c.get("author", {}).get("displayName", ""),
                "body": c.get("body", ""),
            }
            for c in fields.get("comment", {}).get("comments", [])
        ]

        out.append({
            "id": issue["id"],
            "key": issue["key"],
            "url": f"{BASE_URL}/browse/{issue['key']}",
            "summary": fields.get("summary", ""),
            "description": fields.get("description") or "",
            "status": fields.get("status", {}).get("name", ""),
            "priority": fields.get("priority", {}).get("name", ""),
            "issuetype": fields.get("issuetype", {}).get("name", ""),
            "assignee": (fields.get("assignee") or {}).get("displayName", ""),
            "reporter": (fields.get("reporter") or {}).get("displayName", ""),
            "updated": fields.get("updated", ""),
            "created": fields.get("created", ""),
            "comments": comments,
        })

    return out


def _write_to_s3(bucket: str, issues: list[dict]) -> str | None:
    if not issues:
        return None

    now = datetime.now(timezone.utc)

    key = (
        f"raw/jira/"
        f"{now.strftime('%Y-%m-%d')}/"
        f"{now.strftime('%H%M%S')}_issues.json"
    )

    _S3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(issues, ensure_ascii=False, default=str).encode(),
        ContentType="application/json",
    )

    return f"s3://{bucket}/{key}"


def handler(event: dict, context=None) -> dict:
    bucket = os.getenv("S3_BUCKET")

    if not bucket:
        raise ValueError("S3_BUCKET environment variable is required")

    issues = _flatten(_load())

    uri = _write_to_s3(bucket, issues)

    print(f"Jira: {len(issues)} issues → {uri}")

    return {
        "status": "ok",
        "issues": len(issues),
    }


# Run locally
if __name__ == "__main__":
    result = handler({})
    print(result)