import axios from 'axios'
import type {
  BatchRunResponse,
  BeInsightResponse,
  ChatMessage,
  DashboardFilters,
  DashboardInsights,
  IngestionFilesResponse,
  MockFileEntry,
  RecommendationsData,
  SummaryData,
  TriggerResult,
} from '../types'

const legacyBase = import.meta.env.VITE_API_URL ?? '/api'
const dataSource = import.meta.env.VITE_DATA_SOURCE ?? 'mock'
const useLambdaData = dataSource === 'lambda'
const authTokenStorageKey = import.meta.env.VITE_AUTH_TOKEN_STORAGE_KEY ?? 'ai-insight-hub-auth-token'

const apiBase = import.meta.env.VITE_API_LAMBDA_URL ?? legacyBase
const chatBase = import.meta.env.VITE_CHAT_LAMBDA_URL ?? legacyBase
const insightsBuilderBase = import.meta.env.VITE_INSIGHTS_BUILDER_LAMBDA_URL ?? legacyBase
const ingestionBase = import.meta.env.VITE_INGESTION_LAMBDA_URL ?? legacyBase
const transformBase = import.meta.env.VITE_TRANSFORM_LAMBDA_URL ?? legacyBase

const insightsPath = import.meta.env.VITE_API_INSIGHTS_PATH ?? '/insights'
const chatPath = import.meta.env.VITE_CHAT_PATH ?? '/chat'
const insightsBuilderPath = import.meta.env.VITE_INSIGHTS_BUILDER_LAMBDA_URL
  ? (import.meta.env.VITE_INSIGHTS_BUILDER_PATH ?? '')
  : (import.meta.env.VITE_INSIGHTS_BUILDER_PATH ?? '/insights-builder')
  const ingestionPath = import.meta.env.VITE_INGESTION_PATH ?? '/ingestion'

function joinUrl(base: string, path = ''): string {
  if (!path) return base
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}

export const lambdaEndpoints = {
  api: joinUrl(apiBase, insightsPath),
  chat: joinUrl(chatBase, chatPath),
  insightsBuilder: joinUrl(insightsBuilderBase, insightsBuilderPath),
  ingestion: joinUrl(ingestionBase, ingestionPath),
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
    { stage: 'consideration', count: 11, pct: 55.0 },
    { stage: 'won', count: 7, pct: 35.0 },
    { stage: 'lost', count: 2, pct: 10.0 },
  ],
  funnel_summary: 'The funnel is heavily weighted toward consideration, indicating strong pipeline generation but significant conversion friction.',
  icp_narrative: 'Core ICP is mid-market companies (50-200 employees) in education and software sectors pursuing small-to-medium engagements. They are internationally based and prioritize structured onboarding and career outcomes.',
  top_pain_points: [
    { label: 'Unemployed', count: 4, insight: 'Unemployment is the primary driver pushing candidates to seek retraining and upskilling opportunities.' },
    { label: 'Lack of career prospects', count: 4, insight: 'Stagnant career growth motivates customers to invest in new skills and pivot industries.' },
    { label: 'Async job failures', count: 1, insight: 'Technical instability in job processing pipelines disrupts customer workflows and erodes trust.' },
  ],
  icp_summary: [
    { sector: 'education',     client_type: 'corporate', tech_maturity: 'semi-tech', deal_size: 'small',  market: 'international', count: 5 },
    { sector: 'software',      client_type: 'startup',   tech_maturity: 'technical', deal_size: 'medium', market: 'international', count: 3 },
    { sector: 'healthcare',    client_type: 'corporate', tech_maturity: 'non-tech',  deal_size: 'large',  market: 'vietnam',       count: 2 },
    { sector: 'software',      client_type: 'corporate', tech_maturity: 'technical', deal_size: 'large',  market: 'japan',         count: 2 },
    { sector: 'manufacturing', client_type: 'corporate', tech_maturity: 'non-tech',  deal_size: 'medium', market: 'vietnam',       count: 1 },
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
    summary: raw.recommendations?.summary ?? undefined,
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
  sessionId: string | null,
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

  const res = await axios.post(lambdaEndpoints.chat, { question, session_id: sessionId }, { headers: requireAuthHeaders() })
  const raw = res.data
  return {
    answer: raw.answer ?? '',
    references: (raw.references ?? []).map((r: { title: string; source_url: string }) => ({
      title: r.title,
      url: r.source_url,
    })),
  }
}

// ── Ingestion demo API ────────────────────────────────────────────────────────

const MOCK_FILES: MockFileEntry[] = [
  { id: 'redmine_01', source: 'redmine', file: 'mock/redmine_01.json', label: 'Redmine — International Project Tickets', description: 'Support, bug, and feature tickets across international client projects' },
  { id: 'redmine_02', source: 'redmine', file: 'mock/redmine_02.json', label: 'Redmine — Japan Project Tickets', description: 'Japanese-language project tickets from PayFlow JP, EduNavi JP, KeiRetail JP and others' },
  { id: 'outlook_email_01', source: 'outlook_email', file: 'mock/outlook_email_01.json', label: 'Outlook Email — International', description: 'Pre-sales, delivery, and commercial emails across international markets' },
  { id: 'outlook_email_02', source: 'outlook_email', file: 'mock/outlook_email_02.json', label: 'Outlook Email — Vietnam Focus', description: 'Emails covering Vietnam-market deals including VinPay, ShopViet, MedViet' },
  { id: 'teams_transcript_01', source: 'teams_transcript', file: 'mock/teams_transcript_01.json', label: 'Teams Transcripts — Sales & Delivery', description: 'Meeting transcripts: kick-offs, sprint reviews, escalations, and discovery calls' },
]

export async function listIngestionFiles(): Promise<IngestionFilesResponse> {
  if (!useLambdaData) {
    return { files: MOCK_FILES }
  }
  const res = await axios.get<IngestionFilesResponse>(lambdaEndpoints.ingestion)
  return res.data
}

export async function triggerIngestionFile(fileId: string): Promise<TriggerResult> {
  if (!useLambdaData) {
    await new Promise(r => setTimeout(r, 1800))
    const entry = MOCK_FILES.find(f => f.id === fileId)
    return {
      file_id: fileId,
      source: entry?.source ?? fileId,
      mode: 'local',
      upserted: 0,
      vectors: 0,
      record_count: 0,
      note: 'Mock mode — no data written.',
    }
  }
  const res = await axios.post<TriggerResult>(`${lambdaEndpoints.ingestion}/trigger`, { file_id: fileId })
  return res.data
}

export async function fetchTransformLogs(since: string): Promise<{ events: { ts: number; message: string }[] }> {
  if (!useLambdaData) return { events: [] }
  const res = await axios.get<{ events: { ts: number; message: string }[] }>(
    `${transformBase}/logs`,
    { params: { since } },
  )
  return res.data
}

export async function fetchIngestionPreview(fileId: string): Promise<{ file_id: string; source: string; label: string; records: unknown[] }> {
  if (!useLambdaData) {
    const entry = MOCK_FILES.find(f => f.id === fileId)
    return { file_id: fileId, source: entry?.source ?? fileId, label: entry?.label ?? fileId, records: [] }
  }
  const res = await axios.get<{ file_id: string; source: string; label: string; records: unknown[] }>(
    `${lambdaEndpoints.ingestion}/preview`,
    { params: { file_id: fileId } },
  )
  return res.data
}

