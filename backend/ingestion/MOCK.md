# Implementation Mock Ingestion (Demo)

Handler (`handler.py`) đóng vai **Ingestion UI Lambda** — không crawl source thật mà phục vụ màn hình Pipeline của frontend.

## Chiến thuật demo: _trigger_local gộp Transform vào

Ở local dev, `_trigger_local` không upload S3 mà **chạy thẳng Transform pipeline inline** (normalize → extract → insert → embed). Đây là chiến thuật demo có chủ ý:

Flow AWS chuẩn là async — sau khi trigger, frontend phải poll logs để biết transform đang chạy, không có feedback tức thì. Gộp vào inline cho phép response trả về ngay kết quả (`upserted`, `vectors`) — người xem thấy dữ liệu xuất hiện ngay sau khi bấm trigger, phù hợp với mục tiêu demo nhanh.

Local dev sẽ không show đúng flow ingest → S3 event → transform như trên AWS — đây là điều được chấp nhận ở scope demo.

## File structure

```text
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

## Endpoints

| Method | Path                                   | Mô tả                                                     |
|--------|----------------------------------------|-----------------------------------------------------------|
| GET    | `/ingestion` (hoặc `/ingestion/files`) | List tất cả mock files với metadata                       |
| GET    | `/ingestion/preview`                   | Trả toàn bộ records của một file (`?file_id=...`)         |
| POST   | `/ingestion/trigger`                   | Trigger pipeline với một mock file (`{"file_id": "..."}`) |

CloudWatch logs của Transform Lambda được serve bởi **Transform Lambda Function URL** (`VITE_TRANSFORM_LAMBDA_URL`) — `GET /logs`. Xem `backend/transform/handler.py`.

## Flow (AWS)

```text
POST /ingestion/trigger  {"file_id": "redmine_01"}
  → đọc mock/redmine_01.json
  → upload lên S3: raw/redmine/2026-05-19/120000_redmine_01.json
  → S3 ObjectCreated event → Transform Lambda (async)

GET <VITE_TRANSFORM_LAMBDA_URL>/logs?since=2026-05-19T12:00:00Z
  → CloudWatch filter_log_events trên /aws/lambda/ai-insight-hub-transform
  → trả events (bỏ START/END/REPORT lines)
```
