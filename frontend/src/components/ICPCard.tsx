import type { ICP } from '../types'

const card: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: 24,
  boxShadow: 'var(--shadow)',
}

interface Props {
  narrative: string
  segments: (ICP & { count: number })[]
}

export default function ICPCard({ narrative, segments }: Props) {
  const sorted = [...segments].sort((a, b) => b.count - a.count)

  return (
    <div style={card}>
      <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 12 }}>
        Ideal Customer Profile (ICP)
      </h2>

      {narrative && (
        <div style={{
          marginBottom: 16, padding: '10px 14px',
          background: '#faf5ff', border: '1px solid #ede9fe',
          borderLeft: '3px solid #7c3aed', borderRadius: 7,
          fontSize: 12, fontWeight: 500, color: '#3b0764', lineHeight: 1.6,
        }}>
          <div style={{ fontWeight: 700, fontSize: 11, color: '#7c3aed', marginBottom: 5, letterSpacing: '0.06em' }}>
            ICP ANALYSIS
          </div>
          {narrative}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
        {sorted.map((seg, i) => (
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
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)', textTransform: 'capitalize' }}>
                {seg.sector}
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600 }}>#{i + 1}</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 8px' }}>
              {([
                { label: 'Client type', value: seg.client_type },
                { label: 'Deal size',   value: seg.deal_size },
                { label: 'Market',      value: seg.market },
                { label: 'Tech',        value: seg.tech_maturity },
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

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 8, display: 'flex', alignItems: 'baseline', gap: 5 }}>
              <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)' }}>{seg.count}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>deals</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
