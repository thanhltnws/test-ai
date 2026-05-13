import { useState, useRef, useEffect } from 'react'
import { sendChat } from '../api/lambdas'
import type { ChatMessage, Reference } from '../types'

const SUGGESTED = [
  'Khách hàng hay gặp vấn đề gì nhất?',
  'Phân khúc ICP nào đang có tỷ lệ win cao nhất?',
  'Deal đang ở giai đoạn Consideration có điểm chung gì?',
]


export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send(question: string) {
    if (!question.trim() || loading) return
    const userMsg: ChatMessage = { role: 'user', content: question }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await sendChat(question, messages)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.answer,
        references: res.references,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: err instanceof Error ? err.message : 'Unable to reach the server. Please check the backend.',
      }])
    } finally {
      setLoading(false)
    }
  }

  const lastRefs: Reference[] = [...messages].reverse().find((m: ChatMessage) => m.role === 'assistant')?.references ?? []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{
        padding: '20px 32px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        flexShrink: 0,
      }}>
        <h1 style={{ fontSize: 18, fontWeight: 700 }}>AI Chatbox</h1>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Hỏi bất kỳ câu hỏi nào về customer insights</div>
      </div>

      {/* Body: chat + right panel */}
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
                    borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface)',
                    border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
                    fontSize: 14,
                    lineHeight: 1.7,
                    color: msg.role === 'user' ? '#fff' : 'var(--text)',
                    boxShadow: 'var(--shadow)',
                  }}>
                    {msg.content}
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

        {/* Right: Related Insights */}
        <div style={{
          width: 272,
          minWidth: 272,
          borderLeft: '1px solid var(--border)',
          background: 'var(--surface)',
          overflowY: 'auto',
          padding: '24px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 15 }}>📎</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>Related Insights</span>
          </div>

          {lastRefs.length === 0 ? (
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              color: 'var(--text-muted)',
              textAlign: 'center',
              paddingTop: 40,
            }}>
              <div style={{ fontSize: 32 }}>🔍</div>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>
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
                  padding: '12px 14px',
                  borderLeft: '3px solid var(--accent)',
                }}>
                  <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.5, marginBottom: 8 }}>
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
  )
}

