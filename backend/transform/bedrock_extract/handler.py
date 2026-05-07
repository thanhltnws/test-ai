"""
Lambda: read staging JSON from S3, extract insight records using Amazon Bedrock.

Flow:
    s3://{S3_BUCKET}/{S3_STAGING_KEY}
        → batch by source
        → Bedrock AI (Claude Haiku)
        → s3://{S3_BUCKET}/{S3_INSIGHTS_KEY}

Environment variables:
    S3_BUCKET          S3 bucket (required)
    S3_STAGING_KEY     input staging key  (default: transform/staging/staging.json)
    S3_INSIGHTS_KEY    output insights key (default: transform/insights/insights.json)
    BEDROCK_MODEL_ID   (default: anthropic.claude-3-haiku-20240307-v1:0)
    AWS_REGION         (default: us-east-1)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import instructor
from dotenv import load_dotenv
from typing import Any
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt import build_extract_prompt

load_dotenv()

_DEFAULT_STAGING_KEY  = "transform/staging/staging.json"
_DEFAULT_INSIGHTS_KEY = "transform/insights/insights.json"
DEFAULT_MODEL_ID      = "us.anthropic.claude-3-haiku-20240307-v1:0"

MAX_BATCH_CHARS   = 150_000
MAX_BATCH_RECORDS = 40
API_DELAY_S       = 1.0


# ── output schema ─────────────────────────────────────────────────────────────

_VALID_STAGES        = {"awareness", "consideration", "negotiation", "won", "lost"}
_VALID_SECTORS       = {"fintech", "logistics", "retail", "healthcare", "manufacturing",
                        "software", "education", "ict", "other"}
_VALID_COMPANY_SIZES = {"1-10", "11-50", "50-200", "200-1000", "1000+"}
_VALID_DEAL_SIZES    = {"small", "medium", "large"}


class _ICP(BaseModel):
    sector:       str = "other"
    company_size: str = "50-200"
    deal_size:    str = "medium"
    region:       str = "Southeast Asia"

    @field_validator("sector")
    @classmethod
    def _v_sector(cls, v: str) -> str:
        return v if v in _VALID_SECTORS else "other"

    @field_validator("company_size")
    @classmethod
    def _v_company_size(cls, v: str) -> str:
        return v if v in _VALID_COMPANY_SIZES else "50-200"

    @field_validator("deal_size")
    @classmethod
    def _v_deal_size(cls, v: str) -> str:
        return v if v in _VALID_DEAL_SIZES else "medium"


class _Extraction(BaseModel):
    pain_points:      list[str] = Field(default_factory=list)
    objections:       list[str] = Field(default_factory=list)
    use_cases:        list[str] = Field(default_factory=list)
    icp:              _ICP      = Field(default_factory=_ICP)
    funnel_stage:     str       = "consideration"
    confidence_score: float     = 0.5
    source_id:        str       = ""

    @field_validator("funnel_stage")
    @classmethod
    def _v_funnel_stage(cls, v: str) -> str:
        return v if v in _VALID_STAGES else "consideration"

    @field_validator("confidence_score")
    @classmethod
    def _v_confidence_score(cls, v: float) -> float:
        return round(max(0.0, min(1.0, float(v))), 2)


class _ExtractionBatch(BaseModel):
    records: list[_Extraction] = []


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _s3(region: str):
    return boto3.client("s3", region_name=region)


def read_staging(s3, bucket: str, key: str) -> list[dict]:
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body.decode("utf-8"))


def upload_insights(s3, payload: list[dict], bucket: str, key: str) -> str:
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    return f"s3://{bucket}/{key}"


# ── bedrock client ────────────────────────────────────────────────────────────

def _build_client(region: str) -> Any:
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    return instructor.from_bedrock(bedrock, mode=instructor.Mode.BEDROCK_TOOLS)


# ── batching ──────────────────────────────────────────────────────────────────

def make_batches(records: list[dict]) -> list[list[dict]]:
    batches   = []
    current   = []
    cur_chars = 0
    for rec in records:
        text_len = len(rec["text"])
        if current and (cur_chars + text_len > MAX_BATCH_CHARS or len(current) >= MAX_BATCH_RECORDS):
            batches.append(current)
            current   = []
            cur_chars = 0
        current.append(rec)
        cur_chars += text_len
    if current:
        batches.append(current)
    return batches


# ── extraction ────────────────────────────────────────────────────────────────

def extract_batch(
    records: list[dict],
    source: str,
    client: Any,
    model_id: str,
) -> list[_Extraction]:
    texts  = [r["text"] for r in records]
    prompt = build_extract_prompt(texts, source, context_content="")
    result = client.messages.create(
        model=model_id,
        max_tokens=4096,
        response_model=_ExtractionBatch,
        max_retries=2,
        messages=[{"role": "user", "content": prompt}],
    )
    extractions = result.records
    if len(extractions) < len(records):
        print(f"  WARN  AI returned {len(extractions)}/{len(records)} records — padding")
    while len(extractions) < len(records):
        extractions.append(_Extraction())
    return extractions


def assemble_row(rec: dict, ext: _Extraction) -> dict:
    return {
        "source":           rec["source"],
        "source_id":        ext.source_id or rec["hash"],
        "source_url":       rec["source_url"],
        "raw_text":         rec["text"],
        "pain_points":      ext.pain_points,
        "objections":       ext.objections,
        "use_cases":        ext.use_cases,
        "icp":              ext.icp.model_dump(),
        "funnel_stage":     ext.funnel_stage,
        "confidence_score": ext.confidence_score,
        "ingested_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── source processor ──────────────────────────────────────────────────────────

def process_source(
    source: str,
    records: list[dict],
    client: Any,
    model_id: str,
) -> tuple[list[dict], list[dict]]:
    batches = make_batches(records)
    print(f"  {source}: {len(records)} records → {len(batches)} batch(es)")

    results = []
    errors  = []

    for batch_num, batch in enumerate(batches, 1):
        try:
            extractions = extract_batch(batch, source, client, model_id)
            for rec, ext in zip(batch, extractions):
                results.append(assemble_row(rec, ext))
            print(f"    batch {batch_num}/{len(batches)} ✓  ({len(batch)} records)")
        except Exception as exc:
            errors.append({"source": source, "batch": batch_num, "error": str(exc)})
            print(f"    batch {batch_num}/{len(batches)} ✗  {exc}")

        time.sleep(API_DELAY_S)

    return results, errors


# ── Lambda entry point ────────────────────────────────────────────────────────

def handler(event: dict, context=None) -> dict:
    bucket       = os.getenv("S3_BUCKET", "")
    staging_key  = os.getenv("S3_STAGING_KEY",  _DEFAULT_STAGING_KEY)
    insights_key = os.getenv("S3_INSIGHTS_KEY", _DEFAULT_INSIGHTS_KEY)
    model_id     = os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
    region       = os.getenv("AWS_REGION", "us-east-1")
    dry_run      = bool(event.get("dry_run", False))
    limit        = event.get("limit")

    if not bucket:
        raise RuntimeError("S3_BUCKET env var is required")

    s3      = _s3(region)
    client  = _build_client(region)
    staging = read_staging(s3, bucket, staging_key)

    print(f"bedrock_extract: model={model_id}  staging={len(staging)} records\n")

    if limit:
        staging = staging[:limit]

    by_source: dict[str, list[dict]] = {}
    for rec in staging:
        by_source.setdefault(rec["source"], []).append(rec)

    all_records: list[dict] = []
    all_errors:  list[dict] = []

    for source, records in by_source.items():
        recs, errs = process_source(source, records, client, model_id)
        all_records.extend(recs)
        all_errors.extend(errs)
        print()

    s3_uri = None
    if not dry_run:
        s3_uri = upload_insights(s3, all_records, bucket, insights_key)
        print(f"✓ {len(all_records)} records → {s3_uri}")

    if all_errors:
        print(f"✗ {len(all_errors)} error(s):")
        for e in all_errors:
            print(f"  {e}")

    return {
        "status":       "ok",
        "record_count": len(all_records),
        "error_count":  len(all_errors),
        "s3_uri":       s3_uri,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args   = parser.parse_args()
    result = handler({"dry_run": args.dry_run, "limit": args.limit})
    print(result)
