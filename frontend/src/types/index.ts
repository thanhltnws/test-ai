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

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  references?: Reference[]
}

export interface Reference {
  title: string
  url: string
  source: string
}
