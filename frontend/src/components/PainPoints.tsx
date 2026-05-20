import { useState, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const card: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: 24,
  boxShadow: 'var(--shadow)',
  display: 'flex',
  flexDirection: 'column',
}

type PainPointItem = { label: string; count: number; insight: string }
type DedupedItem = { label: string; fullLabel: string; count: number; insight: string }

interface Props {
  topPainPoints: PainPointItem[]
}

function BarTooltip({ active, payload }: { active?: boolean; payload?: { payload: DedupedItem }[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 14px', fontSize: 13, maxWidth: 300 }}>
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, lineHeight: 1.4 }}>{d.fullLabel}</div>
      <div style={{ color: 'var(--text-muted)', marginBottom: d.insight ? 8 : 0 }}>
        Count: <strong style={{ color: 'var(--text)' }}>{d.count}</strong>
      </div>
      {d.insight && (
        <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
          {d.insight}
        </div>
      )}
    </div>
  )
}

export default function PainPoints({ topPainPoints }: Props) {
  const [labelTooltip, setLabelTooltip] = useState<{ item: DedupedItem; x: number; y: number } | null>(null)

  const dedupedPainPoints = useMemo(() => {
    const countMap = new Map<string, number>()
    const insightMap = new Map<string, string>()
    for (const p of topPainPoints) {
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
  }, [topPainPoints])

  return (
    <>
      <div style={card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>Top Pain Points</h2>
          <span style={{
            fontSize: 11, color: '#2563eb', background: '#eff6ff',
            border: '1px solid #bfdbfe', borderRadius: 20, padding: '3px 10px',
            display: 'flex', alignItems: 'center', gap: 4, fontWeight: 500,
          }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 7v5M8 5.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
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
            <Tooltip content={<BarTooltip />} />
            <Bar dataKey="count" fill="var(--accent)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

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
          <div style={{ color: 'var(--text-muted)', marginBottom: labelTooltip.item.insight ? 8 : 0 }}>
            Count: <strong style={{ color: 'var(--text)' }}>{labelTooltip.item.count}</strong>
          </div>
          {labelTooltip.item.insight && (
            <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
              {labelTooltip.item.insight}
            </div>
          )}
        </div>
      )}
    </>
  )
}
