# Session History — Design Notes

> Liên quan: `strategy.md` (code flow tổng thể), `backlog.md` (backlog chưa xong).

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
_SESSION_WINDOW = 12                    # 12 turns = 6 exchanges (initial + 5 follow-ups)
```

`session_id` do client gửi lên trong request body (optional). Nếu thiếu → stateless (không lưu history).

### Tại sao `_SESSION_WINDOW = 12`

1 turn = 1 message (user hoặc assistant). 1 exchange = 2 turns.

| Scenario | Turns | Exchanges |
| --- | --- | --- |
| Initial question + answer | 2 | 1 |
| + 5 follow-ups | 10 | 5 |
| **Tổng** | **12** | **6** |

Window = 12 đủ giữ toàn bộ cuộc hội thoại demo (initial + 5 follow-ups) mà không drop turn nào.

### Sliding window — không có detection, không có summarization

`_append_history` append vào full list không giới hạn. `_get_history` chỉ slice `[-12:]` khi đọc.

```python
def _append_history(session_id, role, content):
    _sessions.setdefault(session_id, []).append(...)   # grow unbounded

def _get_history(session_id):
    return _sessions.get(session_id, [])[-_SESSION_WINDOW:]  # slice khi đọc
```

Khi vượt quá window: oldest turns bị bỏ qua silently — không có detection, không có summarization, không có thông báo cho user. Với demo (max 5 follow-ups, window = 12) overflow không xảy ra nên summarization không cần thiết.

### Không có token counting

History được nhét thẳng vào prompt dưới dạng raw text. Không đếm token, không truncate theo token. Với Sonnet ~200K context window và demo scale, không bao giờ chạm giới hạn.

### Flow trong lambda_handler

```
POST /chat { question, session_id }
    │
    ├─ _get_history(session_id) → last 12 turns (tối đa)
    │
    ├─ rewrite_question(question, history)     ← chỉ khi history không rỗng
    │      small LLM call (Gemini Flash / Haiku)
    │      "Còn về chi phí?" + context → "Khách fintech gặp vấn đề gì về chi phí tích hợp API?"
    │      error → trả nguyên question gốc
    │      output: standalone (rewritten question)
    │
    ├─ [PARALLEL] detect_intent(standalone) + _embed_queries([standalone])
    │      intent detection và embedding chạy song song (ThreadPoolExecutor)
    │      cả hai đều dùng standalone, không phải question gốc
    │
    ├─ ... (query, LLM) ...
    │
    └─ _append_history(session_id, "user", question)      ← question GỐC, không phải standalone
       _append_history(session_id, "assistant", answer)
```

**Lưu ý về rewrite vs history:**

- `standalone` (rewritten) được dùng để embed + detect intent — tối ưu cho vector search
- `question` gốc được lưu vào history — giữ đúng điều user nói, tránh history bị "AI hoá"
- Nếu rewrite fail → `standalone = question` → không ảnh hưởng gì

History được prepend vào prompt (sau INSIGHTS/SIGNALS, trước QUESTION) để LLM có context hội thoại khi trả lời.

### Out-of-scope không lưu history

Khi `out_of_scope=True`, handler return sớm với canned response — `_append_history` không chạy. Exchange đó không tồn tại trong `_sessions`.

Intentional: canned response không có giá trị ngữ cảnh để rewrite follow-up từ đó.

---

## Giới hạn hiện tại

| Vấn đề | Hiện trạng | Ảnh hưởng |
| --- | --- | --- |
| In-memory storage | `_sessions` dict trong Lambda process | Mất sạch khi Lambda cold start hoặc restart |
| Không có TTL thực | Không có cơ chế expire session | Session tồn tại mãi trong process lifetime |
| Không có cleanup | Dict chỉ tăng, không bao giờ shrink | Memory leak dài hạn nếu nhiều session |
| Không scale ngang | Mỗi Lambda instance có dict riêng | 2 request cùng session_id → 2 instance khác nhau → history không đồng bộ |

Với demo scale (1 instance, vài user) — các giới hạn trên chấp nhận được.

_Backlog còn lại xem `NOTES.md`._
