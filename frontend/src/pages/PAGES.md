# Pages

## Dashboard (`Dashboard.tsx`)

Main insight overview page. Fetches `DashboardInsights` on mount and on filter changes.

### State

| State | Type | Purpose |
|---|---|---|
| `period` | `PeriodType` | Applied period type (`weekly`/`monthly`/`quarterly`/`yearly`) |
| `periodAnchor` | `string` | Applied period start date (ISO `YYYY-MM-DD`) |
| `market` | `string` | Applied market filter (`''` = all markets) |
| `draftPeriod/draftAnchor/draftMarket` | same types | Buffered values before Apply is clicked |
| `data` | `SummaryData \| null` | Fetched summary |
| `recs` | `RecommendationsData \| null` | Fetched recommendations |
| `loading / error / noData` | boolean/string | UI states |
| `retryTick` | `number` | Incremented to trigger retry on error |
| `labelTooltip` | `{ item, x, y } \| null` | Drives the floating tooltip shown when hovering Y-axis labels in the pain points chart |

### Key helpers

- `getPeriodOptions(period)` — generates dropdown options (12 months / 8 quarters / 5 years back from today). Deduplicates by anchor value.
- `getPeriodStart(period, isoDate)` — normalizes a date to its period's start date.
- `getPeriodLabel(period, isoDate)` — human-readable label (e.g. "May 2026", "Q2 2026", "2026").
- `dedupedPainPoints` (useMemo) — merges duplicate pain point labels, caps at 8, truncates labels to 48 chars.

### Layout order (top → bottom)

1. **Header** — title + filter bar (period type select → period select → market select → Apply button)
2. **No-data banner** — shown when API returns empty period
3. **AI Recommendations card** — 2-column grid (Sales / Marketing), numbered items
4. **Funnel + Pain Points row** — `grid 1fr 1fr`
   - Funnel: `PieChart` donut + `funnel_summary` callout (blue left-border box)
   - Pain Points: `BarChart` horizontal bars with custom tooltip showing `insight` field. "Hover for insight" pill badge in header. Tooltip triggers on both the bar AND the Y-axis label text (via `onMouseEnter/Move/Leave` on the custom SVG tick). The label tooltip is a `position: fixed` div driven by `labelTooltip` state `{ item, x, y }` — positioned at cursor coordinates.
5. **ICP card** — `icp_narrative` purple callout + responsive card grid `minmax(200px, 1fr)` (one card per segment, sorted by count desc). Each card shows: sector name + rank badge (`#1`, `#2`…), labeled metadata rows (Employees / Deal size / Region), count + "deals" separated by a divider. Rank #1 card has a blue left border accent.

### Color constants

```typescript
const FUNNEL_COLORS: Record<string, string> = {
  awareness: '#93c5fd', consideration: '#60a5fa',
  negotiation: '#3b82f6', won: '#16a34a', lost: '#ef4444',
}
```

ICP segment cards use `--accent` (`#2563eb`) for the count number and `#eff6ff` pill badges — no per-sector color map.

---

## Chat (`Chat.tsx`)

RAG chatbox with persistent session history stored in `localStorage`.

### State

| State | Purpose |
|---|---|
| `messages` | Current conversation (`ChatMessage[]`) |
| `input` | Controlled textarea value |
| `loading` | Shows "Đang xử lý..." bubble while waiting for API |
| `activeSessionId` | ID of the session being edited (null = new chat) |
| `sidebarOpen` | Toggles right panel (history + related insights) |

### Send flow

```
send(question)
  → append user message to messages
  → sendChat(question, messages.slice(-6))   ← last 6 messages as history context
    → on success: append assistant message
      → if activeSessionId: updateSession()
      → else: createSession() → setActiveSessionId()
    → on error: append error message as assistant bubble
```

History limit: last 6 messages sent as context to avoid token bloat. See `messages.slice(-6)` in `Chat.tsx:58`.

### Right sidebar

Split into two halves:
- **Top — History**: lists all `ChatSession[]` from `useChatHistory`. Click to restore, × to delete.
- **Bottom — Related Insights**: shows `references` from the last assistant message (title + URL). Empty state shown otherwise.

### Suggested questions

Hardcoded in `SUGGESTED` array at top of file. Rendered as clickable buttons when `messages.length === 0`.

### Markdown rendering

Assistant messages are rendered with `react-markdown`. Custom components override `p`, `ul`, `ol`, `li`, `strong`, `code`, `pre` to apply inline styles.

---

## Analysis (`Analysis.tsx`)

Static informational page. No API calls, no state.

Content is defined in two data arrays at the top of the file:

- `BREAKS` — 3 "break problems" cards (data fragmentation, normalization, insight generation), each with a colored left border, quote, body text, and optional highlight box.
- `SCOPE_ITEMS` — 2 items explaining AI's role and how this differs from standard RAG.

Uses local `card`, `sectionLabel`, `quote`, `body`, `highlight` style constants (defined in the file, not shared).
