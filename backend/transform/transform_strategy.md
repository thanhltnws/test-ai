# AI Insight Hub — Transform Strategy (Extraction)

> Spec mô tả chiến lược AI call trong luồng Transform: từ raw record S3 → structured signals Aurora. Dùng để review thiết kế, onboard người mới, và làm baseline khi quyết định nâng cấp.
>
> **Scope:** `backend/transform/handler.py` + `backend/transform/prompt.py`. Seed pipeline (`backend/seed/generate.py`) dùng cùng prompt và cùng batch logic — hai môi trường chạy song song nhưng cùng spec này.

---

## Trạng thái hiện tại

Một Bedrock/Gemini call duy nhất mỗi khi Lambda trigger từ S3 ObjectCreated. Call nhận một batch tối đa 40 records (≤ 150 000 chars), extract tất cả fields cùng lúc theo structured JSON schema, sau đó upsert vào Aurora và pgvector.

```
S3 raw/{source}/{date}/{ts}.json
    → normalize (dedup, text flatten)
    → make_batches (≤40 records, ≤150k chars)
    → _extract_batch (Bedrock Haiku hoặc Gemini Flash)
    → merge + noise filter (_has_signal)
    → upsert signals + signal_embeddings (concurrent)
```

---

## Fields được extract

| Field | Type | Nguồn | Ghi chú |
|---|---|---|---|
| `pain_points` | `TEXT[]` | LLM | Vấn đề thực sự của customer, inferred từ signal |
| `objections` | `TEXT[]` | LLM | Chỉ lấy từ voice của prospect, không phải vendor ghi nhận |
| `use_cases` | `TEXT[]` | LLM | Cách customer dùng hoặc có thể dùng sản phẩm |
| `deal_size` | `TEXT` | LLM | `small` · `medium` · `large` |
| `client_type` | `TEXT` | LLM | `individual` · `startup` · `corporate` |
| `tech_maturity` | `TEXT` | LLM | `non-tech` · `semi-tech` · `technical` |
| `funnel_stage` | `TEXT` | LLM | `awareness` · `consideration` · `negotiation` · `won` · `lost` |
| `source_id` | `TEXT` | LLM | Unique ID từ chính record — fallback về hash nếu thiếu |
| `source_url` | `TEXT` | LLM | URL gốc nếu có; nếu không, fictional demo URL dạng `https://example.com/{source}/{source_id}` |
| `embedding_text` | `TEXT` | LLM | 2–4 câu summary tối ưu cho semantic search |
| `record_date` | `DATE` | LLM + fallback | Date ngữ nghĩa nhất trong record; fallback về candidate fields trong raw nếu LLM không trả |
| `market` | `TEXT` | LLM | `vietnam` · `japan` · `korea` · `international` — target geographic market |
| `sector` | `TEXT` | LLM | `fintech` · `logistics` · `retail` · `healthcare` · `manufacturing` · `software` · `education` · `ict` · `other` |

---

## Prompt design

**File:** `backend/transform/prompt.py` — `_EXTRACT_TEMPLATE`

Toàn bộ prompt logic nằm trong `prompt.py`, không inline trong `handler.py`. Đây là convention cứng của project.

### Cấu trúc prompt

```
[Role]          B2B customer insight analyst
[Context]       Source subfolder name + optional context file content
[Goal]          Surface genuine customer signals, không hallucinate
[Field specs]   Mô tả từng field với guidance rõ ràng về cách infer
[Constraints]   Valid enum values cho mỗi categorical field
[Output format] {n} objects, JSON array, no markdown
[Records]       [Record 1] ... [Record N]
```

### Quyết định thiết kế

**Tại sao batch nhiều records trong một call thay vì call từng cái?**
Token overhead của prompt (system instruction + field specs) chiếm ~800 tokens cố định. Với 40 records/batch, overhead này được amortize. Call đơn lẻ tốn ~820 tokens mỗi record; batch 40 records tốn ~40 tokens overhead/record.

**Tại sao `funnel_stage` có guidance chi tiết theo record type?**
Các record type khác nhau (marketing lead, CRM profile, ops ticket) cho signal khác nhau nhưng dễ bị model confuse. Prompt explicit hóa cách đọc signal theo từng type để giảm inconsistency giữa sources.

**Tại sao `objections` chỉ lấy từ voice của prospect?**
CRM tags, ticket descriptions, và scoring labels phản ánh góc nhìn của vendor, không phải prospect. Lẫn hai nguồn này tạo ra false objections làm sai lệch sales analysis.

**Tại sao `deal_size`, `client_type`, `tech_maturity` là flat column thay vì gom vào `icp` JSONB?**
Cả ba cần indexed filtering trực tiếp (Dashboard filter, RAG metadata filter). JSONB không thể index theo field con hiệu quả. Flat columns cũng làm CHECK constraint và Pydantic validation đơn giản hơn. `icp` JSONB đã bị loại bỏ hoàn toàn.

**Tại sao `sector` và `market` là top-level column?**
Cùng lý do — cần indexed filtering. `sector` và `market` được extract thẳng thành column riêng từ đầu, không qua JSONB.

---

## Batch strategy

| Parameter | Giá trị | Lý do |
|---|---|---|
| `MAX_BATCH_CHARS` | 150 000 | Dưới context limit của Haiku (200k). Buffer cho prompt overhead. |
| `MAX_BATCH_RECORDS` | 40 | Trên 40 records, JSON output dài làm tăng lỗi cấu trúc và field confusion. |
| `API_DELAY_S` | 1.0s | Rate limit buffer giữa các batch. |

Nếu response trả ít hơn số records trong batch, handler pad bằng `_Extraction()` default thay vì raise — tránh mất toàn bộ batch vì một record lỗi.

---

## Validation và noise filter

**Pydantic validation** (`_Extraction`): enforce enum values cho `funnel_stage`, `sector`, `deal_size`, `client_type`, `tech_maturity`, `market`. Giá trị ngoài enum bị coerce về default thay vì raise exception — giữ record với phần data hợp lệ thay vì bỏ cả record.

**Noise filter** (`_has_signal`): record không có `embedding_text`, `pain_points`, `use_cases`, hoặc `objections` bị drop trước khi insert. Ngăn data rỗng vào store làm nhiễu search và dashboard.

**`record_date` fallback**: nếu LLM không trả `record_date` hoặc trả `null`, handler scan các candidate fields trong raw record (`closedate`, `createdAt`, `created_at`, v.v.) để lấy date. Đảm bảo time-series filtering hoạt động dù source record không có field date canonical.

---

## Idempotency

- S3 object tag `processed=true` set sau khi Lambda chạy thành công — retry hoặc duplicate event không re-call Bedrock.
- Aurora INSERT dùng `ON CONFLICT (source, source_id) DO UPDATE` — re-extract overwrite row hiện tại, không duplicate.
- `RETURNING id` capture actual DB id trên cả insert và conflict-update path để embedding step dùng đúng FK.

---

## Provider switching

| Môi trường | Extraction model | Embedding model |
|---|---|---|
| Local dev | Gemini Flash Lite (free tier) | Gemini `gemini-embedding-001` (1024 dims) |
| AWS | Bedrock Haiku (via `instructor`) | Bedrock Cohere `embed-multilingual-v3` |

Switch điều kiện: `DB_SECRET_ARN` có giá trị → Bedrock path. Không có → Gemini path. Không có code path riêng cho logic extraction — chỉ khác ở client và response parsing.

---

## Concurrent write

Aurora INSERT và embedding API call chạy song song bằng `ThreadPoolExecutor(max_workers=2)`. `_embed_rows` không access DB nên an toàn khi dùng chung global connection. Sau khi cả hai future hoàn thành, `_insert_embeddings` dùng `id_map` (từ `RETURNING id`) để map pre-assigned UUID sang actual DB id — đảm bảo FK đúng trên cả insert path lẫn conflict-update path.