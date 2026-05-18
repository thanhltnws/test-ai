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


export default function Dashboard() {
  const [data, setData] = useState<SummaryData | null>(null)
  const [recs, setRecs] = useState<RecommendationsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [period, setPeriod] = useState<PeriodType>('monthly')
  const [periodAnchor, setPeriodAnchor] = useState<string>(() => getPeriodStart('monthly', toISODate(new Date())))
  const [market, setMarket] = useState<string>('')
  const [retryTick, setRetryTick] = useState(0)
  const [draftPeriod, setDraftPeriod] = useState<PeriodType>('monthly')
  const [draftAnchor, setDraftAnchor] = useState<string>(() => getPeriodStart('monthly', toISODate(new Date())))
  const [draftMarket, setDraftMarket] = useState<string>('')
  const [noData, setNoData] = useState(false)
  const [labelTooltip, setLabelTooltip] = useState<{ item: { fullLabel: string; count: number; insight: string }; x: number; y: number } | null>(null)

  const dedupedPainPoints = useMemo(() => {
    if (!data) return []
    const countMap = new Map<string, number>()
    const insightMap = new Map<string, string>()
    for (const p of data.top_pain_points) {
      const key = p.label.toLowerCase().trim().replace(/[.,!?]$/, '')
      countMap.set(key, (countMap.get(key) ?? 0) + p.count)
      if (!insightMap.has(key) && p.insight) insightMap.set(key, p.insight)
    }
    return Array.from(countMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([label, count]) => {
        const full = label.charAt(0).toUpperCase() + label.slice(1)
        return {
          label: full.length > 48 ? full.slice(0, 47) + '…' : full,
          fullLabel: full,
          count,
          insight: insightMap.get(label) ?? '',
        }
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



  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 24, background: 'var(--bg)' }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', marginBottom: 4, fontFamily: "'Plus Jakarta Sans', sans-serif", letterSpacing: '-0.3px' }}>Customer Insight Overview</h1>
        {/* Filter bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {/* Period type */}
          <select
            value={draftPeriod}
            onChange={e => {
              const p = e.target.value as PeriodType
              setDraftPeriod(p)
              setDraftAnchor(getPeriodStart(p, toISODate(new Date())))
            }}
            style={inputStyle}
          >
            {PERIODS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>

          {/* Period dropdown */}
          <select
            value={draftAnchor}
            onChange={e => setDraftAnchor(e.target.value)}
            style={{ ...inputStyle, minWidth: 140 }}
          >
            {getPeriodOptions(draftPeriod).map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Market */}
          <select
            value={draftMarket}
            onChange={e => setDraftMarket(e.target.value)}
            style={inputStyle}
          >
            {MARKETS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>

          {/* Apply */}
          <button
            onClick={() => {
              setPeriod(draftPeriod)
              setPeriodAnchor(draftAnchor)
              setMarket(draftMarket)
            }}
            style={{
              background: 'var(--accent)', color: '#fff',
              padding: '7px 18px', borderRadius: 7, fontSize: 13, fontWeight: 600,
            }}
          >
            Apply
          </button>
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

      {/* Recommendations */}
      <div style={card}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 16 }}>AI Recommendations</h2>
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

      {/* Row: Funnel + Pain Points */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>

        {/* Funnel Distribution */}
        <div style={{ ...card, display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 20 }}>Funnel Distribution</h2>
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
          {data.funnel_summary && (
            <div style={{
              marginTop: 16,
              padding: '10px 14px',
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderLeft: '3px solid #3b82f6',
              borderRadius: 7,
              fontSize: 12,
              fontWeight: 500,
              color: '#1e40af',
              lineHeight: 1.6,
            }}>
              {data.funnel_summary}
            </div>
          )}
        </div>

        {/* Top Pain Points */}
        <div style={{ ...card, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>Top Pain Points</h2>
            <span style={{ fontSize: 11, color: '#2563eb', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 20, padding: '3px 10px', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 500 }}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M8 7v5M8 5.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              Hover for insight
            </span>
          </div>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dedupedPainPoints} layout="vertical" margin={{ left: 0, right: 32 }}>
              <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="label"
                width={310}
                axisLine={false}
                tickLine={false}
                interval={0}
                tick={(props: { x: string | number; y: string | number; index: number; payload: { value: string } }) => {
                  const item = dedupedPainPoints[props.index]
                  return (
                    <text
                      x={props.x} y={props.y} dy={4} textAnchor="end" fill="var(--text)" fontSize={11}
                      style={{ cursor: 'default' }}
                      onMouseEnter={e => item && setLabelTooltip({ item, x: e.clientX, y: e.clientY })}
                      onMouseMove={e => setLabelTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)}
                      onMouseLeave={() => setLabelTooltip(null)}
                    >
                      {props.payload.value}
                    </text>
                  )
                }}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 14px', fontSize: 13, maxWidth: 300 }}>
                      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, lineHeight: 1.4 }}>{d.fullLabel}</div>
                      <div style={{ color: 'var(--text-muted)', marginBottom: d.insight ? 8 : 0 }}>Count: <strong style={{ color: 'var(--text)' }}>{d.count}</strong></div>
                      {d.insight && (
                        <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                          {d.insight}
                        </div>
                      )}
                    </div>
                  )
                }}
              />
              <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ICP — Narrative + Treemap */}
      <div style={card}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 12 }}>Ideal Customer Profile (ICP)</h2>

        {/* Narrative callout */}
        {data.icp_narrative && (
          <div style={{
            marginBottom: 16, padding: '10px 14px',
            background: '#faf5ff', border: '1px solid #ede9fe',
            borderLeft: '3px solid #7c3aed', borderRadius: 7,
            fontSize: 12, fontWeight: 500, color: '#3b0764', lineHeight: 1.6,
          }}>
            <div style={{ fontWeight: 700, fontSize: 11, color: '#7c3aed', marginBottom: 5, letterSpacing: '0.06em' }}>
              ICP ANALYSIS
            </div>
            {data.icp_narrative}
          </div>
        )}

        {/* Segment cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {[...data.icp_summary].sort((a, b) => b.count - a.count).map((seg, i) => (
            <div key={i} style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderLeft: i === 0 ? '3px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 8,
              padding: '12px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)', textTransform: 'capitalize' }}>
                  {seg.sector}
                </div>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>#{i + 1}</span>
              </div>

              {/* Metadata */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 8px' }}>
                {([
                  { label: 'Employees', value: seg.company_size },
                  { label: 'Deal size', value: seg.deal_size },
                  ...(seg.region ? [{ label: 'Region', value: seg.region }] : []),
                ] as { label: string; value: string }[]).map((row, j) => (
                  <div key={j}>
                    <div style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                      {row.label}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500, textTransform: 'capitalize' }}>
                      {row.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Count */}
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 8, display: 'flex', alignItems: 'baseline', gap: 5 }}>
                <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)' }}>{seg.count}</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>deals</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Floating label tooltip for pain point Y-axis */}
      {labelTooltip && (
        <div style={{
          position: 'fixed',
          left: labelTooltip.x + 14,
          top: labelTooltip.y - 10,
          background: '#fff',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 13,
          maxWidth: 300,
          zIndex: 100,
          pointerEvents: 'none',
          boxShadow: 'var(--shadow-md)',
        }}>
          <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, lineHeight: 1.4 }}>{labelTooltip.item.fullLabel}</div>
          <div style={{ color: 'var(--text-muted)', marginBottom: labelTooltip.item.insight ? 8 : 0 }}>Count: <strong style={{ color: 'var(--text)' }}>{labelTooltip.item.count}</strong></div>
          {labelTooltip.item.insight && (
            <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
              {labelTooltip.item.insight}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
