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

=== INSIGHTS (PRIMARY — pre-computed summaries) ===
{insight_section}

=== SIGNALS (EVIDENCE — granular raw signals) ===
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
            parts.append(f"{header}\n{c['embedding_text'] or ''}")
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

    return _TEMPLATE.format(
        system=_SYSTEM,
        insight_section=insight_section,
        signal_section=signal_section,
        history_block=history_block,
        question=question,
    )
