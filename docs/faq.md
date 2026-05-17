# Technical Q&A

> Về bề ngoài, hệ thống có thể trông giống một RAG pipeline thông thường: đưa data vào, đặt câu hỏi bằng ngôn ngữ tự nhiên. Những câu hỏi dưới đây làm rõ các điểm khác biệt cốt lõi trong thiết kế.

## Tại sao không embed raw text như RAG thông thường?

Thay vì embed raw text rồi search theo độ tương đồng, AI extract ra các trường có cấu trúc — pain_point, objection, funnel_stage, ICP — trước khi lưu. Điều này cho phép filter có ngữ cảnh thật sự: *"khách fintech đang ở giai đoạn negotiation lo về điều gì?"* thay vì chỉ tìm câu gần nghĩa nhất.

## Tại sao cần 2 nguồn context khi trả lời câu hỏi?

Mỗi câu hỏi được trả lời dựa trên hai nguồn context độc lập trước khi gọi AI — SQL query trên structured data (cho câu hỏi có số liệu: *"bao nhiêu deal bị lost vì giá?"*) và semantic search trên vector store (cho câu hỏi mở: *"khách thường nói gì sau khi thấy demo?"*). Kết hợp cả hai giúp AI không bị giới hạn vào một kiểu câu hỏi.

## Data từ Ops khác gì so với CRM data?

CRM chỉ capture signal trước khi deal closed — những gì khách nói trong quá trình bán hàng, khi họ còn đang được thuyết phục. Ops là bộ phận duy nhất làm việc với khách sau khi ký, khi khách không còn lý do để nói đẹp. Đây là nguồn data phản ánh vấn đề thực sự, không phải vấn đề được kể lại. Hệ thống đưa nguồn data này vào chung một store với CRM data để có thể đối chiếu pre-sale signal với post-sale reality.
