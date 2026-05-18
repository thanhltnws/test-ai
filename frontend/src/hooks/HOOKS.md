# Hooks

## useChatHistory (`useChatHistory.ts`)

Manages persistent chat sessions in `localStorage`. Used exclusively by `pages/Chat.tsx`.

### Storage

- Key: `ai-insight-hub-chat-sessions` (hardcoded constant `STORAGE_KEY`)
- Format: `ChatSession[]` serialized as JSON
- Max sessions: 30 (oldest are dropped when limit is exceeded)

### ChatSession shape

```typescript
interface ChatSession {
  id: string          // crypto.randomUUID()
  title: string       // first user message, truncated to 60 chars
  messages: ChatMessage[]
  createdAt: string   // ISO timestamp
}
```

### API

| Function | Signature | Behavior |
|---|---|---|
| `createSession` | `(messages) => string` | Creates new session, prepends to list, returns new `id` |
| `updateSession` | `(id, messages) => void` | Replaces messages in an existing session |
| `deleteSession` | `(id) => void` | Removes session by id |

All three functions call `persist()` internally which writes the full sessions array to localStorage.

### Notes

- Sessions are loaded once on mount via `useState(loadSessions)` — `loadSessions` is called as the initializer, not on every render.
- `createSession` derives the title from the first user message: `firstUser.content.slice(0, 60)`.
- All three mutators use the functional `setSessions(prev => ...)` pattern to avoid stale closure bugs.
