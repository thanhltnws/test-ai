// Raw response shape from backend API
export interface BeInsightResponse {
  period_start: string
  computed_at: string
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
  top_pain_points: { label: string; count: number }[]
  icp_summary: (ICP & { count: number })[]
  period: string
  period_start: string
}

export interface RecommendationsData {
  recommendations: string[]
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
