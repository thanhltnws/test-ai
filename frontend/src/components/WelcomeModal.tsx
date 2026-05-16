import { useState } from 'react'

const SCOPE_ITEMS = [
  {
    num: '01',
    title: 'AI làm gì trong hệ thống này?',
    content: [
      'AI đóng vai trò phân tích và tổng hợp — đọc hiểu toàn bộ dữ liệu khách hàng, trích xuất insight có giá trị và đưa ra khuyến nghị hành động cụ thể cho Sales và Marketing. Đây là phần mà con người mất nhiều giờ để làm thủ công.',
      <>Tuy nhiên, <strong>AI không tự động thu thập dữ liệu thay bạn</strong>. Đây là điều quan trọng cần hiểu đúng ngay từ đầu: những cuộc gọi với khách hàng, email trao đổi, hay ghi chú sau buổi demo — AI chỉ phân tích được khi đội ngũ đã ghi nhận vào hệ thống. <strong>Dữ liệu càng đầy đủ, insight càng chính xác.</strong></>,
    ],
  },
  {
    num: '02',
    title: 'Điều gì khiến hệ thống này khác?',
    bullets: [
      {
        label: 'Tìm đúng vấn đề, không chỉ tìm từ khóa',
        text: 'AI đọc hiểu nội dung từng cuộc hội thoại và phân loại thông tin — đây là pain point, đây là lý do từ chối, đây là loại khách hàng nào. Nhờ đó kết quả luôn phù hợp với ngữ cảnh kinh doanh, không chỉ khớp từ khóa.',
      },
      {
        label: 'Trả lời được cả câu hỏi số lẫn câu hỏi mở',
        text: 'Dù bạn hỏi "có bao nhiêu deal đang ở giai đoạn Consideration?" hay "khách hàng hay lo ngại điều gì nhất?", hệ thống đều xử lý được — không giới hạn ở một kiểu câu hỏi duy nhất.',
      },
      {
        label: 'Bao gồm cả phản hồi sau khi ký hợp đồng',
        text: 'CRM chỉ lưu những gì khách hàng nói trong lúc được thuyết phục. Nhưng sau khi ký, họ mới nói thật. Đội Vận hành là người duy nhất nghe được phản hồi đó — hệ thống ghi nhận và đưa vào cùng bức tranh tổng thể.',
      },
    ],
  },
]

export default function WelcomeModal() {
  const [open, setOpen] = useState(true)

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
      onClick={e => { if (e.target === e.currentTarget) setOpen(false) }}
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
                Hệ thống tổng hợp customer insight từ nhiều nguồn — CRM, email, ops note — để hỗ trợ ra quyết định cho Sales và Marketing. Trước khi bắt đầu, hãy đọc qua phạm vi và kỳ vọng dưới đây.
              </p>
            </div>
            <button
              onClick={() => setOpen(false)}
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
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16 }}>
            Phạm vi &amp; kỳ vọng
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
                    {item.content && item.content.map((p, i) => (
                      <p key={i} style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text)', marginBottom: i < item.content!.length - 1 ? 8 : 0 }}>
                        {p}
                      </p>
                    ))}
                    {item.bullets && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {item.bullets.map(b => (
                          <div key={b.label} style={{
                            background: 'var(--surface)',
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            padding: '10px 14px',
                          }}>
                            <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--accent)', marginBottom: 4 }}>{b.label}</div>
                            <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text)' }}>{b.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
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
            onClick={() => setOpen(false)}
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
