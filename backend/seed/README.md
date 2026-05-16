# AI Insight Hub - Seed Raw Data Plan

> Chốt lại các quyết định đã thống nhất cho bộ seed raw data phục vụ ingestion, transform, batch insights, và chat RAG.

---

## Mục tiêu

Bộ seed mới không dùng dataset generic kiểu Kaggle làm nguồn chính nữa. Mục tiêu là tạo raw data gần với bối cảnh của Newwave Solution:

- Công ty outsource phần mềm B2B
- Thị trường chính: Việt Nam nội bộ, Nhật Bản, Hàn Quốc
- Ngành xuất hiện nhiều: fintech, e-learning, healthcare, real estate, e-commerce
- Dữ liệu phải phản ánh cả pre-sale và post-sale signal
- Dữ liệu phải đủ nhiễu để kiểm tra transform và retrieval, không chỉ toàn record "đẹp"

---

## Quyết định kiến trúc

### 1. Raw data giữ đúng pattern ingestion hiện tại

`backend/ingestion/handler.py` đang đọc từng source riêng và đẩy lên S3 theo dạng:

`raw/{source}/{date}/{timestamp}.json`

Hệ quả:

- Seed raw data cũng phải là `1 file / source`
- Không gộp tất cả sources vào một file duy nhất
- Transform hiện tại suy ra `source` từ S3 key, nên cách tổ chức file raw ảnh hưởng trực tiếp tới logic downstream

### 2. Seed ở đây là raw data, chưa transform

Các file raw mới chỉ là input cho ingestion/transform. Chúng chưa có:

- `pain_points`
- `objections`
- `use_cases`
- `icp`
- `embedding_text`

Các field đó vẫn sẽ được sinh ra ở bước sau bởi `backend/seed/generate.py` hoặc Transform Lambda.

### 3. Embedding phải đồng bộ giữa import và query

Khi import vào `signal_embeddings`, embedding model dùng để index phải trùng với model dùng khi query RAG:

- Dev: Gemini embedding
- Prod: `cohere.embed-multilingual-v3`

Điểm này đặc biệt quan trọng vì bộ data có đa ngôn ngữ VI/EN/JP và có một phần KR context.

---

## Nguồn dữ liệu đã chốt

Giữ 6 nguồn sau:

1. `hubspot`
2. `twenty_crm`
3. `redmine`
4. `outlook_email`
5. `teams_transcript`
6. `sharepoint`

Ý nghĩa từng nguồn:

- `hubspot`: phía Marketing dùng cho inbound lead, campaign note, handoff signal
- `twenty_crm`: phía Sales dùng cho deal, contact, activity
- `redmine`: nguồn nội bộ của công ty, phản ánh post-sale delivery/ops signal
- `outlook_email`: vừa có sales email, delivery email, lẫn internal noise
- `teams_transcript`: transcript họp có mật độ signal cao
- `sharepoint`: ít record nhất, chủ yếu note, delivery plan, proposal metadata

Giả định tổ chức:

- Marketing dùng HubSpot
- Sales dùng Twenty CRM
- Hai team không liên thông chặt qua tool
- Việc phối hợp thường diễn ra qua họp hoặc file share trên SharePoint

---

## Phân phối record

Tổng cộng: `1000` raw records

| Source | Records | Ghi chú |
| --- | ---: | --- |
| HubSpot | 160 | Marketing / inbound / lead notes |
| Twenty CRM | 200 | Sales deals, activities, contacts |
| Redmine | 230 | Nhiều ticket nhất, bao gồm meaningful signal và technical noise |
| Outlook Email | 230 | Giàu natural language nhất |
| Teams Transcript | 120 | Ít hơn email nhưng dense signal |
| SharePoint | 60 | Ít nhất, chủ yếu document-ish data |

---

## Thời gian và spike

Khoảng thời gian dữ liệu:

- Từ `2026-03-01` đến `2026-05-15`

Có 2 giai đoạn spike cố ý:

1. `2026-03-25` đến `2026-03-31`
   Lý do: cuối fiscal year của khách Nhật, nhiều deal discussion, follow-up, proposal pressure.

2. `2026-04-28` đến `2026-05-09`
   Lý do: sau Golden Week, backlog quay lại, nhiều activity ở sales, delivery, ticket và email.

Mục đích của spike:

- Tạo dữ liệu có tính mùa vụ
- Giúp dashboard và batch insight có điểm biến động rõ ràng
- Giúp test query theo thời gian và aggregation logic

---

## Ngôn ngữ

Phân bố ngôn ngữ được chốt như sau:

- Tiếng Việt chiếm phần lớn
- Tiếng Anh xuất hiện ở giao tiếp trực tiếp với khách, nhất là KR, SG, US
- Tiếng Nhật xuất hiện rõ ở khách JP, đặc biệt trong sales note, email, transcript
- KR không nhất thiết nhiều tiếng Hàn trong text, nhưng có đủ client và market context Hàn Quốc trong data

Ý đồ:

- Phản ánh đúng môi trường làm việc của công ty outsource tại Việt Nam
- Tạo điều kiện kiểm tra retrieval đa ngôn ngữ
- Làm nổi bật lý do chọn embedding model multilingual ở production

---

## Cấu trúc nội dung theo source

### HubSpot

Bao gồm các kiểu record như:

- contact form
- marketing note
- campaign member
- lead score snapshot

### Twenty CRM

Bao gồm:

- deal
- activity
- contact

Có đủ trạng thái như:

- `DISCOVERY`
- `PROPOSAL`
- `NEGOTIATION`
- `CLOSED_WON`
- `CLOSED_LOST`

### Redmine

Bao gồm cả hai nhóm:

- Ticket có tín hiệu business thật: scope change, approval flow, compliance, release friction
- Ticket technical noise: upgrade runtime, cleanup infra, flaky test, config rename

### Outlook Email

Bao gồm:

- sales external
- delivery external
- internal account sync
- internal noise

### Teams Transcript

Là transcript họp theo lượt nói, có:

- participant nội bộ
- client participant
- nội dung discussion đa ngôn ngữ

### SharePoint

Bao gồm:

- meeting note
- retro note
- proposal metadata
- delivery plan

---

## Tên client và market

Dùng client fictional nhưng realistic, có thiên hướng JP và KR, ví dụ:

- Finamo KK
- MedCore Korea
- EduSpring Japan
- ShopWave Korea
- Kirei Care KK
- Hanbit Platform

Mục tiêu không phải mô phỏng khách hàng thật, mà tạo landscape hợp lý cho:

- ICP extraction
- market segmentation
- objections
- post-sale pain points

---

## Output thực tế đã tạo

Các file raw hiện nằm tại:

- `backend/seed/data/raw/hubspot.json`
- `backend/seed/data/raw/twenty_crm.json`
- `backend/seed/data/raw/redmine.json`
- `backend/seed/data/raw/outlook_email.json`
- `backend/seed/data/raw/teams_transcript.json`
- `backend/seed/data/raw/sharepoint.json`

Các file này là JSON array và có schema không hoàn toàn đồng nhất giữa các records trong cùng source. Điều đó là chủ đích, để gần với dữ liệu thật hơn và để transform phải xử lý dữ liệu biến thiên.

---

## Generate strategy

### LLM provider và model

`generate.py` hỗ trợ hai provider: `gemini` (default local dev) và `bedrock`. Trong thực tế đã chạy với Bedrock để đồng nhất với AWS stack:

- **Model:** `apac.anthropic.claude-haiku-4-5-20251001-v1:0` (APAC cross-region inference profile)
- **Region:** `us-east-1`
- **Auth:** AWS SSO qua profile `aih`, load vào boto3 thông qua `AWS_PROFILE` trong `.env`
- **Provider switch:** set `SEED_LLM_PROVIDER=bedrock` trong `.env` (không phải `EMBEDDING_PROVIDER`)

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

### Kết quả generate thực tế (lần chạy 2026-05-16)

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
