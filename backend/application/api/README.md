# GET /insights — API Reference

Returns pre-computed batch results from the `insights` table.

---

## Query Parameters

| Param    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `period` | string | No       | `weekly` · `monthly` · `quarterly` · `yearly` |
| `date`   | string | No       | Any ISO date (`YYYY-MM-DD`) that falls within the desired period |
| `market` | string | No       | `vietnam` · `japan` · `korea` · `international` |

**Behaviour:**

| `period` | `date` | `market` | Returns |
|----------|--------|----------|---------|
| omitted  | omitted | omitted  | Latest aggregate snapshot (all markets) |
| provided | omitted | omitted  | Latest aggregate for that period type |
| provided | provided | omitted | Aggregate snapshot for the period containing `date` |
| any      | any    | provided | Same as above, but scoped to that market only |

Rules:
- `date` without `period` → `400`
- `date` must be `YYYY-MM-DD` — the backend snaps it to the correct `period_start` automatically
- `market` is independent of `period`/`date` — can be combined freely

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

Typical flow for a Weekly/Monthly/Quarterly/Yearly + Market selector:

```
1. Page load (no selection yet)
   GET /insights?period=monthly
   → returns latest monthly aggregate (all markets)
   → use period_start from response to initialise the date picker

2. User navigates to a specific period
   GET /insights?period=monthly&date=2026-04-01
   GET /insights?period=quarterly&date=2026-01-01
   GET /insights?period=weekly&date=2026-05-11

3. User filters by market
   GET /insights?period=monthly&date=2026-05-01&market=vietnam
   GET /insights?period=monthly&date=2026-05-01&market=japan

4. User switches granularity (e.g. Monthly → Quarterly)
   GET /insights?period=quarterly&market=vietnam
   → latest quarterly for Vietnam, reset the date picker

5. User clears market filter (back to aggregate)
   GET /insights?period=quarterly
   → aggregate (market param omitted = all markets)
```

---

## Response Shape

```jsonc
{
  "period":       "monthly",
  "period_start": "2026-05-01",
  "period_end":   "2026-05-31",
  "computed_at":  "2026-05-16T08:30:00+00:00",
  "market":       "vietnam",   // null when no market filter was applied

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
| `400` | `market` not in `vietnam / japan / korea / international` |
| `400` | `date` provided without `period` |
| `400` | `date` is not a valid `YYYY-MM-DD` string |
| `404` | Path other than `/insights` |

---

## Examples

```bash
# Latest aggregate (all markets)
curl "$API/insights"

# Latest monthly aggregate
curl "$API/insights?period=monthly"

# May 2026, all markets
curl "$API/insights?period=monthly&date=2026-05-01"

# May 2026, Vietnam market only
curl "$API/insights?period=monthly&date=2026-05-01&market=vietnam"

# Latest quarterly, Japan market
curl "$API/insights?period=quarterly&market=japan"

# Specific week (snaps to Monday)
curl "$API/insights?period=weekly&date=2026-05-14&market=korea"

# All-markets aggregate, Q1
curl "$API/insights?period=quarterly&date=2026-01-01"
```

---

## Local Run

```bash
# Latest aggregate
python backend/application/api/handler.py

# period only
python backend/application/api/handler.py monthly

# period + date
python backend/application/api/handler.py monthly 2026-05-01

# period + date + market
python backend/application/api/handler.py monthly 2026-05-01 vietnam
python backend/application/api/handler.py quarterly 2026-04-01 japan
python backend/application/api/handler.py weekly 2026-05-14 korea
```
