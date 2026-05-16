# GET /insights — API Reference

Returns pre-computed batch results from the `insights` table.

---

## Query Parameters

| Param    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `period` | string | No       | `weekly` · `monthly` · `quarterly` · `yearly` |
| `date`   | string | No       | Any ISO date (`YYYY-MM-DD`) that falls within the desired period |

**Behaviour:**

| `period` | `date` | Returns |
|----------|--------|---------|
| omitted  | omitted | Latest snapshot across all period types |
| provided | omitted | Latest snapshot for that period type |
| provided | provided | Snapshot for the period containing `date` |

Rules:
- `date` without `period` → `400`
- `date` must be `YYYY-MM-DD` — the backend snaps it to the correct `period_start` automatically

---

## How the `date` param works

Pass **any date that falls within the period you want**. The backend resolves it:

| `period`    | `date` example | Resolved `period_start` |
|-------------|----------------|-------------------------|
| `weekly`    | `2026-05-14`   | `2026-05-11` (Monday of that week) |
| `monthly`   | `2026-05-14`   | `2026-05-01` |
| `quarterly` | `2026-05-14`   | `2026-04-01` (Q2 starts Apr 1) |
| `yearly`    | `2026-05-14`   | `2026-01-01` |

> **Frontend tip:** For a period dropdown, store `period_start` from the response and pass it back as `date` on the next request — it round-trips cleanly since `period_start` is always the first day of the period.

---

## Dashboard dropdown pattern

Typical flow for a Weekly/Monthly/Quarterly/Yearly selector:

```
1. Page load (no selection yet)
   GET /insights?period=monthly
   → returns latest monthly data
   → use period_start from response to initialise the date picker

2. User navigates to a specific period
   GET /insights?period=monthly&date=2026-04-01   ← first day of Apr
   GET /insights?period=quarterly&date=2026-01-01 ← first day of Q1
   GET /insights?period=weekly&date=2026-05-11    ← any Monday

3. User switches granularity (e.g. Monthly → Quarterly)
   GET /insights?period=quarterly
   → latest quarterly, reset the date picker
```

---

## Response Shape

```jsonc
{
  "period":       "monthly",
  "period_start": "2026-05-01",
  "period_end":   "2026-05-31",
  "computed_at":  "2026-05-16T08:30:00+00:00",

  "funnel_distribution": { /* LLM payload */ },
  "pain_points_summary": { /* LLM payload */ },
  "icp_narrative":       { /* LLM payload */ },
  "recommendations":     { /* LLM payload */ }
}
```

If no data exists for the requested period, all metadata fields are `null` and no `result_type` keys are present — **not a 404**.

---

## Error Responses

| HTTP  | Condition |
|-------|-----------|
| `400` | `period` not in `weekly / monthly / quarterly / yearly` |
| `400` | `date` provided without `period` |
| `400` | `date` is not a valid `YYYY-MM-DD` string |
| `404` | Path other than `/insights` |

---

## Examples

```bash
# Latest (default load)
curl "$API/insights"

# Latest monthly
curl "$API/insights?period=monthly"

# Specific month — pass any date in May
curl "$API/insights?period=monthly&date=2026-05-01"

# Specific week — pass any date in the week (snaps to Monday)
curl "$API/insights?period=weekly&date=2026-05-14"

# Specific quarter — pass any date in Q1
curl "$API/insights?period=quarterly&date=2026-01-15"

# Specific year
curl "$API/insights?period=yearly&date=2026-01-01"
```

---

## Local Run

```bash
# Latest
python backend/application/api/handler.py

# With period + date
python backend/application/api/handler.py monthly 2026-05-01
python backend/application/api/handler.py weekly 2026-05-14
python backend/application/api/handler.py quarterly 2026-04-01
python backend/application/api/handler.py yearly 2026-01-01
```
