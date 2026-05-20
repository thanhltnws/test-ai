// Raw response shape from backend API
export interface BeInsightResponse {
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

export interface ICP {
  sector: string
  company_size: string
  deal_size: string
  region: string
}

export interface SummaryData {
  funnel_distribution: { stage: string; count: number }[]
  funnel_summary: string
  top_pain_points: { label: string; count: number; insight: string }[]
  icp_summary: (ICP & { count: number })[]
  icp_narrative: string
  period: string
  period_start: string
  period_end: string
  market: string | null
}

export interface RecommendationsData {
  recommendations: string[]
  sales: string[]
  marketing: string[]
  computed_at?: string
}

export interface DashboardInsights {
  summary: SummaryData
  recommendations: RecommendationsData
}

export interface BatchRunResponse {
  period_start?: string
  written?: number
  body?: string
  statusCode?: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  references?: Reference[]
}

export interface Reference {
  title: string
  url: string
}

export type PeriodType = 'weekly' | 'monthly' | 'quarterly' | 'yearly'
export type MarketType = 'vietnam' | 'japan' | 'korea' | 'international'

export interface DashboardFilters {
  period: PeriodType | ''
  date: string
  market: MarketType | ''
}

// ── Ingestion demo types ──────────────────────────────────────────────────────

export interface MockFileEntry {
  id: string
  source: string
  file: string
  label: string
  description: string
  record_count?: number
}

export interface IngestionFilesResponse {
  files: MockFileEntry[]
}

export type TriggerStatus = 'idle' | 'triggering' | 'done' | 'error'

export interface TriggerResult {
  file_id: string
  source: string
  mode: 'aws' | 'local'
  s3_uri?: string
  upserted?: number
  vectors?: number
  record_count?: number
  note?: string
}

export interface ActivityLogEntry {
  ts: string
  level: 'info' | 'success' | 'error' | 'warning'
  message: string
  detail?: string
}
