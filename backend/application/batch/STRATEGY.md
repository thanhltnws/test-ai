# Batch Insight Builder — Strategy

## Mục tiêu

Chạy định kỳ (EventBridge daily trigger) để tổng hợp toàn bộ tín hiệu khách hàng trong kỳ, sinh pre-computed insights lưu vào bảng `insights`. Frontend dashboard đọc trực tiếp từ bảng này — không call LLM real-time.

---

## Granularity và lịch chạy

Mỗi lần Lambda được trigger, nó xét các granularity sau:

| Granularity | Period window | Điều kiện chạy | Trạng thái |
| --- | --- | --- | --- |
| `weekly` | Thứ 2 đầu tuần → hôm nay | Luôn chạy | Bật |
| `monthly` | Ngày 1 tháng → hôm nay | Luôn chạy | Bật |
| `quarterly` | Ngày 1 quý → hôm nay | Mỗi thứ 2, hoặc ngày cuối quý | Tạm tắt |
| `yearly` | 1/1 → hôm nay | Ngày 1 mỗi tháng, hoặc 31/12 | Tạm tắt |

`weekly` và `monthly` chạy mỗi ngày → snapshot rolling, không phải snapshot cuối kỳ.

`quarterly` và `yearly` tạm tắt trong khi data còn nhỏ — cần đánh giá token budget thực tế khi dataset đạt ~100+ signals trước khi bật lại.

**Market slicing:** Batch chạy theo từng market trong `MARKETS = [None, "vietnam", "japan", "korea", "international"]` — `None` là slice toàn thị trường (không filter). Mỗi (granularity × market) là 1 LLM call độc lập. Với cấu hình hiện tại (2 granularity × 5 market), mỗi trigger sinh tối đa **10 LLM calls**.

---

## Pipeline mỗi granularity

```
Aurora (raw signals + Python aggregates)  ──→ build_batch_prompt → LLM → parse JSON → write_insights
```

### 1. Query Aurora

`query_aurora()` chạy **1 câu SQL duy nhất** trên bảng `signals`, filter theo `COALESCE(record_date, extracted_at::date)`:

```sql
SELECT source, pain_points, objections, use_cases,
       deal_size, client_type, tech_maturity, market, sector, funnel_stage
FROM signals
WHERE COALESCE(record_date, extracted_at::date) BETWEEN %s AND %s
[AND market = %s]
```

Kết quả được xử lý bằng Python (`collections.Counter`) để tính:

- `funnel_distribution`: đếm theo `funnel_stage`, tính %
- `icp_breakdown`: top 10 combinations theo count — 4 chiều `(deal_size, client_type, tech_maturity, sector)` khi đã có market filter, 5 chiều thêm `market` khi slice `market=None`

**Lý do không dùng 6 queries như trước:**

`pain_points`, `objections`, `use_cases` là **free-text arrays** — mỗi phần tử là chuỗi unique. `unnest() GROUP BY` luôn trả về `count=1` cho mọi item, vô nghĩa. LLM nhận list count=1 sẽ fabricate counts bằng cách cluster ngữ nghĩa, không grounded vào data thực.

Với single-query: toàn bộ raw signals được gửi lên prompt → LLM đọc trực tiếp và tự đếm số signals đề cập từng theme. Count trả về là **LLM estimate** (không phải SQL count chính xác), nhưng grounded vào actual signals trong period.

**pgvector không còn được dùng trong batch** — khi toàn bộ raw signals đã có trong prompt, semantic search không bổ sung thêm giá trị.

### 2. LLM call

1 call duy nhất. Prompt structure:

```text
=== AGGREGATE STATS ===
Total signals: N
Funnel distribution: ...
ICP breakdown (top 10): ...

=== RAW SIGNALS (N records) ===
[{source, pain_points, objections, use_cases, deal_size, ...}, ...]
```

**Model:**

- Dev: Gemini `gemini-3.1-flash-lite-preview`
- Prod: Bedrock Haiku (`BEDROCK_MODEL_ID` từ env, default `apac.anthropic.claude-3-haiku-20240307-v1:0`)

Chọn Haiku vì output có cấu trúc JSON rõ ràng, prompt template cố định — không cần reasoning phức tạp.

### 3. Output — 4 result types

LLM trả về JSON với đúng 4 keys, mỗi key là 1 `result_type`:

| result_type           | Nội dung                                            |
| --------------------- | --------------------------------------------------- |
| `pain_points_summary` | Top pain points + narrative tổng hợp                |
| `funnel_distribution` | Counts và % theo stage + nhận xét sức khỏe funnel   |
| `icp_narrative`       | Top 5 ICP segments + narrative mô tả ideal customer |
| `recommendations`     | Action items cho Sales và Marketing                 |

### 4. Ghi vào DB

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

**Tradeoff chính:** Hướng 2 hiện tại không sạch — DB tiếng Anh nhưng app hiển thị tiếng Việt. Hướng 1 sạch hơn nhưng đòi hỏi re-generate seed data. Chưa quyết định, để lại để cân nhắc sau.

---

## Known Issues

### Không có context window guard

Strategy hiện tại gửi toàn bộ raw signals lên prompt — không có giới hạn. Token estimate thô: ~38 tok/signal. Với 200 signals/period → ~7,600 tok chỉ riêng signals, cộng thêm template + aggregate stats có thể vượt ngưỡng an toàn của Haiku (200K token limit về lý thuyết, nhưng prompt quá lớn tăng latency và cost đáng kể).

Cần đánh giá sau khi có dataset ~100+ signals. Nếu cần, thêm truncation: ưu tiên giữ signals gần nhất hoặc sample đều theo funnel stage.

### Không có minimum signal threshold

Hiện tại chỉ skip khi `total_signals == 0`. Slice có `signals=1` vẫn call LLM và ra 4 insight rows — `icp_narrative` từ 1 signal, `funnel_distribution` từ 1 signal không có nghĩa, LLM sẽ hallucinate.

Fix: đổi `if total == 0` thành `if total < MIN_SIGNALS` (đề xuất 3–5) trong cả `handler.py` lẫn `run_batch.py`.

---

## Backfill

Lambda thông thường chỉ tính period hiện tại (từ đầu tuần/tháng/quý/năm đến hôm nay). Để backfill dữ liệu lịch sử (seed data), dùng `backend/seed/run_batch.py` — script này lặp qua tất cả các period trong khoảng seed data thay vì chỉ tính period hiện tại.
