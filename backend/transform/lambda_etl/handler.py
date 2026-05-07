"""
Lambda ETL: download raw files from S3, normalize, deduplicate, upload staging JSON back to S3.

Flow:
    s3://{S3_BUCKET}/{S3_RAW_PREFIX}**  →  normalize + dedup  →  s3://{S3_BUCKET}/{S3_KEY}

S3 raw prefix structure mirrors local seed/raw/:
    raw/sales/sales_pipeline_crm/sales_pipeline.csv
    raw/marketing/marketing_lead_scoring/Lead Scoring.csv
    raw/ops/ofbiz_issues.json

Event keys (all optional):
    dry_run   bool — download + process but skip final S3 upload

Environment variables:
    S3_BUCKET        S3 bucket (required)
    S3_RAW_PREFIX    prefix for raw input files  (default: raw/)
    S3_KEY           output object key           (default: transform/staging/staging.json)
    AWS_REGION       (default: us-east-1)
"""
import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_RAW_PREFIX = "raw/"
_DEFAULT_S3_KEY     = "transform/staging/staging.json"
MIN_ROW_TEXT_LEN    = 10


# ── inlined file utils (self-contained for Lambda deploy) ─────────────────────

def find_subfolders(raw_dir: Path) -> list[Path]:
    results = []
    for domain in sorted(raw_dir.iterdir()):
        if not domain.is_dir():
            continue
        subdirs = [p for p in domain.iterdir() if p.is_dir()]
        if subdirs:
            results.extend(sorted(subdirs))
        else:
            results.append(domain)
    return results


def load_records(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []


def row_to_text(row: dict) -> str:
    lines = []
    for k, v in row.items():
        if k.startswith("_"):
            continue
        v = str(v).strip()
        if v and v.lower() not in ("select", "nan", "none", ""):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _s3_client(region: str):
    return boto3.client("s3", region_name=region)


def download_raw_from_s3(s3, bucket: str, raw_prefix: str, tmp_dir: Path) -> None:
    """Download all objects under raw_prefix into tmp_dir, preserving folder structure."""
    paginator = s3.get_paginator("list_objects_v2")
    pages     = paginator.paginate(Bucket=bucket, Prefix=raw_prefix)
    keys = [
        obj["Key"] for page in pages
        for obj in page.get("Contents", [])
        if not obj["Key"].endswith("/")
    ]

    if not keys:
        raise RuntimeError(f"No objects found at s3://{bucket}/{raw_prefix}")

    print(f"Downloading {len(keys)} file(s) from s3://{bucket}/{raw_prefix} …")
    for key in keys:
        rel        = key[len(raw_prefix):].lstrip("/")
        local_path = tmp_dir / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        local_path.write_bytes(body)
        print(f"  ↓ {key}")


def upload_to_s3(s3, payload: list[dict], bucket: str, key: str) -> str:
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return f"s3://{bucket}/{key}"


# ── normalize + dedup ─────────────────────────────────────────────────────────

def _content_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def normalize_subfolder(subfolder: Path, raw_prefix: str, bucket: str) -> list[dict]:
    data_files = [
        f for f in sorted(subfolder.iterdir())
        if f.is_file() and f.suffix.lower() in (".csv", ".json")
    ]
    records = []
    seen    = set()

    for f in data_files:
        for i, row in enumerate(load_records(f)):
            text = row_to_text(row)
            if len(text) < MIN_ROW_TEXT_LEN:
                continue
            h = _content_hash(text)
            if h in seen:
                continue
            seen.add(h)
            rel_path = "/".join(subfolder.parts[-2:]) + "/" + f.name
            records.append({
                "source":     subfolder.name,
                "domain":     subfolder.parent.name,
                "file":       f.name,
                "source_url": f"s3://{bucket}/{raw_prefix.rstrip('/')}/{rel_path}",
                "row_index":  i,
                "hash":       h,
                "fields":     {k: str(v) for k, v in row.items()},
                "text":       text,
            })

    return records


# ── Lambda entry point ────────────────────────────────────────────────────────

def handler(event: dict, context=None) -> dict:
    bucket     = os.environ.get("S3_BUCKET", "")
    raw_prefix = os.environ.get("S3_RAW_PREFIX", _DEFAULT_RAW_PREFIX).rstrip("/") + "/"
    out_key    = os.environ.get("S3_KEY", _DEFAULT_S3_KEY)
    region     = os.environ.get("AWS_REGION", "us-east-1")
    dry_run    = bool(event.get("dry_run", False))

    if not bucket:
        raise RuntimeError("S3_BUCKET env var is required")

    s3 = _s3_client(region)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        download_raw_from_s3(s3, bucket, raw_prefix, tmp_dir)

        subfolders  = find_subfolders(tmp_dir)
        all_records: list[dict] = []

        for sf in subfolders:
            recs = normalize_subfolder(sf, raw_prefix, bucket)
            print(f"  {sf.relative_to(tmp_dir)}: {len(recs)} records")
            all_records.extend(recs)

    print(f"\nTotal: {len(all_records)} records after dedup")

    s3_uri = None
    if not dry_run:
        s3_uri = upload_to_s3(s3, all_records, bucket, out_key)
        print(f"✓ Uploaded staging → {s3_uri}")

    return {
        "status":       "ok",
        "record_count": len(all_records),
        "s3_uri":       s3_uri,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args   = parser.parse_args()
    result = handler({"dry_run": args.dry_run})
    print(result)
