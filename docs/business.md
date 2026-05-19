# AI Insight Hub — Business Decisions

## Dashboard vs Chat/RAG — phân chia thông tin

### Nguyên tắc
Dashboard là **digest tổng hợp định kỳ** (pre-computed batch). Chat là **query dimensional on-demand**. 6 factor từ đề bài đều là input cho cả hai — câu hỏi là cái nào hợp lý để snapshot định kỳ, cái nào để query theo yêu cầu.

Không build pivot table / cross-tab trên dashboard. LLM synthesis xử lý cross-dimensional reasoning, output ra narrative + ranked list. Dashboard là tool for **digest**, không phải BI.

### Phân chia 6 factor

| Factor | Dashboard | Chat |
|---|---|---|
| `pain_points` | Ranked list + AI synthesis | Drill-down theo segment |
| `objections` | Gộp vào pain_points — cùng là customer friction | Câu hỏi dimensional |
| `use_cases` | Gộp vào ICP — segment X dùng để làm gì | Câu hỏi cụ thể per segment |
| `funnel_stage` | Distribution chart + health narrative | Cross với objections, win/loss |
| `ICP` | Segment cards + narrative | ICP của won vs lost deals |
| `market` | Filter dimension (dropdown) — không phải section riêng | Context trong mọi câu chat |

---

## Insights — 4 result_type

Giữ nguyên 4 tên result_type hiện tại. Mở rộng nội dung payload của 2 type mà không đổi tên.

| result_type | Nội dung | Thay đổi |
|---|---|---|
| `pain_points_summary` | top pain_points + **top_objections** (cùng nhóm friction) + summary | Thêm `top_objections` vào payload |
| `funnel_distribution` | stage counts + pct + health narrative | Giữ nguyên |
| `icp_narrative` | top segments + **top_use_cases** per segment + narrative | Thêm `top_use_cases` vào payload |
| `recommendations` | sales actions + marketing actions + summary | Giữ nguyên |

### Quyết định cuối (2026-05-19)
Giữ nguyên prompt và 4 result_type, không thêm `top_objections` hay `top_use_cases` vào dashboard. Lý do: objections và use_cases có thể khai thác qua chat/RAG on-demand — không cần pre-compute thành snapshot định kỳ.

### FE component tương ứng (chưa implement đầy đủ)

| result_type | FE component | Data fields cần dùng |
|---|---|---|
| `pain_points_summary` | Horizontal bar chart + AI synthesis text | `top_items[].item`, `top_items[].count`, `top_items[].insight`, `summary` |
| `funnel_distribution` | Donut/pie chart + AI health narrative | `stages[].stage`, `stages[].count`, `stages[].pct`, `summary` |
| `icp_narrative` | Segment cards + AI narrative | `top_segments[].sector/market/client_type/tech_maturity/deal_size/count`, `narrative` |
| `recommendations` | 2 cột Sales / Marketing | `sales[]`, `marketing[]`, `summary` |

### BE — không cần thay đổi API

API Lambda (`api/handler.py`) đã map động `result_type → key` trong response. FE nhận 1 JSON phẳng với 4 key tương ứng 4 result_type:

```json
{
  "period": "monthly",
  "period_start": "2026-05-01",
  "period_end": "2026-05-17",
  "market": null,
  "pain_points_summary": { ... },
  "funnel_distribution": { ... },
  "icp_narrative": { ... },
  "recommendations": { ... }
}
```

Không cần đụng API handler khi thêm/đổi result_type — response tự adapt.

---

## Pending

- [ ] FE: fix ICP field mismatch (`company_size`/`region` → `client_type`/`tech_maturity`/`market`)
