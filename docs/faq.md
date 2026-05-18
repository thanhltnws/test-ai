# Technical Q&A

> Về bề ngoài, hệ thống có thể trông giống một RAG pipeline thông thường: đưa data vào, đặt câu hỏi bằng ngôn ngữ tự nhiên. Những câu hỏi dưới đây làm rõ các điểm khác biệt cốt lõi trong thiết kế.

## Tại sao không embed raw text như RAG thông thường?

Thay vì embed raw text rồi search theo độ tương đồng, AI extract ra các trường có cấu trúc — pain_point, objection, funnel_stage, ICP — trước khi lưu. Điều này cho phép filter có ngữ cảnh thật sự: *"khách fintech đang ở giai đoạn negotiation lo về điều gì?"* thay vì chỉ tìm câu gần nghĩa nhất.

## Tại sao không embed raw text mà phải qua LLM để sinh `embedding_text` trước?

`embedding_text` được generate trong **cùng 1 LLM call** với extraction — không phải call riêng, không tốn thêm cost. Lý do không embed raw text trực tiếp:

- **Noise**: CRM note có tên người, ngày tháng, lời chào → vector bị kéo lệch khỏi signal thật
- **Length**: Teams transcript có thể 10,000 token → phải chunking nếu embed trực tiếp, thêm complexity; LLM compress xuống 2–4 câu tập trung vào signal, không cần chunking
- **Cross-source consistency**: HubSpot note và Jira ticket về cùng vấn đề sẽ có `embedding_text` tương tự → vector gần nhau → semantic search tìm được cả hai

Raw text embedding chạy được nhưng precision của semantic search thấp hơn đáng kể.

## Tại sao dùng Cohere `embed-multilingual-v3` mà không dùng model embedding thông thường?

Cohere multilingual được chọn để hỗ trợ cross-lingual search khi data và query khác ngôn ngữ — ví dụ source data tiếng Nhật/Hàn, user query tiếng Việt (schema đã có `market = japan | korea`). Tuy nhiên, với thiết kế hiện tại — transform normalize toàn bộ output về cùng một ngôn ngữ và user chỉ query tiếng Việt — khả năng multilingual của Cohere không được tận dụng. Ở production thực sự với nhiều thị trường, multilingual capability mới phát huy giá trị. Với scope demo all-Vietnamese, bất kỳ embedding model tốt nào cũng cho kết quả tương đương.

## Tại sao cần 2 nguồn context khi trả lời câu hỏi?

Mỗi câu hỏi được trả lời dựa trên hai nguồn context độc lập trước khi gọi AI — SQL query trên structured data (cho câu hỏi có số liệu: *"bao nhiêu deal bị lost vì giá?"*) và semantic search trên vector store (cho câu hỏi mở: *"khách thường nói gì sau khi thấy demo?"*). Kết hợp cả hai giúp AI không bị giới hạn vào một kiểu câu hỏi.

## Data từ Ops khác gì so với CRM data?

CRM chỉ capture signal trước khi deal closed — những gì khách nói trong quá trình bán hàng, khi họ còn đang được thuyết phục. Ops là bộ phận duy nhất làm việc với khách sau khi ký, khi khách không còn lý do để nói đẹp. Đây là nguồn data phản ánh vấn đề thực sự, không phải vấn đề được kể lại. Hệ thống đưa nguồn data này vào chung một store với CRM data để có thể đối chiếu pre-sale signal với post-sale reality.
