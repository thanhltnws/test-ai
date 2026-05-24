# ── intent prompt (pre-LLM: extract search parameters from user question) ──────

_INTENT_SCHEMA = (
    '{"market": null|"vietnam"|"japan"|"korea"|"international",'
    ' "sector": null|string,'
    ' "period": "weekly"|"monthly"|"quarterly"|"yearly",'
    ' "period_start": null|"YYYY-MM-DD",'
    ' "use_latest": false|true,'
    ' "result_type": null|"pain_points_summary"|"funnel_distribution"|"icp_narrative"|"recommendations",'
    ' "question_type": null|"summary",'
    ' "funnel_stage": null|"awareness"|"consideration"|"negotiation"|"won"|"lost",'
    ' "needs_citations": false|true,'
    ' "out_of_scope": false|true}'
)

_INTENT_PROMPT = """\
Today is {today}. Extract search intent from the user question below. Return ONLY valid JSON matching this schema:
{schema}

Rules:
- market: null if not mentioned
- sector: null if not mentioned; industry/domain string if clearly stated (e.g. "fintech", "healthcare")
- period: "monthly" if not mentioned
- period_start: ISO date (YYYY-MM-DD) for the start of the target period. Always compute — do not leave null for normal questions.
  "tuần này"/"this week" → Monday of current week
  "tuần trước"/"last week" → Monday of last week
  "tháng này"/"this month" → first day of current month
  "tháng trước"/"last month" → first day of last month
  "2 tháng trước" → first day of the month 2 months ago
  Named period: "Q1 2026" → "2026-01-01", "tháng 3 2026" → "2026-03-01", "2026" → "2026-01-01"
  No time reference at all → first day of last month
  null only if the time reference is structurally impossible to resolve
- use_latest: true ONLY for "gần đây", "mới nhất", "latest", "most recent"
- result_type: null if not clearly one of the four types. Mapping hints:
  pain/vấn đề/khó khăn/phàn nàn/complaint → pain_points_summary
  funnel/pipeline/conversion/tỷ lệ/lost/won/stage/drop-off → funnel_distribution
  ICP/ideal customer/khách mục tiêu/segment/profile → icp_narrative
  khuyến nghị/đề xuất/nên làm/action/recommendation → recommendations
- question_type: classify what kind of answer the user expects:
  "summary" → aggregated view, trend, pattern, overall situation
    (tóm tắt, nhìn chung, tình hình, xu hướng, thường gặp, phổ biến)
  null → open-ended, ambiguous, drill-down, or anything not clearly "summary"
- funnel_stage: null if not mentioned; one of the enum values if the question is about a specific stage
- needs_citations: true if user asks for specific sources, examples, or evidence
- out_of_scope: true if question is completely unrelated to B2B sales, customer signals, or internal platform data

Question: {question}"""


def intent_defaults() -> dict:
    return {
        "market": None,
        "sector": None,
        "period": "monthly",
        "period_start": None,
        "use_latest": False,
        "result_type": None,
        "question_type": None,
        "funnel_stage": None,
        "needs_citations": False,
        "out_of_scope": False,
    }


def build_intent_prompt(question: str, today: str) -> str:
    return _INTENT_PROMPT.format(schema=_INTENT_SCHEMA, today=today, question=question)


# ── chat prompt (answer LLM: build RAG context prompt) ────────────────────────

_SYSTEM = (
    "You are an AI analyst for an internal B2B sales and customer insights platform. "
    "Answer the user's question using ONLY the context provided. "
    "If the question is in Vietnamese, answer in Vietnamese. "
    "Do not invent data, statistics, or source references not present in the context. "
    "If INSIGHTS is marked [NO MATCHING DATA], explicitly state that data is not available "
    "for the requested period/market."
)

_TEMPLATE = """\
{system}

=== INSIGHTS ===
{insight_section}

=== SIGNALS ===
{signal_section}

{history_block}=== QUESTION ===
{question}

Return ONLY valid JSON (no markdown, no explanation):
{{"answer": "...", "references": [{{"title": "short title", "source_url": "source_url"}}]}}

References: use only source_urls from SIGNALS above. Empty array if no signals cited. Max 5."""

_TEMPLATE_SIGNALS_ONLY = """\
{system}

=== SIGNALS ===
{signal_section}

{history_block}=== QUESTION ===
{question}

Return ONLY valid JSON (no markdown, no explanation):
{{"answer": "...", "references": [{{"title": "short title", "source_url": "source_url"}}]}}

References: use only source_urls from SIGNALS above. Empty array if no signals cited. Max 5."""


def build_chat_prompt(
    question: str,
    insight_ctx: list[dict],
    signal_ctx: list[dict],
    history: list[dict] | None = None,
    flow: str = "B",
) -> str:
    if not insight_ctx:
        insight_section = "[NO MATCHING DATA]"
    else:
        parts = []
        for c in insight_ctx:
            header = f"[{c.get('result_type', '')} | {c.get('period', '')} | market={c.get('market') or 'all'}]"
            parts.append(f"{header}\n{c['embedding_text'] or '(summary not available)'}")
        insight_section = "\n\n".join(parts)

    if signal_ctx:
        parts = []
        for c in signal_ctx:
            url = c.get("source_url") or "n/a"
            header = (
                f"[{c.get('source', '')} | {c.get('funnel_stage', '')} | "
                f"score={c.get('score', '')}] url={url}"
            )
            lines = [header]
            if c.get("pain_points"):
                lines.append(f"pain_points: {', '.join(c['pain_points'])}")
            if c.get("objections"):
                lines.append(f"objections: {', '.join(c['objections'])}")
            if c.get("use_cases"):
                lines.append(f"use_cases: {', '.join(c['use_cases'])}")
            meta = " | ".join(filter(None, [c.get("market"), c.get("sector"), c.get("deal_size"), c.get("client_type"), c.get("tech_maturity")]))
            if meta:
                lines.append(f"meta: {meta}")
            if c.get("embedding_text"):
                lines.append(c["embedding_text"])
            parts.append("\n".join(lines))
        signal_section = "\n\n".join(parts)
    else:
        signal_section = "(no matching signals found)"

    history_block = ""
    if history:
        lines = ["=== CONVERSATION HISTORY ==="]
        for turn in history:
            role = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{role}: {turn['content']}")
        history_block = "\n".join(lines) + "\n\n"

    if flow == "C":
        return _TEMPLATE_SIGNALS_ONLY.format(
            system=_SYSTEM,
            signal_section=signal_section,
            history_block=history_block,
            question=question,
        )

    return _TEMPLATE.format(
        system=_SYSTEM,
        insight_section=insight_section,
        signal_section=signal_section,
        history_block=history_block,
        question=question,
    )
