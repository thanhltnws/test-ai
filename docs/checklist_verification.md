# Verification Checklist

> Mục tiêu: xác nhận toàn bộ pipeline hoạt động đúng từ seed → transform → batch → chat trước khi demo.
> Ngày hiện tại: 2026-05-18. "3 tháng gần nhất" = Mar–May 2026.

---

## 1. Seed Data & Import (4 bảng)

### 1.1 Chuẩn bị seed data

- [ ] Raw data trong `backend/seed/data/raw/` có đủ records thuộc khoảng **Mar–May 2026** (`record_date`)
  - Kiểm tra từng file: `hubspot.json`, `twenty_crm.json`, `redmine.json`, `outlook_email.json`, `teams_transcript.json`, `sharepoint.json`
  - Nếu thiếu records trong range này, cần bổ sung hoặc điều chỉnh `record_date` trong raw data

- [ ] Chạy `generate.py` để tạo `signals_seed.json`
  ```
  python generate.py --provider gemini
  ```
  - Output file tồn tại: `backend/seed/data/signals_seed.json`
  - Số records output hợp lý so với input (không quá ít)
  - Kiểm tra sample: các field `pain_points`, `objections`, `use_cases`, `icp`, `funnel_stage`, `embedding_text` được populate (không rỗng phần lớn)
  - `confidence_score` trung bình ≥ 0.5
  - `record_date` phân bổ đều trong khoảng Mar–May 2026

### 1.2 Import vào DB — bảng `signals` và `signal_embeddings`

- [ ] Chạy `import.py`
  ```
  python import.py --provider gemini
  ```
  - Không có unhandled exception
  - Log báo số records upserted vào `signals`
  - Log báo số embeddings upserted vào `signal_embeddings`

- [ ] Kiểm tra bảng `signals`
  ```sql
  SELECT COUNT(*) FROM signals;
  SELECT source, COUNT(*) FROM signals GROUP BY source ORDER BY source;
  SELECT market, COUNT(*) FROM signals GROUP BY market;
  SELECT funnel_stage, COUNT(*) FROM signals GROUP BY funnel_stage;
  SELECT MIN(record_date), MAX(record_date) FROM signals;
  -- Phải cover Mar–May 2026
  SELECT COUNT(*) FROM signals WHERE record_date BETWEEN '2026-03-01' AND '2026-05-31';
  ```
  - Có đủ 6 sources
  - Có đủ 4 markets (`vietnam`, `japan`, `korea`, `international`)
  - Có đủ 5 funnel stages
  - Records trong Mar–May 2026 đủ nhiều để aggregate có nghĩa (≥ 50 records)

- [ ] Kiểm tra bảng `signal_embeddings`
  ```sql
  SELECT COUNT(*) FROM signal_embeddings;
  -- Phải gần bằng số signals có embedding_text không rỗng
  SELECT COUNT(*) FROM signals WHERE embedding_text IS NOT NULL AND embedding_text != '';
  -- Kiểm tra embedding dimension
  SELECT vector_dims(embedding) FROM signal_embeddings LIMIT 5;
  -- Phải = 1024
  ```
  - Row count khớp với signals có `embedding_text`
  - `vector_dims` = 1024

### 1.3 Backfill batch — bảng `insights` và `insight_embeddings`

- [ ] Chạy `run_batch.py` để backfill historical periods
  ```
  python run_batch.py
  ```
  - Không có unhandled exception
  - Log cho thấy periods được xử lý (weekly, monthly, quarterly, yearly × các markets)

- [ ] Kiểm tra bảng `insights`
  ```sql
  SELECT COUNT(*) FROM insights;
  SELECT period, result_type, market, COUNT(*) FROM insights
    GROUP BY period, result_type, market ORDER BY period, result_type, market;
  -- Phải có 4 result_types cho mỗi (period × market combo)
  SELECT COUNT(*) FROM insights
    WHERE period_start BETWEEN '2026-03-01' AND '2026-05-31';
  ```
  - Có đủ 4 `result_type`: `pain_points_summary`, `funnel_distribution`, `icp_narrative`, `recommendations`
  - Có rows cho tất cả markets (vietnam, japan, korea, international, NULL=all)
  - Payload không rỗng — sample 1 row: `SELECT payload FROM insights LIMIT 1`

- [ ] Kiểm tra bảng `insight_embeddings`
  ```sql
  SELECT COUNT(*) FROM insight_embeddings;
  -- Phải khớp với số insights rows
  SELECT COUNT(*) FROM insights;
  SELECT vector_dims(embedding) FROM insight_embeddings LIMIT 5;
  -- Phải = 1024
  ```

---

## 2. Transform Lambda

> Strategy: sinh thêm một số raw file locally, gọi transform handler trực tiếp (không qua S3/Lambda thật), kiểm tra data được insert vào DB đúng. Bật debug mode để xem output trước khi insert.

### 2.1 Chuẩn bị test data

- [ ] Tạo 2–3 raw records test mới (dạng JSON, format giống `data/raw/*.json`) với `record_date` trong tháng hiện tại (May 2026)
  - Dùng ít nhất 2 sources khác nhau (vd: `hubspot` + `redmine`)
  - Đặt trong thư mục tạm `backend/transform/test_data/`

### 2.2 Debug trước khi insert

- [ ] Thêm / kích hoạt debug flag trong `backend/transform/handler.py` để in extraction output trước khi INSERT
  - Xem `_Extraction` / `_ExtractionBatch` Pydantic output được parse từ LLM response
  - Xác nhận: `pain_points`, `objections`, `use_cases`, `icp`, `funnel_stage`, `confidence_score`, `embedding_text` được populate đúng
  - Xác nhận `source_url` đúng: CRM/Jira → có URL, email/form → NULL

- [ ] Kiểm tra idempotency guard: S3 tag `processed=true`
  - Simulate tag đã tồn tại → Lambda phải return sớm, không gọi LLM

- [ ] Kiểm tra retry logic: record có `confidence_score < 0.4` → phải trigger `build_retry_prompt()`

### 2.3 Kiểm tra insert vào DB

- [ ] Chạy transform handler với test data (invoke local, bypass S3 trigger)
  ```
  # Invoke handler trực tiếp với event mock
  python -c "from handler import handler; handler(event, None)"
  ```
  - Return `{status: ok, inserted: N}` với N > 0

- [ ] Query DB xác nhận records đã vào
  ```sql
  SELECT source, source_id, funnel_stage, market, confidence_score, extracted_at
    FROM signals
    WHERE source_id IN (<test_source_ids>);
  ```
  - Records tồn tại, các field hợp lệ

- [ ] Test UPSERT — chạy lại transform với cùng test data
  - Số rows trong `signals` không tăng (upsert, không duplicate)
  - `extracted_at` được cập nhật

- [ ] Kiểm tra `signal_embeddings` cho test records
  ```sql
  SELECT se.signal_id, vector_dims(se.embedding), se.metadata
    FROM signal_embeddings se
    JOIN signals s ON se.signal_id = s.id
    WHERE s.source_id IN (<test_source_ids>);
  ```
  - Embedding tồn tại, `metadata` có `source`, `funnel_stage`, `market`, `sector`

---

## 3. Batch Lambda (Insights Builder)

> Strategy: trigger batch handler trực tiếp cho một period cụ thể, kiểm tra output LLM trước khi write, sau đó kiểm tra `insights` + `insight_embeddings`.

### 3.1 Debug trước khi write

- [ ] Thêm / kích hoạt debug flag trong `backend/application/batch/handler.py`
  - In Aurora aggregate output (pain_points counts, funnel distribution, ICP breakdown)
  - In pgvector semantic search results (top chunks)
  - In raw LLM response JSON trước khi parse và INSERT

- [ ] Chạy batch cho một period test nhỏ (vd: weekly, 2026-05-12 → 2026-05-18, market=vietnam)
  ```python
  # Invoke handler trực tiếp
  python -c "
  from handler import _run_period
  _run_period('weekly', '2026-05-12', '2026-05-18', 'vietnam')
  "
  ```
  - Log hiển thị SQL aggregate results (có data, không phải empty)
  - Log hiển thị pgvector chunks (có content)
  - LLM response có đủ 4 keys: `pain_points_summary`, `funnel_distribution`, `icp_narrative`, `recommendations`
  - Payload structure đúng schema trong `prompt.py`

### 3.2 Kiểm tra write vào DB

- [ ] Sau khi chạy, query `insights`
  ```sql
  SELECT id, period, period_start, period_end, market, result_type,
         computed_at, payload
    FROM insights
    WHERE period = 'weekly' AND period_start = '2026-05-12' AND market = 'vietnam'
    ORDER BY result_type;
  ```
  - Có đủ 4 rows (1 per `result_type`)
  - `payload` JSON valid và có content (không rỗng)

- [ ] Chạy lại cùng period → rows mới được APPEND (không overwrite)
  ```sql
  SELECT COUNT(*) FROM insights
    WHERE period = 'weekly' AND period_start = '2026-05-12' AND market = 'vietnam';
  -- Phải = 8 (2 runs × 4 result_types)
  ```
  - Query `MAX(computed_at)` trả về rows mới nhất đúng

- [ ] Kiểm tra `insight_embeddings`
  ```sql
  SELECT ie.insight_id, vector_dims(ie.embedding), ie.metadata
    FROM insight_embeddings ie
    JOIN insights i ON ie.insight_id = i.id
    WHERE i.period = 'weekly' AND i.period_start = '2026-05-12';
  ```
  - Embedding tồn tại cho mỗi insight row
  - `metadata` có `period`, `period_start`, `period_end`, `result_type`, `market`

### 3.3 Kiểm tra scheduling logic

- [ ] Verify `_should_run()` cho từng granularity với ngày hiện tại (2026-05-18, Monday)
  - `weekly` → True
  - `monthly` → True
  - `quarterly` → check logic (Q2 = Apr–Jun, không phải đầu/cuối quarter)
  - `yearly` → check (1st của tháng? → False nếu ngày 18)

---

## 4. Chat Lambda (RAG)

> Strategy: gửi câu hỏi test trực tiếp vào handler, kiểm tra context assembly, debug prompt trước khi gọi LLM, và kiểm tra output cuối.

### 4.1 Debug context assembly

- [ ] Thêm / kích hoạt debug flag trong `backend/application/chat/handler.py`
  - In SQL aggregate results (background context)
  - In keyword-matched signal rows
  - In pgvector top-K chunks (8 results)
  - In full prompt được gửi vào LLM (trước khi call)

### 4.2 Test câu hỏi theo loại

- [ ] **Câu hỏi structured** (có số liệu, dùng SQL path nhiều hơn)
  ```
  "Bao nhiêu deal bị lost vì vấn đề giá?"
  "Top 3 pain point của khách Vietnam là gì?"
  ```
  - SQL aggregate context có data
  - LLM answer trích dẫn số liệu cụ thể

- [ ] **Câu hỏi mở** (dùng vector search path nhiều hơn)
  ```
  "Khách thường nói gì sau khi xem demo?"
  "Ops team gặp vấn đề gì khi triển khai?"
  ```
  - pgvector trả về chunks liên quan
  - LLM answer có evidence từ chunks

- [ ] **Câu hỏi cross-source** (kết hợp CRM + Ops data)
  ```
  "So sánh những gì khách nói trước và sau khi ký hợp đồng"
  ```
  - Context assembly kéo được cả signal từ `hubspot`/`twenty_crm` và `sharepoint`/`teams_transcript`

### 4.3 Kiểm tra output

- [ ] Response format đúng: `{answer: string, references: [{title, source_url}]}`
- [ ] `references` có `source_url` hợp lệ khi signal có URL (HubSpot, Redmine)
- [ ] `references` không có `source_url` null/rỗng bị expose cho user
- [ ] `answer` không hallucinate — không claim số liệu ngoài context
- [ ] `answer` trả lời đúng ngôn ngữ câu hỏi (tiếng Việt nếu hỏi tiếng Việt)

### 4.4 Kiểm tra dual-source retrieval (4-table join)

- [ ] Xác nhận chat handler query **cả** `signal_embeddings` (raw signals) **và** `insight_embeddings` (LLM narratives)
  ```sql
  -- Signal embeddings: raw customer evidence
  SELECT COUNT(*) FROM signal_embeddings;
  -- Insight embeddings: synthesized trends
  SELECT COUNT(*) FROM insight_embeddings;
  ```
  - Cả 2 bảng đều được query trong một chat request
  - LLM nhận được context từ cả hai nguồn trong prompt

### 4.5 Edge cases

- [ ] Câu hỏi quá dài (> 2000 chars) → bị truncate, không crash
- [ ] Câu hỏi không liên quan → LLM trả lời "không đủ data" thay vì hallucinate
- [ ] DB rỗng (0 signals) → graceful response, không crash

---

## Tóm tắt — Trạng thái 4 bảng sau toàn bộ pipeline

| Bảng | Populated by | Verify |
|---|---|---|
| `signals` | `import.py` hoặc Transform Lambda | `SELECT COUNT(*), MIN(record_date), MAX(record_date) FROM signals` |
| `signal_embeddings` | `import.py` hoặc Transform Lambda | `SELECT COUNT(*) FROM signal_embeddings` — khớp với signals có `embedding_text` |
| `insights` | `run_batch.py` hoặc Batch Lambda | `SELECT period, result_type, market, COUNT(*) FROM insights GROUP BY 1,2,3` |
| `insight_embeddings` | `run_batch.py` hoặc Batch Lambda | `SELECT COUNT(*) FROM insight_embeddings` — khớp với `insights` |
