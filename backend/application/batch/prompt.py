import json
from datetime import date

_BATCH_TEMPLATE = """\
You are an AI analyst for a B2B software outsourcing company.
Below is aggregated customer insight data for the {granularity} period \
({period_start} to {period_end}){market_context}.

=== STRUCTURED DATA (SQL aggregates from Aurora) ===
{sql_context}

=== SEMANTIC CONTEXT (top matching chunks from pgvector semantic search) ===
{vector_context}

Analyze the combined data above and return ONLY valid JSON (no markdown, no explanation) \
with exactly these 4 keys:

{{
  "pain_points_summary": {{
    "top_items": [
      {{"item": "...", "count": N, "insight": "một câu diễn giải bằng tiếng Việt"}}
    ],
    "summary": "2-3 câu tóm tắt tiếng Việt về các vấn đề lặp lại, dựa trên cả SQL counts và semantic patterns"
  }},
  "funnel_distribution": {{
    "stages": [{{"stage": "...", "count": N, "pct": 0.0}}],
    "summary": "2-3 câu tiếng Việt nhận xét sức khoẻ funnel và rủi ro drop-off"
  }},
  "icp_narrative": {{
    "top_segments": [
      {{"sector": "...", "market": "...", "client_type": "...", "tech_maturity": "...", "deal_size": "...", "count": N}}
    ],
    "narrative": "3-4 câu tiếng Việt mô tả ICP lý tưởng dựa trên các segment hàng đầu"
  }},
  "recommendations": {{
    "sales": ["khuyến nghị hành động 1 bằng tiếng Việt", "khuyến nghị hành động 2"],
    "marketing": ["khuyến nghị hành động 1 bằng tiếng Việt", "khuyến nghị hành động 2"],
    "summary": "1-2 câu tiếng Việt về định hướng chiến lược tổng thể"
  }}
}}

Rules:
- All narrative text fields (insight, summary, narrative, recommendations) must be written in Vietnamese
- pain_points_summary.top_items: include all items from SQL data, sorted by count desc
- funnel_distribution.stages: preserve exact counts and pct from SQL input
- icp_narrative.top_segments: top 5 segments by count from SQL input; use exact values from icp_breakdown
- recommendations: 3-5 items each, grounded in both SQL aggregates and semantic context
- Do NOT invent data not present in the input"""


def build_batch_prompt(
    sql_context: dict,
    vector_context: list[dict],
    granularity: str,
    period_start: date,
    period_end: date,
    market: str | None = None,
) -> str:
    market_context = f", {market} market" if market else ""
    vector_section = (
        json.dumps(vector_context, indent=2, ensure_ascii=False)
        if vector_context
        else "(no vector data available - pgvector returned no semantic chunks)"
    )
    return _BATCH_TEMPLATE.format(
        granularity=granularity,
        period_start=period_start,
        period_end=period_end,
        market_context=market_context,
        sql_context=json.dumps(sql_context, indent=2, ensure_ascii=False),
        vector_context=vector_section,
    )
