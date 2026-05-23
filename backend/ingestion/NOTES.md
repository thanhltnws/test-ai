# Ingestion — Design Notes

> Ghi chú về các cách ingest data vào pipeline.

---

## Tình trạng handler hiện tại

`handler.py` hiện tại **đã bị thay thế bởi demo UI code** — không còn là ingestion Lambda thật. Nó phục vụ màn hình Pipeline của frontend (list mock files, preview records, trigger từng file).

Code ingestion thật được lưu lại ở `handler_real.py`:

- Trigger bởi EventBridge schedule
- Xác định nguồn cần crawl và cách crawl phù hợp với từng source (poll API, webhook, đọc file) → upload raw records lên S3
- `handler_real.py` hiện tại chỉ là skeleton đơn giản nhất: xác định data sources tại sources.json, đọc mock file → upload S3. Ingestion thật với từng source sẽ cần nhiều logic phức tạp hơn

Hướng xử lý dài hạn: tách demo UI thành `ingestion_demo` Lambda riêng, đưa `handler_real.py` trở thành `handler.py`. Xem thêm `MOCK.md`.

---

## Nguyên tắc chung

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
