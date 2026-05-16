# AI Insight Hub — Tối ưu AI Workflows Chatbox

> Tài liệu này tập trung vào Feature 2 (Chatbox RAG) — luồng real-time từ câu hỏi của user đến response stream. Phân biệt với `rag_optimization.md` vốn nói về chất lượng retrieve/generate; tài liệu này nói về **kiến trúc vận hành** của chat workflow: quản lý context, streaming, conversation state, và trải nghiệm người dùng.

---

## Kiến trúc hiện tại

```
POST /chat  { question, session_id? }
  → DashboardApiFn
      → keyword extract từ question
      → SQL query Aurora signals
      → pgvector semantic search
      → merge context → build prompt
      → Bedrock / Claude
  → streaming JSON { answer, references }
  → Frontend · Chatbox
```

Mỗi request hiện tại là stateless — không nhớ lịch sử hội thoại, không tối ưu context window, không có cơ chế phát hiện câu hỏi không trả lời được.

---

## 1 · Conversation State Management

Stateless RAG hoạt động tốt với câu hỏi độc lập nhưng gãy ngay khi user hỏi follow-up (_"còn về logistics thì sao?"_, _"cho tôi xem thêm"_).

### 1.1 Session-based history

Lưu conversation history theo `session_id` trong ElastiCache Redis (đã có trong stack). Mỗi turn thêm `{ role, content }` vào session. Khi build prompt, prepend lịch sử N turn gần nhất.

```
session:{session_id} → [ { role: "user", content: "..." }, { role: "assistant", content: "..." }, ... ]
TTL: 30 phút
```

**Trade-off:** Context window tăng tuyến tính theo số turn — cần kết hợp với sliding window hoặc summarization (xem 1.2).

### 1.2 Context window compression

Khi lịch sử vượt ngưỡng token (ví dụ > 4K tokens), thay vì cắt cụt đầu:

- **Sliding window** — giữ N turn gần nhất, bỏ turn cũ. Đơn giản, không mất thông tin quan trọng nếu N đủ lớn.
- **Rolling summary** — sau mỗi 5–10 turn, gọi thêm một LLM call nhỏ để tóm tắt phần lịch sử cũ thành 2–3 câu, thay thế raw turns bằng summary đó. Giữ ngữ cảnh mà không tốn token.

**Cho demo:** Sliding window (N = 6 turns) đủ dùng. Rolling summary defer.

---

## 2 · Query Understanding

Trước khi retrieve, phân tích intent của câu hỏi để routing đúng hướng.

### 2.1 Intent classification

Phân loại câu hỏi thành các nhóm trước khi xử lý:

| Intent                    | Ví dụ                                 | Xử lý                         |
| ------------------------- | ------------------------------------- | ----------------------------- |
| Factual / aggregate       | _"Có bao nhiêu khách fintech?"_       | Ưu tiên SQL                   |
| Semantic / open-ended     | _"Khách hàng lo ngại gì về bảo mật?"_ | Ưu tiên pgvector              |
| Follow-up / clarification | _"Còn về giá thì sao?"_               | Dùng context từ turn trước    |
| Out-of-scope              | _"Thời tiết hôm nay thế nào?"_        | Trả về graceful fallback ngay |

Classification bằng một LLM call nhỏ (Haiku) hoặc rule-based keyword matching — không cần model phức tạp.

### 2.2 Follow-up resolution

Câu hỏi follow-up thường thiếu subject (_"còn về X?"_ — X ở đây là gì?). Trước khi embed và search, rewrite câu hỏi thành dạng đầy đủ bằng cách kết hợp với context từ turn trước.

```
turn[-1]: "Khách fintech gặp vấn đề gì với tích hợp API?"
turn[0]:  "Còn về chi phí thì sao?"
→ rewritten: "Khách fintech gặp vấn đề gì về chi phí tích hợp API?"
```

### 2.3 Embedding model lock — bắt buộc nhất quán giữa write và query

> **Quy tắc bất biến:** Model dùng để embed `embedding_text` khi **ghi vào `signal_embeddings`** phải là **cùng một model** được dùng để embed câu hỏi khi **query pgvector**.

Mỗi embedding model tạo ra một vector space riêng. Nếu write dùng model A nhưng query dùng model B, cosine similarity sẽ tính trên hai không gian khác nhau — kết quả search sai hoàn toàn mà **không có error hay warning nào báo**. Bug kiểu này rất khó phát hiện vì hệ thống vẫn chạy bình thường, chỉ trả về kết quả không liên quan.

**Mapping môi trường:**

| Môi trường | Embedding model                                              | Dims |
| ---------- | ------------------------------------------------------------ | ---- |
| Local dev  | Gemini `gemini-embedding-001` (`output_dimensionality=1024`) | 1024 |
| AWS (prod) | Bedrock `cohere.embed-multilingual-v3`                       | 1024 |

Cả hai dùng 1024 dims — schema không đổi giữa môi trường, nhưng **vector không tương thích chéo nhau**. Không import dump từ local lên Aurora mà không re-embed lại bằng Cohere.

**Checklist khi thêm hoặc thay embedding model:**

1. Re-embed toàn bộ `signal_embeddings` bằng model mới — không patch từng dòng.
2. Cập nhật cả Transform Lambda (write) lẫn DashboardApiFn (query) cùng lúc — không deploy lệch.
3. Cập nhật bảng trên trong doc này.

---

## 3 · Streaming & Latency

### 3.1 Response streaming

Bedrock hỗ trợ streaming response — trả về từng chunk thay vì đợi full response. Frontend hiển thị dần thay vì spinner dài. Triển khai qua Lambda Response Streaming (AWS Lambda streaming mode).

```
Bedrock invoke_model_with_response_stream
  → yield chunk → Lambda stream → API Gateway → EventSource (SSE)
  → Frontend render token by token
```

**Lưu ý:** API Gateway cần cấu hình `Transfer-Encoding: chunked`. Lambda cần `FunctionResponseTypes: [RESPONSE_STREAM]`.

### 3.2 Pre-fetch context trước khi gọi LLM

SQL query và pgvector search chạy song song (asyncio), không tuần tự. Gộp kết quả rồi mới gọi Bedrock — giảm total latency từ `T_sql + T_vector + T_llm` xuống `max(T_sql, T_vector) + T_llm`.

```python
sql_task    = asyncio.create_task(query_aurora(question))
vector_task = asyncio.create_task(search_pgvector(embedding))
sql_ctx, vector_ctx = await asyncio.gather(sql_task, vector_task)
```

### 3.3 Cache phản hồi với Redis

Câu hỏi lặp lại (cùng `question` hash) → trả từ Redis cache thay vì gọi Bedrock. TTL 10–15 phút. Phù hợp với câu hỏi dashboard thông dụng trong demo.

---

## 4 · Prompt Engineering cho Chat

### 4.1 System prompt phân tách rõ vai trò

```
System:
  Bạn là AI analyst của [tổ chức]. Nhiệm vụ: trả lời câu hỏi về customer insights
  dựa trên context được cung cấp. KHÔNG suy đoán ngoài context. Nếu context không
  đủ, nói rõ "Dữ liệu hiện tại chưa đủ để trả lời câu hỏi này."

Context (SQL):
  [structured rows từ Aurora]

Context (Semantic):
  [relevant chunks từ pgvector]

Conversation history:
  [N turns gần nhất]

User: [câu hỏi hiện tại]
```

### 4.2 Citation trong response

Yêu cầu model output references dưới dạng structured JSON bên cạnh câu trả lời. Frontend dùng `source_url` để render chip links đến Jira / HubSpot.

```json
{
  "answer": "Khách fintech chủ yếu lo ngại về...",
  "references": [
    { "label": "Jira PROJ-123", "url": "https://jira.example.com/..." },
    { "label": "HubSpot Deal #456", "url": "https://app.hubspot.com/..." }
  ]
}
```

### 4.3 Graceful fallback khi thiếu data

Khi pgvector similarity score thấp trên toàn bộ top-K hoặc SQL trả về empty, model cần biết context rỗng. Thay vì để model hallucinate, inject rõ vào prompt:

```text
Context (Semantic): [KHÔNG CÓ KẾT QUẢ PHÙ HỢP]
```

Model được hướng dẫn trong system prompt để trả về câu từ chối chuẩn thay vì bịa số liệu.

---

## 5 · Observability

### 5.1 Metrics cần track

| Metric                                 | Mục đích                              |
| -------------------------------------- | ------------------------------------- |
| Latency breakdown (SQL / vector / LLM) | Xác định bottleneck                   |
| pgvector top-1 similarity score        | Phát hiện câu hỏi out-of-distribution |
| Token count per request                | Monitor cost                          |
| Fallback rate                          | Đo tỷ lệ câu hỏi không trả lời được   |
| Session turn count                     | Hiểu usage pattern                    |

### 5.2 Structured logging

Log mỗi request với đủ context để debug:

```json
{
  "session_id": "...",
  "question_hash": "...",
  "intent": "semantic",
  "sql_rows": 5,
  "vector_top_score": 0.82,
  "tokens_input": 1240,
  "tokens_output": 310,
  "latency_ms": { "sql": 45, "vector": 38, "llm": 1820 },
  "cache_hit": false
}
```

---

## Ưu tiên cho demo

| Tối ưu                  | Impact     | Effort     | Ghi chú                            |
| ----------------------- | ---------- | ---------- | ---------------------------------- |
| Parallel SQL + pgvector | Cao        | Thấp       | Asyncio gather — một dòng thay đổi |
| Response streaming      | Cao        | Trung bình | UX rõ rệt — user thấy output ngay  |
| Graceful fallback       | Cao        | Thấp       | Tránh hallucinate trước demo       |
| Session history (N=6)   | Trung bình | Thấp       | Redis đã có sẵn trong stack        |
| Intent classification   | Trung bình | Trung bình | Rule-based trước, LLM sau nếu cần  |
| Citation / source links | Trung bình | Thấp       | Đã có `source_url` trong schema    |
| Response cache Redis    | Thấp       | Thấp       | Demo nhỏ — ít câu hỏi lặp          |
| Rolling summary         | Thấp       | Cao        | Defer — sliding window đủ dùng     |
