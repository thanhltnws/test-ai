# AI Insight Hub - Seed Raw Data Plan

> Chốt lại các quyết định đã thống nhất cho bộ seed raw data phục vụ ingestion, transform, batch insights, và chat RAG.

---

## Mục tiêu

Mục tiêu là tạo raw data gần với bối cảnh của Newwave Solution:

- Công ty outsource phần mềm B2B
- Thị trường chính: Việt Nam, Nhật Bản, Hàn Quốc, International
- Ngành xuất hiện nhiều: fintech, healthcare, education, retail, construction tech
- Dữ liệu phải phản ánh đủ từ marketing, pre-sale đến post-sale signal
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
- `deal_size`, `client_type`, `tech_maturity`
- `funnel_stage`
- `market`
- `embedding_text`

Các field đó vẫn sẽ được sinh ra ở bước sau bởi `backend/seed/generate.py` hoặc Transform Lambda.

### 3. `raw_text` — không lưu vào DB

`raw_text` là toàn bộ nội dung record gốc sau khi flatten thành chuỗi key-value (output của `row_to_text()`). Đây là text thực sự được truyền vào LLM để extract.

Quyết định: **không persist vào DB** để giảm storage. Re-extraction nếu cần phải refetch từ S3 raw.

### 4. Embedding phải đồng bộ giữa import và query

Khi import vào `signal_embeddings`, embedding model dùng để index phải trùng với model dùng khi query RAG:

- Dev: Gemini embedding
- Prod: `cohere.embed-multilingual-v3`

Điểm này đặc biệt quan trọng vì bộ data có đa ngôn ngữ VI/EN/JP và có một phần KR context.

---

## Nguồn dữ liệu đã chốt

Giữ 5 nguồn sau:

1. `hubspot`
2. `twenty_crm`
3. `redmine`
4. `outlook_email`
5. `teams_transcript`

Ý nghĩa từng nguồn:

- `hubspot`: phía Marketing dùng cho inbound lead, campaign note, handoff signal
- `twenty_crm`: phía Sales dùng cho deal, contact, activity
- `redmine`: nguồn nội bộ của công ty, phản ánh post-sale delivery/ops signal, sẽ crawl dựa trên tag đặc thù, ít record nhất nhưng quan trọng nhất
- `outlook_email`: vừa có sales email, delivery email, lẫn internal noise
- `teams_transcript`: transcript họp có mật độ signal cao

Giả định tổ chức:

- Marketing dùng HubSpot
- Sales dùng Twenty CRM
- Hai team không liên thông chặt qua tool

---

## Phân phối record

Tổng cộng: `30` raw records

| Source           | Records | Ghi chú |
| ---------------- | ------: | ------- |
| HubSpot          |       6 | Marketing / inbound / lead notes |
| Twenty CRM       |       7 | Sales deals, activities, contacts |
| Redmine          |       5 | Mix signal (customer-feedback tag) và technical noise |
| Outlook Email    |       7 | Sales external, delivery external, internal noise |
| Teams Transcript |       5 | Kick-off, discovery, sprint review, UAT |

---

## Thời gian

Khoảng thời gian dữ liệu: `2026-05-01` đến `2026-05-19`

Dữ liệu tập trung trong tháng 5 để dễ test query theo thời gian và batch insight.

---

## Ngôn ngữ

Phân bố ngôn ngữ được chốt như sau:

- Tiếng Việt chiếm phần lớn
- Tiếng Anh xuất hiện ở giao tiếp trực tiếp với khách, nhất là AU, SG, US
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
- marketing note (engagement + metadata)

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

### Redmine

Bao gồm cả hai nhóm:

- Ticket có tín hiệu business thật: compliance request, scope change, security requirement từ client (tag `customer-feedback`, `client-request`)
- Ticket technical noise: infra upgrade, flaky test (tag `infra`, `technical`)

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
- nội dung discussion đa ngôn ngữ (VI, EN, JP, KR)

---

## Tên client và market

Fictional clients được dùng trong bộ data này:

| Client          | Market        | Sector             |
| --------------- | ------------- | ------------------ |
| Finamo KK       | Japan         | Fintech            |
| EduSpring Japan | Japan         | Education          |
| MedCore Korea   | Korea         | Healthcare         |
| ShopWave Korea  | Korea         | Retail             |
| BuildTech AU    | International | Construction Tech  |
| Learnify APAC   | International | Education          |
| VietHealth      | Vietnam       | Healthcare         |

---

## Output thực tế đã tạo

Các file raw hiện nằm tại:

- `backend/seed/data/raw/hubspot.json`
- `backend/seed/data/raw/twenty_crm.json`
- `backend/seed/data/raw/redmine.json`
- `backend/seed/data/raw/outlook_email.json`
- `backend/seed/data/raw/teams_transcript.json`

Các file này là JSON array và có schema không hoàn toàn đồng nhất giữa các records trong cùng source. Điều đó là chủ đích, để gần với dữ liệu thật hơn và để transform phải xử lý dữ liệu biến thiên.
