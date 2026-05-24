# AI Insight Hub — Transform Strategy (Extraction)

> Spec mô tả chiến lược AI call trong luồng Transform: từ raw record S3 → structured signals Aurora. Dùng để review thiết kế, onboard người mới, và làm baseline khi quyết định nâng cấp.
>
> **Scope:** `backend/transform/handler.py` + `backend/transform/prompt.py`. Seed pipeline (`backend/seed/generate.py`) dùng cùng prompt và cùng batch logic. Toàn bộ prompt logic nằm trong `prompt.py` — xem chi tiết kỹ thuật và quyết định thiết kế tại `prompt.md`.

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
| `source_url` | `TEXT` | LLM | URL gốc nếu có; nếu không, fictional demo URL dạng `https://example.com/{source}/{source_id}` cho CRM/issue tracker. NULL cho email, form, ops note. |
| `embedding_text` | `TEXT` | LLM | Grounded evidence text từ các field chính của record — preserve wording gốc, tối ưu cho semantic retrieval. Xem spec chi tiết tại `prompt.md`. |
| `record_date` | `DATE` | LLM + fallback | Date ngữ nghĩa nhất trong record; fallback về candidate fields trong raw nếu LLM không trả |
| `market` | `TEXT` | LLM | `vietnam` · `japan` · `korea` · `international` — target geographic market |
| `sector` | `TEXT` | LLM | `fintech` · `logistics` · `retail` · `healthcare` · `manufacturing` · `software` · `education` · `ict` · `other` |

---

## Dedup

`normalize()` dedup records trong cùng một S3 file bằng SHA-1 hash của text content — record có cùng hash bị drop trước khi đưa vào extraction. Xử lý trường hợp source gửi trùng record trong một batch.

Dedup cross-batch (cùng record xuất hiện ở nhiều lần chạy khác nhau) được xử lý ở tầng DB bằng `ON CONFLICT (source, source_id) DO UPDATE` — xem **Idempotency**.

---

## Batch strategy

```text
S3 raw/{source}/{date}/{ts}.json
    → normalize (dedup, text flatten)
    → make_batches (≤40 records, ≤150k chars)
    → _extract_batch (Bedrock Haiku hoặc Gemini Flash)
    → merge + noise filter (_has_signal)
    → upsert signals + signal_embeddings (concurrent)
```

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

## Confidence-based retry

Sau mỗi batch extraction, handler chạy một lượt retry có chọn lọc cho các record có chất lượng thấp.

**Cơ chế:**

1. LLM tự báo cáo `confidence_score` (0.0–1.0) cho mỗi record — phản ánh mức độ chắc chắn khi infer các field từ raw text.
2. Record nào có `confidence_score < 0.4` **và** `len(raw_text) >= 150 chars` được đưa vào retry. Điều kiện thứ hai đảm bảo chỉ retry khi record đủ dài để có thêm thông tin — record ngắn < 150 chars thì retry cũng không cải thiện được.
3. Các record low-confidence được gom lại, gửi lên LLM lần hai với `build_retry_prompt` (prompt focused hơn, ít nhiễu hơn).
4. Kết quả retry chỉ được dùng nếu `confidence_score` mới **cao hơn** lần đầu — không bao giờ ghi đè khi không cải thiện.

**`confidence_score` không persist vào DB** — chỉ dùng trong-memory trong `extract_and_merge` để điều phối retry. `generate.py` (seed pipeline) không implement pattern này.

---

## Idempotency

- S3 object tag `processed=true` set sau khi Lambda chạy thành công — retry hoặc duplicate event không re-call Bedrock.
- Aurora INSERT dùng `ON CONFLICT (source, source_id) DO UPDATE` — re-extract overwrite row hiện tại, không duplicate.
- `RETURNING id` capture actual DB id trên cả insert và conflict-update path để embedding step dùng đúng FK.

---

## Provider switching

| Môi trường | Extraction model                 | Embedding model                           |
|------------|----------------------------------|-------------------------------------------|
| Local dev  | Gemini Flash Lite (free tier)    | Gemini `gemini-embedding-001` (1024 dims) |
| AWS        | Bedrock Haiku (via `instructor`) | Bedrock Cohere `embed-multilingual-v3`    |

Switch điều kiện: `DB_SECRET_ARN` có giá trị → Bedrock path. Không có → Gemini path. Không có code path riêng cho logic extraction — chỉ khác ở client và response parsing.
