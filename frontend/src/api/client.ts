import axios from 'axios'
import type { SummaryData, RecommendationsData, ChatMessage } from '../types'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ── Mock data ──────────────────────────────────────────────────────────────────

const MOCK_SUMMARY: SummaryData = {
  period: 'weekly',
  period_start: '2026-05-01',
  funnel_distribution: [
    { stage: 'awareness', count: 12 },
    { stage: 'consideration', count: 28 },
    { stage: 'negotiation', count: 15 },
    { stage: 'won', count: 22 },
    { stage: 'lost', count: 18 },
  ],
  top_pain_points: [
    { label: 'Integration complexity', count: 31 },
    { label: 'High implementation cost', count: 27 },
    { label: 'Lack of local support', count: 24 },
    { label: 'Unclear ROI', count: 19 },
    { label: 'Security concerns', count: 15 },
    { label: 'Vendor lock-in risk', count: 11 },
  ],
  icp_summary: [
    { sector: 'Fintech', company_size: '50-200', deal_size: 'large', region: 'Southeast Asia', count: 18 },
    { sector: 'Logistics', company_size: '200-1000', deal_size: 'medium', region: 'Vietnam', count: 14 },
    { sector: 'Retail', company_size: '11-50', deal_size: 'small', region: 'Vietnam', count: 11 },
    { sector: 'Manufacturing', company_size: '1000+', deal_size: 'large', region: 'International', count: 9 },
  ],
}

const MOCK_RECOMMENDATIONS: RecommendationsData = {
  recommendations: [
    'Tăng cường nội dung về ROI và case study cho segment Fintech tại SEA — pain point "Unclear ROI" chiếm 19 trường hợp.',
    'Xây dựng gói hỗ trợ triển khai local cho khách hàng SMB (11-200 nhân viên) để giảm rào cản "Lack of local support".',
    'Ưu tiên deals trong giai đoạn Consideration (28 deals) — tỷ lệ chuyển đổi sang Negotiation chỉ đạt 54%.',
    'Chuẩn bị tài liệu về bảo mật và data sovereignty cho segment Manufacturing quốc tế.',
  ],
}

// ── API calls ──────────────────────────────────────────────────────────────────

export async function fetchSummary(): Promise<SummaryData> {
  try {
    const res = await axios.get<SummaryData>(`${BASE}/insights/summary`)
    return res.data
  } catch {
    return MOCK_SUMMARY
  }
}

export async function fetchRecommendations(): Promise<RecommendationsData> {
  try {
    const res = await axios.get<RecommendationsData>(`${BASE}/recommendations`)
    return res.data
  } catch {
    return MOCK_RECOMMENDATIONS
  }
}

export async function sendChat(
  question: string,
  history: ChatMessage[],
): Promise<{ answer: string; references: ChatMessage['references'] }> {
  const res = await axios.post(`${BASE}/chat`, { question, history })
  return res.data
}
