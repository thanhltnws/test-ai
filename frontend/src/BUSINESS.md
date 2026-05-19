# Business Context — AI Insight Hub Frontend

## Mục tiêu tổng thể

Dashboard này giúp đội Sales và Marketing của một công ty outsourcing IT **hiểu khách hàng nhanh hơn và ra quyết định dựa trên dữ liệu** — thay vì phải đọc thủ công hàng trăm CRM note, email, và transcript mỗi tháng.

Hệ thống không tự thu thập dữ liệu — AI chỉ phân tích sau khi đội ngũ đã ghi nhận vào hệ thống. Dữ liệu càng đầy đủ, insight càng chính xác.

---

## Ai dùng gì

| Người dùng | Dùng phần nào | Mục đích |
|---|---|---|
| Sales Manager | Funnel, Pain Points, Recommendations | Biết pipeline kẹt ở đâu, chuẩn bị objection handling |
| Marketing | ICP Cards, Recommendations | Biết target ai, viết content đúng ngành |
| C-level / Leadership | Toàn bộ Dashboard | Theo dõi xu hướng theo kỳ, ra quyết định chiến lược |
| Tất cả | AI Chat | Hỏi ad-hoc khi cần thông tin ngoài dashboard |

---

## Ý nghĩa từng section

### AI Recommendations

Kết quả AI tổng hợp thành hành động cụ thể — không phải insight chung chung.

- **Sales**: tập trung vào deal nào, xử lý objection nào, ưu tiên segment nào
- **Marketing**: tạo content gì, nhắm đến pain point nào, nurture lead ra sao

Đây là phần nên đọc **đầu tiên** mỗi khi mở dashboard — AI đã đọc toàn bộ dữ liệu và tóm tắt hành động quan trọng nhất.

---

### Funnel Distribution

Cho thấy pipeline đang phân bổ như thế nào theo các giai đoạn: Awareness → Consideration → Negotiation → Won / Lost.

**Đọc thế nào:**
- Nếu Consideration chiếm tỷ lệ lớn → pipeline dồi dào nhưng đang kẹt, cần action để đẩy deal về phía Won
- Nếu Lost cao → cần review lại ICP hoặc objection handling
- Callout bên dưới chart là AI tóm tắt pattern đang thấy trong kỳ đó

---

### Top Pain Points

Các vấn đề khách hàng hay đề cập nhất, tổng hợp từ toàn bộ nguồn dữ liệu trong kỳ.

**Đọc thế nào:**
- Bar dài = pain point phổ biến → nên ưu tiên giải quyết trong pitch
- Hover vào bar hoặc tên để đọc insight chi tiết — AI giải thích tại sao pain point đó quan trọng
- Dùng để chuẩn bị nội dung demo, proposal, và objection handling script

---

### Ideal Customer Profile (ICP)

Cho thấy loại khách hàng nào đang chiếm nhiều deal nhất, phân theo sector, company size, và deal size.

**Đọc thế nào:**
- Card #1 = segment có nhiều deal nhất → đây là "core ICP" đã được market validate
- Dùng để quyết định kênh tiếp cận (outbound hay inbound), loại content, và mức đầu tư per lead
- ICP Analysis callout ở trên giải thích tại sao các segment này lại phù hợp

**Lưu ý quan trọng:** ICP không chỉ để "biết khách hàng là ai" — mà để **biết nên từ chối ai**. Đúng ICP thì margin cao, sai ICP thì delivery vất vả và khó scale.

---

### AI Chat

Dùng khi cần câu trả lời nằm ngoài những gì dashboard hiển thị sẵn.

**Nên hỏi:**
- "Deal đang ở Consideration có điểm chung gì?"
- "Khách hàng ngành fintech hay lo ngại điều gì nhất?"
- "Tháng vừa rồi có objection nào mới không?"

**Không nên kỳ vọng:**
- Số liệu real-time (hệ thống chạy batch theo kỳ)
- Thông tin chưa được ghi nhận vào nguồn dữ liệu

Chat lưu lịch sử trong browser — tối đa 30 sessions, mỗi session gửi 6 tin nhắn gần nhất lên AI để giữ context mà không tốn quá nhiều token.

---

## Cách dùng filter hiệu quả

- **Period type** — chọn Weekly để xem biến động ngắn hạn, Monthly để theo dõi xu hướng, Quarterly/Yearly để review chiến lược
- **Period dropdown** — chọn kỳ cụ thể muốn xem (12 tuần / 12 tháng / 8 quý / 5 năm gần nhất)
- **Market** — lọc theo thị trường nếu cần so sánh Vietnam vs Japan vs Korea
- Nhớ nhấn **Apply** sau khi thay đổi filter — hệ thống không tự động load để tránh gọi API thừa

---

## Giới hạn cần biết

| Giới hạn | Lý do |
|---|---|
| Insight theo kỳ, không real-time | Chạy batch định kỳ để tổng hợp — không stream từng record |
| Chất lượng phụ thuộc vào dữ liệu đầu vào | AI không thể phân tích những gì chưa được ghi nhận |
| Chat không nhớ giữa các session khác nhau | Mỗi session là context độc lập |
| Không tự crawl dữ liệu từ các tool | CRM, email, Jira cần được sync thủ công hoặc qua pipeline |
