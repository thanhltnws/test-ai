import { NavLink } from 'react-router-dom'
import Logo from './Logo'

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
  { to: '/ingestion', label: 'Pipeline', icon: (
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

interface Props {
  onOpenWelcome: () => void
}

export default function Navbar({ onOpenWelcome }: Props) {

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


      {/* Footer */}
      <div style={{ marginTop: 'auto', padding: '12px 8px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button
          type="button"
          onClick={onOpenWelcome}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '9px 12px',
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 500,
            background: 'transparent',
            color: 'var(--text-muted)',
            border: 'none',
            cursor: 'pointer',
            width: '100%',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          Phạm vi &amp; kỳ vọng
        </button>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: '0 4px', lineHeight: 1.6 }}>
          Internal Demo · v0.1
          <br />
          Mock data · 27 signals · May 2026
        </div>
      </div>
    </nav>
  )
}
