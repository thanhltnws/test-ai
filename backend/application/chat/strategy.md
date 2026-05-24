# Chat RAG Strategy — Question-Type Routing

> File này ghi lại chiến thuật RAG cho chat lambda. Liên quan: `backlog.md` (backlog cụ thể).

---

## Nguyên tắc cốt lõi

**Router chính là loại câu hỏi, không phải period.**

`period` và `market` là filter phổ thông — áp vào tất cả queries ở mọi flow để thu hẹp data về đúng time window và thị trường. Chúng không quyết định bảng nào được query.

| Bảng                              | Vai trò                                               |
| --------------------------------- | ----------------------------------------------------- |
| `insights` + `insight_embeddings` | Pre-computed narratives theo period/market/result_type |
| `signals` + `signal_embeddings`   | Raw customer signals, granular evidence, source_url   |

---

## Routing

### Strategy 0 — Baseline _(chỉ để tham khảo, không implement)_

Query tất cả bảng, chỉ áp filter thời gian. Không phân biệt loại câu hỏi — merge toàn bộ insights + signals trong period vào một prompt, để LLM tự tổng hợp.

Dạng đơn giản nhất của RAG: không sai do routing nhầm, nhưng prompt phình to khi data tăng. Hữu ích để benchmark chất lượng answer trước khi tune routing.

### Strategy 1 — 3-Flow Routing _(đang dùng)_

```text
question
   │
   ├─ result_type detected? (pain_points_summary / funnel_distribution / icp_narrative / recommendations)
   │     YES → Flow A: SQL trên insights
   │
   └─ NO → question_type?
             │
             ├─ "summary" → Flow B: semantic trên insight_embeddings
             │
             └─ null / mở / mơ hồ / khác → Flow C: semantic trên signal_embeddings
```

### Flow A — result_type known

Câu hỏi map rõ vào một trong 4 loại output dashboard đã có sẵn.

- `query_insights_structured()`: SQL trực tiếp, filter `period` + `period_start` + `market` + `result_type`. Score = 1.0.
- 0 rows → fallback `query_insight_embeddings()` (flow ghi là `A-fallback`).
- Signal: `top_k=3`, vai trò bổ sung citations.

### Flow B — summary

Câu hỏi về tổng quan, trend, pattern — không map rõ result_type nhưng rõ là hỏi ở mức tổng hợp.

- `query_insight_embeddings()`: vector search trên `insight_embeddings`, top `_INSIGHT_TOP_K=4`.
- Signal: `top_k=3` thông thường, `_VECTOR_TOP_K` khi `needs_citations=True`.

### Flow C — open / ambiguous / other (default fallback)

Câu hỏi mở, mơ hồ, drill-down, hoặc không xác định được loại.

- Không query insights.
- `query_signal_embeddings()`: vector search trên `signal_embeddings`, `top_k=_VECTOR_TOP_K`.
- `null` question_type cũng rơi vào đây — tránh over-route sang insight side khi không chắc.

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

- Intent: **Haiku** (`BEDROCK_INTENT_MODEL`) hoặc Gemini Flash.
- Schema: `market, sector, period, period_start, use_latest, result_type, question_type, funnel_stage, needs_citations, out_of_scope`.
- `period_start` luôn được tính — default tháng trước khi không nhắc thời gian.
- `result_type`: detect dựa trên keyword mapping (pain/funnel/ICP/recommendations).
- `question_type`: "summary" | null — quyết định Flow B vs C.
- Fail → fallback `intent_defaults()`.
- Embedding: vector cho semantic search ở Flow B/C.

### [2a] Out-of-scope gate

`out_of_scope=true` → canned response ngay, **không query DB, không gọi LLM lớn**.

### [3] Retrieval — 3-flow

Xem 3-Flow Routing ở trên. Tất cả query functions đều nhận `intent` và apply filter `market`, `sector`, `funnel_stage`, `period` từ đó.

`query_signal_embeddings` filter period theo `COALESCE(record_date, extracted_at::date)`.
`query_insights_structured` filter period theo `period_start <= anchor AND period_end >= anchor`.
`query_insight_embeddings` filter tương tự structured nhưng rank bằng cosine similarity.

### [4] Build prompt

Flow A/B: template 2 section — `INSIGHTS` trên, `SIGNALS` dưới, label trung tính (không bias "primary/evidence").
Flow C: template 1 section — chỉ `SIGNALS`.

Không inject `[NO MATCHING DATA]` cho Flow C vì insights không được query.
Flow A/B: `insight_ctx` rỗng → inject `[NO MATCHING DATA]` vào section INSIGHTS.

History block prepend trước `QUESTION` ở mọi flow.

### [5] LLM answer

`call_llm(prompt)` → **Sonnet** (`BEDROCK_CHAT_MODEL_ID`) hoặc Gemini.
Parse JSON response qua `json_repair` trước `json.loads`: `{"answer": "...", "references": [...]}`.
Max 5 references — chỉ từ `source_url` của SIGNALS.

### [6] Append history

`_append_history(session_id, "user", question)` + `_append_history(session_id, "assistant", answer)`.

---

**Đã bỏ:** `query_aurora` background aggregates, `_extract_keywords`, `raw_text ILIKE`, `insight_low` metric, `intent_has_period` / `intent_structured` discriminators.

---

_Backlog còn lại xem `backlog.md`._
