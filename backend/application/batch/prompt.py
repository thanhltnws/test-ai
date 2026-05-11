import json

_BATCH_TEMPLATE = """\
You are an AI analyst for a B2B software company. \
Below is aggregated customer insight data from today's batch run.

=== STRUCTURED DATA (SQL aggregates from Aurora) ===
{sql_context}

=== SEMANTIC CONTEXT (top matching chunks from pgvector semantic search) ===
{vector_context}

Analyze the combined data above and return ONLY valid JSON (no markdown, no explanation) \
with exactly these 4 keys:

{{
  "pain_points_summary": {{
    "top_items": [
      {{"item": "...", "count": N, "insight": "one-sentence interpretation"}}
    ],
    "summary": "2-3 sentence narrative about recurring pain themes, grounded in both SQL counts and semantic patterns"
  }},
  "funnel_distribution": {{
    "stages": [{{"stage": "...", "count": N, "pct": 0.0}}],
    "summary": "2-3 sentence interpretation of funnel health and drop-off risk"
  }},
  "icp_narrative": {{
    "top_segments": [
      {{"sector": "...", "company_size": "...", "deal_size": "...", "region": "...", "count": N}}
    ],
    "narrative": "3-4 sentence ICP profile describing the ideal customer based on top segments"
  }},
  "recommendations": {{
    "sales": ["actionable recommendation 1", "actionable recommendation 2"],
    "marketing": ["actionable recommendation 1", "actionable recommendation 2"],
    "summary": "1-2 sentences on overall strategic direction"
  }}
}}

Rules:
- pain_points_summary.top_items: include all items from SQL data, sorted by count desc
- funnel_distribution.stages: preserve exact counts and pct from SQL input
- icp_narrative.top_segments: top 5 segments by count from SQL input
- recommendations: 3-5 items each, grounded in both SQL aggregates and semantic context
- Do NOT invent data not present in the input"""


def build_batch_prompt(
    sql_context: dict,
    vector_context: list[dict],
    period: str = "daily",
) -> str:
    vector_section = (
        json.dumps(vector_context, indent=2, ensure_ascii=False)
        if vector_context
        else "(no vector data available - pgvector returned no semantic chunks)"
    )
    return _BATCH_TEMPLATE.format(
        period=period,
        sql_context=json.dumps(sql_context, indent=2, ensure_ascii=False),
        vector_context=vector_section,
    )
