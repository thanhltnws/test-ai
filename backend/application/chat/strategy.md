# Chat RAG Strategy — Insights-First

> File này ghi lại chiến thuật RAG cho chat lambda. Liên quan: `backlog.md` (backlog cụ thể).

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

### [1] Session context

`session_id → _get_history` — trả về sliding window **N=12 turns** từ in-memory dict `_sessions`.  
Không có session_id → `history = []`, bỏ qua rewrite.

`session_id` do FE generate bằng `crypto.randomUUID()` trước khi gửi request đầu tiên.

Nếu `history` tồn tại: gọi small LLM (`rewrite_question`) viết lại câu hỏi thành **standalone** — loại bỏ pronoun, tham chiếu ngữ cảnh ("cái đó", "họ", "tuần trước đó").  
Output: `standalone` — dùng cho toàn bộ các bước sau. Lưu `question` gốc vào history, không phải `standalone`.

### [2] Intent detection (LLM)

`detect_intent(standalone)` và `_embed_queries([standalone])` chạy song song (`ThreadPoolExecutor`).

- Intent: **Haiku** (`BEDROCK_INTENT_MODEL`) hoặc Gemini Flash. Schema: `market, sector, period, period_start, use_latest, result_type, funnel_stage, needs_citations, out_of_scope`. `period_start` được model tính từ `today` — xử lý được "tuần trước", "Q1 2026", v.v. Fail → fallback `_intent_defaults()`.
- Embedding: vector cho semantic search ở Phase 1 + 2.

### [2a] Out-of-scope gate

`out_of_scope=true` → canned response ngay, **không query DB, không gọi LLM lớn**.

### [3] Phase 1 — structured-first, semantic fallback

**Routing:** `intent_has_period = period_start is not None OR use_latest`

**`intent_has_period=True` → `query_insights_structured`:** query thẳng `insights` LEFT JOIN `insight_embeddings`, filter `period` + range overlap + `market` + `result_type`. Score = 1.0 (exact match). 0 rows → fallback semantic.

**`intent_has_period=False` → `query_insight_embeddings`:** vector search trên `insight_embeddings` JOIN `insights`, rank cosine similarity, top `_INSIGHT_TOP_K=4`.

**Lý do structured-first:** phần lớn câu hỏi map được sang period/market/result_type → query thẳng đúng hơn semantic (vốn dễ trả về đúng nghĩa nhưng sai business slice).

**Post-processing:**

- `insight_low = top_insight_score < 0.5` — metric đánh giá chất lượng insight, ảnh hưởng `top_k` ở Phase 2.
- `not insight_ctx` → inject `[NO MATCHING DATA]` vào prompt ở bước [5].

### [4] Phase 2 — signal vector search (always)

Luôn chạy. `top_k` dynamic: `_VECTOR_TOP_K` khi `insight_low=True` hoặc `needs_citations=True`; `3` khi insight đủ (giảm prompt size, vẫn đủ source_url cho references).

`query_signal_embeddings(conn, vector, intent, top_k)` — primary table là `signal_embeddings` (vector ranking), JOIN `signals` để lấy metadata (`source`, `source_url`, `funnel_stage`) và apply WHERE filter:

- Filter: `s.market`, `s.sector`, `s.funnel_stage` từ intent
- Filter period: `s.record_date >= period_start AND s.record_date <= period_end` _(window đúng, không lấy tràn lan)_
- Rank bằng cosine similarity — phù hợp hơn structured query vì `signals` không có dimension tương đương `result_type` của `insights` để exact match
- Trả về top `top_k` chunks kèm `source_url` (dùng cho citations)

### [5] Build prompt

Template: `INSIGHTS (PRIMARY) → SIGNALS (EVIDENCE) → HISTORY → QUESTION`

- `not insight_ctx` → inject `[NO MATCHING DATA]` vào INSIGHTS section
- Signal section: mỗi chunk kèm header `[source | funnel_stage | score] url=...`
- Citation format enforce: `{"label": "...", "url": "..."}` — chỉ từ `source_url` của SIGNALS

### [6] LLM answer

`call_llm(prompt)` → **Sonnet** (`BEDROCK_CHAT_MODEL_ID`) hoặc Gemini.  
Parse JSON response: `{"answer": "...", "references": [...]}`.  
Max 5 references.

### [7] Append history

`_append_history(session_id, "user", question)` + `_append_history(session_id, "assistant", answer)`.

---

**Đã bỏ:** `query_aurora` background aggregates (`pain_points`, `use_cases` TEXT[] không `GROUP BY` được vì exact-string match), `_extract_keywords`, `raw_text ILIKE`.

---

_Backlog còn lại xem `backlog.md`._
