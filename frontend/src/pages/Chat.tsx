import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { sendChat } from '../api/lambdas'
import { useChatHistory } from '../hooks/useChatHistory'
import type { ChatMessage, Reference } from '../types'

const SUGGESTED = [
  'Gần đây objection nào xuất hiện nhiều nhất?',
  'Fintech sector đang gặp vấn đề gì tháng này?',
  'Retail market đang cần hỗ trợ gì tháng này?',
  'Khách ở consideration stage đang quan tâm điều gì tháng này?',
  'Thị trường Korea đang gặp pain point gì nổi bật nhất tháng này?',
]

function formatDate(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const { sessions, createSession, updateSession, deleteSession } = useChatHistory()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function startNewChat() {
    setMessages([])
    setActiveSessionId(null)
    setInput('')
  }

  function restoreSession(id: string) {
    const session = sessions.find(s => s.id === id)
    if (!session) return
    setMessages(session.messages)
    setActiveSessionId(id)
    setInput('')
  }

  async function send(question: string) {
    if (!question.trim() || loading) return
    const userMsg: ChatMessage = { role: 'user', content: question }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    const sessionId = activeSessionId ?? crypto.randomUUID()
    if (!activeSessionId) setActiveSessionId(sessionId)

    try {
      const res = await sendChat(question, sessionId)
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: res.answer,
        references: res.references,
      }
      const finalMessages = [...nextMessages, assistantMsg]
      setMessages(finalMessages)

      if (activeSessionId) {
        updateSession(activeSessionId, finalMessages)
      } else {
        createSession(finalMessages, sessionId)
      }
    } catch (err) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: err instanceof Error ? err.message : 'Unable to reach the server. Please check the backend.',
      }
      setMessages([...nextMessages, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const lastRefs: Reference[] = [...messages].reverse().find((m: ChatMessage) => m.role === 'assistant')?.references ?? []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{
        padding: '16px 24px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div>
          <h1 style={{ fontSize: 16, fontWeight: 700 }}>AI Chatbox</h1>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Hỏi bất kỳ câu hỏi nào về customer insights</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={startNewChat}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--accent)',
              color: '#fff',
              padding: '7px 14px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            + New Chat
          </button>
          <button
            onClick={() => setSidebarOpen(o => !o)}
            title={sidebarOpen ? 'Collapse sidebar' : 'Open sidebar'}
            style={{
              width: 34, height: 34,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--surface2)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              color: 'var(--text-muted)',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="2" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.4"/>
              <line x1="10" y1="2" x2="10" y2="14" stroke="currentColor" strokeWidth="1.4"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Chat area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '28px 28px 28px 32px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {messages.length === 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, marginTop: 48 }}>
                  <div style={{ fontSize: 36, marginBottom: 4 }}>💬</div>
                  <div style={{ fontWeight: 600, fontSize: 16, color: 'var(--text)' }}>Hỏi về Customer Insights</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 12 }}>
                    Gợi ý câu hỏi để bắt đầu:
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 440 }}>
                    {SUGGESTED.map(q => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        style={{
                          background: 'var(--surface)',
                          border: '1px solid var(--border)',
                          borderRadius: 10,
                          padding: '11px 16px',
                          fontSize: 14,
                          textAlign: 'left',
                          color: 'var(--text)',
                          transition: 'all 0.15s',
                          boxShadow: 'var(--shadow)',
                        }}
                        onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.background = 'var(--accent-bg)' }}
                        onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--surface)' }}
                      >
                        <span style={{ marginRight: 8, color: 'var(--accent)' }}>→</span>{q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div style={{
                    maxWidth: '80%',
                    padding: '12px 16px',
                    borderRadius: 12,
                    background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface)',
                    border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
                    fontSize: 14,
                    lineHeight: 1.7,
                    color: msg.role === 'user' ? '#fff' : 'var(--text)',
                    boxShadow: 'var(--shadow)',
                    wordBreak: 'break-word',
                    overflowWrap: 'break-word',
                    minWidth: 0,
                  }}>
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p style={{ margin: '0 0 8px 0' }}>{children}</p>,
                          ul: ({ children }) => <ul style={{ margin: '4px 0', paddingLeft: 20 }}>{children}</ul>,
                          ol: ({ children }) => <ol style={{ margin: '4px 0', paddingLeft: 20 }}>{children}</ol>,
                          li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
                          strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
                          code: ({ children }) => (
                            <code style={{
                              background: 'var(--surface2)',
                              border: '1px solid var(--border)',
                              borderRadius: 4,
                              padding: '1px 5px',
                              fontSize: 12,
                              fontFamily: 'monospace',
                              wordBreak: 'break-all',
                            }}>{children}</code>
                          ),
                          pre: ({ children }) => (
                            <pre style={{
                              background: 'var(--surface2)',
                              border: '1px solid var(--border)',
                              borderRadius: 8,
                              padding: '10px 14px',
                              fontSize: 12,
                              fontFamily: 'monospace',
                              overflowX: 'auto',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-all',
                              margin: '8px 0',
                            }}>{children}</pre>
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    ) : msg.content}
                  </div>
                </div>
              ))}

              {loading && (
                <div style={{
                  alignSelf: 'flex-start',
                  padding: '12px 16px',
                  borderRadius: '16px 16px 16px 4px',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  fontSize: 14,
                  color: 'var(--text-muted)',
                  boxShadow: 'var(--shadow)',
                }}>
                  Đang xử lý...
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </div>

          {/* Input */}
          <div style={{
            padding: '14px 28px 14px 32px',
            borderTop: '1px solid var(--border)',
            background: 'var(--surface)',
            display: 'flex',
            gap: 10,
            flexShrink: 0,
          }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send(input)}
              placeholder="Nhập câu hỏi về customer insights..."
              style={{
                flex: 1,
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 16px',
                fontSize: 14,
                color: 'var(--text)',
                outline: 'none',
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={loading || !input.trim()}
              style={{
                background: 'var(--accent)',
                color: '#fff',
                padding: '10px 20px',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                opacity: loading || !input.trim() ? 0.5 : 1,
                transition: 'opacity 0.15s',
              }}
            >
              Gửi
            </button>
          </div>
        </div>

        {/* Right panel: History (top) + Related Signals (bottom) */}
        <div style={{
          width: sidebarOpen ? 272 : 0,
          minWidth: sidebarOpen ? 272 : 0,
          borderLeft: sidebarOpen ? '1px solid var(--border)' : 'none',
          background: 'var(--surface2)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          transition: 'width 0.2s ease, min-width 0.2s ease',
        }}>

          {/* History — top half */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderBottom: '1px solid var(--border)' }}>
            <div style={{ padding: '14px 16px 8px', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: 14 }}>🕐</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>History</span>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 10px' }}>
              {sessions.length === 0 ? (
                <div style={{ padding: '16px 8px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
                  No past conversations yet
                </div>
              ) : (
                sessions.map(session => (
                  <div
                    key={session.id}
                    className="history-item"
                    onClick={() => restoreSession(session.id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 10,
                      marginBottom: 6,
                      cursor: 'pointer',
                      background: activeSessionId === session.id ? 'var(--accent-bg)' : 'var(--surface)',
                      border: activeSessionId === session.id ? '1px solid #bfdbfe' : '1px solid var(--border)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      boxShadow: 'var(--shadow)',
                    }}
                    onMouseOver={e => {
                      if (activeSessionId !== session.id) {
                        (e.currentTarget as HTMLDivElement).style.background = 'var(--accent-bg)'
                        const btn = e.currentTarget.querySelector('.delete-btn') as HTMLElement
                        if (btn) btn.style.opacity = '1'
                      }
                    }}
                    onMouseOut={e => {
                      if (activeSessionId !== session.id) {
                        (e.currentTarget as HTMLDivElement).style.background = 'var(--surface)'
                        const btn = e.currentTarget.querySelector('.delete-btn') as HTMLElement
                        if (btn) btn.style.opacity = '0'
                      }
                    }}
                  >
                    <span style={{ fontSize: 13, flexShrink: 0, marginTop: 1 }}>💬</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{
                        fontSize: 12,
                        color: activeSessionId === session.id ? 'var(--accent)' : 'var(--text)',
                        fontWeight: 500,
                        lineHeight: 1.4,
                        overflow: 'hidden',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }}>
                        {session.title}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
                        {formatDate(session.createdAt)}
                      </div>
                    </div>
                    <button
                      className="delete-btn"
                      onClick={e => {
                        e.stopPropagation()
                        deleteSession(session.id)
                        if (activeSessionId === session.id) startNewChat()
                      }}
                      style={{
                        flexShrink: 0,
                        fontSize: 14,
                        color: 'var(--text-muted)',
                        padding: '0 3px',
                        borderRadius: 4,
                        lineHeight: 1,
                        opacity: activeSessionId === session.id ? 1 : 0,
                        transition: 'opacity 0.15s',
                      }}
                      title="Delete"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Related Signals — bottom half */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px 8px', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
              <span style={{ fontSize: 14 }}>📌</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Related Signals</span>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 16px' }}>
              {lastRefs.length === 0 ? (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  color: 'var(--text-muted)',
                  textAlign: 'center',
                  paddingTop: 24,
                }}>
                  <div style={{ fontSize: 28 }}>🔍</div>
                  <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                    Context liên quan sẽ hiện ở đây sau khi AI trả lời
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {lastRefs.map((ref, i) => (
                    <div key={i} style={{
                      background: 'var(--surface2)',
                      border: '1px solid var(--border)',
                      borderRadius: 10,
                      padding: '10px 12px',
                      borderLeft: '3px solid var(--accent)',
                    }}>
                      <div style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.5, marginBottom: 6 }}>
                        "{ref.title}"
                      </div>
                      <a
                        href={ref.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          fontSize: 11,
                          color: 'var(--accent)',
                          fontWeight: 500,
                          wordBreak: 'break-all',
                        }}
                      >
                        {ref.url}
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
