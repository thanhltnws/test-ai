# Transform — Prompt Design

> Mô tả cách prompt được xây dựng trong `backend/transform/prompt.py` và các kỹ thuật đang sử dụng.

---

## Constants trong prompt.py

| Constant | Mục đích |
|---|---|
| `_EXTRACT_TEMPLATE` | Template chính — field specs, constraints, output format |
| `_EMBEDDING_TEXT_INSTRUCTION` | Instruction riêng cho `embedding_text` — tách ra để tune độc lập |
| `_FEW_SHOT_EXAMPLES` | 3 examples covering CRM deal, support ticket, prospect email |
| `_RETRY_PREAMBLE` | Prefix cho retry pass — focused hơn, khuyến khích infer từ implicit signals |

---

## Kỹ thuật

### Multi-record batching trong một call

Token overhead của prompt (field specs + instructions) chiếm ~800 tokens cố định. Gom tối đa 40 records vào một call để amortize overhead — call đơn lẻ tốn ~820 tokens/record, batch 40 records tốn ~40 tokens overhead/record.

### Few-shot examples

Ba examples cover ba loại source khác nhau (CRM, issue tracker, email) để model học cách đọc signal từ format khác nhau. `embedding_text` trong examples viết theo style grounded evidence — quote/paraphrase sát raw text, không thêm editorial language.

### Field-specific guidance

Các field có nhiều cách hiểu sai được viết instruction chi tiết:

- **`funnel_stage`** — có guidance riêng theo từng record type (marketing lead, CRM profile, ops ticket) vì cùng một status field có ý nghĩa khác nhau giữa các source
- **`objections`** — explicit rằng chỉ lấy từ voice của prospect, không phải vendor ghi nhận
- **`embedding_text`** — tách thành `_EMBEDDING_TEXT_INSTRUCTION` với hard rules rõ ràng

### Confidence-based retry

LLM tự báo cáo `confidence_score` (0.0–1.0). Record có `confidence_score < 0.4` và `raw_text >= 150 chars` được gửi lên LLM lần hai với `_RETRY_PREAMBLE` — focused hơn, ít few-shot noise hơn. Kết quả retry chỉ ghi đè nếu score cải thiện.

---

## Quyết định thiết kế

**Tại sao `objections` chỉ lấy từ voice của prospect?**
CRM tags, ticket descriptions, và scoring labels phản ánh góc nhìn của vendor, không phải prospect. Lẫn hai nguồn này tạo ra false objections làm sai lệch sales analysis.

**Tại sao `funnel_stage` có guidance chi tiết theo record type?**
Các record type khác nhau (marketing lead, CRM profile, ops ticket) cho signal khác nhau nhưng dễ bị model confuse. Prompt explicit hóa cách đọc signal theo từng type để giảm inconsistency giữa sources.

**Tại sao `embedding_text` là grounded evidence text thay vì free-form summary?**
Version trước dùng LLM sinh 2–4 câu narrative summary. Phân tích seed data cho thấy hai vấn đề: (1) LLM thêm interpretive/editorial language không có trong raw record; (2) một số CRM record absorb thông tin từ transcript/email của cùng deal — cross-source conflation không kiểm soát được.

Grounded evidence text yêu cầu LLM preserve wording gốc, chỉ dùng thông tin có trong record đó. Quan trọng vì embedding_text được dùng cho semantic retrieval trong chat RAG — hallucination ở tầng này ảnh hưởng trực tiếp đến chất lượng câu trả lời.

**Tại sao `deal_size`, `client_type`, `tech_maturity` là flat column thay vì gom vào `icp` JSONB?**
Cả ba cần indexed filtering trực tiếp (Dashboard filter, RAG metadata filter). JSONB không thể index theo field con hiệu quả. Flat columns cũng làm CHECK constraint và Pydantic validation đơn giản hơn.
