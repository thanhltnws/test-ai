const card: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '24px 28px',
  boxShadow: 'var(--shadow)',
}

const sectionLabel = (color: string): React.CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  background: color + '15',
  color: color,
  border: `1px solid ${color}30`,
  borderRadius: 6,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.05em',
  textTransform: 'uppercase',
  marginBottom: 12,
})

const quote: React.CSSProperties = {
  borderLeft: '3px solid var(--accent)',
  paddingLeft: 14,
  color: 'var(--text-muted)',
  fontSize: 14,
  lineHeight: 1.7,
  fontStyle: 'italic',
  margin: '12px 0',
}

const body: React.CSSProperties = {
  fontSize: 14,
  lineHeight: 1.8,
  color: 'var(--text)',
}

const highlight: React.CSSProperties = {
  background: 'var(--accent-bg)',
  border: '1px solid #bfdbfe',
  borderRadius: 10,
  padding: '14px 18px',
  fontSize: 14,
  lineHeight: 1.7,
  color: 'var(--text)',
  marginTop: 12,
}

const BREAKS = [
  {
    id: 'Break 1',
    color: '#2563eb',
    title: 'Phân mảnh dữ liệu',
    quote: 'Thống nhất dữ liệu giữa Sales, Marketing và Vận hành bằng cách tự động thu thập và chuẩn hóa thông tin từ các nguồn hiện có: CRM, Email, Call-note, Form và công cụ triển khai dự án.',
    body: 'Dữ liệu khách hàng hiện đang phân tán trên nhiều nền tảng riêng biệt mà không có cơ chế tổng hợp tập trung. Bài toán này được giải quyết ở tầng hạ tầng: thu thập dữ liệu về một kho duy nhất, chuẩn hóa schema và loại bỏ trùng lặp.',
  },
  {
    id: 'Break 2',
    color: '#7c3aed',
    title: 'Chuẩn hóa & Trích xuất',
    quote: 'Ứng dụng AI để xử lý dữ liệu dạng văn bản và trích xuất các yếu tố cốt lõi: pain point, nhu cầu, rào cản quyết định mua (objections) và các trường hợp sử dụng thực tế (use cases).',
    body: 'Call note, email và ops note là văn bản tự do — các pipeline ETL truyền thống không có khả năng đọc hiểu ngữ nghĩa. LLM được sử dụng để phân tích các đoạn text này và trích xuất thành các trường có cấu trúc: pain point, objection, use case, ICP signal.',
    highlight: 'Lợi thế đặc thù: Đội Vận hành là bộ phận duy nhất tiếp xúc trực tiếp với khách hàng sau khi hợp đồng được ký kết — thời điểm khách hàng phản ánh vấn đề thực sự thay vì những gì họ nói trong quá trình đàm phán. Nguồn dữ liệu này thường bị bỏ qua trong các hệ thống CRM analytics thông thường.',
  },
  {
    id: 'Break 3',
    color: '#16a34a',
    title: 'Insight & Recommendation',
    quote: 'Xây dựng kho insight tập trung, phân loại theo market, ICP và funnel stage — làm nền tảng cho các khuyến nghị hành động cụ thể dành cho Sales và Marketing.',
    body: 'Dữ liệu sau khi được trích xuất cần được phân loại theo ngữ cảnh kinh doanh để có giá trị thực tế. Thay vì chỉ ghi nhận "khách hàng lo ngại về timeline", hệ thống xác định: "khách hàng ngành fintech, deal size lớn, tại giai đoạn negotiation, lo ngại về timeline triển khai." Mức độ chi tiết này mới đủ để ra quyết định.',
  },
]

const SCOPE_ITEMS = [
  {
    num: '01',
    title: 'Vai trò của AI trong hệ thống',
    content: [
      'AI trong hệ thống này đóng vai trò processor — phân tích, hiểu và tổng hợp dữ liệu sau khi dữ liệu đã được tập trung. Không phải collector tự động.',
      'Một kỳ vọng phổ biến là AI có thể tự crawl dữ liệu từ mọi nền tảng đang sử dụng. Trên thực tế, điều này không khả thi với nhiều nguồn quan trọng: GA4 không cung cấp raw event data cho bên thứ ba, môi trường Jira của khách hàng nằm trong tenant riêng biệt, phản hồi của Sales nằm trong kênh chat nội bộ.',
      'Với những nguồn này, cần có sự thay đổi quy trình vận hành song song — người phụ trách chủ động ghi nhận thông tin vào hệ thống nội bộ. Đây không phải giới hạn của thiết kế mà là đặc trưng cố hữu của bài toán: dữ liệu có giá trị nhất thường không tồn tại ở dạng có thể tự động thu thập.',
    ],
  },
  {
    num: '02',
    title: 'Điểm khác biệt so với RAG thông thường',
    bullets: [
      {
        label: 'Structured transform thay vì raw embedding',
        text: 'Thay vì embed văn bản thô và tìm kiếm theo độ tương đồng vector, hệ thống dùng AI để trích xuất các trường có cấu trúc — pain_point, objection, funnel_stage, ICP — trước khi lưu trữ. Điều này cho phép filter theo ngữ cảnh kinh doanh thực sự, không chỉ theo mức độ gần nghĩa về mặt ngôn ngữ.',
      },
      {
        label: 'Dual-context retrieval',
        text: 'Mỗi câu hỏi được xử lý qua hai nguồn context độc lập trước khi gọi LLM: SQL query trên structured data cho các câu hỏi định lượng, và semantic search trên vector store cho các câu hỏi mở. Kết hợp cả hai giúp hệ thống xử lý được toàn bộ phổ câu hỏi thực tế của người dùng.',
      },
      {
        label: 'Post-sale signal từ đội Vận hành',
        text: 'CRM chỉ ghi nhận tín hiệu trước khi deal được chốt — những gì khách hàng nói trong quá trình được thuyết phục. Đội Vận hành là bộ phận duy nhất tiếp xúc sau khi ký hợp đồng, khi khách hàng không còn lý do để che giấu vấn đề thực sự. Hệ thống tích hợp nguồn dữ liệu này vào cùng một store với CRM data, cho phép đối chiếu pre-sale signal với post-sale reality.',
      },
    ],
  },
]

export default function Analysis() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 32, display: 'flex', flexDirection: 'column', gap: 28, background: 'var(--bg)' }}>

      {/* Page header */}
      <div>
        <h1 style={{
          fontSize: 24, fontWeight: 800, color: 'var(--text)', marginBottom: 6,
          fontFamily: "'Plus Jakarta Sans', sans-serif", letterSpacing: '-0.3px',
        }}>
          Phân tích bài toán
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-muted)', maxWidth: 720, lineHeight: 1.7 }}>
          AI Insight Hub xây dựng nền tảng dữ liệu khách hàng tập trung cho Sales, Marketing và Vận hành —
          tự động thu thập, chuẩn hóa và tổng hợp insight từ nhiều nguồn để hỗ trợ ra quyết định và tối ưu hiệu quả chuyển đổi.
        </p>
      </div>

      {/* Break problems */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          Bài toán cần giải
        </div>
        {BREAKS.map(b => (
          <div key={b.id} style={{ ...card, borderLeft: `3px solid ${b.color}` }}>
            <div style={sectionLabel(b.color)}>{b.id} · {b.title}</div>
            <div style={quote}>{b.quote}</div>
            <p style={body}>{b.body}</p>
            {b.highlight && <div style={highlight}>{b.highlight}</div>}
          </div>
        ))}
      </div>

      {/* Solution */}
      <div style={card}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16 }}>
          Giải pháp
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {[
            {
              title: '1. AI Transform',
              sub: 'Chuẩn hóa dữ liệu bằng AI',
              text: 'Văn bản thô từ nhiều nguồn (call note, email, ops note) được xử lý qua LLM để trích xuất các trường có cấu trúc: pain point, objection, use case, ICP, funnel stage. Kết quả là một Unified Store — nguồn dữ liệu duy nhất, có cấu trúc, sẵn sàng cho các downstream query và phân tích.',
            },
            {
              title: '2. AI Query + RAG',
              sub: 'Insight và khuyến nghị hành động',
              text: 'Dựa trên Unified Store, hệ thống kết hợp structured query và semantic search để trả lời câu hỏi bằng ngôn ngữ tự nhiên, đồng thời chạy batch định kỳ để tạo khuyến nghị cụ thể cho Sales và Marketing. Người dùng nhận được "bước tiếp theo" thay vì phải tự phân tích raw data.',
            },
          ].map(s => (
            <div key={s.title} style={{
              background: 'var(--surface2)',
              border: '1px solid var(--border)',
              borderRadius: 10,
              padding: '18px 20px',
            }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 2 }}>{s.title}</div>
              <div style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 500, marginBottom: 10 }}>{s.sub}</div>
              <p style={{ ...body, fontSize: 13 }}>{s.text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Scope & expectations */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 }}>
          Phạm vi và kỳ vọng
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          Những điểm dễ bị hiểu sai nếu không được làm rõ — về những gì hệ thống làm được, không làm được, và tại sao thiết kế lại như vậy.
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {SCOPE_ITEMS.map(item => (
            <div key={item.num} style={card}>
              <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                <div style={{
                  fontSize: 20, fontWeight: 800, color: 'var(--accent)', opacity: 0.25,
                  fontFamily: "'Plus Jakarta Sans', sans-serif",
                  lineHeight: 1, flexShrink: 0, paddingTop: 2,
                }}>
                  {item.num}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', marginBottom: 12 }}>{item.title}</div>
                  {item.content && item.content.map((p, i) => (
                    <p key={i} style={{ ...body, marginBottom: i < item.content!.length - 1 ? 10 : 0 }}>{p}</p>
                  ))}
                  {item.bullets && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {item.bullets.map(b => (
                        <div key={b.label} style={{
                          background: 'var(--surface2)',
                          border: '1px solid var(--border)',
                          borderRadius: 8,
                          padding: '12px 16px',
                        }}>
                          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--accent)', marginBottom: 6 }}>
                            {b.label}
                          </div>
                          <p style={{ ...body, fontSize: 13 }}>{b.text}</p>
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

    </div>
  )
}
