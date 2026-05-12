import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Legend,
} from 'recharts'
import { fetchDashboardInsights } from '../api/lambdas'
import type { SummaryData, RecommendationsData } from '../types'

const FUNNEL_COLORS: Record<string, string> = {
  awareness: '#93c5fd',
  consideration: '#60a5fa',
  negotiation: '#3b82f6',
  won: '#16a34a',
  lost: '#ef4444',
}

const card: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: 24,
  boxShadow: 'var(--shadow)',
}

const statCard = (accent: string): React.CSSProperties => ({
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '20px 24px',
  boxShadow: 'var(--shadow)',
  borderTop: `3px solid ${accent}`,
})

export default function Dashboard() {
  const [data, setData] = useState<SummaryData | null>(null)
  const [recs, setRecs] = useState<RecommendationsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchDashboardInsights()
      .then(({ summary, recommendations }) => {
        setData(summary)
        setRecs(recommendations)
        setLoading(false)
      })
      .catch(err => {
        setError(err?.message ?? 'Không thể tải dữ liệu. Vui lòng thử lại.')
        setLoading(false)
      })
  }, [retryCount])

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
        <div>Đang tải dữ liệu...</div>
      </div>
    </div>
  )

  if (error) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        textAlign: 'center',
        background: 'var(--surface)',
        border: '1px solid #fca5a5',
        borderRadius: 'var(--radius)',
        padding: '32px 40px',
        boxShadow: 'var(--shadow)',
      }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
        <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>Lỗi tải dữ liệu</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20 }}>{error}</div>
        <button
          onClick={() => setRetryCount(c => c + 1)}
          style={{
            background: 'var(--accent)',
            color: '#fff',
            padding: '8px 20px',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          Thử lại
        </button>
      </div>
    </div>
  )
  if (!data) return null

  const total = data.funnel_distribution.reduce((s, d) => s + d.count, 0)
  const won = data.funnel_distribution.find(d => d.stage === 'won')?.count ?? 0
  const winRate = total ? Math.round((won / total) * 100) : 0

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 24, background: 'var(--bg)' }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>Customer Insight Overview</h1>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          Period: <strong>{data.period}</strong> · Starting {data.period_start}
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {[
          { label: 'Total Insights', value: total, accent: '#2563eb' },
          { label: 'Win Rate', value: `${winRate}%`, accent: '#16a34a' },
          { label: 'Pain Points', value: data.top_pain_points.length, accent: '#d97706' },
          { label: 'ICP Segments', value: data.icp_summary.length, accent: '#7c3aed' },
        ].map(({ label, value, accent }) => (
          <div key={label} style={statCard(accent)}>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Row: Funnel + Pain Points */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', gap: 24 }}>

        {/* Funnel Distribution */}
        <div style={card}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 20 }}>Funnel Distribution</h2>
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie
                data={data.funnel_distribution.map(d => ({ ...d, fill: FUNNEL_COLORS[d.stage] ?? '#93c5fd' }))}
                dataKey="count"
                nameKey="stage"
                cx="50%"
                cy="50%"
                outerRadius={85}
                innerRadius={40}
              />
              <Legend
                formatter={(value) => <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{value}</span>}
              />
              <Tooltip
                contentStyle={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, fontSize: 13 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top Pain Points */}
        <div style={card}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 20 }}>Top Pain Points</h2>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={data.top_pain_points} layout="vertical" margin={{ left: 0, right: 32 }}>
              <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={170} tick={{ fill: 'var(--text)', fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, fontSize: 13 }}
              />
              <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ICP Cards */}
      <div style={card}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>Ideal Customer Profile (ICP)</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 }}>
          {data.icp_summary.map((icp, i) => (
            <div key={i} style={{
              background: 'var(--surface2)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 16,
              borderLeft: '3px solid var(--accent-light)',
            }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 10, color: 'var(--text)' }}>{icp.sector}</div>
              {[
                ['Region', icp.region],
                ['Company size', icp.company_size],
                ['Deal size', icp.deal_size],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}>
                  <span style={{ color: 'var(--text-muted)' }}>{k}</span>
                  <span style={{ fontWeight: 500 }}>{v}</span>
                </div>
              ))}
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>Insights</span>
                <span style={{ fontWeight: 700, color: 'var(--accent)' }}>{icp.count}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div style={card}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 16 }}>AI Recommendations</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {(recs?.recommendations ?? []).map((rec, i) => (
            <div key={i} style={{
              display: 'flex',
              gap: 12,
              padding: '14px 16px',
              background: 'var(--accent-bg)',
              border: '1px solid #bfdbfe',
              borderRadius: 8,
              fontSize: 14,
              lineHeight: 1.6,
            }}>
              <span style={{
                background: 'var(--accent)',
                color: '#fff',
                borderRadius: '50%',
                width: 22,
                height: 22,
                minWidth: 22,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 700,
                marginTop: 1,
              }}>{i + 1}</span>
              <span style={{ color: 'var(--text)' }}>{rec}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
