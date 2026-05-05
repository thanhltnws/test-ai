"""
Read seed data from backend/seed/raw/, call Gemini to extract unified-table fields,
write output to backend/seed/data/unified_seed.json.

Usage:
    python backend/seed/generate.py
    python backend/seed/generate.py --jira 15 --crm 5
"""
import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai

sys.path.insert(0, str(Path(__file__).parent))
from prompt import build_extraction_prompt

# ── constants ────────────────────────────────────────────────────────────────

DEFAULT_JIRA_SAMPLE = 20
DEFAULT_CRM_SAMPLE  = 8
GEMINI_MODEL        = "gemini-1.5-flash"
API_DELAY_S         = 0.5          # polite delay between Gemini calls

_HERE         = Path(__file__).parent
RAW_DIR       = _HERE / "raw"
OUTPUT_PATH   = _HERE / "data" / "unified_seed.json"


# ── loaders ──────────────────────────────────────────────────────────────────

def load_jira_issues(limit: int) -> list[dict]:
    path = RAW_DIR / "ops" / "ofbiz_issues.json"
    with open(path, encoding="utf-8") as f:
        issues = json.load(f)["issues"]
    issues = [i for i in issues if len(i.get("description") or "") > 80]
    return random.sample(issues, min(limit, len(issues)))


def load_crm_pipeline(limit: int) -> list[dict]:
    crm_dir = RAW_DIR / "sales" / "sales_pipeline_crm"

    accounts: dict[str, dict] = {}
    with open(crm_dir / "accounts.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            accounts[row["account"]] = row

    with open(crm_dir / "sales_pipeline.csv", encoding="utf-8") as f:
        pipeline = list(csv.DictReader(f))

    sampled = random.sample(pipeline, min(limit, len(pipeline)))
    for row in sampled:
        row["_account_info"] = accounts.get(row.get("account", ""), {})
    return sampled


# ── text builders ─────────────────────────────────────────────────────────────

def build_jira_text(issue: dict) -> str:
    lines = [
        f"Issue type: {issue.get('issuetype', '')}",
        f"Priority: {issue.get('priority', '')}",
        f"Summary: {issue.get('summary', '')}",
        f"Description: {(issue.get('description') or '')[:1200]}",
    ]
    return "\n".join(l for l in lines if l.split(": ", 1)[1].strip())


def build_crm_text(row: dict) -> str:
    acc = row.get("_account_info", {})
    lines = [
        f"Account: {row.get('account', '')}",
        f"Industry / sector: {acc.get('sector', '')}",
        f"Employees: {acc.get('employees', '')}",
        f"Annual revenue: {acc.get('revenue', '')}",
        f"Product: {row.get('product', '')}",
        f"Deal stage: {row.get('deal_stage', '')}",
        f"Close value: {row.get('close_value', '')}",
        f"Engagement date: {row.get('engage_date', '')}",
    ]
    return "\n".join(l for l in lines if l.split(": ", 1)[1].strip())


# ── gemini call ───────────────────────────────────────────────────────────────

def call_gemini(raw_text: str, source_hint: str, model) -> dict:
    prompt = build_extraction_prompt(raw_text, source_hint)
    response = model.generate_content(prompt)
    text = response.text.strip()
    # Strip markdown code fences if Gemini wraps the output
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── row assembler ─────────────────────────────────────────────────────────────

def assemble_row(source: str, source_id: str, source_url: str,
                 raw_text: str, extraction: dict) -> dict:
    return {
        "source":           source,
        "source_id":        source_id,
        "source_url":       source_url,
        "raw_text":         raw_text,
        "pain_points":      extraction.get("pain_points") or [],
        "objections":       extraction.get("objections") or [],
        "use_cases":        extraction.get("use_cases") or [],
        "icp":              extraction.get("icp") or {},
        "funnel_stage":     extraction.get("funnel_stage") or "consideration",
        "confidence_score": round(float(extraction.get("confidence_score") or 0.5), 2),
        "ingested_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jira", type=int, default=DEFAULT_JIRA_SAMPLE)
    parser.add_argument("--crm",  type=int, default=DEFAULT_CRM_SAMPLE)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set in .env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        generation_config=genai.types.GenerationConfig(temperature=0.2),
    )

    records: list[dict] = []
    errors:  list[dict] = []

    # ── Jira issues ──────────────────────────────────────────────────────────
    print(f"Processing {args.jira} Jira issues …")
    for issue in load_jira_issues(args.jira):
        key = issue["key"]
        raw = build_jira_text(issue)
        url = f"https://issues.apache.org/jira/browse/{key}"
        try:
            ext = call_gemini(raw, "Jira support ticket", model)
            records.append(assemble_row("jira", key, url, raw, ext))
            print(f"  ✓ {key}")
        except Exception as exc:
            errors.append({"source_id": key, "error": str(exc)})
            print(f"  ✗ {key}: {exc}")
        time.sleep(API_DELAY_S)

    # ── CRM pipeline ─────────────────────────────────────────────────────────
    print(f"\nProcessing {args.crm} CRM pipeline records …")
    for row in load_crm_pipeline(args.crm):
        opp_id = row.get("opportunity_id", "")
        raw    = build_crm_text(row)
        url    = f"https://demo.twentycrm.io/objects/opportunities/{opp_id}"
        try:
            ext = call_gemini(raw, "CRM sales pipeline record", model)
            records.append(assemble_row("crm", opp_id, url, raw, ext))
            print(f"  ✓ {opp_id}")
        except Exception as exc:
            errors.append({"source_id": opp_id, "error": str(exc)})
            print(f"  ✗ {opp_id}: {exc}")
        time.sleep(API_DELAY_S)

    # ── write output ─────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"\n{len(records)} records → {OUTPUT_PATH}")
    if errors:
        print(f"{len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()
