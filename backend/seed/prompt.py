_TEMPLATE = """\
You are an AI assistant extracting B2B customer insight signals from sales, support, and project notes.

Return ONLY a JSON object — no markdown, no explanation.

{{
  "pain_points": ["<specific problem or frustration>"],
  "objections": ["<reason hesitating to buy or proceed>"],
  "use_cases": ["<workflow or goal the customer wants to accomplish>"],
  "icp": {{
    "sector": "<fintech|logistics|retail|healthcare|manufacturing|software|other>",
    "company_size": "<1-10|11-50|50-200|200-1000|1000+>",
    "deal_size": "<small|medium|large>",
    "region": "<Vietnam|Southeast Asia|International>"
  }},
  "funnel_stage": "<awareness|consideration|negotiation|won|lost>",
  "confidence_score": <0.0 to 1.0>
}}

Rules:
- pain_points, objections, use_cases: return [] if none found in text
- icp: infer from available context; use "other" for sector and "International" for region if unclear
- funnel_stage: infer from context; default to "consideration" if unclear
- confidence_score: reflect how confident you are in the extraction quality (0 = very uncertain, 1 = very certain)

Source type: {source_hint}

Text:
{raw_text}"""


def build_extraction_prompt(raw_text: str, source_hint: str = "customer note") -> str:
    return _TEMPLATE.format(
        source_hint=source_hint,
        raw_text=raw_text[:2000],
    )
