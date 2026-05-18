# Batch Insight Builder — Strategy

## Mục tiêu

Chạy định kỳ (EventBridge daily trigger) để tổng hợp toàn bộ tín hiệu khách hàng trong kỳ, sinh pre-computed insights lưu vào bảng `insights`. Frontend dashboard đọc trực tiếp từ bảng này — không call LLM real-time.

---

## Granularity và lịch chạy

Mỗi lần Lambda được trigger, nó xét 4 granularity:

| Granularity | Period window            | Điều kiện chạy                |
| ----------- | ------------------------ | ----------------------------- |
| `weekly`    | Thứ 2 đầu tuần → hôm nay | Luôn chạy                     |
| `monthly`   | Ngày 1 tháng → hôm nay   | Luôn chạy                     |
| `quarterly` | Ngày 1 quý → hôm nay     | Mỗi thứ 2, hoặc ngày cuối quý |
| `yearly`    | 1/1 → hôm nay            | Ngày 1 mỗi tháng, hoặc 31/12  |

`weekly` và `monthly` chạy mỗi ngày → snapshot rolling, không phải snapshot cuối kỳ. Một trigger duy nhất có thể sinh tối đa 4 LLM calls (1 per granularity).

---

## Pipeline mỗi granularity

```
Aurora (SQL aggregates)  ──┐
                            ├─→ build_batch_prompt → LLM → parse JSON → write_insights
pgvector (semantic search) ─┘
```

### 1. Query Aurora

`query_aurora()` chạy 6 câu SQL trên bảng `signals`, filter theo `COALESCE(record_date, extracted_at::date)`:

- `summary`: tổng số signals
- `top_pain_points`: unnest array `pain_points`, đếm tần suất
- `top_objections`: unnest array `objections`
- `top_use_cases`: unnest array `use_cases`
- `funnel_distribution`: đếm theo `funnel_stage`, tính %
- `icp_breakdown`: GROUP BY flat columns `deal_size`, `client_type`, `tech_maturity`, `sector`, `market`

**Đánh giá 6 queries:**

6 queries là hợp lý cho batch job — latency không phải ưu tiên, mỗi query phục vụ đúng 1 slice context cho LLM prompt, không có query nào thừa.

Điểm cần lưu ý:

- `top_pain_points`, `top_objections`, `top_use_cases` cùng pattern unnest-GROUP BY-COUNT, chỉ khác tên array column. Có thể gộp thành helper function trong code để tránh lặp logic, nhưng không cần thiết về mặt SQL.
- `summary` chỉ trả về count + avg confidence. Có thể bổ sung `COUNT(DISTINCT customer_id)` nếu schema có field đó, để LLM biết số lượng khách hàng thực sự (không chỉ số tín hiệu).

### 2. Query pgvector

`query_pgvector()` chạy 3 semantic queries cố định:

```python
_VECTOR_QUERIES = [
    "customer pain points and challenges",
    "sales objections and friction",
    "product use cases and applications",
]
```

Mỗi query → embed → cosine similarity search trên `signal_embeddings`, lấy top 10. Deduplicate theo `signal_id`. Kết quả trả về sorted by score desc.

**Embedding model:**

- Dev (local): Gemini `gemini-embedding-001`, `RETRIEVAL_QUERY`, dim=1024
- Prod (Lambda): Bedrock `cohere.embed-multilingual-v3`, `search_query`

Phải đồng bộ với model dùng lúc import (`search_document`). Nếu đổi model thì phải re-embed toàn bộ `signal_embeddings`.

### 3. LLM call

1 call duy nhất với prompt gộp cả SQL context và vector context.

**Model:**

- Dev: Gemini `gemini-3.1-flash-lite-preview`
- Prod: Bedrock Haiku (`BEDROCK_MODEL_ID` từ env, default `apac.anthropic.claude-3-haiku-20240307-v1:0`)

Chọn Haiku vì output có cấu trúc JSON rõ ràng, prompt template cố định — không cần reasoning phức tạp.

### 4. Output — 4 result types

LLM trả về JSON với đúng 4 keys, mỗi key là 1 `result_type`:

| result_type           | Nội dung                                            |
| --------------------- | --------------------------------------------------- |
| `pain_points_summary` | Top pain points + narrative tổng hợp                |
| `funnel_distribution` | Counts và % theo stage + nhận xét sức khỏe funnel   |
| `icp_narrative`       | Top 5 ICP segments + narrative mô tả ideal customer |
| `recommendations`     | Action items cho Sales và Marketing                 |

### 5. Ghi vào DB

`write_insights()` insert 1 row per result_type vào bảng `insights`:

```
(period, period_start, period_end, result_type, payload)
```

Bảng là **append-only** — không update, không xóa. Mỗi lần chạy thêm 4 rows mới cho granularity đó. Frontend query row mới nhất theo `(period, result_type)`.

---

## Dev vs Prod

Provider được chọn qua `LLM_PROVIDER` env var (`gemini` | `bedrock`, default `bedrock`).

|           | Dev (local)              | Prod (Lambda)               |
| --------- | ------------------------ | --------------------------- |
| LLM       | Gemini API               | Bedrock Haiku               |
| Embedding | Gemini embedding         | Bedrock Cohere multilingual |
| DB        | `DATABASE_URL` từ `.env` | Secret từ `DB_SECRET_ARN`   |

---

## Language Strategy

### Hướng đang apply (Hướng 2): Vietnamese chỉ ở batch output

Transform vẫn ra tiếng Anh — `pain_points`, `objections`, `use_cases`, `embedding_text` trong `signals` là tiếng Anh. `prompt.py` thêm instruction output tiếng Việt → batch nhận SQL context tiếng Anh nhưng generate narrative tiếng Việt.

**Hướng thay thế cần cân nhắc — Hướng 1 (Vietnamese từ transform):**
Toàn bộ pipeline chạy tiếng Việt từ tầng transform. Lợi điểm: nhất quán hoàn toàn, batch nhận Vietnamese context → generate Vietnamese tự nhiên hơn. Nhược điểm: Cohere multilingual mất lợi thế ở chat (user hỏi tiếng Việt → search Vietnamese `embedding_text` — cross-lingual không còn cần thiết, nhưng cũng không còn là giá trị thêm).

**Tradeoff chính:** Hướng 2 hiện tại không sạch — DB tiếng Anh nhưng app hiển thị tiếng Việt. Hướng 1 sạch hơn nhưng đòi hỏi re-generate seed data và đổi `_VECTOR_QUERIES` sang tiếng Việt. Chưa quyết định, để lại để cân nhắc sau.

---

## Pending Design Decisions

### icp_breakdown query — 5D GROUP BY vs per-dimension distributions

Hiện tại `icp_breakdown` GROUP BY 5 columns cùng lúc (`deal_size`, `client_type`, `tech_maturity`, `sector`, `market`). Với data nhỏ, hầu hết combinations có count=1 — LLM khó rút ra ICP profile có nghĩa.

**Hướng cần xem lại:** Đổi sang 5 distribution riêng (1D per column) — LLM nhận "40% startup, 35% corporate..." thay vì list exact combos sparse. Cũng là input tốt hơn cho `icp_chart` nếu thêm result_type đó sau.

### Phân loại theo ICP và funnel_stage — pre-compute vs chat

Requirement "phân loại theo market, ICP và funnel_stage" có thể tách làm 2 use case:

- **Market:** đã pre-compute per slice trong `insights` — hợp lý vì Japan vs Vietnam có narrative khác nhau căn bản.
- **ICP và funnel_stage:** *không* nên pre-compute thêm slice — quá nhiều LLM calls (sector×funnel = 45 combos), giá trị narrative không tương xứng.

**Hướng đề xuất:**

1. Thêm `result_type` thứ 5 (`icp_chart`) vào cùng batch prompt — LLM generate chart-ready data từ distributions sẵn có, không tốn thêm LLM call.
2. "Phân loại theo ICP/funnel_stage" theo kiểu dynamic → use case của **chat lambda**: user hỏi → chat filter `signals` bằng flat indexed columns + RAG retrieval.

Chưa implement, cần quyết định trước khi làm frontend dashboard chart.

---

## Known Issues

### Không có minimum signal threshold

Hiện tại chỉ skip khi `total_signals == 0`. Slice có `signals=1` vẫn call LLM và ra 4 insight rows — `icp_narrative` từ 1 signal, `funnel_distribution` từ 1 signal không có nghĩa, LLM sẽ hallucinate.

Fix: đổi `if total == 0` thành `if total < MIN_SIGNALS` (đề xuất 3–5) trong cả `handler.py` lẫn `run_batch.py`.

### `query_pgvector` không filter theo date range

`query_pgvector(conn, p_start, p_end)` nhận `p_start`/`p_end` nhưng thực tế search toàn bộ `signal_embeddings` không giới hạn period. Hậu quả: slice `signals=1` nhưng `semantic=11` — LLM nhận context từ signals ngoài period window, insight bị lẫn lộn cross-period.

Fix: thêm JOIN `signal_embeddings → signals ON signal_id` với filter `record_date BETWEEN p_start AND p_end` trong query cosine similarity.

### Payload chứa content không grounded vào signals thực tế

Nhiều insight rows có narrative/recommendations "sáng tạo" — không phản ánh data trong bảng `signals`. Nguyên nhân có thể là tổ hợp: (1) vector context cross-period (issue trên), (2) threshold quá thấp (1 signal), (3) top_k semantic search chưa được tune đúng.

Cần review: so sánh payload trong `insights` với raw signals trong cùng period/market để xác định LLM đang hallucinate ở mức nào.

### top_k semantic search chưa được review

`query_pgvector` hiện lấy top 10 per query (3 queries cố định) → tối đa 30 chunks trước dedup. Chưa đánh giá: top_k = 10 có phù hợp không, hay nên scale theo `total_signals` (ít signals → top_k nhỏ hơn để tránh over-retrieve), hoặc dùng threshold similarity score thay vì fixed k.

Cần review kỹ trước khi dùng batch insights cho demo.

### `write_insight_embeddings` dùng sai `input_type`

`_embed_bedrock` dùng `"input_type": "search_query"` cho cả việc lưu document vào `insight_embeddings`. Đúng ra phải dùng `"search_document"` (Cohere) / `"RETRIEVAL_DOCUMENT"` (Gemini) khi embed text để index. `signal_embeddings` được import đúng với `search_document` — chỉ `insight_embeddings` từ Lambda bị sai.

Fix: tách riêng `_embed_documents()` dùng `search_document`, dùng nó trong `write_insight_embeddings` thay vì `_embed_queries`.

---

## Backfill

Lambda thông thường chỉ tính period hiện tại (từ đầu tuần/tháng/quý/năm đến hôm nay). Để backfill dữ liệu lịch sử (seed data), dùng `backend/seed/run_batch.py` — script này lặp qua tất cả các period trong khoảng seed data thay vì chỉ tính period hiện tại.
