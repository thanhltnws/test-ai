import { PieChart, Pie, Legend, Tooltip, ResponsiveContainer } from 'recharts'

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
  display: 'flex',
  flexDirection: 'column',
}

interface Props {
  distribution: { stage: string; count: number; pct: number }[]
  summary: string
}

function FunnelTooltip({ active, payload }: { active?: boolean; payload?: { payload: { stage: string; count: number; pct: number } }[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: '#fff',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 6, textTransform: 'capitalize' }}>
        {d.stage}
      </div>
      <div style={{ color: 'var(--text-muted)', display: 'flex', gap: 12 }}>
        <span>Count: <strong style={{ color: 'var(--text)' }}>{d.count}</strong></span>
        <span>Share: <strong style={{ color: 'var(--text)' }}>{d.pct}%</strong></span>
      </div>
    </div>
  )
}

export default function FunnelDistribution({ distribution, summary }: Props) {
  const chartData = distribution.map(d => ({
    ...d,
    fill: FUNNEL_COLORS[d.stage] ?? '#93c5fd',
  }))

  return (
    <div style={card}>
      <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 20 }}>
        Funnel Distribution
      </h2>
      <ResponsiveContainer width="100%" height={230}>
        <PieChart>
          <Pie
            data={chartData}
            dataKey="count"
            nameKey="stage"
            cx="50%"
            cy="50%"
            outerRadius={85}
            innerRadius={40}
          />
          <Legend
            formatter={(value) => (
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{value}</span>
            )}
          />
          <Tooltip content={<FunnelTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      {summary && (
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
          {summary}
        </div>
      )}
    </div>
  )
}
