import json

_CHAT_TEMPLATE = """\
You are an AI assistant for an internal B2B sales and customer insights platform. \
Answer the user's question using ONLY the context provided below. \
Do not invent data, statistics, or source references not present in the context.

=== USER QUESTION ===
{question}

=== STRUCTURED CONTEXT (Aurora — aggregates across all insights) ===
{sql_aggregates}

=== RELEVANT INSIGHTS (Aurora — keyword-matched rows) ===
{sql_relevant}

=== SEMANTIC CONTEXT (pgvector — similar text chunks) ===
{vector_context}

Instructions:
- Answer the question directly and concisely, grounded in the context above.
- When citing a specific insight, reference its source_url.
- If the context does not contain enough information to answer confidently, say so explicitly.
- Do NOT invent numbers or source URLs.

Return ONLY valid JSON (no markdown, no explanation) with exactly this structure:
{{
  "answer": "your answer here",
  "references": [
    {{"title": "short descriptive title", "source_url": "exact source_url from context"}}
  ]
}}

The references array must contain only source_urls that appear in the context above. \
Maximum 5 references. Empty array if no specific sources were cited."""


def build_chat_prompt(
    question: str,
    sql_ctx: dict,
    vector_ctx: list[dict],
) -> str:
    aggregates = {
        "total_insights": sql_ctx.get("total_insights", 0),
        "avg_confidence": sql_ctx.get("avg_confidence", 0),
        "top_pain_points": sql_ctx.get("top_pain_points", []),
        "top_use_cases": sql_ctx.get("top_use_cases", []),
        "funnel_distribution": sql_ctx.get("funnel_distribution", []),
    }

    relevant = sql_ctx.get("relevant_insights", [])
    relevant_section = (
        json.dumps(relevant, indent=2, ensure_ascii=False)
        if relevant
        else "(no keyword-matched insights found)"
    )

    vector_section = (
        json.dumps(vector_ctx, indent=2, ensure_ascii=False)
        if vector_ctx
        else "(pgvector not yet available — insight_embedding table not created)"
    )

    return _CHAT_TEMPLATE.format(
        question=question,
        sql_aggregates=json.dumps(aggregates, indent=2, ensure_ascii=False),
        sql_relevant=relevant_section,
        vector_context=vector_section,
    )
