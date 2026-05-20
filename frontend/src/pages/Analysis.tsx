const card: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '24px 28px',
  boxShadow: 'var(--shadow)',
};

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
});

const quote: React.CSSProperties = {
  borderLeft: '3px solid var(--accent)',
  paddingLeft: 14,
  color: 'var(--text-muted)',
  fontSize: 14,
  lineHeight: 1.7,
  fontStyle: 'italic',
  margin: '12px 0',
};

const body: React.CSSProperties = {
  fontSize: 14,
  lineHeight: 1.8,
  color: 'var(--text)',
};

const highlight: React.CSSProperties = {
  background: 'var(--accent-bg)',
  border: '1px solid var(--accent-border, #bfdbfe)',
  borderRadius: 10,
  padding: '14px 18px',
  fontSize: 14,
  lineHeight: 1.7,
  color: 'var(--text)',
  marginTop: 12,
};

type BreakSection = { quote: string; body: string };
type BreakItem = {
  id: string;
  color: string;
  title: string;
  sections: BreakSection[];
  highlight?: string;
};

const BREAKS: BreakItem[] = [
  {
    id: 'Break 1',
    color: '#2563eb',
    title: 'Phân mảnh data',
    sections: [
      {
        quote:
          'Giảm sự phân mảnh dữ liệu giữa các bộ phận Sales, Marketing và Vận hành bằng cách tự động thu thập, chuẩn hóa thông tin từ nhiều nguồn hiện có (CRM, Email, Call-note, Form, tool triển khai dự án).',
        body: 'Dữ liệu khách hàng đang nằm rải rác ở nhiều hệ thống khác nhau, không ai tổng hợp lại. Bài toán này giải quyết ở tầng kỹ thuật thuần túy: kéo data về một chỗ, chuẩn hóa schema, loại bỏ trùng lặp.',
      },
    ],
  },
  {
    id: 'Break 2',
    color: '#7c3aed',
    title: 'Chuẩn hóa data',
    sections: [
      {
        quote:
          'Ứng dụng AI để xử lý dữ liệu dạng text và trích xuất các yếu tố cốt lõi như nỗi đau (pain point), nhu cầu, rào cản quyết định mua (objections) và các trường hợp sử dụng thực tế (use cases).',
        body: 'CRM note, email, Teams transcript, Jira/Redmine note là text tự do — ETL không đọc hiểu được. LLM đọc những đoạn text này và extract ra các trường có cấu trúc: pain point, objection, use case, ICP signal. Đây là lý do hệ thống cần AI.',
      },
    ],
    highlight:
      'Đặc biệt: tận dụng insight từ quá trình triển khai dự án của bộ phận Vận hành để bổ sung dữ liệu thực tế cho Marketing và Sales. Ops là bộ phận duy nhất làm việc với khách hàng sau khi ký hợp đồng — khi khách mới nói thật về vấn đề thực sự của họ. Sales và Marketing không có được data này. Đây là điểm phân biệt của hệ thống so với CRM analytics thông thường.',
  },
  {
    id: 'Break 3',
    color: '#16a34a',
    title: 'Insight & Recommendation',
    sections: [
      {
        quote:
          'Hình thành nguồn insight tập trung, phân loại theo market, ICP và funnel stage.',
        body: 'Insight sau khi được extract cần được gắn nhãn để có thể filter và aggregate. Không chỉ biết "khách lo về timeline" mà cần biết "khách fintech, deal size lớn, đang ở giai đoạn negotiation lo về timeline."',
      },
      {
        quote:
          'Cung cấp gợi ý hành động cụ thể cho hoạt động Marketing và Sales.',
        body: 'Output cuối cùng người dùng cần không phải data hay chart — mà là "tôi nên làm gì tiếp theo." Generative AI tổng hợp insight và generate recommendation cụ thể cho từng bộ phận.',
      },
      {
        quote:
          'Kết hợp dashboard theo dõi sự thay đổi insight theo thời gian nhằm hỗ trợ tối ưu hiệu quả tạo lead và chuyển đổi.',
        body: 'Pain point của thị trường thay đổi theo thời gian. Dashboard không chỉ hiển thị trạng thái hiện tại mà còn cho thấy xu hướng — insight nào đang tăng, insight nào đang giảm, segment nào đang shift.',
      },
    ],
  },
];

export default function Analysis() {
  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: 32,
        display: 'flex',
        flexDirection: 'column',
        gap: 28,
        background: 'var(--bg)',
      }}
    >
      {/* Page header */}
      <div>
        <h1
          style={{
            fontSize: 24,
            fontWeight: 800,
            color: 'var(--text)',
            marginBottom: 6,
            fontFamily: "'Plus Jakarta Sans', sans-serif",
            letterSpacing: '-0.3px',
          }}
        >
          Phân tích bài toán
        </h1>
        <p
          style={{ fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.7 }}
        >
          Xây dựng nền tảng AI Insight Hub nhằm giảm sự phân mảnh dữ liệu giữa
          các bộ phận Sales, Marketing và Vận hành bằng cách tự động thu thập,
          chuẩn hóa thông tin từ nhiều nguồn hiện có (CRM, Email, Call-note,
          Form, tool triển khai dự án). Hệ thống ứng dụng AI để xử lý dữ liệu
          dạng text và trích xuất các yếu tố cốt lõi như nỗi đau (pain point),
          nhu cầu, rào cản quyết định mua (objections) và các trường hợp sử dụng
          thực tế (use cases), trong đó đặc biệt tận dụng insight từ quá trình
          triển khai dự án của bộ phận Vận hành để bổ sung dữ liệu thực tế cho
          Marketing và Sales. Trên cơ sở đó, hệ thống hình thành nguồn insight
          tập trung, phân loại theo market, ICP và funnel stage, đồng thời cung
          cấp gợi ý hành động cụ thể cho hoạt động Marketing và Sales, kết hợp
          dashboard theo dõi sự thay đổi insight theo thời gian nhằm hỗ trợ tối
          ưu hiệu quả tạo lead và chuyển đổi.
        </p>
      </div>

      {/* Break problems */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: '#94a3b8',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}
        >
          Bài toán cần giải
        </div>
        {BREAKS.map((b) => (
          <div
            key={b.id}
            style={{ ...card, borderLeft: `3px solid ${b.color}` }}
          >
            <div style={sectionLabel(b.color)}>
              {b.id} · {b.title}
            </div>
            {b.sections.map((s, i) => (
              <div key={i}>
                <div style={quote}>{s.quote}</div>
                <p
                  style={{
                    ...body,
                    marginBottom: i < b.sections.length - 1 ? 16 : 0,
                  }}
                >
                  {s.body}
                </p>
              </div>
            ))}
            {b.highlight && <div style={highlight}>{b.highlight}</div>}
          </div>
        ))}
      </div>

      {/* Solution */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: '#94a3b8',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}
        >
          Giải pháp
        </div>
        {[
          {
            title: '1. AI Transform',
            sub: 'Chuẩn hóa dữ liệu bằng AI',
            text: 'Raw text từ nhiều nguồn (CRM note, email, Teams transcript, Jira/Redmine note) được xử lý qua LLM để extract ra các trường có cấu trúc: pain point, objection, use case, ICP, funnel stage. Output là một Unified Store — nguồn dữ liệu duy nhất, có cấu trúc, sẵn sàng cho downstream query.',
          },
          {
            title: '2. AI Query + RAG',
            sub: 'Insight và khuyến nghị hành động',
            text: 'Dựa trên Unified Store, hệ thống dùng AI kết hợp RAG để trả lời câu hỏi của người dùng bằng ngôn ngữ tự nhiên, đồng thời chạy batch định kỳ để generate insights và recommendations cụ thể cho Sales và Marketing. Thay vì người dùng phải tự đọc data, AI tổng hợp và đưa ra "bước tiếp theo" trực tiếp.',
          },
        ].map((s) => (
          <div key={s.title} style={{ ...card, borderLeft: '3px solid var(--accent)' }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 2 }}>{s.title}</div>
            <div style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 500, marginBottom: 10 }}>{s.sub}</div>
            <p style={{ ...body, fontSize: 13 }}>{s.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
