import { useState } from 'react'
import { getAuthToken, isLambdaDataSource, setAuthToken } from '../api/lambdas'

export default function AccessTokenControl() {
  const [savedToken, setSavedToken] = useState(() => getAuthToken())
  const [draftToken, setDraftToken] = useState(savedToken)
  const [status, setStatus] = useState(savedToken ? 'Saved' : 'Not set')

  if (!isLambdaDataSource) return null

  const hasUnsavedChanges = draftToken.trim() !== savedToken

  return (
    <div style={{ marginTop: 16, padding: '12px 8px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        Live Access
      </div>
      <input
        type="password"
        value={draftToken}
        onChange={e => {
          setDraftToken(e.target.value)
          setStatus('Unsaved')
        }}
        placeholder="Access token"
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: 'var(--surface2)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '8px 10px',
          fontSize: 12,
          color: 'var(--text)',
          outline: 'none',
        }}
      />
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={() => {
            const value = draftToken.trim()
            setAuthToken(value)
            setSavedToken(value)
            setDraftToken(value)
            setStatus(value ? 'Saved' : 'Not set')
          }}
          disabled={!hasUnsavedChanges}
          style={{
            flex: 1,
            background: 'var(--accent)',
            border: '1px solid var(--accent)',
            color: '#fff',
            borderRadius: 8,
            padding: '7px 10px',
            fontSize: 12,
            fontWeight: 600,
            opacity: hasUnsavedChanges ? 1 : 0.5,
          }}
        >
          Save
        </button>
        <button
          onClick={() => {
            setAuthToken('')
            setSavedToken('')
            setDraftToken('')
            setStatus('Cleared')
          }}
          style={{
            flex: 1,
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
            color: 'var(--text-muted)',
            borderRadius: 8,
            padding: '7px 10px',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          Clear
        </button>
      </div>
      <div style={{
        fontSize: 11,
        color: status === 'Unsaved' ? '#d97706' : 'var(--text-muted)',
        lineHeight: 1.4,
      }}>
        {status === 'Saved' ? 'Token saved for this browser.' : status}
      </div>
    </div>
  )
}
