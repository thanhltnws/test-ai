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
  ingestion:       joinUrl(VITE_INGESTION_LAMBDA_URL, VITE_INGESTION_PATH),   // ingestion demo
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

`requireAuthHeaders()` is called for mutating endpoints (`runBatch`, `sendChat`). Ingestion endpoints and `fetchDashboardInsights` do NOT require auth.

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
`MOCK_FILES` — 5 `MockFileEntry` objects mirroring `mock_sources.json` (redmine ×2, outlook_email ×2, teams_transcript ×1).

The mock chat answer is a multiline Vietnamese string with inline markdown, code block, and 2 references — used to test the chat rendering in mock mode.

---

## Ingestion demo functions

### `listIngestionFiles()`

```typescript
listIngestionFiles(): Promise<IngestionFilesResponse>
```

- Mock: returns `{ files: MOCK_FILES }` — no network call
- Lambda: `GET lambdaEndpoints.ingestion`

### `triggerIngestionFile(fileId)`

```typescript
triggerIngestionFile(fileId: string): Promise<TriggerResult>
```

- Mock: 1.8 s delay → returns stub `{ mode: 'local', upserted: 0, vectors: 0, note: 'Mock mode...' }`
- Lambda: `POST lambdaEndpoints.ingestion/trigger` with `{ file_id: fileId }`

### `fetchTransformLogs(since)`

```typescript
fetchTransformLogs(since: string): Promise<{ events: { ts: number; message: string }[] }>
```

- Mock: returns `{ events: [] }`
- Lambda: `GET VITE_TRANSFORM_LAMBDA_URL/logs?since=<ISO8601>` — polls every 5 s from `Pipeline.tsx`
- Calls Transform Lambda directly (not Ingestion Lambda) — Transform Lambda reads its own CloudWatch log group

### `fetchIngestionPreview(fileId)`

```typescript
fetchIngestionPreview(fileId: string): Promise<{ file_id: string; source: string; label: string; records: unknown[] }>
```

- Mock: returns stub with `records: []` (preview modal shows a "requires lambda" message)
- Lambda: `GET lambdaEndpoints.ingestion/preview?file_id=<id>`
