import { useEffect, useState } from 'react'
import { fetchDashboardInsights } from '../api/lambdas'
import type { PeriodType, SummaryData, RecommendationsData } from '../types'
import FunnelDistribution from '../components/FunnelDistribution'
import PainPoints from '../components/PainPoints'
import ICPCard from '../components/ICPCard'

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
    d.setDate(d.getDate() + (day === 0 ? -6 : 1 - day))
    return toISODate(d)
  }
  if (period === 'monthly') return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  if (period === 'quarterly') return `${d.getFullYear()}-${String(Math.floor(d.getMonth() / 3) * 3 + 1).padStart(2, '0')}-01`
  return `${d.getFullYear()}-01-01`
}

function getPeriodLabel(period: PeriodType, isoDate: string): string {
  const d = new Date(isoDate)
  if (period === 'monthly') return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
  if (period === 'weekly') {
    const end = new Date(d); end.setDate(end.getDate() + 6)
    return `${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} – ${end.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
  }
  if (period === 'quarterly') return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`
  return String(d.getFullYear())
}

function getPeriodOptions(period: PeriodType): { value: string; label: string }[] {
  const now = new Date()
  const count = period === 'quarterly' ? 8 : period === 'yearly' ? 5 : 12
  const options: { value: string; label: string }[] = []
  for (let i = 0; i < count; i++) {
    const d = new Date(now)
    if (period === 'monthly') d.setMonth(d.getMonth() - i)
    else if (period === 'quarterly') d.setMonth(d.getMonth() - i * 3)
    else d.setFullYear(d.getFullYear() - i)
    const anchor = getPeriodStart(period, toISODate(d))
    if (!options.find(o => o.value === anchor))
      options.push({ value: anchor, label: getPeriodLabel(period, anchor) })
  }
  return options
}

const selectStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  borderRadius: 0,
  padding: '6px 20px 6px 4px',
  fontSize: 13,
  fontWeight: 500,
  color: 'var(--text)',
  outline: 'none',
  cursor: 'pointer',
  appearance: 'none',
  WebkitAppearance: 'none',
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath d='M2 3l3 4 3-4' stroke='%2364748b' strokeWidth='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: 'no-repeat',
  backgroundPosition: 'right 2px center',
}

const card: React.CSSProperties = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', padding: 24, boxShadow: 'var(--shadow)',
}

export default function Dashboard() {
  const [data, setData] = useState<SummaryData | null>(null)
  const [recs, setRecs] = useState<RecommendationsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [noData, setNoData] = useState(false)
  const [retryTick, setRetryTick] = useState(0)
  const [period, setPeriod] = useState<PeriodType>('monthly')
  const [periodAnchor, setPeriodAnchor] = useState(() => getPeriodStart('monthly', toISODate(new Date())))
  const [market, setMarket] = useState('')
  const [draftPeriod, setDraftPeriod] = useState<PeriodType>('monthly')
  const [draftAnchor, setDraftAnchor] = useState(() => getPeriodStart('monthly', toISODate(new Date())))
  const [draftMarket, setDraftMarket] = useState('')

  useEffect(() => {
    setLoading(true); setError(null); setNoData(false)
    fetchDashboardInsights({ period, date: periodAnchor, market: market as '' })
      .then(({ summary, recommendations }) => {
        if (summary.period_start === '') { setNoData(true) }
        else { setData(summary); setRecs(recommendations) }
        setLoading(false)
      })
      .catch(err => { setError(err?.message ?? 'Không thể tải dữ liệu.'); setLoading(false) })
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
      <div style={{ textAlign: 'center', background: 'var(--surface)', border: '1px solid #fca5a5', borderRadius: 'var(--radius)', padding: '32px 40px', boxShadow: 'var(--shadow)' }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
        <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>Lỗi tải dữ liệu</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20 }}>{error}</div>
        <button onClick={() => setRetryTick(t => t + 1)} style={{ background: 'var(--accent)', color: '#fff', padding: '8px 20px', borderRadius: 8, fontSize: 14, fontWeight: 600 }}>
          Thử lại
        </button>
      </div>
    </div>
  )

  if (!data) return null

  const totalSignals = data.funnel_distribution.reduce((s, d) => s + d.count, 0)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 24, background: 'var(--bg)' }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', marginBottom: 4, fontFamily: "'Plus Jakarta Sans', sans-serif", letterSpacing: '-0.3px' }}>Customer Insight Overview</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 0 }}>
          Dựa trên <strong style={{ color: 'var(--text)' }}>{totalSignals}</strong> signals
          {data.market && <> · <span style={{ textTransform: 'capitalize' }}>{data.market}</span></>}
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 10 }}>

          {/* Period group */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '2px 10px', boxShadow: 'var(--shadow)' }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--text-muted)', flexShrink: 0, marginRight: 6 }}>
              <rect x="1" y="2" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.4"/>
              <path d="M5 1v2M11 1v2M1 6h14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            <select value={draftPeriod} onChange={e => { const p = e.target.value as PeriodType; setDraftPeriod(p); setDraftAnchor(getPeriodStart(p, toISODate(new Date()))) }} style={selectStyle}>
              {PERIODS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <div style={{ width: 1, height: 16, background: 'var(--border)', margin: '0 8px' }} />
            <select value={draftAnchor} onChange={e => setDraftAnchor(e.target.value)} style={{ ...selectStyle, minWidth: 120 }}>
              {getPeriodOptions(draftPeriod).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>

          {/* Market */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '2px 10px', boxShadow: 'var(--shadow)' }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--text-muted)', flexShrink: 0, marginRight: 6 }}>
              <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4"/>
              <ellipse cx="8" cy="8" rx="2.8" ry="6.5" stroke="currentColor" strokeWidth="1.4"/>
              <path d="M1.5 8h13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            <select value={draftMarket} onChange={e => setDraftMarket(e.target.value)} style={selectStyle}>
              {MARKETS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </div>

          {/* Apply */}
          <button onClick={() => { setPeriod(draftPeriod); setPeriodAnchor(draftAnchor); setMarket(draftMarket) }} style={{ background: 'var(--accent)', color: '#fff', padding: '7px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, boxShadow: 'var(--shadow)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h12M4 8h8M6 12h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
            </svg>
            Apply
          </button>
        </div>
      </div>

      {noData && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 8, padding: '10px 16px', fontSize: 13, color: '#92400e' }}>
          <span>📭 Không có dữ liệu cho khoảng thời gian này. Đang hiển thị dữ liệu gần nhất.</span>
          <button onClick={() => setNoData(false)} style={{ color: '#92400e', fontSize: 16, marginLeft: 12 }}>×</button>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <FunnelDistribution distribution={data.funnel_distribution} summary={data.funnel_summary} />
        <PainPoints topPainPoints={data.top_pain_points} />
      </div>

      <ICPCard narrative={data.icp_narrative} segments={data.icp_summary} />

      {/* Recommendations */}
      <div style={card}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>AI Recommendations</h2>
        {recs?.summary && <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>{recs.summary}</p>}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {([
            { key: 'sales',     label: '🎯 Sales',     items: recs?.sales     ?? [], bg: 'var(--accent-bg)', border: '#bfdbfe', accent: 'var(--accent)' },
            { key: 'marketing', label: '📣 Marketing', items: recs?.marketing ?? [], bg: '#f0fdf4',          border: '#bbf7d0', accent: '#16a34a' },
          ] as const).map(col => (
            <div key={col.key}>
              <div style={{ fontSize: 12, fontWeight: 700, color: col.accent, marginBottom: 10, letterSpacing: '0.03em' }}>{col.label}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {col.items.map((rec, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, padding: '12px 14px', background: col.bg, border: `1px solid ${col.border}`, borderRadius: 8, fontSize: 13, lineHeight: 1.6 }}>
                    <span style={{ background: col.accent, color: '#fff', borderRadius: '50%', width: 20, height: 20, minWidth: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, marginTop: 1, flexShrink: 0 }}>{i + 1}</span>
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
