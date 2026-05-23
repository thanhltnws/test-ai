_FEW_SHOT_EXAMPLES = """\
Examples — correct extraction for three representative record types:

[Example 1 — CRM deal record, Korea]
company: Seoul Digital Partners
industry: fintech
deal_stage: contract_sent
amount: 85000
last_activity: 2024-11-20
employees: 320
notes: We need this integrated with our legacy core banking system within 90 days or we miss \
the regulatory deadline. The price is manageable but the timeline worries us.

→ {"pain_points":["Legacy core banking integration required under 90-day regulatory deadline"],\
"objections":["Timeline worries us — 90-day integration window is too tight"],\
"use_cases":["Core banking integration","Regulatory compliance workflow"],\
"deal_size":"large","client_type":"corporate","tech_maturity":"semi-tech",\
"funnel_stage":"negotiation","confidence_score":0.87,"source_id":"seoul-digital-partners",\
"source_url":"https://example.com/twenty_crm/seoul-digital-partners",\
"embedding_text":"Seoul Digital Partners (320-person fintech, Korea) needs legacy core banking \
integration within 90 days due to a regulatory deadline. Customer stated: 'The price is manageable \
but the timeline worries us.' Deal at contract stage, ~$85K.",\
"record_date":"2024-11-20","market":"korea"}

[Example 2 — Support ticket, Japan]
id: 8821
subject: CSV export encoding error — Japanese characters
status: open
description: Export function breaks on records with full-width Japanese characters \
(Shift-JIS vs UTF-8 mismatch). Affects Osaka branch only.
created_on: 2025-01-08

→ {"pain_points":["CSV export fails on Japanese character encoding (Shift-JIS vs UTF-8)",\
"Data export disruption for Osaka branch"],\
"objections":[],\
"use_cases":["Data export for Japanese-language records","Multi-encoding support for regional offices"],\
"deal_size":"medium","client_type":"corporate","tech_maturity":"semi-tech",\
"funnel_stage":"consideration","confidence_score":0.52,"source_id":"8821",\
"source_url":"https://example.com/redmine/8821",\
"embedding_text":"CSV export fails on full-width Japanese characters due to Shift-JIS vs UTF-8 \
mismatch. Affects Osaka branch only. Status: open.",\
"record_date":"2025-01-08","market":"japan"}

[Example 3 — Prospect email, International]
from: procurement@globallogistics.com
subject: Re: Proposal — AI Insight Platform
body: Our IT team is worried about data residency — we cannot store customer data outside \
Vietnam per internal policy. Also, the 6-month onboarding seems long; our previous vendor \
did it in 8 weeks. Still evaluating two other vendors.
receivedDateTime: 2025-02-14

→ {"pain_points":["Data residency constraint — no offshore data storage allowed",\
"Onboarding timeline longer than market alternatives"],\
"objections":["Cannot store data outside Vietnam per internal policy",\
"6-month onboarding is too long — previous vendor delivered in 8 weeks"],\
"use_cases":["AI customer insight platform","Sales and procurement analytics"],\
"deal_size":"large","client_type":"corporate","tech_maturity":"technical",\
"funnel_stage":"consideration","confidence_score":0.81,"source_id":"globallogistics-re-proposal",\
"source_url":"https://example.com/outlook_email/globallogistics-re-proposal",\
"embedding_text":"Procurement at globallogistics.com: 'We cannot store customer data outside \
Vietnam per internal policy.' Also: '6-month onboarding seems long; our previous vendor did it \
in 8 weeks.' Still evaluating two other vendors.",\
"record_date":"2025-02-14","market":"international"}
"""

_EMBEDDING_TEXT_INSTRUCTION = """\
  A grounded evidence text for semantic retrieval, not a free-form narrative summary.

  Purpose:
  - Capture the most retrieval-useful customer/business signal from this record.
  - Preserve the original meaning and wording as closely as possible.
  - Reduce noise from raw metadata while avoiding invented synthesis.

  How to write it:
  - Write 2–6 sentences in clear English.
  - Prefer customer-stated or record-explicit facts over interpretation.
  - Reuse important wording from the record when possible, especially for pain points, \
objections, blockers, requirements, timelines, or compliance constraints.
  - Include: who the customer/account is · the main problem/requirement/blocker · \
objection or risk if explicitly present · use case if clearly supported · \
commercial or delivery stage only if directly evidenced.
  - Keep useful specifics: named systems, compliance terms, deadlines, required integrations, \
or quantified constraints when they appear in the record.
  - Remove low-signal metadata, filler, greetings, internal admin text, and generic wording.

  Hard rules:
  - Do not invent facts not supported by the record.
  - Do not add sales narrative or strategic interpretation.
  - Do not merge multiple weak guesses into one confident sentence.
  - Do not include field labels, JSON-like formatting, or key-value dumps.
  - Do not use vendor-side phrasing or opinion unless the record clearly supports it.

  Return "" when the record has no meaningful customer/business signal, is mostly operational \
noise, or the usable evidence is too weak to form a reliable retrieval text."""

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

sector: one of fintech | logistics | retail | healthcare | manufacturing | software | education | ict | other
  Infer from company/industry context; map any unlisted industry to "other".

deal_size: one of small | medium | large
  Estimated deal value. Infer from company size, amount fields, team size, or project scope. \
When signals conflict, weigh them and pick the most plausible value.

client_type: one of individual | startup | corporate
  individual — solo buyer or 1-2 person team; startup — early-stage company with informal \
process; corporate — established organisation with budget owners and approval chain.

tech_maturity: one of non-tech | semi-tech | technical
  non-tech needs full guidance on requirements; technical can define specs and review code. \
Infer from how the customer communicates, what they ask for, and their role.

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

source_url: str
  If a full http/https URL is explicitly present in the record, use it exactly. Otherwise: \
for sources that have external record URLs (CRM deals, issue trackers), construct a fictional \
demo URL: https://example.com/{{source}}/{{source_id}}. For email, form, or ops note sources, \
return null when no explicit URL is present in the record.

embedding_text: str
{embedding_text_instruction}

record_date: string (YYYY-MM-DD)
  The most semantically relevant date in the record — e.g. close_date, engage_date, \
LastRenewalDate, created_at, issue_date, submission_date, timestamp. \
Return null if the record contains no date field.

market: one of international | korea | japan | vietnam
  The specific target market of this customer or deal.
  vietnam      — customer or deal is based in / targeting Vietnam
  korea        — customer or deal is based in / targeting South Korea
  japan        — customer or deal is based in / targeting Japan
  international — any other market not specifically vietnam, korea, or japan
  Infer from company name, language of records, country/region fields, domain, or \
explicit geographic mentions. When the record provides no usable signal, return \
"international" as the default.

Constraints:
- market: international | korea | japan | vietnam
- sector: fintech | logistics | retail | healthcare | manufacturing | software | education | ict | other
- deal_size: small | medium | large
- client_type: individual | startup | corporate
- tech_maturity: non-tech | semi-tech | technical
- Return [] for empty lists
- record_date must be exactly YYYY-MM-DD format or null — no other format accepted

{few_shot_section}\
Return exactly {n} objects in input order. No markdown, no explanation.

Records:
{records_block}"""

_RETRY_PREAMBLE = """\
The following records had low extraction confidence on first pass. Re-examine each record \
carefully — look for implicit signals, infer from context, and consider what the record type \
reveals about the customer relationship. Prioritise evidence over assumptions, but do not \
leave fields empty when the record genuinely supports an inference.

"""


def build_extract_prompt(
    texts: list[str],
    source: str,
    context_content: str,
    include_examples: bool = True,
) -> str:
    context_section = (
        f"Context / reference data from this subfolder:\n{context_content}\n"
        if context_content.strip()
        else ""
    )
    few_shot_section = _FEW_SHOT_EXAMPLES + "\n" if include_examples else ""
    records_block = "\n\n".join(
        f"[Record {i + 1}]\n{t}" for i, t in enumerate(texts)
    )
    return _EXTRACT_TEMPLATE.format(
        source=source,
        context_section=context_section,
        few_shot_section=few_shot_section,
        embedding_text_instruction=_EMBEDDING_TEXT_INSTRUCTION,
        n=len(texts),
        records_block=records_block,
    )


def build_retry_prompt(
    texts: list[str],
    source: str,
) -> str:
    return _RETRY_PREAMBLE + build_extract_prompt(texts, source, "", include_examples=True)
