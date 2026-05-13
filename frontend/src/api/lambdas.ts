import axios from 'axios'
import type {
  BatchRunResponse,
  BeInsightResponse,
  ChatMessage,
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
const batchBase = import.meta.env.VITE_BATCH_LAMBDA_URL ?? legacyBase

const recommendationsPath = import.meta.env.VITE_API_RECOMMENDATIONS_PATH ?? '/recommendations'
const chatPath = import.meta.env.VITE_CHAT_PATH ?? '/chat'
const batchPath = import.meta.env.VITE_BATCH_LAMBDA_URL
  ? (import.meta.env.VITE_BATCH_PATH ?? '')
  : (import.meta.env.VITE_BATCH_PATH ?? '/batch')

function joinUrl(base: string, path = ''): string {
  if (!path) return base
  return `${base.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`
}

export const lambdaEndpoints = {
  api: joinUrl(apiBase, recommendationsPath),
  chat: joinUrl(chatBase, chatPath),
  batch: joinUrl(batchBase, batchPath),
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
  period: 'weekly',
  period_start: '2026-05-07',
  funnel_distribution: [
    { stage: 'consideration', count: 11 },
    { stage: 'won', count: 7 },
    { stage: 'lost', count: 2 },
  ],
  top_pain_points: [
    { label: 'Unemployed', count: 4 },
    { label: 'Lack of career prospects', count: 4 },
    { label: 'Async job failures', count: 1 },
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
  recommendations: [
    'Prioritize outreach to small and medium-sized companies in the education, software, and healthcare sectors, as these appear to be the top segments based on the data.',
    'Develop targeted sales strategies and messaging to address the key pain points of unemployment, lack of career prospects, and technical issues with asynchronous job processing.',
    'Create content and campaigns that highlight the company\'s expertise in upskilling, professional development, and operational efficiency solutions.',
    'Leverage customer success stories and testimonials from the top industry segments to showcase the value proposition of the company\'s offerings.',
  ],
}

const MOCK_DASHBOARD_INSIGHTS: DashboardInsights = {
  summary: MOCK_SUMMARY,
  recommendations: MOCK_RECOMMENDATIONS,
}

function toSummary(raw: BeInsightResponse): SummaryData {
  return {
    period: 'daily',
    period_start: raw.period_start,
    funnel_distribution: raw.funnel_distribution.stages,
    top_pain_points: raw.pain_points_summary.top_items.map(p => ({
      label: p.item,
      count: p.count,
    })),
    icp_summary: raw.icp_narrative.top_segments,
  }
}

function toRecommendations(raw: BeInsightResponse): RecommendationsData {
  return {
    recommendations: [
      ...raw.recommendations.sales,
      ...raw.recommendations.marketing,
    ],
    computed_at: raw.computed_at,
  }
}

async function fetchInsightResponse(): Promise<BeInsightResponse> {
  const res = await axios.get<BeInsightResponse>(lambdaEndpoints.api)
  return res.data
}

export async function fetchDashboardInsights(): Promise<DashboardInsights> {
  if (!useLambdaData) {
    return MOCK_DASHBOARD_INSIGHTS
  }

  const raw = await fetchInsightResponse()
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

  const res = await axios.post<BatchRunResponse>(lambdaEndpoints.batch, {}, { headers: requireAuthHeaders() })
  return res.data
}

export async function sendChat(
  question: string,
  history: ChatMessage[],
): Promise<{ answer: string; references: ChatMessage['references'] }> {
  if (!useLambdaData) {
    return {
      answer: `Mock response for: "${question}". Set VITE_DATA_SOURCE=lambda to call the chat Lambda.`,
      references: [],
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
