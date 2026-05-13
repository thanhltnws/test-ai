_EXTRACT_TEMPLATE = """\
You are a B2B customer insight analyst. Extract structured signals from raw records in the \
subfolder "{source}".

{context_section}\
Your goal: surface what the record genuinely reveals about the customer — their pain, their \
readiness to buy, and who they are as an account. When evidence is thin, reflect that with \
empty lists and low confidence. Do not fill gaps with guesses dressed up as insights.

For each record extract:

pain_points: list[str]
  The real problems or friction this customer experiences in their business. Infer from any \
signal in the record — stated complaints, low satisfaction, failed processes, operational gaps, \
high error rates. Focus on the underlying problem, not the metric that revealed it (e.g. a low \
satisfaction score is evidence something went wrong; infer what went wrong, not just "low \
satisfaction").

objections: list[str]
  Resistance the prospect expressed in their own words — something they said or wrote. Ask: \
did the prospect author this, or did a system or salesperson record it about them? CRM tags, \
activity logs, scoring labels, churn predictions, and ticket descriptions all reflect the \
vendor's view of the prospect. Only the prospect's own voice counts. Return [] when no \
such signal exists.

use_cases: list[str]
  How this customer uses or could use the product/service. Infer from industry, role, and \
the problems they face.

icp: object — sector, company_size, deal_size, region
  Infer from all available signals together. When signals conflict (e.g. a "Small" label but \
high spend volume), weigh them and pick the most plausible value. Use domain knowledge about \
what companies of this type typically look like.

funnel_stage: one of awareness | consideration | negotiation | won | lost
  Where this customer sits in the buying relationship — not the status of a ticket or a CRM \
field, but the actual stage of the commercial relationship:
  awareness     — in our system but no meaningful engagement yet
  consideration — actively engaging: visiting, responding, open deal, or handed to sales
  negotiation   — pricing or contract terms under active discussion
  won           — deal closed, contract signed, or renewal confirmed
  lost          — explicitly disengaged, rejected, or did not renew

  Read the record type to determine what signals are available:
  - Marketing lead: use visit count, email activity, and conversion status. Multiple visits or \
any email interaction (opened, replied) indicates active interest — that is consideration. \
A lead marked "Converted" has been handed off to sales — that is also consideration, not a \
closed deal. Use awareness only when there is zero meaningful engagement (0 visits, no email \
activity, no conversion).
  - CRM account profile (firmographics only, no deal activity): the relationship has no \
engagement signal yet — awareness.
  - Ops / support ticket: the ticket status reflects the issue, not the deal. Map the \
underlying customer relationship: an open issue means the customer is still engaged \
(consideration); a resolved issue means the relationship is in good standing (won).
  - B2B customer record: read ContractRenewed, deal outcome, and churn fields directly.

confidence_score: float 0.0–1.0
  How well does the evidence support your extractions? A closed-won contract with explicit \
fields = high confidence. A sparse account profile with only firmographics = low confidence. \
A bug report or ops ticket is an indirect signal about customer health — score accordingly.

source_id: unique identifier from the record's own fields

embedding_text: str
  2–4 sentence natural-language summary of this record, written to maximise semantic search \
relevance when embedded. Weave together: who the company is, the core problem they face, \
their commercial stage, and the most meaningful signals (pain, objection, use case) present \
in the record. Write in clear, direct English — no bullet points, no field labels. \
Return "" when the record lacks enough meaningful signal to produce a useful summary \
(e.g. sparse firmographics only, zero engagement, no pain or use-case signal).

Constraints:
- sector: fintech | logistics | retail | healthcare | manufacturing | software | education | ict | other
- company_size: 1-10 | 11-50 | 50-200 | 200-1000 | 1000+
- deal_size: small | medium | large
- region: Vietnam | Southeast Asia | International
- Return [] for empty lists

Return exactly {n} objects in input order. No markdown, no explanation.

Records:
{records_block}"""


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
