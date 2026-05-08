import axios from 'axios'
import type { SummaryData, RecommendationsData, ChatMessage, BeInsightResponse } from '../types'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ── Mock data ──────────────────────────────────────────────────────────────────

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

// ── Transform BE response → FE types ──────────────────────────────────────────

function toSummary(raw: BeInsightResponse): SummaryData {
  return {
    period: 'weekly',
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

// ── API calls ──────────────────────────────────────────────────────────────────
// Hiện tại: fallback về mock data khi API lỗi (dùng cho dev/demo)
// Khi go-live: xóa try/catch + MOCK_* objects, dùng version bên dưới

export async function fetchSummary(): Promise<SummaryData> {
  try {
    const res = await axios.get<BeInsightResponse>(`${BASE}/insights/summary`)
    return toSummary(res.data)
  } catch {
    return MOCK_SUMMARY
  }
}

// [GO-LIVE] export async function fetchSummary(): Promise<SummaryData> {
//   const res = await axios.get<BeInsightResponse>(`${BASE}/insights/summary`)
//   return toSummary(res.data)
// }

export async function fetchRecommendations(): Promise<RecommendationsData> {
  try {
    const res = await axios.get<BeInsightResponse>(`${BASE}/insights/summary`)
    return toRecommendations(res.data)
  } catch {
    return MOCK_RECOMMENDATIONS
  }
}

// [GO-LIVE] export async function fetchRecommendations(): Promise<RecommendationsData> {
//   const res = await axios.get<BeInsightResponse>(`${BASE}/insights/summary`)
//   return toRecommendations(res.data)
// }

export async function sendChat(
  question: string,
  history: ChatMessage[],
): Promise<{ answer: string; references: ChatMessage['references'] }> {
  const res = await axios.post(`${BASE}/chat`, { question, history })
  return res.data
}
