# Chat Lambda — Notes

## Strategy: LLM pre-call để extract query intent

Thêm 1 LLM pre-call (Haiku) phân tích câu hỏi trước khi query DB, extract `{period_start, period_end, market, sector, result_type_hint}`. Dùng kết quả này làm filter cho cả Aurora lẫn pgvector metadata pre-filter.

Lợi ích:

- Giải quyết vấn đề LIMIT — query filtered by market/sector trả ít rows, không cần LIMIT cứng
- pgvector metadata pre-filter chính xác hơn
- Consistent với cách batch store data (insights/insight_embeddings đều có metadata theo slice)

Trade-off: thêm 1 LLM call → latency tăng. Pre-call nhẹ, dùng Haiku là đủ.

### Fail-visible và quyết định skip LLM

Nếu pre-call extract sai sector → SQL WHERE filter trả 0 relevant rows → LLM trả lời "không đủ dữ liệu" → **fail visible**, không phải silent wrong answer như text-to-SQL. Điều này mở ra một chiến thuật: dùng output của pre-call (hoặc kiểm tra `relevant_signals == []` sau query) để quyết định có thực sự cần RAG bằng SQL không — nếu không match, fallback về pgvector-only.

**Empty context hiện tại:** code không có gate nào — `build_chat_prompt` và `call_llm` luôn được gọi dù `relevant_signals` rỗng và pgvector trả `[]`. Chi phí LLM bị tốn dù context trống. Cần thêm gate: nếu `total_signals == 0` (DB chưa có data), trả về canned response mà không call LLM. Nếu chỉ `relevant_signals` rỗng, vẫn call LLM bình thường vì background aggregates (`top_pain_points`, `funnel_distribution`) vẫn có giá trị làm context.

### Câu hỏi không có filter rõ ràng

Câu như *"deal bị stuck ở đâu nhiều nhất?"* không chứa sector hay market → pre-call phải nhận ra **không cần filter**, để SQL chạy toàn dataset. Rủi ro: LLM infer sector từ context khi không được hỏi rõ. Cần prompt pre-call chỉ định rõ: output `null` cho field không có signal trong câu hỏi, không được suy diễn.

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

## Strategy: Phân vai rõ SQL và pgvector, không dùng LLM quyết định query

Thay vì dùng pre-call để quyết định SQL filter (dẫn đến text-to-SQL territory), phân vai rõ ràng:

- **pgvector** → relevance: *"signal nào liên quan đến câu hỏi này?"* — đây là câu hỏi semantic, pgvector làm tốt hơn SQL bất kỳ dạng nào
- **SQL** → distribution: *"toàn dataset phân bố như thế nào?"* — background stats (funnel counts, top pain points tổng thể), LIMIT chấp nhận được vì đây là context tổng quan, không phải câu trả lời cụ thể

Theo hướng này: bỏ keyword matching SQL (`raw_text ILIKE`) vì pgvector cover semantic matching tốt hơn. Pre-call chỉ cần để extract metadata filter cho pgvector (`{sector, market, funnel_stage}`) — mục tiêu hẹp, rủi ro thấp, không cần LLM quyết định SQL WHERE clause.

### `metadata` trong `signal_embeddings`

```json
{ "source": "hubspot", "funnel_stage": "consideration", "market": "vietnam", "sector": "fintech", "source_url": "..." }
```

GIN index trên `metadata` cho phép pre-filtered similarity search: filter theo `{sector, market}` **trước** khi tính cosine similarity → thu hẹp search space, kết quả sát câu hỏi hơn. Hiện tại `query_pgvector` không dùng metadata filter — search toàn bộ `signal_embeddings` không phân biệt sector/market. Đây là điểm cần bổ sung khi implement pre-call.

---

## Missing: query insight_embeddings

`query_pgvector` currently only queries `signal_embeddings` (raw customer signals).
Per architecture, chat RAG should also query `insight_embeddings` (pre-computed LLM
narratives from the batch pipeline) and join with `insights` for richer prompt context.

## Conversation history

Current chat is stateless — each request is independent. Consider adding lightweight
conversation history (last N turns) to the prompt so follow-up questions can reference
prior context. Trade-off: longer prompts → higher token cost and latency.
