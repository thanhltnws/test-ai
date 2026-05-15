# AI Insight Hub — Lộ trình tối ưu RAG

> Ba tầng kỹ thuật cho từng luồng — tầng càng cao càng phức tạp về kiến trúc. Tầng 1 chỉ thay đổi cách gọi model, không đụng đến flow. Tầng 2 thêm decision point và loop. Tầng 3 chia hệ thống thành nhiều agent phối hợp.
>
> **Với demo này:** áp dụng Tầng 1 cho cả hai luồng. Xem xét thêm *Fallback routing* và *Tool use* ở Tầng 2 nếu còn thời gian — impact cao, đủ justify complexity tăng thêm. Tầng 3 defer.

---

## Luồng 1 · Transform (Extraction)

Hiện tại: một AI call duy nhất mỗi khi có file mới từ S3, extract tất cả fields cùng lúc, insert vào Aurora nếu không có exception.

### Tầng 1 · Pipeline

Cải thiện chất lượng extraction mà không thay đổi kiến trúc — chỉ thay đổi cách gọi model và xử lý kết quả.

- **Few-shot prompting** — thêm 2–3 ví dụ input/output thực tế vào prompt. Model học pattern từ ví dụ cụ thể thay vì chỉ từ mô tả trừu tượng. Đặc biệt hiệu quả với tiếng Việt mixed tiếng Anh và call note viết tắt.

- **Chain of thought extraction** — yêu cầu model giải thích reasoning trước khi output structured fields. Giảm hallucination trên text ngắn hoặc mơ hồ vì model buộc phải "đọc lại" trước khi kết luận.

- **Multi-pass extraction** — tách một call lớn thành nhiều call chuyên biệt: call 1 chỉ extract `pain_point`, call 2 chỉ extract `ICP`, v.v. Tốn token hơn nhưng giảm context confusion trên text dài.

- **Validation layer** — code hiện tại dùng Pydantic để validate schema, nhưng khi fail chỉ raise exception. Gap thực sự là ở hành vi sau khi fail: reject và log, flag để human review, hay retry với prompt khác. Thêm logic này ngăn data rác vào store mà không làm im lặng lỗi.

### Tầng 2 · Agentic

Model tự điều chỉnh hành vi dựa trên kết quả — không chỉ chạy một lần rồi thôi. Yêu cầu thêm retry logic và routing vào Lambda handler.

- **Retry loop** — nếu extraction trả về field quan trọng trống hoặc `confidence_score` dưới ngưỡng, tự retry với prompt khác (thêm chain of thought, hoặc cung cấp thêm context). Số lần retry có giới hạn để tránh loop vô hạn.

- **Fallback routing** — nếu text quá ngắn hoặc quá nhiễu, tự escalate sang model mạnh hơn hoặc đẩy vào hàng đợi để human review thay vì insert record rỗng.

### Tầng 3 · Multi-agent

Mỗi agent chỉ làm một việc — phân tách trách nhiệm để tối ưu từng bước độc lập và chạy song song.

- **Agent chuyên biệt theo field** — agent A chỉ extract `pain_point`, agent B chỉ extract `ICP`, agent C validate và merge kết quả. Cho phép fine-tune prompt riêng cho từng field và chạy song song để giảm latency.

---

## Luồng 2 · Application (RAG)

Hiện tại: keyword extraction từ câu hỏi → SQL query + pgvector search → merge cả hai context → một AI call generate response.

### Tầng 1 · Pipeline

Cải thiện chất lượng retrieve và generate mà không thay đổi flow cơ bản.

- **Query rewriting** — rewrite câu hỏi của user thành dạng tối ưu cho semantic search trước khi embed. Câu hỏi dạng hội thoại (*"còn về giá thì sao?"*) thường cho kết quả search kém hơn câu được viết lại thành query độc lập.

- **HyDE (Hypothetical Document Embedding)** — thay vì embed câu hỏi, generate một đoạn trả lời giả định rồi embed đoạn đó để search. Vector của "câu trả lời giả định" gần với vector của chunk thực tế hơn vector của câu hỏi. Tốn thêm một LLM call trước khi search.

- **Metadata filtering** — filter theo `funnel_stage`, `icp->>'sector'`, hoặc `source` bằng SQL trước khi chạy pgvector, thu hẹp không gian search. Hiệu quả với câu hỏi có context rõ (*"khách fintech lo gì?"*). Code hiện tại chưa làm bước này — pgvector search trên toàn bộ store.

- **Reranking** — sau khi retrieve top-K chunks, chạy một pass reranking để sắp xếp lại theo relevance thực sự trước khi đưa vào prompt. Cosine similarity không phải lúc nào cũng đồng nghĩa với relevance.

### Tầng 2 · Agentic

RAG tự đánh giá kết quả của mình và quyết định bước tiếp theo. Yêu cầu thay đổi flow trong chat handler từ linear sang có decision point.

- **Self-RAG / Iterative retrieval** — sau khi retrieve, model tự đánh giá context đủ để trả lời chưa. Nếu chưa, loop lại với query được mở rộng hoặc điều chỉnh thay vì generate câu trả lời thiếu căn cứ.

- **Fallback routing** — nếu pgvector similarity score thấp trên toàn bộ top-K, fallback sang SQL query rộng hơn hoặc trả về "không đủ data" thay vì hallucinate. Tránh tình huống model tự bịa khi context rỗng — ảnh hưởng trực tiếp đến credibility của demo.

- **Dynamic model selection** — câu hỏi factual đơn giản dùng model nhỏ hơn để giảm cost và latency; câu hỏi phân tích phức tạp escalate lên model mạnh hơn.

- **Tool use** — thay vì luôn chạy cả SQL lẫn pgvector, model tự quyết định dùng công cụ nào tùy loại câu hỏi. Câu hỏi có số liệu → SQL. Câu hỏi ngữ nghĩa → pgvector. Câu hỏi phức tạp → cả hai. Thể hiện hệ thống "thông minh" hơn RAG pipeline cố định.

### Tầng 3 · Multi-agent

Phân tách retrieve, validate, và generate thành các agent độc lập.

- **Agent chuyên biệt** — agent A retrieve chunks, agent B đánh giá relevance, agent C generate response. Mỗi agent có thể được tối ưu hoặc thay thế độc lập.

- **Orchestrator agent** — nhận câu hỏi phức tạp, tự decompose thành sub-queries, giao cho các agent con xử lý song song, rồi tổng hợp kết quả. Phù hợp với câu hỏi yêu cầu nhiều góc nhìn (*"so sánh pain point của khách fintech vs logistics"*).

---

## Thực tế cho demo

> Timeline 3 tuần — tập trung vào Tầng 1. Hai kỹ thuật Tầng 2 có thể xem xét nếu có thời gian vì impact cao với effort tương đối thấp.

| Kỹ thuật | Luồng | Tầng | Impact | Effort | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| Few-shot prompting | Transform | 1 | Cao | Thấp | Chỉ thay đổi prompt |
| Validation layer | Transform | 1 | Cao | Thấp | Thêm logic sau Pydantic fail |
| Metadata filtering | RAG | 1 | Cao | Thấp | Thêm WHERE clause trước pgvector |
| Query rewriting | RAG | 1 | Trung bình | Thấp | Thêm một LLM call trước search |
| Fallback routing | RAG | 2 | Cao | Trung bình | Tránh hallucinate khi thiếu data — quan trọng cho demo |
| Tool use cơ bản | RAG | 2 | Trung bình | Trung bình | Tự chọn SQL hay pgvector tùy câu hỏi |
| HyDE | RAG | 1 | Trung bình | Trung bình | Defer — thêm LLM call, cần đánh giá tradeoff |
| Reranking | RAG | 1 | Trung bình | Cao | Defer |
| Self-RAG | RAG | 2 | Cao | Cao | Defer |
| Multi-agent | Cả hai | 3 | Cao | Rất cao | Defer — over-engineering cho scope hiện tại |
