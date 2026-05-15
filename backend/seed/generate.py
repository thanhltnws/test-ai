"""
Generate unified signal seed data from raw source JSON files.

Input:
    backend/seed/data/raw/
      hubspot.json
      twenty_crm.json
      redmine.json
      outlook_email.json
      teams_transcript.json
      sharepoint.json

Output:
    backend/seed/data/signals_seed.json

Defaults:
    - Local/dev uses Gemini for extraction
    - Optional Bedrock mode is available for production-parity spot checks

Usage:
    python backend/seed/generate.py
    python backend/seed/generate.py --limit 10
    python backend/seed/generate.py --provider bedrock
    python backend/seed/generate.py --source redmine --source outlook_email
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from json_repair import repair_json

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_extract_prompt


MAX_BATCH_CHARS = 150_000
MAX_BATCH_RECORDS = 40
API_DELAY_S = 1.0
MIN_ROW_TEXT_LEN = 10

DEFAULT_PROVIDER = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_BEDROCK_MODEL = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_AWS_REGION = "ap-southeast-1"

_HERE = Path(__file__).parent
RAW_DIR = _HERE / "data" / "raw"
OUTPUT_PATH = _HERE / "data" / "signals_seed.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max records per source file; omit to process all",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "bedrock"],
        default=None,
        help="LLM provider for extraction; default comes from env or Gemini",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="specific source name(s) to process, e.g. --source redmine",
    )
    return parser.parse_args()


def get_provider(cli_provider: str | None) -> str:
    provider = (
        cli_provider
        or os.getenv("SEED_LLM_PROVIDER")
        or os.getenv("LOCAL_LLM_PROVIDER")
        or DEFAULT_PROVIDER
    ).strip().lower()
    if provider not in {"gemini", "bedrock"}:
        raise RuntimeError("Provider must be one of: gemini, bedrock")
    return provider


def get_source_files(selected_sources: list[str]) -> list[Path]:
    if not RAW_DIR.exists():
        raise RuntimeError(f"Raw data directory not found: {RAW_DIR}")

    files = sorted(p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".json")
    if not files:
        raise RuntimeError(f"No JSON source files found in {RAW_DIR}")

    if not selected_sources:
        return files

    selected = {name.strip().lower() for name in selected_sources}
    filtered = [p for p in files if p.stem.lower() in selected]
    if not filtered:
        raise RuntimeError(f"No matching sources found for: {sorted(selected)}")
    return filtered


def load_source_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"{path.name} must contain a JSON array")
    return [row for row in data if isinstance(row, dict)]


def _flatten_value(prefix: str, value: Any, out: list[str]) -> None:
    if value is None:
        return

    if isinstance(value, str):
        text = value.strip()
        if text:
            out.append(f"{prefix}: {text}" if prefix else text)
        return

    if isinstance(value, (int, float, bool)):
        out.append(f"{prefix}: {value}" if prefix else str(value))
        return

    if isinstance(value, list):
        for idx, item in enumerate(value, 1):
            child_prefix = f"{prefix}[{idx}]" if prefix else f"item[{idx}]"
            _flatten_value(child_prefix, item, out)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_value(child_prefix, item, out)


def row_to_text(row: dict) -> str:
    lines: list[str] = []
    for key, value in row.items():
        _flatten_value(str(key), value, lines)
    return "\n".join(lines).strip()


def make_batches(records: list[dict]) -> list[list[tuple[int, dict, str]]]:
    batches: list[list[tuple[int, dict, str]]] = []
    current: list[tuple[int, dict, str]] = []
    current_chars = 0

    for idx, row in enumerate(records):
        text = row_to_text(row)
        if len(text) < MIN_ROW_TEXT_LEN:
            continue

        if current and (
            current_chars + len(text) > MAX_BATCH_CHARS
            or len(current) >= MAX_BATCH_RECORDS
        ):
            batches.append(current)
            current = []
            current_chars = 0

        current.append((idx, row, text))
        current_chars += len(text)

    if current:
        batches.append(current)

    return batches


def parse_json_response(response_text: str) -> Any:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(repair_json(text.strip()))


class GeminiExtractor:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.model = os.getenv("LOCAL_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    def extract_batch(self, texts: list[str], source: str) -> list[dict]:
        prompt = build_extract_prompt(texts, source, context_content="")
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        result = parse_json_response(response.text)
        if not isinstance(result, list):
            raise RuntimeError("Gemini returned non-array JSON")
        return result


class BedrockExtractor:
    def __init__(self) -> None:
        import boto3

        region = os.getenv("AWS_REGION", DEFAULT_AWS_REGION)
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model = os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL)

    def extract_batch(self, texts: list[str], source: str) -> list[dict]:
        prompt = build_extract_prompt(texts, source, context_content="")
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 8192,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        response = self.client.invoke_model(modelId=self.model, body=body)
        payload = json.loads(response["body"].read())
        text = payload["content"][0]["text"]
        result = parse_json_response(text)
        if not isinstance(result, list):
            raise RuntimeError("Bedrock returned non-array JSON")
        return result


def get_extractor(provider: str) -> GeminiExtractor | BedrockExtractor:
    if provider == "bedrock":
        return BedrockExtractor()
    return GeminiExtractor()


def _parse_record_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def normalize_extraction(ext: dict) -> dict:
    if not isinstance(ext, dict):
        ext = {}
    return {
        "pain_points": ext.get("pain_points") or [],
        "objections": ext.get("objections") or [],
        "use_cases": ext.get("use_cases") or [],
        "icp": ext.get("icp") or {},
        "funnel_stage": ext.get("funnel_stage") or "consideration",
        "confidence_score": round(float(ext.get("confidence_score") or 0.5), 2),
        "source_id": str(ext.get("source_id") or "").strip(),
        "embedding_text": str(ext.get("embedding_text") or "").strip(),
        "record_date": _parse_record_date(ext.get("record_date")),
    }


def build_signal_row(
    source: str,
    raw_path: Path,
    row_idx: int,
    raw_row: dict,
    raw_text: str,
    ext: dict,
) -> dict:
    normalized = normalize_extraction(ext)

    source_id = (
        normalized["source_id"]
        or str(raw_row.get("id") or raw_row.get("hs_object_id") or raw_row.get("meetingId") or f"{source}-{row_idx}")
    )

    return {
        "source": source,
        "source_id": source_id,
        "source_url": f"file://seed/{raw_path.name}#{row_idx}",
        "raw_text": raw_text,
        "pain_points": normalized["pain_points"],
        "objections": normalized["objections"],
        "use_cases": normalized["use_cases"],
        "icp": normalized["icp"],
        "funnel_stage": normalized["funnel_stage"],
        "confidence_score": normalized["confidence_score"],
        "embedding_text": normalized["embedding_text"],
        "record_date": normalized["record_date"],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def process_source_file(
    path: Path,
    extractor: GeminiExtractor | BedrockExtractor,
    limit: int | None,
) -> tuple[list[dict], list[dict]]:
    source = path.stem
    raw_records = load_source_records(path)
    if limit is not None:
        raw_records = raw_records[:limit]

    batches = make_batches(raw_records)
    print(f"[{source}] {len(raw_records)} raw rows -> {len(batches)} batch(es)")

    records: list[dict] = []
    errors: list[dict] = []

    for batch_num, batch in enumerate(batches, 1):
        texts = [text for _, _, text in batch]
        try:
            extractions = extractor.extract_batch(texts, source)
            while len(extractions) < len(batch):
                extractions.append({})

            for (row_idx, raw_row, raw_text), ext in zip(batch, extractions):
                records.append(build_signal_row(source, path, row_idx, raw_row, raw_text, ext))

            print(
                f"  batch {batch_num}/{len(batches)} OK "
                f"({len(batch)} records, {sum(len(t) for t in texts):,} chars)"
            )
        except Exception as exc:
            errors.append({"source": source, "batch": batch_num, "error": str(exc)})
            print(f"  batch {batch_num}/{len(batches)} FAILED: {exc}")

        if batch_num < len(batches):
            time.sleep(API_DELAY_S)

    return records, errors


def main() -> None:
    args = parse_args()
    load_dotenv()

    provider = get_provider(args.provider)
    extractor = get_extractor(provider)
    source_files = get_source_files(args.source)

    print(f"Provider: {provider}")
    if provider == "gemini":
        print(f"Model: {os.getenv('LOCAL_GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}")
    else:
        print(f"Model: {os.getenv('BEDROCK_MODEL_ID', DEFAULT_BEDROCK_MODEL)}")
    print(f"Raw dir: {RAW_DIR}")
    print("Sources:")
    for path in source_files:
        print(f"  - {path.name}")
    print()

    all_records: list[dict] = []
    all_errors: list[dict] = []

    for path in source_files:
        records, errors = process_source_file(path, extractor, args.limit)
        all_records.extend(records)
        all_errors.extend(errors)
        print()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)

    print(f"OK {len(all_records)} records -> {OUTPUT_PATH}")
    if all_errors:
        print(f"FAILED batches: {len(all_errors)}")
        for error in all_errors:
            print(f"  {error}")


if __name__ == "__main__":
    main()
