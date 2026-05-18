import { useEffect, useState, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Legend,
} from 'recharts'
import { fetchDashboardInsights } from '../api/lambdas'
import type { PeriodType, SummaryData, RecommendationsData } from '../types'

const PERIODS: { value: PeriodType; label: string }[] = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
]

const MARKETS = [
  { value: '' as const, label: 'All Markets' },
  { value: 'vietnam' as const, label: 'Vietnam' },
  { value: 'japan' as const, label: 'Japan' },
  { value: 'korea' as const, label: 'Korea' },
  { value: 'international' as const, label: 'International' },
]

function toISODate(d: Date): string {
  return d.toISOString().split('T')[0]
}

function getPeriodStart(period: PeriodType, isoDate: string): string {
  const d = new Date(isoDate)
  if (period === 'weekly') {
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day
    d.setDate(d.getDate() + diff)
    return toISODate(d)
  }
  if (period === 'monthly') return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  if (period === 'quarterly') {
    const q = Math.floor(d.getMonth() / 3)
    return `${d.getFullYear()}-${String(q * 3 + 1).padStart(2, '0')}-01`
  }
  return `${d.getFullYear()}-01-01`
}

function navigatePeriod(period: PeriodType, isoDate: string, dir: -1 | 1): string {
  const d = new Date(isoDate)
  if (period === 'weekly') d.setDate(d.getDate() + dir * 7)
  else if (period === 'monthly') d.setMonth(d.getMonth() + dir)
  else if (period === 'quarterly') d.setMonth(d.getMonth() + dir * 3)
  else d.setFullYear(d.getFullYear() + dir)
  return getPeriodStart(period, toISODate(d))
}

function getPeriodLabel(period: PeriodType, isoDate: string): string {
  const d = new Date(isoDate)
  if (period === 'monthly') return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
  if (period === 'weekly') {
    const end = new Date(d); end.setDate(end.getDate() + 6)
    const s = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    const e = end.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    return `${s} – ${e}`
  }
  if (period === 'quarterly') return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`
  return String(d.getFullYear())
}



const FUNNEL_COLORS: Record<string, string> = {
  awareness: '#93c5fd',
  consideration: '#60a5fa',
  negotiation: '#3b82f6',
  won: '#16a34a',
  lost: '#ef4444',
}

const inputStyle: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 7,
  padding: '7px 10px',
  fontSize: 13,
  color: 'var(--text)',
  outline: 'none',
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
  const [period, setPeriod] = useState<PeriodType>('monthly')
  const [periodAnchor, setPeriodAnchor] = useState<string>(() => getPeriodStart('monthly', toISODate(new Date())))
  const [market, setMarket] = useState<string>('')
  const [retryTick, setRetryTick] = useState(0)
  const [noData, setNoData] = useState(false)
const dedupedPainPoints = useMemo(() => {
    if (!data) return []
    const map = new Map<string, number>()
    for (const p of data.top_pain_points) {
      const key = p.label.toLowerCase().trim().replace(/[.,!?]$/, '')
      map.set(key, (map.get(key) ?? 0) + p.count)
    }
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([label, count]) => {
        const full = label.charAt(0).toUpperCase() + label.slice(1)
        return { label: full.length > 34 ? full.slice(0, 33) + '…' : full, fullLabel: full, count }
      })
  }, [data])

  useEffect(() => {
    setLoading(true)
    setError(null)
    setNoData(false)
    fetchDashboardInsights({ period, date: periodAnchor, market: market as '' })
      .then(({ summary, recommendations }) => {
        if (summary.period_start === '') {
          setNoData(true)
        } else {
          setData(summary)
          setRecs(recommendations)
        }
        setLoading(false)
      })
      .catch(err => {
        setError(err?.message ?? 'Không thể tải dữ liệu. Vui lòng thử lại.')
        setLoading(false)
      })
  }, [period, periodAnchor, market, retryTick])

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
          onClick={() => setRetryTick(t => t + 1)}
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
  const lost = data.funnel_distribution.find(d => d.stage === 'lost')?.count ?? 0
  const closed = won + lost
  const closeRate = closed ? Math.round((won / closed) * 100) : 0


  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 24, background: 'var(--bg)' }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', marginBottom: 4, fontFamily: "'Plus Jakarta Sans', sans-serif", letterSpacing: '-0.3px' }}>Customer Insight Overview</h1>
        {/* Filter bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {/* Period selector */}
          <select
            value={period}
            onChange={e => {
              const p = e.target.value as PeriodType
              setPeriod(p)
              setPeriodAnchor(getPeriodStart(p, toISODate(new Date())))
            }}
            style={inputStyle}
          >
            {PERIODS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>

          {/* Period navigator */}
          <div style={{ display: 'flex', alignItems: 'center', border: '1px solid var(--border)', borderRadius: 7, overflow: 'hidden', background: 'var(--surface)' }}>
            <button
              onClick={() => setPeriodAnchor(a => navigatePeriod(period, a, -1))}
              style={{ padding: '7px 10px', fontSize: 14, color: 'var(--text-muted)', borderRight: '1px solid var(--border)' }}
            >‹</button>
            <span style={{ padding: '7px 14px', fontSize: 13, color: 'var(--text)', whiteSpace: 'nowrap', minWidth: 130, textAlign: 'center' }}>
              {getPeriodLabel(period, periodAnchor)}
            </span>
            <button
              onClick={() => setPeriodAnchor(a => navigatePeriod(period, a, 1))}
              style={{ padding: '7px 10px', fontSize: 14, color: 'var(--text-muted)', borderLeft: '1px solid var(--border)' }}
            >›</button>
          </div>

          {/* Market selector */}
          <select
            value={market}
            onChange={e => setMarket(e.target.value)}
            style={inputStyle}
          >
            {MARKETS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          {(market !== '') && (
            <button
              onClick={() => setMarket('')}
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)', padding: '7px 12px', borderRadius: 7, fontSize: 13 }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* No data banner */}
      {noData && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8,
          padding: '10px 16px', fontSize: 13, color: '#92400e',
        }}>
          <span>📭 Không có dữ liệu cho khoảng thời gian này. Đang hiển thị dữ liệu gần nhất.</span>
          <button onClick={() => setNoData(false)} style={{ color: '#92400e', fontSize: 16, marginLeft: 12 }}>×</button>
        </div>
      )}

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {[
          { label: 'Total Insights', value: total, accent: '#2563eb' },
          { label: 'Close Rate', value: `${closeRate}%`, accent: '#16a34a' },
          { label: 'Pain Points', value: dedupedPainPoints.length, accent: '#d97706' },
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
            <BarChart data={dedupedPainPoints} layout="vertical" margin={{ left: 0, right: 32 }}>
              <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="label"
                width={240}
                axisLine={false}
                tickLine={false}
                interval={0}
                tick={(props: { x: string | number; y: string | number; payload: { value: string } }) => (
                  <text x={props.x} y={props.y} dy={4} textAnchor="end" fill="var(--text)" fontSize={11}>
                    {props.payload.value}
                  </text>
                )}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 13, maxWidth: 280 }}>
                      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 4, lineHeight: 1.4 }}>{d.fullLabel}</div>
                      <div style={{ color: 'var(--text-muted)' }}>Count: <strong>{d.count}</strong></div>
                    </div>
                  )
                }}
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {([
            { key: 'sales', label: '🎯 Sales', items: recs?.sales ?? [], bg: 'var(--accent-bg)', border: '#bfdbfe', accent: 'var(--accent)' },
            { key: 'marketing', label: '📣 Marketing', items: recs?.marketing ?? [], bg: '#f0fdf4', border: '#bbf7d0', accent: '#16a34a' },
          ] as const).map(col => (
            <div key={col.key}>
              <div style={{ fontSize: 12, fontWeight: 700, color: col.accent, marginBottom: 10, letterSpacing: '0.03em' }}>
                {col.label}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {col.items.map((rec, i) => (
                  <div key={i} style={{
                    display: 'flex', gap: 10,
                    padding: '12px 14px',
                    background: col.bg,
                    border: `1px solid ${col.border}`,
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}>
                    <span style={{
                      background: col.accent, color: '#fff',
                      borderRadius: '50%', width: 20, height: 20, minWidth: 20,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 700, marginTop: 1, flexShrink: 0,
                    }}>{i + 1}</span>
                    <span style={{ color: 'var(--text)' }}>{rec}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
