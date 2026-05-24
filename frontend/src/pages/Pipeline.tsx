import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchBatchRunLogs,
  fetchIngestionPreview,
  fetchTransformLogs,
  isLambdaDataSource,
  listIngestionFiles,
  triggerBatch,
  triggerIngestionFile,
} from '../api/lambdas'
import type {
  ActivityLogEntry,
  MockFileEntry,
  TriggerStatus,
} from '../types'

const SOURCE_COLORS: Record<string, string> = {
  hubspot: '#f97316',
  twenty_crm: '#8b5cf6',
  redmine: '#ef4444',
  outlook_email: '#0ea5e9',
  teams_transcript: '#6366f1',
  sharepoint: '#10b981',
}

const SOURCE_LABELS: Record<string, string> = {
  hubspot: 'HubSpot',
  twenty_crm: 'Twenty CRM',
  redmine: 'Redmine',
  outlook_email: 'Outlook',
  teams_transcript: 'Teams',
  sharepoint: 'SharePoint',
}

function sourceColor(source: string) {
  return SOURCE_COLORS[source] ?? '#64748b'
}

function nowTime() {
  return new Date().toLocaleTimeString('en-GB', { hour12: false })
}

// ── Flow Diagram ──────────────────────────────────────────────────────────────

type FlowStage = 'idle' | 'ingestion' | 's3' | 'transform' | 'aurora' | 'done'

interface FlowNodeProps {
  label: string
  sublabel?: string
  active: boolean
  done: boolean
  icon: string
}

function FlowNode({ label, sublabel, active, done, icon }: FlowNodeProps) {
  const bg = done ? 'var(--accent)' : active ? '#1e40af' : 'var(--surface-2)'
  const border = active ? '2px solid #3b82f6' : done ? '2px solid var(--accent)' : '1px solid var(--border)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 90 }}>
      <div style={{
        width: 52, height: 52, borderRadius: 12, background: bg, border,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 22, transition: 'all 0.4s',
        boxShadow: active ? '0 0 16px rgba(59,130,246,0.5)' : done ? '0 0 12px rgba(99,102,241,0.3)' : 'none',
      }}>
        {icon}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: done ? 'var(--accent)' : active ? '#93c5fd' : 'var(--text-muted)', textAlign: 'center', lineHeight: 1.3 }}>
        {label}
      </div>
      {sublabel && (
        <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>{sublabel}</div>
      )}
    </div>
  )
}

function Arrow({ active, done }: { active: boolean; done: boolean }) {
  const color = done ? 'var(--accent)' : active ? '#3b82f6' : 'var(--border)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', paddingBottom: 28, flex: '0 0 auto' }}>
      <svg width="40" height="20" viewBox="0 0 40 20">
        <line x1="0" y1="10" x2="32" y2="10" stroke={color} strokeWidth="2" strokeDasharray={active && !done ? '4 3' : undefined}>
          {active && !done && <animate attributeName="stroke-dashoffset" values="14;0" dur="0.5s" repeatCount="indefinite" />}
        </line>
        <polygon points="32,5 40,10 32,15" fill={color} />
      </svg>
    </div>
  )
}

function FlowDiagram({ stage }: { stage: FlowStage }) {
  const s = (name: FlowStage) => stage === name
  const after = (name: FlowStage) => {
    const order: FlowStage[] = ['idle', 'ingestion', 's3', 'transform', 'aurora', 'done']
    return order.indexOf(stage) > order.indexOf(name)
  }
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16,
      padding: '24px 28px', display: 'flex', alignItems: 'center', gap: 0,
      overflowX: 'auto', flexWrap: 'nowrap',
    }}>
      <FlowNode icon="📄" label="Mock File" sublabel="JSON" active={s('ingestion')} done={true} />
      <Arrow active={s('ingestion')} done={after('ingestion')} />
      <FlowNode icon="⚡" label="Ingestion" sublabel="Lambda" active={s('ingestion')} done={after('ingestion')} />
      <Arrow active={s('s3')} done={after('s3')} />
      <FlowNode icon="🪣" label="S3 raw/" sublabel="Object" active={s('s3')} done={after('s3')} />
      <Arrow active={s('transform')} done={after('transform')} />
      <FlowNode icon="🤖" label="Transform" sublabel="Lambda + LLM" active={s('transform')} done={after('transform')} />
      <Arrow active={s('aurora')} done={after('aurora')} />
      <FlowNode icon="🗄️" label="Aurora DB" sublabel="+ pgvector" active={s('aurora')} done={after('aurora')} />
      <Arrow active={s('done')} done={s('done')} />
      <FlowNode icon="📊" label="Dashboard" sublabel="/ Chat" active={s('done')} done={s('done')} />
    </div>
  )
}

// ── Batch Flow Diagram ────────────────────────────────────────────────────────

type BatchFlowStage = 'idle' | 'querying' | 'llm' | 'writing' | 'done'

function BatchFlowDiagram({ stage }: { stage: BatchFlowStage }) {
  const after = (s: BatchFlowStage) => {
    const order: BatchFlowStage[] = ['idle', 'querying', 'llm', 'writing', 'done']
    return order.indexOf(stage) > order.indexOf(s)
  }
  const at = (s: BatchFlowStage) => stage === s
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16,
      padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 0,
      overflowX: 'auto', flexWrap: 'nowrap',
    }}>
      <FlowNode icon="🗄️" label="Aurora DB" sublabel="signals" active={at('querying')} done={after('querying')} />
      <Arrow active={at('querying')} done={after('querying')} />
      <FlowNode icon="⚙️" label="Insights Builder" sublabel="Lambda" active={at('querying') || at('llm') || at('writing')} done={at('done')} />
      <Arrow active={at('llm')} done={after('llm')} />
      <FlowNode icon="🤖" label="LLM" sublabel="Bedrock" active={at('llm')} done={after('llm')} />
      <Arrow active={at('writing')} done={after('writing')} />
      <FlowNode icon="📋" label="insights" sublabel="table" active={at('writing')} done={after('writing')} />
      <Arrow active={at('done')} done={at('done')} />
      <FlowNode icon="📊" label="Dashboard" sublabel="/ Chat" active={at('done')} done={at('done')} />
    </div>
  )
}

// ── JSON Preview Modal ────────────────────────────────────────────────────────

function highlightJson(json: string): string {
  return json.replace(
    /("(?:\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      if (match.endsWith(':')) return `<span style="color:#7dd3fc">${match}</span>`
      if (match.startsWith('"')) return `<span style="color:#86efac">${match}</span>`
      if (match === 'true' || match === 'false') return `<span style="color:#c084fc">${match}</span>`
      if (match === 'null') return `<span style="color:#94a3b8">${match}</span>`
      return `<span style="color:#fb923c">${match}</span>`
    },
  )
}

function JsonPreviewModal({ entry, onClose }: { entry: MockFileEntry; onClose: () => void }) {
  const [records, setRecords] = useState<unknown[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchIngestionPreview(entry.id)
      .then(res => setRecords(res.records))
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [entry.id])

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const color = sourceColor(entry.source)
  const jsonText = records ? JSON.stringify(records, null, 2) : ''

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#0d1117', border: '1px solid var(--border)', borderRadius: 16,
          width: '100%', maxWidth: 780, maxHeight: '82vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 32px 80px rgba(0,0,0,0.6)',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12,
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {entry.label}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3, display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ color, fontWeight: 600 }}>{SOURCE_LABELS[entry.source] ?? entry.source}</span>
              <span>·</span>
              <span>{entry.record_count} records</span>
              <span>·</span>
              <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{entry.file}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', fontSize: 18, padding: '2px 6px',
              lineHeight: 1, borderRadius: 6, flexShrink: 0,
            }}
          >✕</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 20px' }}>
          {loading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 40 }}>Loading…</div>
          ) : error ? (
            <div style={{ color: '#f87171', fontSize: 12, fontFamily: 'monospace', padding: 8 }}>{error}</div>
          ) : !isLambdaDataSource ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 40, lineHeight: 1.7 }}>
              Preview requires a lambda connection.<br />
              <span style={{ fontSize: 11, fontFamily: 'monospace' }}>VITE_DATA_SOURCE=lambda</span>
            </div>
          ) : (
            <pre
              style={{
                margin: 0, fontSize: 12, lineHeight: 1.7,
                color: '#e2e8f0', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
              }}
              dangerouslySetInnerHTML={{ __html: highlightJson(jsonText) }}
            />
          )}
        </div>

        {/* Footer */}
        {!loading && records && isLambdaDataSource && (
          <div style={{
            padding: '9px 20px', borderTop: '1px solid rgba(255,255,255,0.07)',
            display: 'flex', justifyContent: 'space-between',
            fontSize: 11, color: 'var(--text-muted)',
          }}>
            <span>{records.length} records</span>
            <span>{jsonText.length.toLocaleString()} chars</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── File row ──────────────────────────────────────────────────────────────────

interface FileRowProps {
  entry: MockFileEntry
  status: TriggerStatus
  onTrigger: () => void
  onPreview: () => void
}

function FileRow({ entry, status, onTrigger, onPreview }: FileRowProps) {
  const color = sourceColor(entry.source)
  const isLoading = status === 'triggering'
  const isDone = status === 'done'
  const isError = status === 'error'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      borderRadius: 10,
      background: isDone ? 'rgba(99,102,241,0.06)' : 'var(--surface-2)',
      border: isDone ? '1px solid rgba(99,102,241,0.25)' : '1px solid transparent',
      transition: 'all 0.2s',
    }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
        background: isDone ? 'var(--accent)' : isError ? '#ef4444' : isLoading ? '#f59e0b' : color,
        boxShadow: isLoading ? '0 0 8px #f59e0b' : undefined,
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {entry.label}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
          {entry.record_count != null ? `${entry.record_count} records · ` : ''}{entry.description.slice(0, 55)}{entry.description.length > 55 ? '…' : ''}
        </div>
      </div>
      <div style={{
        fontSize: 10, fontWeight: 700, color, background: `${color}1a`,
        borderRadius: 6, padding: '2px 8px', flexShrink: 0,
        textTransform: 'uppercase', letterSpacing: '0.06em',
      }}>
        {SOURCE_LABELS[entry.source] ?? entry.source}
      </div>
      <button
        type="button"
        onClick={onPreview}
        title="Preview JSON"
        style={{
          background: 'none', border: '1px solid var(--border)', cursor: 'pointer',
          color: 'var(--text-muted)', fontSize: 14, borderRadius: 7,
          padding: '4px 8px', lineHeight: 1, flexShrink: 0,
          transition: 'all 0.15s',
        }}
      >
        👁
      </button>
      <button
        type="button"
        onClick={onTrigger}
        disabled={isLoading || isDone}
        style={{
          padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600,
          border: 'none', cursor: isLoading || isDone ? 'not-allowed' : 'pointer',
          background: isDone ? 'var(--surface)' : isError ? '#ef444420' : 'var(--accent)',
          color: isDone ? 'var(--text-muted)' : isError ? '#ef4444' : '#fff',
          opacity: isLoading ? 0.7 : 1, transition: 'all 0.15s',
          flexShrink: 0, minWidth: 78,
        }}
      >
        {isLoading ? 'Running…' : isDone ? '✓ Done' : isError ? 'Retry' : '▶ Trigger'}
      </button>
    </div>
  )
}

// ── Activity log ──────────────────────────────────────────────────────────────

function LogLine({ entry }: { entry: ActivityLogEntry }) {
  const colorMap = { info: '#94a3b8', success: '#34d399', error: '#f87171', warning: '#fbbf24' }
  const textColorMap = { info: '#e2e8f0', success: '#d1fae5', error: '#fecaca', warning: '#fef3c7' }
  const prefixMap = { info: '›', success: '✓', error: '✗', warning: '⚠' }
  return (
    <div style={{ fontSize: 12, lineHeight: 1.6 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <span style={{ flexShrink: 0, color: '#6b7280', fontFamily: 'monospace', fontSize: 11, paddingTop: 1 }}>{entry.ts}</span>
        <span style={{ flexShrink: 0, color: colorMap[entry.level], fontWeight: 700, fontSize: 13, lineHeight: '1.4' }}>{prefixMap[entry.level]}</span>
        <span style={{ color: textColorMap[entry.level], wordBreak: 'break-word' }}>{entry.message}</span>
      </div>
      {entry.detail && (
        <div style={{
          marginTop: 3, marginLeft: 84,
          color: '#9ca3af', fontFamily: 'monospace', fontSize: 10,
          wordBreak: 'break-all', lineHeight: 1.5,
          background: 'rgba(255,255,255,0.04)', borderRadius: 4,
          padding: '3px 7px', borderLeft: '2px solid rgba(255,255,255,0.08)',
        }}>
          {entry.detail}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Pipeline() {
  const [files, setFiles] = useState<MockFileEntry[]>([])
  const [statuses, setStatuses] = useState<Record<string, TriggerStatus>>({})
  const [log, setLog] = useState<ActivityLogEntry[]>([])
  const [flowStage, setFlowStage] = useState<FlowStage>('idle')
  const [loading, setLoading] = useState(true)
  const [previewEntry, setPreviewEntry] = useState<MockFileEntry | null>(null)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchDone, setBatchDone] = useState(false)
  const [batchStage, setBatchStage] = useState<BatchFlowStage>('idle')
  const logScrollRef = useRef<HTMLDivElement>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const seenLogTsRef = useRef<Set<number>>(new Set())

  useEffect(() => () => { if (pollTimerRef.current) clearInterval(pollTimerRef.current) }, [])

  const addLog = useCallback((level: ActivityLogEntry['level'], message: string, detail?: string) => {
    setLog(prev => [...prev, { ts: nowTime(), level, message, detail }])
  }, [])

  useEffect(() => {
    listIngestionFiles()
      .then(res => setFiles(res?.files ?? []))
      .catch(() => addLog('error', 'Failed to load mock files.'))
      .finally(() => setLoading(false))
  }, [addLog])

  useEffect(() => {
    const el = logScrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [log])

  function startLogPolling(since: string) {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    seenLogTsRef.current = new Set()
    let attempts = 0

    pollTimerRef.current = setInterval(async () => {
      attempts++
      if (attempts > 30) {
        clearInterval(pollTimerRef.current!)
        addLog('warning', 'Transform log polling timed out (90s).')
        setFlowStage('idle')
        return
      }
      try {
        const { events } = await fetchTransformLogs(since)
        let finished = false
        for (const e of events) {
          if (seenLogTsRef.current.has(e.ts)) continue
          seenLogTsRef.current.add(e.ts)
          const msg = e.message
          if (msg.startsWith('OK ')) {
            addLog('success', msg)
            setFlowStage('aurora')
            setTimeout(() => { setFlowStage('done'); setTimeout(() => setFlowStage('idle'), 1500) }, 600)
            finished = true
          } else if (msg.startsWith('ERROR ')) {
            addLog('error', msg)
            finished = true
          } else if (msg.startsWith('SKIP ')) {
            addLog('warning', msg)
            finished = true
          } else {
            addLog('info', msg)
          }
        }
        if (finished) clearInterval(pollTimerRef.current!)
      } catch {
        // CloudWatch may not have flushed yet — keep polling
      }
    }, 5000)
  }

  function startBatchLogPolling(since: string) {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current)
    seenLogTsRef.current = new Set()
    let attempts = 0
    let emptyStreak = 0

    pollTimerRef.current = setInterval(async () => {
      attempts++
      if (attempts > 60) {
        clearInterval(pollTimerRef.current!)
        addLog('warning', 'Batch log polling timed out (5 min).')
        setBatchRunning(false)
        return
      }
      try {
        const { events } = await fetchBatchRunLogs(since)
        let hasNew = false
        for (const e of events) {
          if (seenLogTsRef.current.has(e.ts)) continue
          seenLogTsRef.current.add(e.ts)
          hasNew = true
          const msg = e.message.trim()
          if (!msg) continue
          if (msg.includes('wrote=') || msg.includes('embedded=')) {
            setBatchStage('writing')
            addLog('success', msg)
          } else if (msg.includes('prompt=') || msg.includes('llm=')) {
            setBatchStage('llm')
            addLog('info', msg)
          } else if (msg.includes('skip') || msg.includes('SKIP')) {
            addLog('warning', msg)
          } else if (msg.startsWith('ERROR') || msg.includes('Traceback')) {
            addLog('error', msg)
          } else {
            if (batchStage === 'idle') setBatchStage('querying')
            addLog('info', msg)
          }
        }
        if (!hasNew) {
          emptyStreak++
          if (emptyStreak >= 2 && attempts > 3) {
            clearInterval(pollTimerRef.current!)
            addLog('success', 'Batch completed.')
            setBatchRunning(false)
            setBatchDone(true)
            setBatchStage('done')
          }
        } else {
          emptyStreak = 0
        }
      } catch {
        // CloudWatch may not have flushed yet — keep polling
      }
    }, 5000)
  }

  async function handleRunBatch() {
    setBatchRunning(true)
    setBatchDone(false)
    setBatchStage('idle')
    addLog('info', 'Triggering Insights Builder')

    if (!isLambdaDataSource) {
      await new Promise(r => setTimeout(r, 1200))
      addLog('success', 'Mock mode — batch skipped.')
      setBatchRunning(false)
      setBatchDone(true)
      setBatchStage('done')
      return
    }

    const triggerTime = new Date().toISOString()
    triggerBatch()
    addLog('info', 'Lambda triggered — waiting for logs…')
    startBatchLogPolling(triggerTime)
  }

  async function handleTrigger(entry: MockFileEntry) {
    setStatuses(prev => ({ ...prev, [entry.id]: 'triggering' }))
    addLog('info', `Triggering ${entry.label}…`)

    if (!isLambdaDataSource) {
      try {
        const result = await triggerIngestionFile(entry.id)
        setStatuses(prev => ({ ...prev, [entry.id]: 'done' }))
        addLog('success', result.note ?? 'Done.')
      } catch (err) {
        setStatuses(prev => ({ ...prev, [entry.id]: 'error' }))
        addLog('error', `Trigger failed for ${entry.id}.`, err instanceof Error ? err.message : String(err))
      }
      return
    }

    const stageDelay = (ms: number) => new Promise(r => setTimeout(r, ms))
    setFlowStage('ingestion')

    try {
      await stageDelay(400)
      setFlowStage('s3')
      addLog('info', `Pushing to S3 raw/${entry.source}/…`)
      await stageDelay(400)

      const triggerTime = new Date().toISOString()
      const result = await triggerIngestionFile(entry.id)

      setStatuses(prev => ({ ...prev, [entry.id]: 'done' }))
      setFlowStage('transform')
      addLog('success', `Pushed to S3.`, result.s3_uri)
      addLog('info', 'Transforming… (waiting for Lambda)')
      startLogPolling(triggerTime)
    } catch (err) {
      setFlowStage('idle')
      setStatuses(prev => ({ ...prev, [entry.id]: 'error' }))
      addLog('error', `Trigger failed for ${entry.id}.`, err instanceof Error ? err.message : String(err))
    }
  }

  const bySource: Record<string, MockFileEntry[]> = {}
  for (const f of files) {
    if (!bySource[f.source]) bySource[f.source] = []
    bySource[f.source].push(f)
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 24 }}>
      {previewEntry && <JsonPreviewModal entry={previewEntry} onClose={() => setPreviewEntry(null)} />}

      {/* Header */}
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', margin: 0 }}>Data Pipeline</h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '4px 0 0' }}>
          Trigger ingestion từ mock files và chạy Insights Builder để tổng hợp insights.
        </p>
      </div>

      {/* Two-column layout: left all content + right Activity Log */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 28, alignItems: 'start' }}>

        {/* Left: all sections */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* 1 · Ingestion */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#94a3b8' }}>
              1 · Ingestion
            </div>
            <FlowDiagram stage={flowStage} />
          </div>

          {/* File list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {loading ? (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>Loading files…</div>
            ) : (
              Object.entries(bySource).map(([source, entries]) => (
                <div key={source}>
                  <div style={{
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: sourceColor(source), marginBottom: 8, paddingLeft: 4,
                  }}>
                    {SOURCE_LABELS[source] ?? source}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {entries.map(entry => (
                      <FileRow
                        key={entry.id}
                        entry={entry}
                        status={statuses[entry.id] ?? 'idle'}
                        onTrigger={() => handleTrigger(entry)}
                        onPreview={() => setPreviewEntry(entry)}
                      />
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* 2 · Insights Builder */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#94a3b8' }}>
              2 · Insights Builder
            </div>
            <BatchFlowDiagram stage={batchStage} />
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>Run Batch</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                  Tổng hợp insights từ signals đã ingested.
                </div>
              </div>
              <button
                type="button"
                onClick={handleRunBatch}
                disabled={batchRunning}
                style={{
                  alignSelf: 'flex-start',
                  padding: '7px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                  border: 'none', cursor: batchRunning ? 'not-allowed' : 'pointer',
                  background: batchDone ? 'var(--surface)' : 'var(--accent)',
                  color: batchDone ? 'var(--text-muted)' : '#fff',
                  opacity: batchRunning ? 0.7 : 1,
                  transition: 'all 0.15s',
                }}
              >
                {batchRunning ? '⏳ Running…' : batchDone ? '✓ Done' : '▶ Run Batch'}
              </button>
              {batchRunning && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Lambda đang xử lý — có thể mất vài phút…
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Right: Activity Log — sticky alongside all content */}
        <div style={{ position: 'sticky', top: 24, marginTop: 24 }}>
          <div style={{
            background: '#111827', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 14,
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            maxHeight: 'calc(100vh - 80px)',
          }}>
            <div style={{
              padding: '12px 16px 10px', borderBottom: '1px solid rgba(255,255,255,0.08)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: 'rgba(99,102,241,0.08)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#4ade80', boxShadow: '0 0 6px #4ade80' }} />
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#e2e8f0' }}>
                  Activity Log
                </span>
              </div>
              {log.length > 0 && (
                <button
                  type="button"
                  onClick={() => setLog([])}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', fontSize: 11, padding: '2px 6px', borderRadius: 4 }}
                >
                  Clear
                </button>
              )}
            </div>
            <div
              ref={logScrollRef}
              style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 4, minHeight: 200 }}
            >
              {log.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: 12, fontStyle: 'italic', lineHeight: 1.6 }}>
                  Trigger a file or run batch to see activity here…
                </div>
              ) : (
                log.map((entry, i) => <LogLine key={i} entry={entry} />)
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
