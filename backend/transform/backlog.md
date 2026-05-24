# Transform Lambda — Backlog

---

## P1 — Tiếp theo

### Source-type context injection

Hook `context_content` đã có trong `build_extract_prompt` nhưng luôn được gọi với `context_content=""` — `context_section` trong prompt template không bao giờ được populate.

Có thể inject metadata về source type để model đọc đúng signal theo từng source, ví dụ:

```text
Source 'redmine': ticket status reflects issue lifecycle, not deal stage.
Source 'hubspot': deal_stage field maps directly to funnel_stage.
```

Giúp giảm funnel_stage confusion giữa các source mà không cần viết nhiều prompt template riêng. Thay đổi nhỏ ở tầng handler — chỉ cần build một dict `SOURCE_CONTEXT` và truyền vào khi gọi `build_extract_prompt`.

### Multi-pass riêng cho embedding_text

`embedding_text` là field quan trọng nhất trong toàn bộ pipeline — chất lượng của nó ảnh hưởng trực tiếp đến RAG retrieval. Hiện tại nó được extract trong cùng một batch call với 13 field khác, tức là model phải chia attention cho toàn bộ schema cùng lúc.

Nếu sau confidence-based retry mà `embedding_text` vẫn rỗng hoặc quá ngắn, chạy thêm một pass riêng với prompt tập trung chỉ vào `embedding_text` — không cần extract các field khác. Pass này có thể dùng `_EMBEDDING_TEXT_INSTRUCTION` làm core, kết hợp với raw text gốc. Chỉ áp dụng cho các record đã qua noise filter (có signal) nhưng `embedding_text` yếu.

---

## P2 — Còn lại

### Coercion rate monitoring

Pydantic hiện tại coerce về default silently — `funnel_stage="open"` → `"consideration"`, `sector="banking"` → `"other"`. Không có log nào báo việc này xảy ra.

Record có nhiều field categorical bị coerce về default (e.g., `funnel_stage` + `sector` + `market` đều là default) là dấu hiệu LLM không parse được record đó, nhưng vẫn pass noise filter nếu có `embedding_text`. Data kiểu này làm sai lệch dashboard filter.

Cần log `coercion_count` per record cùng với `confidence_score` khi test với data thực để detect pattern và xác định ngưỡng cần xử lý.
