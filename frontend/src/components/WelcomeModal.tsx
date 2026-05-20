const SCOPE_ITEMS = [
  {
    num: '01',
    title: 'AI đóng vai trò gì trong hệ thống?',
    content: [
      <>AI ở đây là <strong>bộ phân tích</strong>, không phải bộ thu thập. Khi dữ liệu đã được tập trung về một chỗ, AI đọc hiểu nội dung, trích xuất pain point, objection, use case và ICP signal — rồi đưa ra khuyến nghị cụ thể cho Sales và Marketing.</>,
      <><strong>AI không tự kéo dữ liệu từ các platform bạn đang dùng.</strong> Việc thu thập dữ liệu được giả định là khả thi thông qua các cơ chế như polling, crawl hoặc data sources chủ động push dữ liệu vào hệ thống.</>,
    ],
  },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function WelcomeModal({ open, onClose }: Props) {
  if (!open) return null

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.45)',
      zIndex: 1000,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 24,
    }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--surface)',
        borderRadius: 'var(--radius)',
        boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
        width: '100%',
        maxWidth: 640,
        maxHeight: '88vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>

        {/* Header */}
        <div style={{
          padding: '28px 32px 20px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                AI Insight Hub
              </div>
              <h2 style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', marginBottom: 8, fontFamily: "'Plus Jakarta Sans', sans-serif", letterSpacing: '-0.3px' }}>
                Chào mừng bạn
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, maxWidth: 480 }}>
                Hệ thống thu thập insight từ CRM note, email, Teams transcript, Jira/Redmine note — dùng AI extract pain point, objection, use case, ICP signal — rồi surface qua dashboard và RAG chatbox để hỗ trợ Sales và Marketing ra quyết định. Trước khi bắt đầu, hãy đọc qua phạm vi và kỳ vọng dưới đây.
              </p>
            </div>
            <button
              onClick={onClose}
              style={{
                flexShrink: 0,
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                fontSize: 18,
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 32px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              Phạm vi &amp; kỳ vọng
            </div>
            <div style={{ fontSize: 11, color: '#cbd5e1' }}>
              docs/scope.md
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {SCOPE_ITEMS.map(item => (
              <div key={item.num} style={{
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                borderRadius: 10,
                padding: '16px 20px',
              }}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                  <div style={{
                    fontSize: 18,
                    fontWeight: 800,
                    color: 'var(--accent)',
                    opacity: 0.3,
                    fontFamily: "'Plus Jakarta Sans', sans-serif",
                    lineHeight: 1,
                    flexShrink: 0,
                    paddingTop: 2,
                  }}>
                    {item.num}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 10 }}>
                      {item.title}
                    </div>
                    {item.content.map((p, i) => (
                      <p key={i} style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text)', marginBottom: i < item.content.length - 1 ? 8 : 0 }}>
                        {p}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 32px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            style={{
              background: 'var(--accent)',
              color: '#fff',
              padding: '9px 24px',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Đã hiểu, bắt đầu
          </button>
        </div>

      </div>
    </div>
  )
}
