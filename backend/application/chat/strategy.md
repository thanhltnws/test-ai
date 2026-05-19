# Chat RAG Strategy — Insights-First

> File này ghi lại chiến thuật RAG cho chat lambda. Liên quan: `NOTES.md` (backlog cụ thể).

---

## Nguyên tắc cốt lõi

**Insights = primary context. Signals = evidence layer.**

Batch pipeline đã làm công việc aggregation + summarization trên toàn bộ signals. Kết quả đó nằm trong `insights` — đây là "distilled knowledge" của hệ thống. Chat RAG nên tận dụng tối đa thay vì đi lại từ raw signals.

| Layer | Bảng | Vai trò trong chat |
|-------|------|-------------------|
| Primary | `insights` + `insight_embeddings` | Pre-computed narratives, period-aware, market-aware |
| Secondary | `signals` + `signal_embeddings` | Granular evidence, source_url cho citations |

---

## Code flow — trạng thái implement

```
[1]  session_id → _get_history (sliding window N=6)                     ✓
[2]  rewrite_question (small LLM call — chỉ khi có history)             ✓
[3]  detect_intent ∥ _embed_queries (ThreadPoolExecutor max_workers=2)  ✓
       → market, sector, period, period_start, use_latest,
         result_type, funnel_stage, needs_citations, out_of_scope
[3a] out_of_scope=true → canned response, stop (không query DB)         ✓
[4]  Phase 1 (parallel):
       _count_signals ∥ query_insight_embeddings                        ✓
       → metadata filter via JOIN (market, period, result_type)         ✓
       → time range: _default_period_start khi period_start=null        ✓
[5]  Graceful fallback: total_signals == 0 → canned response, stop      ✓
[6]  Graceful fallback: top_insight_score < 0.5 → insight_low=True      ✓
[7]  Phase 2 conditional (chỉ khi needs_citations or insight_low):
       query_signal_embeddings (filter: market, sector, funnel_stage)   ✓
[8]  build_chat_prompt:
       INSIGHTS (PRIMARY) → SIGNALS (EVIDENCE) → HISTORY → QUESTION    ✓
       Citation format enforced: {label, url} từ SIGNALS only           ✓
       insight_low=True → inject [NO MATCHING DATA] vào prompt          ✓
[9]  1 LLM call (Sonnet/Gemini)                                         ✓
[10] _append_history (user + assistant)                                  ✓
```

**Đã bỏ:** `query_aurora` background aggregates (`pain_points`, `use_cases` TEXT[] không `GROUP BY` được vì exact-string match), `_extract_keywords`, `raw_text ILIKE`.

---

_Backlog còn lại xem `NOTES.md`._
