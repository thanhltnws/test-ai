# Chat Lambda — Implementation Notes

> Xem `strategy.md` cho full strategy + trạng thái implement. File này chỉ giữ backlog chưa xong.

---

## P1 — Tiếp theo

### Review LLM parameters

Cần review liên tục để tuning `top_k`, `top_p`, `temperature` cho intent model (Haiku) và answer model (Sonnet). Cần xem xét trade-off coherence vs. creativity theo từng vai trò.

### Review RAG parameters

retrieval sizing theo flow,...

---

## P2 — Còn lại

### Graceful fallback khi context yếu/rỗng

Khi signal_ctx rỗng hoặc toàn bộ scores thấp (dưới ngưỡng), trả lời an toàn thay vì để LLM hallucinate. Ví dụ: inject rõ "Không đủ dữ liệu để trả lời câu hỏi này." vào response hoặc short-circuit trước khi gọi LLM.

### Fallback routing theo score / context quality

Khi context yếu (top-1 score thấp, hoặc 0 rows sau filter), tự động đổi cách retrieve trước khi trả lời. Ví dụ: nới rộng filter (bỏ `market`/`sector`), hoặc tăng `top_k`, hoặc switch flow. Cần xác định ngưỡng score sau khi có data test thực tế.

### So sánh kỹ thuật đã apply vs. docs

Đối chiếu với `docs/rag_optimization.md` và `docs/chat_optimization.md` — xem còn kỹ thuật nào chưa apply hoặc apply sai.

---

## P3 — Deferred

### ⑩ Response streaming *(nâng cao)*

`invoke_model_with_response_stream` (Bedrock) + `FunctionResponseTypes: [RESPONSE_STREAM]` (Lambda) + SSE (frontend). Đụng infra phức tạp. Khi có streaming, 2-LLM-call pattern (Phase 2 chạy song song trong khi stream LLM call 1) mới có giá trị.

### ⑪ Response cache Redis *(nâng cao)*

Cache câu hỏi lặp bằng Redis. Yêu cầu thêm infra (ElastiCache hoặc Redis OSS). Skip cho demo scale.

### ⑫ Structured logging

Log per request — không liên quan conversation history:

```json
{
  "session_id": "...",
  "intent": {},
  "total_signals": 150,
  "top_insight_score": 0.82,
  "latency_ms": { "intent_embed": 420, "phase1": 85, "llm": 1800, "total": 2350 }
}
```

### ⑬ Rolling summary

Không cần cho demo. `_SESSION_WINDOW = 12` đủ giữ toàn bộ cuộc hội thoại demo (initial + 5 follow-ups = 12 turns) — overflow không xảy ra. Xem xét lại nếu mở rộng conversation limit.

### Redis persistence

In-memory `_sessions` dict mất sạch khi Lambda cold start, không sync giữa nhiều instance. Chấp nhận cho demo (1 instance warm, vài user). Giải pháp nếu scale: Redis (ElastiCache) với TTL 30 phút.

