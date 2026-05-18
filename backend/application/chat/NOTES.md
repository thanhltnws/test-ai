# Chat Lambda — Notes

## Strategy: LLM pre-call để extract query intent

Thêm 1 LLM pre-call (Haiku) phân tích câu hỏi trước khi query DB, extract `{period_start, period_end, market, sector, result_type_hint}`. Dùng kết quả này làm filter cho cả Aurora lẫn pgvector metadata pre-filter.

Lợi ích:

- Giải quyết vấn đề LIMIT — query filtered by market/sector trả ít rows, không cần LIMIT cứng
- pgvector metadata pre-filter chính xác hơn
- Consistent với cách batch store data (insights/insight_embeddings đều có metadata theo slice)

Trade-off: thêm 1 LLM call → latency tăng. Pre-call nhẹ, dùng Haiku là đủ.

---

## Strategy: `insights` thành primary query, `signals` thành evidence fallback

Sau khi add `insight_embeddings`, cân nhắc đổi priority:

- `insights` → primary narrative context (icp_narrative, recommendations, pain_points_summary theo period/market)
- `signals` → fallback cho evidence cụ thể + source_url references

Lưu ý: `insights` chỉ tồn tại cho các period đã batch. Signal rất gần đây (chưa qua batch) chỉ có trong `signals` — không thể bỏ hẳn, chỉ thay đổi priority.

**Strategy mới kết hợp cả hai ý:**

```
1. Pre-call (Haiku): extract {period, market, sector} từ câu hỏi
2. Query insights (filter by slice)           → primary narrative
3. Query insight_embeddings (metadata filter) → semantic match trên narratives
4. Query signal_embeddings (metadata filter)  → granular evidence + source_url
5. Final call (Sonnet): merge all context → answer + references
```

---

## query_aurora — LIMIT và keyword matching cần bàn lại

Background aggregates dùng LIMIT cứng (top_pain_points: 15, top_use_cases: 10) không filter theo intent câu hỏi — câu hỏi về fintech vẫn nhận top N toàn dataset, miss các item nằm ngoài top N dù liên quan trực tiếp.

Keyword matching (`raw_text ILIKE`) match theo chữ không theo nghĩa, LIMIT 8 cắt cứng. Câu hỏi về "vấn đề tích hợp" sẽ miss signal nói "khó kết nối hệ thống". Phần semantic đang được đẩy hoàn toàn cho pgvector.

Hướng cần bàn: bỏ LIMIT ở aggregates (seed data có ~50 pain points tối đa), cân nhắc bỏ keyword matching vì pgvector cover tốt hơn.

### Issue: `_extract_keywords` bị lock vào tiếng Anh

`_STOP_WORDS` chỉ có English stop words. Khi user hỏi tiếng Việt:

- Các Vietnamese stop words (`là`, `và`, `có`, `không`, `của`, `trong`...) không bị lọc → lọt vào WHERE clause → query quá rộng, noise cao
- Keywords tiếng Việt match `raw_text` (Vietnamese source text) được một phần, nhưng không match `pain_points`/`use_cases` nếu chúng đang lưu tiếng Anh

Gợi ý xử lý — tận dụng pre-call (Haiku) đã có trong Strategy phía trên: ngoài extract `{period, market, sector}`, pre-call cũng extract 3–5 **English keyword** từ câu hỏi tiếng Việt để dùng cho keyword matching Aurora. Một call, hai output. Không thêm latency, không đổi schema SQL, không có hallucination risk của text-to-SQL.

---

## Missing: query insight_embeddings

`query_pgvector` currently only queries `signal_embeddings` (raw customer signals).
Per architecture, chat RAG should also query `insight_embeddings` (pre-computed LLM
narratives from the batch pipeline) and join with `insights` for richer prompt context.

## Conversation history

Current chat is stateless — each request is independent. Consider adding lightweight
conversation history (last N turns) to the prompt so follow-up questions can reference
prior context. Trade-off: longer prompts → higher token cost and latency.
