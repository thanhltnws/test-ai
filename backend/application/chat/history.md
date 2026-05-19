# Session History — Design Notes

> Liên quan: `chat_rag_strategy.md` (code flow tổng thể), `NOTES.md` (backlog chưa xong).

---

## Tại sao history quan trọng

Chat RAG không có history = mỗi câu hỏi độc lập. Người dùng không thể hỏi follow-up:

```
User: "Khách fintech Vietnam gặp vấn đề gì với tích hợp API?"
User: "Còn về chi phí thì sao?"   ← không có history → embed "chi phí" thuần túy
                                       → vector search miss hoàn toàn context fintech + API
```

History giải quyết 2 bài toán:
1. **Rewrite** — biến follow-up thành standalone question trước khi embed + search
2. **Context trong prompt** — LLM biết conversation đang ở đâu để trả lời nhất quán

---

## Implement hiện tại ✓

### Storage

```python
_sessions: dict[str, list[dict]] = {}   # in-memory, keyed by session_id
_SESSION_WINDOW = 6                     # giữ tối đa 6 turns gần nhất
```

`session_id` do client gửi lên trong request body (optional). Nếu thiếu → stateless (không lưu history).

### Flow trong lambda_handler

```
POST /chat { question, session_id }
    │
    ├─ _get_history(session_id) → last 6 turns
    │
    ├─ rewrite_question(question, history)     ← chỉ khi history không rỗng
    │      small LLM call (Gemini Flash / Haiku)
    │      "Còn về chi phí?" + context → "Khách fintech gặp vấn đề gì về chi phí tích hợp API?"
    │      error → trả nguyên question gốc
    │
    ├─ ... (intent, embed, query, LLM) ...
    │
    └─ _append_history(session_id, "user", question)
       _append_history(session_id, "assistant", answer)
```

History được prepend vào prompt (sau INSIGHTS/SIGNALS, trước QUESTION) để LLM có context hội thoại khi trả lời.

---

## Giới hạn hiện tại

| Vấn đề | Hiện trạng | Ảnh hưởng |
| --- | --- | --- |
| In-memory storage | `_sessions` dict trong Lambda process | Mất sạch khi Lambda cold start hoặc restart |
| Không có TTL thực | Không có cơ chế expire session | Session tồn tại mãi trong process lifetime |
| Không có cleanup | Dict chỉ tăng, không bao giờ shrink | Memory leak dài hạn nếu nhiều session |
| Không scale ngang | Mỗi Lambda instance có dict riêng | 2 request cùng session_id → 2 instance khác nhau → history không đồng bộ |

Với demo scale (1 instance, vài user) — chấp nhận được. Cần giải quyết khi scale.

_Backlog còn lại xem `NOTES.md`._
