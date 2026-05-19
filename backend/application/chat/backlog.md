# Chat Lambda — Implementation Notes

> Xem `chat_rag_strategy.md` cho full strategy + trạng thái implement. File này chỉ giữ backlog chưa xong.

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

Sliding window N=6 hiện cắt bỏ turns cũ — mất context nếu conversation dài. Thay bằng: khi số turns vượt N, tóm tắt turns cũ thành 1 summary turn (Haiku call nhỏ), prepend vào window.

### Redis persistence

In-memory `_sessions` dict mất sạch khi Lambda cold start, không sync giữa nhiều instance. Giải pháp: thay bằng Redis (ElastiCache) với TTL 30 phút. Đụng infra — defer sau demo.

---

## Schema cleanup — Deferred

### Xóa `metadata` JSONB khỏi embedding tables

`signal_embeddings.metadata` và `insight_embeddings.metadata` là denormalized copy từ bảng cha, không dùng ở bất kỳ đâu trong handler. Cần: `ALTER TABLE DROP COLUMN` + cập nhật `dev/init.sql` + bất kỳ write code nào populate field này.
