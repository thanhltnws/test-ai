# AI Insight Hub — Phân tích bài toán

---

## Break 1 · Phân mảnh data

> Giảm sự phân mảnh dữ liệu giữa các bộ phận Sales, Marketing và Vận hành bằng cách tự động thu thập, chuẩn hóa thông tin từ nhiều nguồn hiện có (CRM, Email, Call-note, Form, tool triển khai dự án)

Dữ liệu khách hàng đang nằm rải rác ở nhiều hệ thống khác nhau, không ai tổng hợp lại. Bài toán này giải quyết ở tầng kỹ thuật thuần túy: kéo data về một chỗ, chuẩn hóa schema, loại bỏ trùng lặp.

---

## Break 2 · Chuẩn hóa data

> Ứng dụng AI để xử lý dữ liệu dạng text và trích xuất các yếu tố cốt lõi như nỗi đau (pain point), nhu cầu, rào cản quyết định mua (objections) và các trường hợp sử dụng thực tế (use cases)

Call note, email, ops note là text tự do — ETL không đọc hiểu được. LLM đọc những đoạn text này và extract ra các trường có cấu trúc: pain point, objection, use case, ICP signal. Đây là lý do hệ thống cần AI.

> **Đặc biệt:** tận dụng insight từ quá trình triển khai dự án của bộ phận Vận hành để bổ sung dữ liệu thực tế cho Marketing và Sales

Ops là bộ phận duy nhất làm việc với khách hàng **sau khi ký hợp đồng** — khi khách mới nói thật về vấn đề thực sự của họ. Sales và Marketing không có được data này. Đây là điểm phân biệt của hệ thống so với CRM analytics thông thường.

---

## Break 3 · Insight & Recommendation

> Hình thành nguồn insight tập trung, phân loại theo market, ICP và funnel stage

Insight sau khi được extract cần được gắn nhãn để có thể filter và aggregate. Không chỉ biết "khách lo về timeline" mà cần biết "khách fintech, deal size lớn, đang ở giai đoạn negotiation lo về timeline."

> Cung cấp gợi ý hành động cụ thể cho hoạt động Marketing và Sales

Output cuối cùng người dùng cần không phải data hay chart — mà là "tôi nên làm gì tiếp theo." Generative AI tổng hợp insight và generate recommendation cụ thể cho từng bộ phận.

> Kết hợp dashboard theo dõi sự thay đổi insight theo thời gian nhằm hỗ trợ tối ưu hiệu quả tạo lead và chuyển đổi

Pain point của thị trường thay đổi theo thời gian. Dashboard không chỉ hiển thị trạng thái hiện tại mà còn cho thấy xu hướng — insight nào đang tăng, insight nào đang giảm, segment nào đang shift.

---

## Giải pháp

### 1. AI Transform — chuẩn hóa data bằng AI

Raw text từ nhiều nguồn (call note, email, ops note) được xử lý qua LLM để extract ra các trường có cấu trúc: pain point, objection, use case, ICP, funnel stage. Output là một Unified store — nguồn dữ liệu duy nhất, có cấu trúc, sẵn sàng cho downstream query.

### 2. AI Query + RAG — tìm ra insight và recommendation

Dựa trên Unified store, hệ thống dùng AI kết hợp RAG để trả lời câu hỏi của người dùng bằng ngôn ngữ tự nhiên, đồng thời chạy batch định kỳ để generate recommendation cụ thể cho Sales và Marketing. Thay vì người dùng phải tự đọc data, AI tổng hợp và đưa ra "bước tiếp theo" trực tiếp.

---

## Phạm vi và kỳ vọng

> Những điểm dễ bị hiểu sai nếu không được làm rõ — về những gì hệ thống làm được, không làm được, và tại sao thiết kế lại như vậy.

### 1. Vai trò của AI trong hệ thống

AI trong hệ thống này đóng vai trò **processor** — đọc, hiểu, và tổng hợp data sau khi data đã được tập trung về một chỗ. Không phải **collector**.

Một kỳ vọng phổ biến là AI sẽ tự động crawl data từ mọi nền tảng đang dùng. Trên thực tế điều này bất khả thi với nhiều nguồn quan trọng: GA4 không expose raw event data cho third-party, Jira của khách nằm trong tenant riêng, feedback Sales nằm trong chat nội bộ. Với những nguồn này, cần **operation change song song** — người có trách nhiệm chủ động ghi lại thông tin vào tool nội bộ.

Đây không phải hạn chế của thiết kế mà là đặc điểm của bài toán: những vấn đề phát sinh trong quá trình triển khai dự án — mà đội Ops trực tiếp quan sát — là nguồn bổ sung pain point, ICP và use case thực tế cho Marketing và Sales. Nguồn data này không tồn tại ở bất kỳ platform nào; nó chỉ tồn tại nếu có quy trình để capture nó.

### 2. Điểm khác biệt so với RAG thông thường

Về bề ngoài, hệ thống có thể trông giống một RAG pipeline thông thường: đưa data vào, đặt câu hỏi bằng ngôn ngữ tự nhiên. Tuy nhiên có một số điểm khác biệt cốt lõi:

- **Transform có chủ đích:** Thay vì embed raw text rồi search theo độ tương đồng, AI extract ra các trường có cấu trúc — pain_point, objection, funnel_stage, ICP — trước khi lưu. Điều này cho phép filter có ngữ cảnh thật sự: *"khách fintech đang ở giai đoạn negotiation lo về điều gì?"* thay vì chỉ tìm câu gần nghĩa nhất.

- **Dual context enrichment:** Mỗi câu hỏi được trả lời dựa trên hai nguồn context độc lập trước khi gọi AI — SQL query trên structured data (cho câu hỏi có số liệu: *"bao nhiêu deal bị lost vì giá?"*) và semantic search trên vector store (cho câu hỏi mở: *"khách thường nói gì sau khi thấy demo?"*). Kết hợp cả hai giúp AI không bị giới hạn vào một kiểu câu hỏi.

- **Data từ Ops sau khi ký hợp đồng:** CRM chỉ capture signal trước khi deal closed — những gì khách nói trong quá trình bán hàng, khi họ còn đang được thuyết phục. Ops là bộ phận duy nhất làm việc với khách sau khi ký, khi khách không còn lý do để nói đẹp. Đây là nguồn data phản ánh vấn đề thực sự, không phải vấn đề được kể lại. Hệ thống đưa nguồn data này vào chung một store với CRM data để có thể đối chiếu pre-sale signal với post-sale reality.
