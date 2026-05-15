_CLASSIFY_TEMPLATE = """\
You are analyzing files inside a data subfolder for a B2B customer insight pipeline.

File list and sample content:
{file_summaries}

Classify each file as either:
- "context": reference, schema, dictionary, or lookup data that describes or enriches other data
- "data": records containing actual customer/business information to extract insights from

Return ONLY valid JSON, no markdown:
{{"context_files": ["filename1", ...], "data_files": ["filename2", ...]}}"""


_EXTRACT_TEMPLATE = """\
You are extracting B2B customer insight signals from records in a subfolder named "{source}".

{context_section}
For each record below, extract:
- pain_points: list[str] — specific problems, friction, frustrations
- objections: list[str] — reasons not to buy, hesitations, churn risk signals
- use_cases: list[str] — how the product/service is or could be used
- icp: object — sector, company_size, deal_size, region (infer from context)
- funnel_stage: one of awareness | consideration | negotiation | won | lost
- confidence_score: float 0.0–1.0
- source_id: a unique identifier you pick from the record's own fields (e.g. ID column, name, or index)
- embedding_text: string - concise natural-language summary of the whole record for semantic search
- record_date: string (YYYY-MM-DD) — the most semantically relevant date in the record (e.g. close_date, engage_date, LastRenewalDate, created_at, issue_date, submission_date). Return null if the record contains no date field.

Rules:
- Return [] for empty lists; default funnel_stage to "consideration" if unclear
- funnel_stage MUST follow explicit stage/status fields first: CLOSED_WON or WON → "won"; CLOSED_LOST or LOST → "lost"; ignore sentiment of note content when explicit stage is present
- embedding_text must be natural language, not flattened JSON or key-value dumps
- embedding_text should summarize the meaningful customer/business signal, including pain points, objections, use cases, ICP, and funnel stage when available
- Set embedding_text to "" if the record does not contain enough meaningful signal for semantic search
- record_date must be exactly YYYY-MM-DD format or null — no other format accepted
- sector choices: fintech | logistics | retail | healthcare | manufacturing | software | education | ict | other
- company_size: 1-10 | 11-50 | 50-200 | 200-1000 | 1000+
- deal_size: small | medium | large
- region: Vietnam | Southeast Asia | International

Return ONLY a JSON array of exactly {n} objects in input order. No markdown, no explanation.

Records:
{records_block}"""


def build_classify_prompt(file_summaries: str) -> str:
    return _CLASSIFY_TEMPLATE.format(file_summaries=file_summaries)


def build_extract_prompt(
    texts: list[str],
    source: str,
    context_content: str,
) -> str:
    context_section = (
        f"Context / reference data from this subfolder:\n{context_content}\n"
        if context_content.strip()
        else ""
    )
    records_block = "\n\n".join(
        f"[Record {i + 1}]\n{t}" for i, t in enumerate(texts)
    )
    return _EXTRACT_TEMPLATE.format(
        source=source,
        context_section=context_section,
        n=len(texts),
        records_block=records_block,
    )
