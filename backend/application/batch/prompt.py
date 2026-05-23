import json
from datetime import date

_BATCH_TEMPLATE = """\
You are an AI analyst for a B2B software outsourcing company.
Below is customer signal data for the {granularity} period \
({period_start} to {period_end}){market_context}.

=== AGGREGATE STATS ===
Total signals: {total_signals}

Funnel distribution:
{funnel_lines}

ICP breakdown (top 10 segments):
{icp_lines}

=== RAW SIGNALS ({total_signals} records) ===
{signals_json}

Analyze the data above and return ONLY valid JSON (no markdown, no explanation) \
with exactly these 4 keys:

{{
  "pain_points_summary": {{
    "top_items": [
      {{"item": "...", "count": N, "insight": "một câu diễn giải bằng tiếng Việt"}}
    ],
    "summary": "2-3 câu tóm tắt tiếng Việt về các vấn đề lặp lại"
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
- All text fields (item, insight, summary, narrative, recommendations) must be written in Vietnamese
- pain_points_summary.top_items: identify recurring themes across signals; \
count = number of signals (not array items) that mention the theme; return top 8-10 sorted by count desc
- funnel_distribution.stages: preserve exact counts and pct from AGGREGATE STATS above
- icp_narrative.top_segments: top 5 segments by count from ICP breakdown above; use exact values
- recommendations: 3-5 items each, grounded in the signals
- Do NOT invent data not present in the input"""


def build_batch_prompt(
    sql_context: dict,
    granularity: str,
    period_start: date,
    period_end: date,
    market: str | None = None,
) -> str:
    market_context = f", {market} market" if market else ""

    funnel_lines = "\n".join(
        f"  {s['stage']}: {s['count']} ({s['pct']}%)"
        for s in sql_context.get("funnel_distribution", [])
    ) or "  (no data)"

    icp_lines = "\n".join(
        f"  {s['sector']}/{s['market']} {s['client_type']} {s['tech_maturity']} {s['deal_size']}: {s['count']}"
        for s in sql_context.get("icp_breakdown", [])
    ) or "  (no data)"

    signals_json = json.dumps(
        sql_context.get("signals", []),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return _BATCH_TEMPLATE.format(
        granularity=granularity,
        period_start=period_start,
        period_end=period_end,
        market_context=market_context,
        total_signals=sql_context["summary"]["total_signals"],
        funnel_lines=funnel_lines,
        icp_lines=icp_lines,
        signals_json=signals_json,
    )
