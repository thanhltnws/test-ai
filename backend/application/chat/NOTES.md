# Chat Lambda — Implementation Notes

> Xem `docs/chat_optimization.md` cho full design doc. File này là backlog implement cụ thể cho `handler.py` + `prompt.py`.

---

## Trạng thái hiện tại (gaps)

- Stateless — không nhớ lịch sử hội thoại
- Sequential — `query_aurora` xong mới `query_pgvector`, không song song
- Không có graceful fallback khi context rỗng hoặc score thấp
- `query_pgvector` chỉ query `signal_embeddings`, bỏ qua `insight_embeddings`
- Keyword matching (`raw_text ILIKE`) bị lock vào English stop words, miss tiếng Việt
- `query_aurora` dùng LIMIT cứng (top 15/10) không filter theo intent câu hỏi
- Citation format `{label, url}` chưa được enforce đúng trong prompt
- Không có empty context gate — LLM vẫn được gọi khi `total_signals == 0`

---

## P1 — Impact cao / Effort thấp

### ~~① Parallel SQL + pgvector~~ ✓ done

`handler.py:336–340` — hiện tại tuần tự. Dùng `ThreadPoolExecutor` (không cần async rewrite toàn handler):

```python
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=2) as ex:
    f_sql    = ex.submit(query_aurora, conn, question)
    f_vector = ex.submit(query_pgvector, conn, question)
sql_ctx, vector_ctx = f_sql.result(), f_vector.result()
```

### ② Graceful fallback khi thiếu data

Hai trường hợp cần xử lý:

- `total_signals == 0` → DB chưa có data → trả canned response ngay, không call LLM (tránh tốn token)
- `vector_ctx` empty hoặc top-1 score < 0.5 → inject `[KHÔNG CÓ KẾT QUẢ PHÙ HỢP]` vào prompt thay vì để model hallucinate

Cần pass `vector_top_score` vào `build_chat_prompt`.

### ③ Query insight_embeddings

`query_pgvector` hiện chỉ query `signal_embeddings`. Cần thêm query song song trên `insight_embeddings` JOIN `insights` để có narrative context từ batch pipeline. Merge cả hai vào prompt.

```
signal_embeddings  → granular evidence + source_url
insight_embeddings → pre-computed narratives (icp, pain_points_summary, recommendations)
```

### ④ Citation format trong prompt

Verify `build_chat_prompt` enforce output format `references: [{label, url}]` rõ ràng. `source_url` đã có trong cả pgvector result lẫn signal row — chỉ cần prompt instruction.

---

## P2 — Impact trung bình / Effort thấp-trung bình

### ⑤ Session history — sliding window N=6

Thêm `session_id` vào request body. Lưu history tạm bằng in-memory dict trước (Redis sau nếu cần). Prepend N=6 turns `{role, content}` gần nhất vào prompt. TTL conceptual: 30 phút.

```python
_sessions: dict[str, list[dict]] = {}  # session_id → turns

def _get_history(sid: str) -> list[dict]:
    return _sessions.get(sid, [])[-6:]  # last 6 turns

def _append_history(sid: str, role: str, content: str) -> None:
    _sessions.setdefault(sid, []).append({"role": role, "content": content})
```

### ⑥ Follow-up resolution

Nếu session có history, rewrite câu hỏi thành dạng standalone trước khi embed + search:

```
turn[-1]: "Khách fintech gặp vấn đề gì với tích hợp API?"
turn[0]:  "Còn về chi phí thì sao?"
→ rewrite: "Khách fintech gặp vấn đề gì về chi phí tích hợp API?"
```

1 LLM call nhỏ (Haiku) trước khi embed. Bỏ qua nếu session history empty.

### ⑦ Pre-call intent + metadata filter

1 LLM call (Haiku) phân tích câu hỏi, output `{sector, market, funnel_stage, period_hint, keywords_en[]}`.

Dùng output này để:

- pgvector metadata pre-filter (`WHERE metadata->>'sector' = ?`) — GIN index đã sẵn
- `keywords_en` thay thế `_extract_keywords` (English stop words bị lock)
- Detect out-of-scope → trả fallback ngay không cần query DB

Quan trọng: output `null` cho field không có signal rõ ràng trong câu hỏi, không được suy diễn.

---

## P2 — Cần làm ngay (fix bugs / logic)

### ⑧ Bỏ keyword matching `raw_text ILIKE`

`_extract_keywords` + `raw_text ILIKE` có 2 vấn đề:

1. Stop words chỉ có English — tiếng Việt lọt qua hết
2. Match theo chữ, miss semantic ("khó kết nối" ≠ "vấn đề tích hợp")

pgvector semantic search cover tốt hơn. Bỏ keyword matching, giữ background aggregates SQL (funnel counts, top pain points toàn dataset).

### ⑨ Bỏ LIMIT cứng ở background aggregates

`top_pain_points LIMIT 15`, `top_use_cases LIMIT 10` không filter theo intent. Seed data ~50 pain points tối đa — bỏ LIMIT, trả hết để LLM có đủ context, không bị miss item liên quan.

---

## P3 — Defer / sau demo

### ⑩ Response streaming

`invoke_model_with_response_stream` (Bedrock) + `FunctionResponseTypes: [RESPONSE_STREAM]` (Lambda) + SSE (frontend). Đụng infra, để sau.

### ⑪ Response cache Redis

Demo scale — ít câu hỏi lặp. Skip.

### ⑫ Structured logging

Log per request: `{session_id, intent, sql_rows, vector_top_score, tokens_in, tokens_out, latency_ms, cache_hit}`. Implement sau khi P1/P2 xong.

### ⑬ Rolling summary

Sliding window N=6 đủ cho demo. Defer.

---

## Thứ tự implement

```text
① Parallel  →  ② Fallback  →  ③ insight_embeddings  →  ④ Citation
→  ⑧ Bỏ keyword matching  →  ⑨ Bỏ LIMIT
→  ⑤ Session history  →  ⑥ Follow-up rewrite  →  ⑦ Pre-call intent
→  ⑩ Streaming (nếu còn thời gian)
```
