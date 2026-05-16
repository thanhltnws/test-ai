# Batch Insight Builder — Strategy

## Mục tiêu

Chạy định kỳ (EventBridge daily trigger) để tổng hợp toàn bộ tín hiệu khách hàng trong kỳ, sinh pre-computed insights lưu vào bảng `insights`. Frontend dashboard đọc trực tiếp từ bảng này — không call LLM real-time.

---

## Granularity và lịch chạy

Mỗi lần Lambda được trigger, nó xét 4 granularity:

| Granularity | Period window | Điều kiện chạy |
|---|---|---|
| `weekly` | Thứ 2 đầu tuần → hôm nay | Luôn chạy |
| `monthly` | Ngày 1 tháng → hôm nay | Luôn chạy |
| `quarterly` | Ngày 1 quý → hôm nay | Mỗi thứ 2, hoặc ngày cuối quý |
| `yearly` | 1/1 → hôm nay | Ngày 1 mỗi tháng, hoặc 31/12 |

`weekly` và `monthly` chạy mỗi ngày → snapshot rolling, không phải snapshot cuối kỳ. Một trigger duy nhất có thể sinh tối đa 4 LLM calls (1 per granularity).

---

## Pipeline mỗi granularity

```
Aurora (SQL aggregates)  ──┐
                            ├─→ build_batch_prompt → LLM → parse JSON → write_insights
pgvector (semantic search) ─┘
```

### 1. Query Aurora

`query_aurora()` chạy 5 câu SQL trên bảng `signals`, filter theo `COALESCE(record_date, extracted_at::date)`:

- `summary`: tổng số signals, avg confidence score
- `top_pain_points`: unnest array `pain_points`, đếm tần suất
- `top_objections`: unnest array `objections`
- `top_use_cases`: unnest array `use_cases`
- `funnel_distribution`: đếm theo `funnel_stage`, tính %
- `icp_breakdown`: GROUP BY `icp->>'sector'`, `company_size`, `deal_size`, `region`

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

| result_type | Nội dung |
|---|---|
| `pain_points_summary` | Top pain points + narrative tổng hợp |
| `funnel_distribution` | Counts và % theo stage + nhận xét sức khỏe funnel |
| `icp_narrative` | Top 5 ICP segments + narrative mô tả ideal customer |
| `recommendations` | Action items cho Sales và Marketing |

### 5. Ghi vào DB

`write_insights()` insert 1 row per result_type vào bảng `insights`:

```
(period, period_start, period_end, result_type, payload)
```

Bảng là **append-only** — không update, không xóa. Mỗi lần chạy thêm 4 rows mới cho granularity đó. Frontend query row mới nhất theo `(period, result_type)`.

---

## Dev vs Prod

`_is_dev()` kiểm tra env vars theo thứ tự: `APP_ENV` → `ENVIRONMENT` → `ENV` → `STAGE`. Nếu không set, fallback dựa vào sự tồn tại của `AWS_LAMBDA_FUNCTION_NAME` hoặc `DB_SECRET_ARN`.

| | Dev (local) | Prod (Lambda) |
|---|---|---|
| LLM | Gemini API | Bedrock Haiku |
| Embedding | Gemini embedding | Bedrock Cohere multilingual |
| DB | `DATABASE_URL` từ `.env` | Secret từ `DB_SECRET_ARN` |

Để force prod mode khi chạy local: set `APP_ENV=production` trong `.env`.

---

## Backfill

Lambda thông thường chỉ tính period hiện tại (từ đầu tuần/tháng/quý/năm đến hôm nay). Để backfill dữ liệu lịch sử (seed data), dùng `backend/seed/run_batch.py` — script này lặp qua tất cả các period trong khoảng seed data thay vì chỉ tính period hiện tại.
