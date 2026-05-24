# RAG & Chat Optimization

> Kỹ thuật tối ưu cho hệ thống RAG và chat AI, sắp xếp theo độ phức tạp tăng dần. Dùng làm reference chung — không gắn với dự án cụ thể.

---

## Tầng 1 — Pipeline

Cải thiện chất lượng mà không thay đổi flow cơ bản. Mỗi kỹ thuật là một cải tiến độc lập, có thể áp dụng riêng lẻ.

### Embedding model consistency

Model dùng để embed document khi **ghi** phải là **cùng model** khi embed query để **tìm kiếm**. Nếu sai, cosine similarity tính trên hai vector space khác nhau — kết quả search sai hoàn toàn mà không có error hay warning nào báo.

### Metadata filtering

Filter theo các field có cấu trúc (category, date, source, market...) bằng SQL/WHERE trước khi chạy vector search. Thu hẹp không gian search, tăng precision, giảm noise.

### Parallel retrieval

Chạy SQL query và vector search song song thay vì tuần tự. Tổng latency giảm từ `T_sql + T_vector + T_llm` xuống `max(T_sql, T_vector) + T_llm`.

### Intent classification

Phân loại câu hỏi trước khi retrieve để routing đúng hướng:

| Intent | Ví dụ | Xử lý |
| ----------- | ----------------------------------- | ----------------------- |
| Aggregate | "Có bao nhiêu deal tháng này?" | SQL |
| Semantic | "Khách lo ngại gì về bảo mật?" | Vector search |
| Follow-up | "Còn về giá thì sao?" | Context từ turn trước |
| Out-of-scope | "Thời tiết hôm nay?" | Reject ngay |

### Query rewriting

Rewrite câu hỏi thành dạng tối ưu cho semantic search trước khi embed. Câu hỏi dạng hội thoại thường cho kết quả search kém hơn câu được viết lại thành query độc lập.

### Follow-up resolution

Câu hỏi follow-up thường thiếu subject. Trước khi search, kết hợp với context từ turn trước để rewrite thành câu đầy đủ.

```text
turn[-1]: "Khách fintech gặp vấn đề gì với tích hợp API?"
turn[0]:  "Còn về chi phí thì sao?"
→ rewritten: "Khách fintech gặp vấn đề gì về chi phí tích hợp API?"
```

### Session history + sliding window

Lưu N turn gần nhất theo session_id, prepend vào prompt khi build context. Sliding window tránh context overflow — drop turn cũ khi vượt ngưỡng.

### System prompt design

Tách system instructions ra khỏi user context. System prompt định nghĩa vai trò, ràng buộc ("chỉ dùng context được cung cấp"), và behavior khi thiếu data.

### Citation / structured output

Yêu cầu LLM output references dưới dạng structured JSON kèm câu trả lời:

```json
{
  "answer": "...",
  "references": [{ "title": "...", "source_url": "..." }]
}
```

### Graceful fallback khi thiếu data

Khi context rỗng hoặc chất lượng thấp, inject rõ vào prompt thay vì để LLM tự suy diễn. Model cần được hướng dẫn trong system prompt để từ chối an toàn thay vì hallucinate.

### Response cache

Cache câu hỏi lặp theo hash. TTL phù hợp với tần suất thay đổi data. Giảm cost và latency cho câu hỏi phổ biến.

---

## Tầng 2 — Agentic

Flow có decision point — model tự đánh giá kết quả và điều chỉnh hành vi. Yêu cầu thêm retry logic và routing vào handler.

### HyDE (Hypothetical Document Embedding)

Thay vì embed câu hỏi, generate một đoạn trả lời giả định rồi embed đoạn đó để search. Vector của "câu trả lời giả định" thường gần với vector của document thực tế hơn vector của câu hỏi. Tốn thêm một LLM call trước search.

### Reranking

Sau khi retrieve top-K, chạy thêm một pass reranking (cross-encoder hoặc LLM-based) để sắp xếp lại theo relevance thực sự trước khi đưa vào prompt. Cosine similarity không phải lúc nào cũng đồng nghĩa với relevance.

### Score threshold + fallback routing

Nếu toàn bộ top-K similarity scores thấp hơn ngưỡng, tự động điều chỉnh: nới filter, tăng top_k, switch strategy, hoặc short-circuit với "không đủ data" thay vì hallucinate.

### Context window compression — rolling summary

Khi lịch sử hội thoại vượt ngưỡng token, gọi LLM call nhỏ để tóm tắt các turn cũ thành 2–3 câu. Giữ ngữ cảnh mà không tốn full token history.

### Self-RAG / Iterative retrieval

Sau khi retrieve, model tự đánh giá context đủ để trả lời chưa. Nếu chưa, loop lại với query được mở rộng hoặc điều chỉnh. Tránh generate câu trả lời thiếu căn cứ.

### Dynamic model selection

Câu hỏi factual đơn giản → model nhỏ hơn để giảm cost và latency. Câu hỏi phân tích phức tạp → escalate lên model mạnh hơn.

### Tool use

Thay vì chạy pipeline cố định, model tự quyết định dùng công cụ nào (SQL, vector search, calculator, external API...) tùy loại câu hỏi.

---

## Tầng 3 — Multi-agent

Phân tách retrieve, validate, và generate thành các agent độc lập. Mỗi agent tối ưu riêng, chạy song song.

### Orchestrator + specialized agents

Orchestrator nhận câu hỏi, decompose thành sub-queries, giao agent con xử lý song song, tổng hợp kết quả. Phù hợp với câu hỏi phức tạp yêu cầu nhiều góc nhìn.

### Response streaming

Trả về từng chunk thay vì đợi full response. Frontend render token-by-token. Yêu cầu infra hỗ trợ streaming (Lambda streaming mode, SSE/WebSocket).
