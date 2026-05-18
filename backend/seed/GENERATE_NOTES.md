# Seed — Generate Notes

> Ghi chú vận hành cho bước generate và import seed data. Không phải spec — là log quyết định và kết quả thực tế.

---

## Generate strategy

### LLM provider và model

`generate.py` hỗ trợ hai provider: `gemini` (default local dev) và `bedrock`. Trong thực tế đã chạy với Bedrock để đồng nhất với AWS stack:

- **Model:** `apac.anthropic.claude-haiku-4-5-20251001-v1:0` (APAC cross-region inference profile)
- **Region:** `ap-southeast-1`
- **Auth:** AWS SSO qua profile, load vào boto3 thông qua `AWS_PROFILE` trong `.env`
- **Provider switch:** set `SEED_LLM_PROVIDER=bedrock` trong `.env` (không phải `SEED_EMBEDDING_PROVIDER`)

Lý do chọn Haiku thay vì Sonnet cho bước extraction: extraction là structured JSON với prompt rõ ràng, không cần reasoning sâu. Haiku đủ chất lượng, cost thấp hơn đáng kể (~$0.10 cho toàn bộ 1000 records).

### Batching

| Tham số | Giá trị |
| --- | --- |
| `MAX_BATCH_RECORDS` | 40 records/batch |
| `MAX_BATCH_CHARS` | 150,000 chars/batch |
| `max_tokens` (Bedrock) | 8192 |
| `API_DELAY_S` | 1.0 giây giữa các batch |

`max_tokens` ban đầu là 4096, bị thiếu với 40 records (output ~6000 token). Đã tăng lên 8192.

### JSON repair

Model đôi khi sinh ra JSON có ký tự đặc biệt chưa escape hoặc quote lỗi trong string field (hay xảy ra với `embedding_text` chứa nội dung đa ngôn ngữ). Đã thêm `json_repair` vào pipeline để xử lý trước khi parse:

```python
json.loads(repair_json(response_text))
```

Package: `json-repair` trong `backend/seed/requirements.txt`.

---

## Kết quả generate thực tế (lần chạy 2026-05-16)

| Metric | Giá trị | Nhận xét |
| --- | --- | --- |
| Total records | 1000 | Đúng kế hoạch |
| Source distribution | Khớp 100% | hubspot 160, twenty_crm 200, ... |
| Date range thực tế | 2026-02-28 → 2026-06-20 | Raw data có drift nhẹ so với plan (03-01 → 05-15) |
| Null dates | 144 (14%) | LLM không extract date — đã fix bằng raw fallback |
| Empty `pain_points` | 217 (22%) | Kỳ vọng: Redmine noise và email nội bộ |
| Empty `embedding_text` | 206 (21%) | Record không có signal RAG |
| `consideration` dominant | 775/1000 (77%) | Skewed — `won` chỉ 36, `lost` chỉ 17; đã fix prompt |
| `icp.sector` rỗng | 70 records | Model không infer được từ record thiếu context |
| Noise records (zero signal) | 201 (20%) | Đã bị bỏ qua trong generate — không vào signals table |

### Fixes đã áp dụng sau lần chạy đầu (commit `ff386ec`)

| Vấn đề | Fix |
| --- | --- |
| `record_date: null` ở 144 records | Thêm `_fallback_date_from_raw()` — scan raw record cho `createdate`, `createdAt`, `timestamp`, v.v. trước khi trả null |
| 201 noise records vẫn vào `signals_seed.json` | Thêm `_has_signal()` guard — record bị drop khỏi output nếu `embedding_text`, `pain_points`, `use_cases`, `objections` đều rỗng |
| `CLOSED_WON` bị map thành `consideration` | Thêm rule vào prompt: explicit stage field (`CLOSED_WON`/`WON`/`CLOSED_LOST`/`LOST`) ưu tiên tuyệt đối trước sentiment của note |

**Chạy lại generate.py sau các fix trên:** signals_seed.json sẽ có ~799 records thay vì 1000, với `record_date` null giảm đáng kể và `won`/`lost` phân phối chính xác hơn.

---

## Bước tiếp theo

Sau raw seed này, flow mong muốn là:

1. Đọc raw files
2. Chạy LLM extraction để sinh `signals_seed.json`
3. Import vào PostgreSQL
4. Sinh embedding và import vào `signal_embeddings`
5. Query lại bằng batch/dashboard/chat trên cùng hệ dữ liệu

Nếu cập nhật code seed/import sau này, ưu tiên giữ nguyên nguyên tắc:

- raw data tách theo source
- embedding index và query phải đồng bộ model
- source mix phải tiếp tục phản ánh đúng bối cảnh outsource B2B của Newwave

---

## TODO

### run_batch.py: dynamic time range from DB

Currently `DATA_START` and `DATA_END` are hardcoded in `run_batch.py`. This breaks if a developer generates their own `signals_seed.json` with a different date range.

**Fix:** replace the two constants with a DB query at the start of `main()`:

```python
cur.execute("SELECT MIN(record_date), MAX(record_date) FROM signals WHERE record_date IS NOT NULL")
DATA_START, DATA_END = cur.fetchone()
```

`_pg_connect()` is already available — no new dependency needed. This also handles the case where `import.py` is run multiple times with different source files.
