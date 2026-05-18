import axios from 'axios'
import type {
  BatchRunResponse,
  BeInsightResponse,
  ChatMessage,
  DashboardFilters,
  DashboardInsights,
  RecommendationsData,
  SummaryData,
} from '../types'

const legacyBase = import.meta.env.VITE_API_URL ?? '/api'
const dataSource = import.meta.env.VITE_DATA_SOURCE ?? 'mock'
const useLambdaData = dataSource === 'lambda'
const authTokenStorageKey = import.meta.env.VITE_AUTH_TOKEN_STORAGE_KEY ?? 'ai-insight-hub-auth-token'

const apiBase = import.meta.env.VITE_API_LAMBDA_URL ?? legacyBase
const chatBase = import.meta.env.VITE_CHAT_LAMBDA_URL ?? legacyBase
const insightsBuilderBase = import.meta.env.VITE_INSIGHTS_BUILDER_LAMBDA_URL ?? legacyBase

const insightsPath = import.meta.env.VITE_API_INSIGHTS_PATH ?? '/insights'
const chatPath = import.meta.env.VITE_CHAT_PATH ?? '/chat'
const insightsBuilderPath = import.meta.env.VITE_INSIGHTS_BUILDER_LAMBDA_URL
  ? (import.meta.env.VITE_INSIGHTS_BUILDER_PATH ?? '')
  : (import.meta.env.VITE_INSIGHTS_BUILDER_PATH ?? '/insights-builder')

function joinUrl(base: string, path = ''): string {
  if (!path) return base
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}

export const lambdaEndpoints = {
  api: joinUrl(apiBase, insightsPath),
  chat: joinUrl(chatBase, chatPath),
  insightsBuilder: joinUrl(insightsBuilderBase, insightsBuilderPath),
}

export const isLambdaDataSource = useLambdaData

export function getAuthToken(): string {
  return window.localStorage.getItem(authTokenStorageKey) ?? ''
}

export function setAuthToken(token: string): void {
  const value = token.trim()
  if (value) {
    window.localStorage.setItem(authTokenStorageKey, value)
  } else {
    window.localStorage.removeItem(authTokenStorageKey)
  }
}

function requireAuthHeaders(): { Authorization: string } {
  const token = getAuthToken()
  if (!token) {
    throw new Error('Missing access token. Enter it in the sidebar before using live Lambda actions.')
  }

  return { Authorization: `Bearer ${token}` }
}

const MOCK_SUMMARY: SummaryData = {
  period: 'monthly',
  period_start: '2026-05-01',
  period_end: '2026-05-31',
  market: null,
  funnel_distribution: [
    { stage: 'consideration', count: 11 },
    { stage: 'won', count: 7 },
    { stage: 'lost', count: 2 },
  ],
  funnel_summary: 'The funnel is heavily weighted toward consideration, indicating strong pipeline generation but significant conversion friction.',
  icp_narrative: 'Core ICP is mid-market companies (50-200 employees) in education and software sectors pursuing small-to-medium engagements. They are internationally based and prioritize structured onboarding and career outcomes.',
  top_pain_points: [
    { label: 'Unemployed', count: 4, insight: 'Unemployment is the primary driver pushing candidates to seek retraining and upskilling opportunities.' },
    { label: 'Lack of career prospects', count: 4, insight: 'Stagnant career growth motivates customers to invest in new skills and pivot industries.' },
    { label: 'Async job failures', count: 1, insight: 'Technical instability in job processing pipelines disrupts customer workflows and erodes trust.' },
  ],
  icp_summary: [
    { sector: 'education', company_size: '1-10', deal_size: 'small', region: 'International', count: 5 },
    { sector: 'software', company_size: '200-1000', deal_size: 'medium', region: 'International', count: 3 },
    { sector: 'healthcare', company_size: '1000+', deal_size: 'large', region: 'International', count: 2 },
    { sector: 'software', company_size: '200-1000', deal_size: 'large', region: 'International', count: 2 },
    { sector: 'manufacturing', company_size: '50-200', deal_size: 'medium', region: 'International', count: 1 },
  ],
}

const MOCK_RECOMMENDATIONS: RecommendationsData = {
  computed_at: '2026-05-07T09:19:30.940150+00:00',
  sales: [
    'Prioritize outreach to small and medium-sized companies in the education, software, and healthcare sectors.',
    'Develop objection-handling scripts targeting the career transition pain point — the majority of prospects are unemployed or seeking better prospects.',
    'Focus pipeline activity on consideration-stage deals: 58% of deals are stalled here.',
  ],
  marketing: [
    'Create content campaigns highlighting career placement and growth outcomes to address the dominant pain point segments.',
    'Leverage customer success stories from education and software sectors to build credibility.',
    'Launch nurture sequences for consideration-stage leads to accelerate pipeline movement.',
  ],
  recommendations: [],
}

const MOCK_DASHBOARD_INSIGHTS: DashboardInsights = {
  summary: MOCK_SUMMARY,
  recommendations: MOCK_RECOMMENDATIONS,
}

function toSummary(raw: BeInsightResponse): SummaryData {
  return {
    period: raw.period ?? '',
    period_start: raw.period_start ?? '',
    period_end: raw.period_end ?? '',
    market: raw.market ?? null,
    funnel_distribution: raw.funnel_distribution?.stages ?? [],
    funnel_summary: raw.funnel_distribution?.summary ?? '',
    icp_narrative: raw.icp_narrative?.narrative ?? '',
    top_pain_points: (raw.pain_points_summary?.top_items ?? []).map(p => ({
      label: p.item,
      count: p.count,
      insight: p.insight ?? '',
    })),
    icp_summary: raw.icp_narrative?.top_segments ?? [],
  }
}

function toRecommendations(raw: BeInsightResponse): RecommendationsData {
  return {
    sales: raw.recommendations?.sales ?? [],
    marketing: raw.recommendations?.marketing ?? [],
    recommendations: [],
    computed_at: raw.computed_at ?? undefined,
  }
}

async function fetchInsightResponse(filters?: DashboardFilters): Promise<BeInsightResponse> {
  const params: Record<string, string> = {}
  if (filters?.period) params.period = filters.period
  if (filters?.date) params.date = filters.date
  if (filters?.market) params.market = filters.market
  const res = await axios.get<BeInsightResponse>(lambdaEndpoints.api, { params })
  return res.data
}

export async function fetchDashboardInsights(filters?: DashboardFilters): Promise<DashboardInsights> {
  if (!useLambdaData) {
    return MOCK_DASHBOARD_INSIGHTS
  }

  const raw = await fetchInsightResponse(filters)
  return {
    summary: toSummary(raw),
    recommendations: toRecommendations(raw),
  }
}

export async function runBatch(): Promise<BatchRunResponse> {
  if (!useLambdaData) {
    return {
      period_start: MOCK_SUMMARY.period_start,
      written: 0,
    }
  }

  const res = await axios.post<BatchRunResponse>(lambdaEndpoints.insightsBuilder, {}, { headers: requireAuthHeaders() })
  return res.data
}

export async function sendChat(
  question: string,
  history: ChatMessage[],
): Promise<{ answer: string; references: ChatMessage['references'] }> {
  if (!useLambdaData) {
    return {
      answer: `Dựa trên dữ liệu hiện có, khách hàng hay gặp các vấn đề sau:\n\n**1. Thất nghiệp / thiếu cơ hội nghề nghiệp**\nĐây là pain point xuất hiện nhiều nhất với 8 lượt đề cập. Chi tiết xem tại: https://crm.internal/insights/pain-points?filter=unemployed&market=EN&date_from=2026-01-01&date_to=2026-05-15&sort=count_desc&page=1\n\n**2. Async job failures**\n\`\`\`\nERROR: asyncJobQueue.process() timeout after 30000ms — jobId=aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899\n\`\`\`\n\nThiết lập retry logic: \`maxRetries=3, backoffMs=1000, jobTimeoutMs=aVeryLongConfigKeyNameThatShouldWrapProperly=true\`\n\nLiên hệ: support@verylongdomainname-thathasnobreaks-andkeepsgoing-forever.internal.company.com`,
      references: [
        { title: 'Insight #42 — Khách hàng phản ánh async job timeout liên tục trong tuần đầu triển khai', url: 'https://crm.internal/insights/42?source=ops_note&market=EN' },
        { title: 'Pain point summary — Unemployed / lack of career prospects (8 records)', url: 'https://crm.internal/pain-points/summary?label=unemployed&count=8' },
      ],
    }
  }

  const res = await axios.post(lambdaEndpoints.chat, { question, history }, { headers: requireAuthHeaders() })
  const raw = res.data
  return {
    answer: raw.answer ?? '',
    references: (raw.references ?? []).map((r: { title: string; source_url: string }) => ({
      title: r.title,
      url: r.source_url,
    })),
  }
}
