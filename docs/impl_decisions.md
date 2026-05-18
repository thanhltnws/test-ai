# Implementation Decisions — Pre-Demo Backlog

> Tạm thời. Tổng hợp các quyết định đã chốt trong session review, chuẩn bị implement.

---

## 1. ICP Schema Redesign (CHỐT — chưa implement hoàn toàn)

### Trạng thái hiện tại
- `icp JSONB` column chứa: `deal_size`, `client_type`, `tech_maturity`, `engagement_type`
- `market` và `sector` đã là top-level column (done)

### Quyết định
- **Bỏ hoàn toàn `icp` JSONB column**
- **Flatten 3 field thành top-level TEXT column**: `deal_size`, `client_type`, `tech_maturity`
- **Bỏ `engagement_type`**: là kết quả hợp đồng (negotiation outcome), LLM không infer được ở early funnel, gây noise

### Schema mới cho `signals`

| Column | Type | Values |
|---|---|---|
| `deal_size` | TEXT | `small` · `medium` · `large` |
| `client_type` | TEXT | `individual` · `startup` · `corporate` |
| `tech_maturity` | TEXT | `non-tech` · `semi-tech` · `technical` |

Lý do flatten (không giữ JSONB):
- Demo audience có thể hỏi filter/group theo từng field → cần indexed column
- Query sạch hơn: `GROUP BY client_type, deal_size` thay vì `GROUP BY icp->>'client_type', icp->>'deal_size'`
- Nhất quán với `market` và `sector` đã flatten trước đó

### SQL sau khi flatten (ICP tiềm năng nhất)

```sql
SELECT
    client_type,
    deal_size,
    tech_maturity,
    COUNT(*) FILTER (WHERE funnel_stage = 'won') AS won_count,
    COUNT(*) AS total_count
FROM signals
GROUP BY client_type, deal_size, tech_maturity
ORDER BY won_count DESC
LIMIT 5;
```

### Files cần sửa

| File | Thay đổi |
|---|---|
| `docs/schema.md` | Bỏ `icp` section, thêm 3 column riêng |
| `transform/handler.py` | Bỏ `_ICP` model, 3 field lên thẳng `_Extraction`, sửa INSERT SQL |
| `transform/prompt.py` | `icp: object` → 3 field riêng, bỏ few-shot `icp` object |
| `seed/generate.py` | `normalize_extraction` trả 3 key riêng, bỏ `icp` dict |
| `seed/prompt.py` | Tương tự transform/prompt.py |
| `batch/handler.py` | `icp_breakdown` SQL dùng column trực tiếp thay JSONB operator |
| `transform/transform_strategy.md` | Update field list + rationale |
| `backend/application/batch/STRATEGY.md` | Update icp_breakdown section |

### Prerequisite
- Không cần migration — drop DB và recreate từ đầu

---

## 2. `funnel_stage` Default (CHỐT — không thay đổi)

Giữ nguyên `"consideration"` làm default khi LLM không xác định được.

Lý do: prompt đã có guidance chi tiết cho từng record type (marketing lead, CRM profile, ops ticket) → trường hợp "genuinely cannot determine" rất hiếm. Default chỉ trigger khi LLM trả về invalid enum value (typo/format error), không phải genuine uncertainty.

---

## 3. `needs` Field (CHỐT — SKIP)

Overlap gần hết với `use_cases`. Sự khác biệt (explicit requirements: team size, timeline, tech stack) chỉ xuất hiện trong một số ít record — mock data không có signal đủ cụ thể để populate field này có nghĩa. Added complexity không justify cho demo.

---

## 4. `raw_text` (CHỐT — không persist vào DB)

Xóa khỏi `signals` table. Giữ in-memory trong Lambda/seed pipeline cho LLM extraction và batch sizing.

Files đã sửa: `transform/handler.py`, `seed/import.py`, `seed/generate.py`, `docs/schema.md`.

---

## 5. `confidence_score` (CHỐT — xóa khỏi DB)

Không có trong đề bài. Không được dùng trong analytics query hay RAG filter. LLM self-reported confidence không reliable.

Giữ `confidence_score` trong Pydantic `_Extraction` model và retry logic (`RETRY_CONFIDENCE_THRESHOLD`) — chỉ dùng internally trong Lambda để quyết định có retry batch không. Không persist vào DB, không hiển thị trong dashboard.

Scope sửa khi implement tổng thể: xóa khỏi INSERT SQL (`transform/handler.py`, `seed/import.py`), xóa khỏi prompt, xóa khỏi `docs/schema.md`.
