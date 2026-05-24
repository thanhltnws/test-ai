# Transform (Extraction) Optimization

> Kỹ thuật tối ưu cho luồng extraction: LLM đọc unstructured text và output structured fields. Sắp xếp theo độ phức tạp tăng dần.

---

## Tầng 1 — Pipeline

Cải thiện chất lượng extraction mà không thay đổi kiến trúc — chỉ thay đổi cách gọi model và xử lý kết quả.

### Few-shot prompting

Thêm 2–3 ví dụ input/output vào prompt. Model học pattern từ ví dụ cụ thể thay vì từ mô tả trừu tượng. Đặc biệt hiệu quả với text nhiều ngôn ngữ, viết tắt, hoặc format không chuẩn.

### Chain of thought extraction

Yêu cầu model giải thích reasoning trước khi output structured fields. Giảm hallucination trên text ngắn hoặc mơ hồ vì model buộc phải "đọc lại" trước khi kết luận.

### Multi-pass extraction

Tách một call lớn thành nhiều call chuyên biệt: call 1 chỉ extract field A, call 2 chỉ extract field B. Tốn token hơn nhưng giảm context confusion trên text dài hoặc khi các field có semantics xung đột.

### Validation layer

Validate schema output (Pydantic, JSON Schema). Quan trọng hơn là xác định behavior sau khi validate fail: reject + log, flag để human review, hay retry với prompt khác. Silent failure để data rác vào store là worst case.

---

## Tầng 2 — Agentic

Model tự điều chỉnh hành vi dựa trên kết quả — không chỉ chạy một lần rồi thôi.

### Retry loop

Nếu extraction trả field quan trọng trống hoặc `confidence_score` thấp hơn ngưỡng, retry với prompt khác (thêm chain of thought, thêm context). Số lần retry có giới hạn để tránh loop vô hạn.

### Fallback routing

Nếu text quá ngắn hoặc quá nhiễu, escalate sang model mạnh hơn hoặc đẩy vào hàng đợi human review thay vì insert record rỗng.

---

## Tầng 3 — Multi-agent

Mỗi agent chỉ làm một việc — phân tách trách nhiệm để tối ưu từng bước độc lập và chạy song song.

### Agent chuyên biệt theo field

Mỗi agent chỉ extract một field — agent A extract `pain_points`, agent B extract ICP, agent C validate và merge kết quả. Cho phép fine-tune prompt riêng cho từng field và chạy song song để giảm latency.
