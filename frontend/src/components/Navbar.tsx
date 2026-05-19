import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { isLambdaDataSource, runBatch } from '../api/lambdas'
import AccessTokenControl from './AccessTokenControl'
import Logo from './Logo'

const batchTriggerEnabled = false

const links = [
  { to: '/', label: 'Overview', icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
      <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
    </svg>
  )},
  { to: '/chat', label: 'AI Chat', icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  )},
  { to: '/ingestion', label: 'Ingestion', icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  )},
  { to: '/analysis', label: 'About', icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  )},
]

export default function Navbar() {
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchMessage, setBatchMessage] = useState<string | null>(null)

  async function handleRunBatch() {
    if (!batchTriggerEnabled) return
    setBatchLoading(true)
    setBatchMessage(null)
    try {
      const result = await runBatch()
      const written = result.written ?? 0
      const periodStart = result.period_start ? ` for ${result.period_start}` : ''
      setBatchMessage(`Done${periodStart}. ${written} rows written.`)
    } catch (err) {
      setBatchMessage(err instanceof Error ? err.message : 'Batch run failed.')
    } finally {
      setBatchLoading(false)
    }
  }

  return (
    <nav style={{
      width: 240,
      minWidth: 240,
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      padding: '20px 16px',
      gap: 4,
      boxShadow: 'var(--shadow)',
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 28, padding: '4px 8px' }}>
        <Logo size={32} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', lineHeight: 1.2 }}>AI Insight Hub</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Customer Intelligence</div>
        </div>
      </div>

      <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase', padding: '0 8px', marginBottom: 4 }}>
        Navigation
      </div>

      {links.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end
          style={({ isActive }) => ({
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '9px 12px',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 500,
            background: isActive ? 'var(--accent-bg)' : 'transparent',
            color: isActive ? 'var(--accent)' : 'var(--text-muted)',
            transition: 'all 0.15s',
          })}
        >
          {icon}
          {label}
        </NavLink>
      ))}

      <AccessTokenControl />

      {isLambdaDataSource && (
        <div style={{ padding: '12px 8px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Batch
          </div>
          <button
            type="button"
            onClick={handleRunBatch}
            disabled={!batchTriggerEnabled || batchLoading}
            style={{
              width: '100%',
              background: 'var(--accent)',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '8px 10px',
              fontSize: 12,
              fontWeight: 600,
              opacity: !batchTriggerEnabled || batchLoading ? 0.45 : 1,
              cursor: batchTriggerEnabled && !batchLoading ? 'pointer' : 'not-allowed',
            }}
          >
            {batchLoading ? 'Running...' : 'Run Batch'}
          </button>
          <div style={{ fontSize: 11, color: batchMessage?.includes('failed') ? '#dc2626' : 'var(--text-muted)', lineHeight: 1.4 }}>
            {batchMessage ?? 'Manual batch trigger temporarily disabled.'}
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ marginTop: 'auto', padding: '12px 8px', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Internal Demo · v0.1</div>
      </div>
    </nav>
  )
}
