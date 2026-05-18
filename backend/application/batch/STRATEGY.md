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

- `summary`: tổng số signals, avg confidence score
- `top_pain_points`: unnest array `pain_points`, đếm tần suất
- `top_objections`: unnest array `objections`
- `top_use_cases`: unnest array `use_cases`
- `funnel_distribution`: đếm theo `funnel_stage`, tính %
- `icp_breakdown`: GROUP BY `sector` (column), `icp->>'company_size'`, `icp->>'deal_size'`

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

### Hướng prefer - chưa apply: Vietnamese từ transform (Hướng 1)

Toàn bộ pipeline chạy tiếng Việt từ tầng transform — `pain_points`, `objections`, `use_cases`, `embedding_text` trong `signals` đều là tiếng Việt. Batch prompt thêm instruction output tiếng Việt, nhận Vietnamese SQL context → generate Vietnamese narrative tự nhiên.

**Hướng thay thế đã cân nhắc — Hướng 2 (Vietnamese chỉ ở batch output):**
Giữ transform tiếng Anh, chỉ instruct batch ra tiếng Việt. Lợi điểm: Cohere multilingual có giá trị thực ở chat (user hỏi tiếng Việt → search English `embedding_text` → cross-lingual). Nhược điểm: batch nhận SQL context tiếng Anh rồi phải "dịch ngược" khi generate narrative — không sạch; data trong DB là tiếng Anh trong khi app nội bộ thuần Việt.

**Lý do chọn Hướng 1:** App nội bộ, user thuần Việt. Cohere multilingual trong Hướng 2 có giá trị nhưng chỉ ở chat, không đủ để đánh đổi sự nhất quán của toàn pipeline. Hướng 1 sạch hơn: DB tiếng Việt, batch context tiếng Việt, output tiếng Việt.

**Tác động đến `_VECTOR_QUERIES`:** Khi transform ra tiếng Việt, cần đổi `_VECTOR_QUERIES` sang tiếng Việt để đồng nhất — English query search trên Vietnamese `embedding_text` hoạt động được nhờ Cohere multilingual nhưng không tối ưu.

---

## Known Issues

### `write_insight_embeddings` dùng sai `input_type`

`_embed_bedrock` dùng `"input_type": "search_query"` cho cả việc lưu document vào `insight_embeddings`. Đúng ra phải dùng `"search_document"` (Cohere) / `"RETRIEVAL_DOCUMENT"` (Gemini) khi embed text để index. `signal_embeddings` được import đúng với `search_document` — chỉ `insight_embeddings` từ Lambda bị sai.

Fix: tách riêng `_embed_documents()` dùng `search_document`, dùng nó trong `write_insight_embeddings` thay vì `_embed_queries`.

---

## Backfill

Lambda thông thường chỉ tính period hiện tại (từ đầu tuần/tháng/quý/năm đến hôm nay). Để backfill dữ liệu lịch sử (seed data), dùng `backend/seed/run_batch.py` — script này lặp qua tất cả các period trong khoảng seed data thay vì chỉ tính period hiện tại.
