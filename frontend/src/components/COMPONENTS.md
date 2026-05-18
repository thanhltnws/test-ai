# Components

## Navbar (`Navbar.tsx`)

Left sidebar, always visible. Width: 240px, `position: static` inside the flex row layout.

### Sections (top → bottom)

1. **Brand** — `<Logo size={32} />` + "AI Insight Hub / Customer Intelligence"
2. **Navigation links** — defined in `links[]` array: Overview (`/`), AI Chat (`/chat`), About (`/analysis`). Uses `<NavLink>` with active styling via `var(--accent-bg)` background.
3. **`<AccessTokenControl />`** — rendered inline inside nav (only visible when `isLambdaDataSource === true`)
4. **Batch section** — only visible when `isLambdaDataSource === true`. Calls `runBatch()` on click. Currently disabled via `const batchTriggerEnabled = false`.
5. **Footer** — "Internal Demo · v0.1"

### Batch trigger

`batchTriggerEnabled = false` gates the button. To re-enable: set to `true`. The `handleRunBatch` function calls `runBatch()` from `api/lambdas.ts` and shows a success/error message inline.

---

## AccessTokenControl (`AccessTokenControl.tsx`)

Manages the Bearer token used for Lambda API calls. Rendered inside `<Navbar />`.

**Returns `null`** when `isLambdaDataSource === false` — invisible in mock mode.

### Behavior

- Token stored in `localStorage` under key from `VITE_AUTH_TOKEN_STORAGE_KEY` (default: `ai-insight-hub-auth-token`).
- Draft/saved pattern: editing the input sets status to "Unsaved". Save button commits to localStorage. Clear button removes the token.
- Status display: "Saved" → "Token saved for this browser." / "Unsaved" → amber color / "Cleared" → muted.
- Save button is disabled (`opacity: 0.5`) when `draftToken === savedToken` (no unsaved changes).

### API functions used

- `getAuthToken()` — reads from localStorage on mount
- `setAuthToken(value)` — writes or removes from localStorage

---

## WelcomeModal (`WelcomeModal.tsx`)

Full-screen overlay shown on first page load. Mounts in `App.tsx` above all routes.

- State: `open` (boolean, defaults to `true`)
- Closes on: clicking the × button, clicking the "Đã hiểu, bắt đầu" footer button, or clicking the backdrop
- No persistence — re-shows on every hard refresh (intentional for demo)

### Content

Static, defined in `SCOPE_ITEMS` array at top of file (2 items):
1. "AI làm gì trong hệ thống này?" — two paragraphs
2. "Điều gì khiến hệ thống này khác?" — three bullet cards

Scrollable body with fixed header and footer (flex column, `overflow: hidden` on outer shell).

---

## Logo (`Logo.tsx`)

Simple SVG logo component. Accepts `size` prop (number, default presumably 32).

Used in `<Navbar />` brand section.
