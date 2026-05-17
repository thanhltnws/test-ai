# Chat Lambda — Notes

## Missing: query insight_embeddings

`query_pgvector` currently only queries `signal_embeddings` (raw customer signals).
Per architecture, chat RAG should also query `insight_embeddings` (pre-computed LLM
narratives from the batch pipeline) and join with `insights` for richer prompt context.

## Conversation history

Current chat is stateless — each request is independent. Consider adding lightweight
conversation history (last N turns) to the prompt so follow-up questions can reference
prior context. Trade-off: longer prompts → higher token cost and latency.
