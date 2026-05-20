# Type Definitions (`types/index.ts`)

## API response types

### `BeInsightResponse`

Raw shape returned by the backend insights Lambda. Not used directly in UI — mapped via `toSummary()` and `toRecommendations()` in `api/lambdas.ts`.

```typescript
interface BeInsightResponse {
  period: string
  period_start: string
  period_end: string
  computed_at: string
  market: string | null
  funnel_distribution: {
    stages: { stage: string; count: number; pct: number }[]
    summary: string
  }
  icp_narrative: {
    narrative: string
    top_segments: { sector: string; company_size: string; deal_size: string; region: string; count: number }[]
  }
  pain_points_summary: {
    summary: string
    top_items: { item: string; count: number; insight: string }[]
  }
  recommendations: {
    sales: string[]
    marketing: string[]
    summary: string
  }
}
```

## Frontend data types

### `SummaryData`

Mapped frontend shape used by `Dashboard.tsx`. All fields are guaranteed (no optional).

```typescript
interface SummaryData {
  period: string                          // 'monthly' | 'quarterly' | 'yearly'
  period_start: string                    // 'YYYY-MM-DD'
  period_end: string
  market: string | null
  funnel_distribution: { stage: string; count: number }[]
  funnel_summary: string                  // narrative for the callout box
  top_pain_points: { label: string; count: number; insight: string }[]
  icp_summary: (ICP & { count: number })[]
  icp_narrative: string                   // narrative for the ICP callout
}
```

### `ICP`

```typescript
interface ICP {
  sector: string       // 'education' | 'software' | 'healthcare' | ...
  company_size: string // '1-10' | '50-200' | '200-1000' | '1000+'
  deal_size: string    // 'small' | 'medium' | 'large'
  region: string       // 'International' | 'Vietnam' | ...
}
```

### `RecommendationsData`

```typescript
interface RecommendationsData {
  sales: string[]
  marketing: string[]
  recommendations: string[]   // legacy field, always [] currently
  computed_at?: string
}
```

### `DashboardInsights`

```typescript
interface DashboardInsights {
  summary: SummaryData
  recommendations: RecommendationsData
}
```

### `BatchRunResponse`

```typescript
interface BatchRunResponse {
  period_start?: string
  written?: number
  body?: string       // raw Lambda response body on error
  statusCode?: number
}
```

## Chat types

### `ChatMessage`

```typescript
interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  references?: Reference[]   // only on assistant messages
}
```

### `Reference`

```typescript
interface Reference {
  title: string
  url: string    // mapped from backend's source_url
}
```

## Filter types

```typescript
type PeriodType = 'weekly' | 'monthly' | 'quarterly' | 'yearly'

type MarketType = 'vietnam' | 'japan' | 'korea' | 'international'

interface DashboardFilters {
  period: PeriodType | ''
  date: string        // ISO date, start of period
  market: MarketType | ''  // '' = all markets
}
```

---

## Ingestion demo types

### `MockFileEntry`

```typescript
interface MockFileEntry {
  id: string           // e.g. 'redmine_01'
  source: string       // e.g. 'redmine', 'outlook_email', 'teams_transcript'
  file: string         // relative path, e.g. 'mock/redmine_01.json'
  label: string        // display name shown in FileRow
  description: string  // short description shown in FileRow subtitle
  record_count?: number
}
```

### `IngestionFilesResponse`

```typescript
interface IngestionFilesResponse {
  files: MockFileEntry[]
}
```

### `TriggerStatus`

```typescript
type TriggerStatus = 'idle' | 'triggering' | 'done' | 'error'
```

Per-file state for the Trigger button in `Pipeline.tsx`.

### `TriggerResult`

```typescript
interface TriggerResult {
  file_id: string
  source: string
  mode: 'aws' | 'local'
  s3_uri?: string        // populated in aws mode
  upserted?: number      // signals written (local mode)
  vectors?: number       // embeddings written (local mode)
  record_count?: number
  note?: string
}
```

### `ActivityLogEntry`

```typescript
interface ActivityLogEntry {
  ts: string                              // time string from nowTime(), e.g. '12:34:56'
  level: 'info' | 'success' | 'error' | 'warning'
  message: string
  detail?: string                         // shown as monospace sub-line
}
```
