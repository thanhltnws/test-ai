"""
Scan backend/seed/raw/ subfolders, let AI classify files (context vs data),
then extract unified insight records in token-aware batches.

Processes ALL records in every subfolder by default.
Use --limit to cap records per subfolder during development/testing.

Structure expected:
    raw/
      marketing/marketing_lead_scoring/   ← subfolder = unit of processing
      sales/sales_pipeline_crm/
      sales/sales_b2b_ict/
      ops/                                ← ops has no subfolder, treated directly

Usage:
    python backend/seed/generate.py                  # process everything
    python backend/seed/generate.py --limit 20       # test run, first 20 rows per subfolder
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_classify_prompt, build_extract_prompt

# ── constants ─────────────────────────────────────────────────────────────────

MAX_BATCH_CHARS    = 150_000   # ~37K tokens — aligned with transform/handler.py
MAX_BATCH_RECORDS  = 40        # 8192 output tokens / ~200 tokens per record
API_DELAY_S        = 5.0   # Gemini free tier: 15 RPM → min 4s between calls
CONTEXT_CHAR_LIMIT = 10_000    # chars of context file content sent per batch
MIN_ROW_TEXT_LEN   = 10        # drop rows shorter than this (truly empty rows)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

_HERE       = Path(__file__).parent
RAW_DIR     = _HERE / "raw"
OUTPUT_PATH = _HERE / "data" / "insights_seed.json"


# ── subfolder discovery ───────────────────────────────────────────────────────

def find_subfolders(raw_dir: Path) -> list[Path]:
    """
    Return leaf subfolders that contain data files.
    If a domain folder (marketing/sales/ops) has direct files, treat it as a subfolder too.
    """
    results = []
    for domain in sorted(raw_dir.iterdir()):
        if not domain.is_dir():
            continue
        subdirs = [p for p in domain.iterdir() if p.is_dir()]
        if subdirs:
            results.extend(sorted(subdirs))
        else:
            results.append(domain)  # ops/ has files directly
    return results


# ── file loading ──────────────────────────────────────────────────────────────

def read_file_as_text(path: Path, char_limit: int = 0) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not char_limit or len(text) <= char_limit:
            return text
        # Truncate at last newline so we don't cut mid-row (CSV) or mid-line (JSON)
        cut = text.rfind("\n", 0, char_limit)
        return text[: cut if cut > 0 else char_limit]
    except Exception:
        return ""


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
    elif path.suffix.lower() == ".csv":
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


# ── token-aware batching ──────────────────────────────────────────────────────

def make_batches(
    rows: list[tuple[str, dict]],
    context_len: int,
    max_batch_chars: int,
) -> list[list[tuple[str, dict, str]]]:
    """
    Split rows into batches so that:
      context_len + sum(len(text) for row in batch) <= max_batch_chars

    Context is sent with every batch so it counts against the budget each time.
    Text is precomputed once here and stored in the tuple to avoid recomputation.
    A single row that exceeds the remaining budget on its own is placed in its
    own batch (we cannot split within a single record).
    """
    batches: list[list[tuple[str, dict, str]]] = []
    current: list[tuple[str, dict, str]] = []
    current_chars = context_len  # context cost applies to every batch

    for fname, row in rows:
        text     = row_to_text(row)
        text_len = len(text)

        if current and (current_chars + text_len > max_batch_chars or len(current) >= MAX_BATCH_RECORDS):
            batches.append(current)
            current       = []
            current_chars = context_len  # reset, but context cost stays

        current.append((fname, row, text))
        current_chars += text_len

    if current:
        batches.append(current)

    return batches


# ── gemini helpers ────────────────────────────────────────────────────────────

def parse_json_response(response_text: str):
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def classify_files(files: list[Path], model) -> tuple[list[Path], list[Path]]:
    """Call 1: ask AI to classify files as context vs data."""
    file_names = [f.name for f in files]
    summaries  = []
    for p in files:
        sample = read_file_as_text(p, char_limit=500)
        if not sample:
            label = "(binary or unreadable — likely reference/dictionary file)"
            summaries.append(f"### {p.name}\n{label}")
        else:
            summaries.append(f"### {p.name}\n{sample}")

    prompt   = build_classify_prompt("\n\n".join(summaries))
    response = model.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    result   = parse_json_response(response.text)

    context_names = set(result.get("context_files", []))
    data_names    = set(result.get("data_files", []))

    # Warn about filenames AI invented that don't exist in the folder
    for name in context_names | data_names:
        if name not in file_names:
            print(f"  ⚠  classify returned unknown filename: '{name}' (ignored)")

    # Only keep names that actually exist
    context_files = [f for f in files if f.name in context_names]
    data_files    = [f for f in files if f.name in data_names]

    # Anything not classified → default to data, with a warning
    classified   = {f.name for f in context_files} | {f.name for f in data_files}
    unclassified = [f for f in files if f.name not in classified]
    if unclassified:
        print(f"  ⚠  unclassified files (defaulting to data): {[f.name for f in unclassified]}")
        data_files.extend(unclassified)

    return context_files, data_files


def extract_batch(
    texts: list[str],
    source: str,
    context_content: str,
    model,
) -> list[dict]:
    """Call 2+: extract unified records from a batch."""
    prompt   = build_extract_prompt(texts, source, context_content)
    response = model.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    result   = parse_json_response(response.text)
    if not isinstance(result, list):
        result = [result]
    # Pad with empty dicts if model returned fewer items than expected
    while len(result) < len(texts):
        result.append({})
    return result


# ── row assembler ─────────────────────────────────────────────────────────────

def assemble_row(source: str, source_id: str, source_url: str,
                 raw_text: str, ext: dict) -> dict:
    return {
        "source":           source,
        "source_id":        source_id,
        "source_url":       source_url,   # empty for seed; production ingest sets real URL
        "raw_text":         raw_text,
        "pain_points":      ext.get("pain_points") or [],
        "objections":       ext.get("objections") or [],
        "use_cases":        ext.get("use_cases") or [],
        "icp":              ext.get("icp") or {},
        "funnel_stage":     ext.get("funnel_stage") or "consideration",
        "confidence_score": round(float(ext.get("confidence_score") or 0.5), 2),
        "embedding_text":    str(ext.get("embedding_text") or "").strip(),
        "ingested_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── subfolder processor ───────────────────────────────────────────────────────

def process_subfolder(
    subfolder: Path,
    limit: int | None,
    max_batch_chars: int,
    model,
) -> tuple[list[dict], list[dict]]:
    source = subfolder.name
    files  = [
        f for f in sorted(subfolder.iterdir())
        if f.is_file() and f.suffix.lower() in (".csv", ".json", ".md", ".txt")
    ]
    if not files:
        print(f"  (no data files, skipping)")
        return [], []

    # ── Call 1: classify ──────────────────────────────────────────────────────
    print(f"  classify ({len(files)} files) …", end=" ", flush=True)
    try:
        context_files, data_files = classify_files(files, model)
        print(f"context={[f.name for f in context_files]}  data={[f.name for f in data_files]}")
    except Exception as exc:
        print(f"✗ classify failed: {exc}")
        return [], [{"source": source, "error": str(exc)}]

    time.sleep(API_DELAY_S)

    if not data_files:
        print(f"  (no data files after classification, skipping)")
        return [], []

    # ── Load context content (sent with every batch) ──────────────────────────
    context_parts = []
    for cf in context_files:
        text = read_file_as_text(cf, char_limit=CONTEXT_CHAR_LIMIT)
        if text:
            context_parts.append(f"[{cf.name}]\n{text}")
    context_content = "\n\n".join(context_parts)
    context_len     = len(context_content)

    # ── Load ALL data records ─────────────────────────────────────────────────
    all_rows: list[tuple[str, dict]] = []
    for df in data_files:
        for row in load_records(df):
            if len(row_to_text(row)) >= MIN_ROW_TEXT_LEN:
                all_rows.append((df.name, row))

    if not all_rows:
        print(f"  (no rows with enough content, skipping)")
        return [], []

    # --limit: first N rows for dev/test runs; None = process everything
    rows_to_process = all_rows[:limit] if limit else all_rows
    if limit and len(all_rows) > limit:
        print(f"  ⚠  --limit {limit}: processing {limit} of {len(all_rows)} rows")

    # ── Token-aware batching ──────────────────────────────────────────────────
    batches = make_batches(rows_to_process, context_len, max_batch_chars)
    print(f"  {len(rows_to_process)} rows → {len(batches)} batch(es)  "
          f"(context={context_len:,} chars, budget={max_batch_chars:,} chars/batch)")

    # ── Call 2+: extract in batches ───────────────────────────────────────────
    records:    list[dict] = []
    errors:     list[dict] = []
    global_idx: int        = 0  # absolute row index across all batches for stable source_id

    for batch_num, batch in enumerate(batches, 1):
        texts = [text for _, _, text in batch]  # precomputed in make_batches
        try:
            extractions = extract_batch(texts, source, context_content, model)
            for i, ((fname, _, text), ext) in enumerate(zip(batch, extractions)):
                sid = str(ext.get("source_id") or f"{fname}#{global_idx + i}")
                url = f"file://seed/{subfolder.relative_to(RAW_DIR).as_posix()}/{fname}#{global_idx + i}"
                records.append(assemble_row(source, sid, url, text, ext))
            print(f"  batch {batch_num}/{len(batches)} ✓  "
                  f"({len(batch)} records, {sum(len(t) for t in texts):,} chars)")
        except Exception as exc:
            errors.append({"source": source, "batch": batch_num, "error": str(exc)})
            print(f"  batch {batch_num}/{len(batches)} ✗  {exc}")

        global_idx += len(batch)
        time.sleep(API_DELAY_S)

    return records, errors


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="max rows per subfolder — omit to process all (use for test runs)",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set in .env")

    model = genai.Client(api_key=api_key)

    subfolders = find_subfolders(RAW_DIR)
    if not subfolders:
        sys.exit(f"No subfolders found in {RAW_DIR}")

    print(f"Found {len(subfolders)} subfolder(s):\n")
    for s in subfolders:
        print(f"  {s.relative_to(RAW_DIR)}")
    print()

    all_records: list[dict] = []
    all_errors:  list[dict] = []

    for i, subfolder in enumerate(subfolders, 1):
        print(f"[{i}/{len(subfolders)}] {subfolder.relative_to(RAW_DIR)}")
        recs, errs = process_subfolder(subfolder, args.limit, MAX_BATCH_CHARS, model)
        all_records.extend(recs)
        all_errors.extend(errs)
        print()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)

    print(f"✓ {len(all_records)} records → {OUTPUT_PATH}")
    if all_errors:
        print(f"✗ {len(all_errors)} error(s):")
        for e in all_errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()
