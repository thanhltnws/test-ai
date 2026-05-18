# API Layer (`lambdas.ts`)

Single file handling all backend communication. Switches between mock data and live Lambda calls based on `VITE_DATA_SOURCE`.

## Mode switch

```typescript
const dataSource = import.meta.env.VITE_DATA_SOURCE ?? 'mock'
const useLambdaData = dataSource === 'lambda'
```

Every exported async function checks `useLambdaData` and returns mock data immediately if false.

## Endpoint configuration

```typescript
lambdaEndpoints = {
  api:             joinUrl(VITE_API_LAMBDA_URL, VITE_API_INSIGHTS_PATH),      // GET insights
  chat:            joinUrl(VITE_CHAT_LAMBDA_URL, VITE_CHAT_PATH),             // POST chat
  insightsBuilder: joinUrl(VITE_INSIGHTS_BUILDER_LAMBDA_URL, VITE_INSIGHTS_BUILDER_PATH), // POST batch
}
```

`joinUrl(base, path)` trims trailing/leading slashes before joining.

## Auth

Token stored in localStorage under `VITE_AUTH_TOKEN_STORAGE_KEY` (default: `ai-insight-hub-auth-token`).

```typescript
getAuthToken(): string          // reads localStorage
setAuthToken(token: string): void  // writes or removes from localStorage
requireAuthHeaders()            // throws if no token; returns { Authorization: 'Bearer <token>' }
```

`requireAuthHeaders()` is called for mutating endpoints (`runBatch`, `sendChat`). The insights fetch (`fetchDashboardInsights`) does NOT require auth — it is a public GET.

## Exported functions

### `fetchDashboardInsights(filters?)`

```typescript
fetchDashboardInsights(filters?: DashboardFilters): Promise<DashboardInsights>
```

- Mock: returns `MOCK_DASHBOARD_INSIGHTS` synchronously (no network)
- Lambda: `GET lambdaEndpoints.api` with query params `period`, `date`, `market`
  - Response shape: `BeInsightResponse` → mapped via `toSummary()` + `toRecommendations()`

### `runBatch()`

```typescript
runBatch(): Promise<BatchRunResponse>
```

- Mock: returns `{ period_start: '2026-05-01', written: 0 }`
- Lambda: `POST lambdaEndpoints.insightsBuilder` with auth headers
- Triggers the batch insight generation pipeline on the backend

### `sendChat(question, history)`

```typescript
sendChat(question: string, history: ChatMessage[]): Promise<{ answer: string; references: Reference[] }>
```

- Mock: returns a hardcoded Vietnamese answer with 2 mock references
- Lambda: `POST lambdaEndpoints.chat` with `{ question, history }` + auth headers
  - Backend returns `{ answer: string, references: { title: string, source_url: string }[] }`
  - `source_url` is mapped to `url` in the returned `Reference` type

## Response mapping

`BeInsightResponse` (raw backend shape) → `DashboardInsights` (frontend shape):

```
raw.funnel_distribution.stages    → summary.funnel_distribution
raw.funnel_distribution.summary   → summary.funnel_summary
raw.icp_narrative.narrative       → summary.icp_narrative
raw.icp_narrative.top_segments    → summary.icp_summary
raw.pain_points_summary.top_items → summary.top_pain_points (item→label, insight preserved)
raw.recommendations.sales         → recommendations.sales
raw.recommendations.marketing     → recommendations.marketing
```

## Mock data

`MOCK_SUMMARY` — 5 ICP segments, 3 pain points with insights, funnel with 3 stages, narrative text.
`MOCK_RECOMMENDATIONS` — 3 sales items, 3 marketing items.
`MOCK_DASHBOARD_INSIGHTS` — combines both above.

The mock chat answer is a multiline Vietnamese string with inline markdown, code block, and 2 references — used to test the chat rendering in mock mode.
