# Chat Lambda — Implementation Notes

> Xem `strategy.md` cho full strategy + trạng thái implement. File này chỉ giữ backlog chưa xong.

---

## P1 — Tiếp theo

### insight_low dual-role (chưa bàn xong)

`insight_low=True` hiện đảm nhiệm hai vai trò: (1) trigger Phase 2 signal fetch, (2) inject `[NO MATCHING DATA]` vào prompt. Vai trò (2) sai với `mode=semantic` — cần tách. Đã revert fix, pending design discussion.

### Tham số LLM — review

Chưa tuning `top_k`, `top_p`, `temperature` cho intent model (Haiku) và answer model (Sonnet). Cần xem xét trade-off coherence vs. creativity theo từng vai trò.

### So sánh kỹ thuật đã apply vs. docs

Đối chiếu với `docs/rag_optimization.md` và `docs/chat_optimization.md` — xem còn kỹ thuật nào chưa apply hoặc apply sai.

### Phase 2 — signals + signal_embeddings

Cùng cơ chế structured-first / semantic fallback như Phase 1. Hiện Phase 2 chỉ có `query_signal_embeddings` (semantic only). Nếu intent rõ period/market → có thể query thẳng `signals` trước.

---

## P2 — Còn lại

### TOP_K rebalance

`_INSIGHT_TOP_K=4` và `_VECTOR_TOP_K=8` cần đảo lại:

- `_INSIGHT_TOP_K` → dynamic: detect được `result_type` → 2, không detect → 4
- `_VECTOR_TOP_K` → 4

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

---

## Schema cleanup — Deferred

### Xóa `metadata` JSONB khỏi embedding tables

`signal_embeddings.metadata` và `insight_embeddings.metadata` là denormalized copy từ bảng cha, không dùng ở bất kỳ đâu trong handler. Cần: `ALTER TABLE DROP COLUMN` + cập nhật `dev/init.sql` + bất kỳ write code nào populate field này.
