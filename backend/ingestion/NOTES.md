# Ingestion — Design Notes

> Ghi chú về các cách ingest data vào pipeline và trade-off của từng cách.

---

## Implementation Mock Ingestion (Demo)

Handler (`handler.py`) đóng vai **Ingestion UI Lambda** — không crawl source thật mà phục vụ màn hình Pipeline của frontend.

### File structure

```
backend/ingestion/
  mock_sources.json          ← catalog: id, source, file, label, description, record_count
  mock/
    redmine_01.json           ← 20 records — International project tickets
    redmine_02.json           ← 15 records — Japan project tickets
    outlook_email_01.json     ← 20 records — International emails
    outlook_email_02.json     ← 15 records — Vietnam-focus emails
    teams_transcript_01.json  ← 20 records — Sales & Delivery call transcripts
```

Catalog hiện tại: `mock_sources.json` — mỗi entry có `id`, `source`, `file`, `label`, `description`, `record_count`.

### Endpoints

| Method | Path                       | Mô tả                                                        |
|--------|----------------------------|--------------------------------------------------------------|
| GET    | `/ingestion` (hoặc `/ingestion/files`) | List tất cả mock files với metadata          |
| GET    | `/ingestion/preview`       | Trả toàn bộ records của một file (`?file_id=...`)            |
| POST   | `/ingestion/trigger`       | Trigger pipeline với một mock file (`{"file_id": "..."}`)    |

CloudWatch logs của Transform Lambda được serve bởi **Transform Lambda Function URL** (`VITE_TRANSFORM_LAMBDA_URL`) — `GET /logs`. Xem `backend/transform/handler.py`.

### Flow (AWS)

```
POST /ingestion/trigger  {"file_id": "redmine_01"}
  → đọc mock/redmine_01.json
  → upload lên S3: raw/redmine/2026-05-19/120000_redmine_01.json
  → S3 ObjectCreated event → Transform Lambda (async)

GET <VITE_TRANSFORM_LAMBDA_URL>/logs?since=2026-05-19T12:00:00Z
  → CloudWatch filter_log_events trên /aws/lambda/ai-insight-hub-transform
  → trả events (bỏ START/END/REPORT lines)
```

---

## Nguyên tắc chung (áp dụng cho mọi cách)

Mỗi source nên có filter condition rõ ràng xác định *record nào đáng extract signal*, không crawl mọi thứ.

Ví dụ Redmine: chỉ crawl ticket có tag `customer-feedback` hoặc `client-request`, không crawl toàn bộ technical ticket. Loại noise trước khi vào pipeline — hiệu quả hơn filter sau ở LLM layer.

---

## Cách 1 — Crawl thông thường, dedup ở transform

Connector pull toàn bộ records từ source (hoặc không có time param) → upload S3 → Lambda xử lý tất cả.

Dedup được xử lý ở transform layer:

- Pre-LLM: query Aurora để lọc `source_id` đã có → chỉ gửi records mới cho LLM
- Post-LLM: `ON CONFLICT (source, source_id) DO UPDATE` đảm bảo DB không bị duplicate

**Trade-off**: đơn giản nhất về connector side, nhưng LLM cost tăng nếu source push nhiều records cũ. Phụ thuộc vào pre-LLM dedup trong Lambda để tiết kiệm cost.

---

## Cách 2 — Crawl có filter theo thời gian

Connector dùng time-range param của source API (`updatedAt`, `modified_since`, `created_after`) để chỉ pull records mới/updated kể từ lần sync trước.

```text
connector: GET /issues?updated_after={last_sync_ts}&tag=customer-feedback
         → S3 upload raw/{source}/{date}/{ts}.json   ← chỉ delta
         → Lambda trigger → LLM chỉ xử lý records mới
```

Internal tool của công ty là một ví dụ — nếu tool expose đủ params thì đây là cách tốt nhất: dedup tự nhiên ở source, không cần pre-LLM dedup trong Lambda.

**Trade-off**: cần source API hỗ trợ time param. Connector phải lưu `last_sync_ts` giữa các lần chạy.

---

## Cách 3 — Data source push data đến (webhook / event-driven)

Source chủ động gửi event khi có record mới/updated → ingestion endpoint nhận, ghi vào S3 → S3 ObjectCreated trigger Transform Lambda như bình thường. S3 vẫn là data lake trung gian — pipeline sau S3 không đổi.

```text
source: POST /webhook
  → ingestion Lambda (API Gateway)
  → write raw/{source}/{date}/{ts}.json vào S3
  → S3 ObjectCreated → Transform Lambda
```

**Trade-off**: latency thấp nhất, không cần schedule connector. Nhưng source phải hỗ trợ push — không phải tool nào cũng có. Cần xử lý retry và at-least-once delivery ở ingestion endpoint.
