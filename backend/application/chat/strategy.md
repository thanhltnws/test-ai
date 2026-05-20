# Chat RAG Strategy — Insights-First

> File này ghi lại chiến thuật RAG cho chat lambda. Liên quan: `NOTES.md` (backlog cụ thể).

---

## Nguyên tắc cốt lõi

**Insights = primary context. Signals = evidence layer.**

Batch pipeline đã làm công việc aggregation + summarization trên toàn bộ signals. Kết quả đó nằm trong `insights` — đây là "distilled knowledge" của hệ thống. Chat RAG nên tận dụng tối đa thay vì đi lại từ raw signals.

| Layer | Bảng | Vai trò trong chat |
|-------|------|-------------------|
| Primary | `insights` + `insight_embeddings` | Pre-computed narratives, period-aware, market-aware |
| Secondary | `signals` + `signal_embeddings` | Granular evidence, source_url cho citations |

---

## Code flow — trạng thái implement

### [1] Session history lookup

`session_id → _get_history` — trả về sliding window **N=12 turns** (6 exchanges = initial + 5 follow-ups) từ in-memory dict `_sessions`.  
Không có session_id → `history = []`, bỏ qua rewrite.

`session_id` do FE generate bằng `crypto.randomUUID()` **trước khi gửi request đầu tiên** — đảm bảo turn 1 được lưu vào `_sessions` ngay từ đầu.

### [2] Question rewrite

Nếu `history` tồn tại: gọi small LLM (`rewrite_question`) để viết lại câu hỏi thành **standalone** — loại bỏ pronoun, tham chiếu ngữ cảnh ("cái đó", "họ", "tuần trước đó").  
Output: `standalone` — dùng cho toàn bộ các bước sau.

### [3] Intent detection ∥ Embedding (parallel)

`ThreadPoolExecutor(max_workers=2)` chạy song song:

- `detect_intent(standalone)` → gọi **Haiku** (`BEDROCK_INTENT_MODEL`) hoặc Gemini Flash
- `_embed_queries([standalone])` → vector cho semantic search

Intent schema trả về:

```
market, sector, period, period_start, use_latest,
result_type, funnel_stage, needs_citations, out_of_scope
```

`period_start`: intent model tính từ `today` (được inject vào prompt) — xử lý được "tuần trước", "tháng này", "Q1 2026", v.v.  
Fail → fallback `_intent_defaults()` (không crash).

### [3a] Out-of-scope gate

`out_of_scope=true` → trả về canned response ngay, **không query DB, không gọi LLM lớn**.

### [4] Phase 1 — structured-first, semantic fallback

**Routing:** `intent_has_period = period_start is not None OR use_latest`

**Nếu `intent_has_period=True` → `query_insights_structured`:**

Query thẳng bảng `insights` (LEFT JOIN `insight_embeddings` để lấy `embedding_text`):

- `i.period = ?` + range overlap `i.period_start <= anchor AND i.period_end >= anchor`
- `i.market = ?` nếu có
- `i.result_type = ?` nếu có
- Không dùng vector — `score = 1.0` (exact match)
- Nếu trả về 0 rows → fallback sang semantic (`retrieval_mode = "semantic-fallback"`)

**Nếu `intent_has_period=False` (câu hỏi mơ hồ, không rõ period) → `query_insight_embeddings`:**

Vector search trên `insight_embeddings` JOIN `insights`:

- Filter: `i.period`, range overlap, `i.market`, `i.result_type`
- Rank bằng cosine similarity (`1 - embedding <=> vector`)
- Trả về top `_INSIGHT_TOP_K=4` chunks kèm cosine score

**Lý do chọn structured-first:**

- `insights` là dữ liệu đã batch-compute theo đúng business slice (period × market × result_type) — chính xác hơn embedding_text
- Phần lớn câu hỏi chat thực tế map được sang period/market/result_type → query thẳng đúng hơn
- Semantic search dễ trả về row "gần nghĩa" nhưng sai business slice (sai period, sai market)
- `insight_embeddings` phù hợp để cứu các câu hỏi mơ hồ, thiếu cấu trúc, hoặc dạng narrative

### [5] Graceful fallback — no signals

`total_signals == 0` → canned response "chưa có dữ liệu", stop. (cần check lại)

### [6] insight_low — đánh giá chất lượng insight

```python
top_insight_score = insight_ctx[0]["score"] if insight_ctx else 0.0
insight_low = top_insight_score < 0.5
```

**Score là cosine similarity** giữa câu hỏi và insight embedding (range 0–1):

- `> 0.7` — rất gần, insight rõ ràng liên quan
- `0.5–0.7` — tương đối liên quan
- `< 0.5` — thấp, insight tìm được nhưng không khớp tốt với câu hỏi

`insight_low=True` có nghĩa: insight hiện có không đủ gần để trả lời tốt câu hỏi → **trigger Phase 2** để bổ sung signals.

> **Lưu ý thiết kế:** `insight_low` hiện đảm nhiệm hai vai trò: (1) quyết định có fetch signals không, (2) kiểm soát việc inject `[NO MATCHING DATA]` vào prompt (xem [8]). Hai vai trò này đang được xem xét tách ra — xem `NOTES.md`.

### [7] Phase 2 — signal vector search (conditional)

Chỉ chạy khi `needs_citations=True` **hoặc** `insight_low=True`.

`query_signal_embeddings(conn, vector, intent)`:

- Filter: `market`, `sector`, `funnel_stage`
- Filter theo period: `s.record_date >= period_start AND s.record_date <= period_end`  
  _(đảm bảo signals thuộc đúng window được hỏi, không lấy tràn lan mọi period)_
- Trả về top `_VECTOR_TOP_K=8` chunks kèm `source_url` (dùng cho citations)

### [8] Build prompt

Template: `INSIGHTS (PRIMARY) → SIGNALS (EVIDENCE) → HISTORY → QUESTION`

- `insight_low=True` hoặc `not insight_ctx` → inject `[NO MATCHING DATA]` vào INSIGHTS section
- Signal section: mỗi chunk kèm header `[source | funnel_stage | score] url=...`
- Citation format enforce: `{"label": "...", "url": "..."}` — chỉ từ `source_url` của SIGNALS

### [9] LLM answer

`call_llm(prompt)` → **Sonnet** (`BEDROCK_CHAT_MODEL_ID`) hoặc Gemini.  
Parse JSON response: `{"answer": "...", "references": [...]}`.  
Max 5 references.

### [10] Append history

`_append_history(session_id, "user", question)` + `_append_history(session_id, "assistant", answer)`.

---

**Đã bỏ:** `query_aurora` background aggregates (`pain_points`, `use_cases` TEXT[] không `GROUP BY` được vì exact-string match), `_extract_keywords`, `raw_text ILIKE`.

---

_Backlog còn lại xem `NOTES.md`._
