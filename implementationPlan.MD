# AXON — Implementation Plan

---

## PRE-STEP — Update Instructions File

- [x] Add `## Error Handling` section to `.github/instructions/nextjs.instructions.md` — every `fetch()` in try/catch + check `response.ok` before `.json()`

---

## PHASE 0 — Install Everything

### 0A — Backend (uv)

- [x] `cd backend && uv init --app`
- [x] `uv add "fastapi[standard]" langgraph langchain-core langchain-openai supabase httpx presidio-analyzer presidio-anonymizer pydantic-settings "python-jose[cryptography]" cryptography slowapi`
- [x] `uv run python -m spacy download en_core_web_sm`
- [x] Create `backend/.env` + `backend/.env.example` with all required keys
- [x] Verify: `uv run uvicorn app.main:app --reload` → `http://localhost:8000/docs` loads

### 0B — Frontend (pnpm)

- [x] `cd frontend && npx create-next-app@latest . --typescript --tailwind --app --turbopack`
- [x] `pnpm add @supabase/supabase-js @supabase/ssr @tanstack/react-query zod react-markdown remark-gfm eventsource-parser`
- [x] `pnpm dlx shadcn@latest init` + manual install of `tw-animate-css class-variance-authority clsx tailwind-merge lucide-react` + `lib/utils.ts` created
- [x] Verify: `pnpm dev` → `http://localhost:3000` loads ✅ (Next.js 16.2.4 + Turbopack, Ready in 5.3s)

### 0C — Supabase (manual)

- [ ] Create Supabase project → copy URL + anon key + service role key
- [ ] Enable Google OAuth → add Google Cloud OAuth2 credentials
- [x] Run DB schema SQL: `conversations`, `messages`, `memory_entries` tables
- [x] Enable `pgvector` extension
- [x] Add HNSW index on `memory_entries.embedding`
- [x] Enable RLS policies on all tables
- [x] Create `.env.example` files for backend and frontend
- [x] Fill actual `.env` files with Supabase + API keys

---

## PHASE 1 — Backend Core Infrastructure

- [x] `app/main.py` — FastAPI app, CORS (`localhost:3000`), lifespan event
- [x] `app/core/config.py` — `Settings(BaseSettings)` reads all env vars
- [x] `app/core/security.py` — `get_current_user(token: HTTPBearer)` validates Supabase JWT, returns `UserSchema`
- [x] `app/features/auth/schemas.py` — `UserSchema(id, email)`
- [x] `app/features/auth/router.py` — `GET /api/v1/auth/me` (protected)
- [x] Mount auth router in `main.py`
- [x] **Verify /docs:** `GET /api/v1/auth/me` → 401 without token, 200 with valid JWT

---

## PHASE 2 — Backend Models Endpoint

- [x] `app/features/models/schemas.py` — `ModelInfo(id, name, provider, context_length)`
- [x] `app/features/models/service.py` — TTL cache + `_fetch_models_from_openrouter()` + `get_models()`
- [x] `app/features/models/router.py` — `GET /api/v1/models` (public, no auth)
- [x] Mount models router in `main.py`
- [x] **Verify /docs:** `GET /api/v1/models` → 200 JSON list

---

## PHASE 3 — Backend Agents Foundation

- [x] `app/agents/state.py` — `AxonState(TypedDict)`: `messages`, `user_id`, `model_id`, `memory_context`
- [x] `app/db/supabase.py` — async Supabase client singleton (`get_supabase_client()`)
- [x] `app/agents/orchestrator.py` — minimal LangGraph graph: single node calling OpenRouter via `httpx.AsyncClient`

---

## PHASE 4 — Backend Chat (SSE Streaming)

- [x] `app/features/chat/schemas.py` — `ChatRequest(message, model_id, conversation_id?)` + `SSEEvent`
- [x] `app/features/chat/service.py` — calls `orchestrator.graph.astream_events(version="v2")`, yields SSE tokens
- [x] `app/features/chat/router.py` — `POST /api/v1/chat/stream` → `StreamingResponse(media_type="text/event-stream")`, protected
- [x] Mount chat router in `main.py`
- [x] **Verify /docs:** POST with JWT → see streamed `{"type":"token","content":"..."}` in response

---

## PHASE 5 — Backend Memory + RAG + File Uploads

- [x] `app/core/privacy.py` — async `mask_pii(text)` using Presidio + `en_core_web_sm`, dispatched via `asyncio.to_thread` (singleton engines)
- [x] `app/core/crypto.py` — Fernet (AES-128-CBC + HMAC) `encrypt`/`decrypt` helpers, fail-fast on bad key
- [x] `app/db/embeddings.py` — `embed_text()` via OpenRouter `/embeddings` (`openai/text-embedding-3-large`, `dimensions=1536`), plus `insert_memory`, `list_memories`, `delete_memory`, `match_memories` (RPC)
- [x] `app/features/memory/schemas.py` — `MemoryCreate`, `MemoryEntry`, `MemorySearchRequest`, `MemorySearchResult`, `FileUploadResult`
- [x] `app/features/memory/ingest.py` — parse `.txt`/`.md`/`.pdf`/`.docx` (pypdf + python-docx in `to_thread`) + `RecursiveCharacterTextSplitter` (800/100); 10 MB / 500 chunk limits
- [x] `app/features/memory/service.py` — pipeline: mask → embed(masked) → encrypt(plaintext) → insert; decrypt on retrieval; `ingest_file` for chunked uploads
- [x] `app/features/memory/router.py` — `POST /api/v1/memory`, `GET /api/v1/memory`, `POST /api/v1/memory/search`, `DELETE /api/v1/memory/{id}`, `POST /api/v1/memory/upload` (multipart) — all protected
- [x] `app/features/memory/tool.py` — `@tool async def search_memory(query, runtime: ToolRuntime)` — reads `user_id` from graph state
- [x] Wire `search_memory` into `orchestrator.py` via `bind_tools` + `ToolNode` + conditional edge `should_continue`
- [x] Add `ENCRYPTION_KEY`, `embedding_model`, `embedding_dimensions` to `app/core/config.py`
- [x] New deps: `pypdf`, `langchain-text-splitters`, `python-docx`
- [x] **Verify /docs:** POST memory → GET list → DELETE works
- [x] **Verify:** Chat message referencing stored memory → orchestrator uses memory tool
- [x] **Verify:** Upload PDF → multiple chunks created → searchable

---

## PHASE 5.5 — Backend Rate Limiting

> **Решение:** in-memory storage по подразбиране (без external dependency, работи перфектно при single-process). Redis се включва само ако зададеш `REDIS_URL` env var — нужен единствено при multiple workers или horizontal scaling. `slowapi` е вече в `pyproject.toml`.

- [x] `app/core/limiter.py` — `Limiter(key_func=_jwt_key)` singleton; `_jwt_key` декодира `sub` от Bearer token без пълна JWT верификация (верификацията е в `security.py`); fallback към `remote_address` за публичните routes
- [x] Register `RateLimitExceeded` → 429 handler в `app/main.py` с `Retry-After` header
- [x] Apply limits per route (decorator `@limiter.limit(...)`) — вижте таблицата по-долу
- [x] Env var `REDIS_URL` в `config.py` (optional, default None) — ако е зададен, `storage_uri=settings.redis_url`, иначе in-memory
- [x] **Verify:** Hammer `/api/v1/chat/stream` → 429 след лимита с `Retry-After`

**Лимити по route:**

| Route                 | Limit     | Причина                                               |
| --------------------- | --------- | ----------------------------------------------------- |
| `POST /chat/stream`   | 20/minute | LLM call + embeddings — най-скъп                      |
| `POST /memory/upload` | 5/minute  | embeddings × N chunks — потенциално стотици API calls |
| `POST /memory`        | 30/minute | 1 embedding call                                      |
| `POST /memory/search` | 30/minute | 1 embedding call                                      |
| `GET /memory`         | 60/minute | само DB read                                          |
| `DELETE /memory/{id}` | 30/minute | само DB write                                         |
| `GET /models`         | 60/minute | cached, публичен — по IP                              |

---

## PHASE 6 — Supervisor Pattern Agent

> **Architecture:** Multi-agent graph — supervisor decides routing, memory_agent handles retrieval.
> Flow: `START → supervisor → (needs memory) → memory_agent → supervisor → END`
> `→ (direct reply)                          → END`

- [x] `app/agents/subagents/__init__.py` — subagents package
- [x] `app/agents/subagents/memory_agent.py` — async node: searches memory service directly, adds ToolMessage + updates `memory_context`
- [x] `app/agents/supervisor.py` — `supervisor_node` with `transfer_to_memory_agent` handoff tool; two model singletons (routing / response) to prevent re-delegation loops
- [x] `app/agents/orchestrator.py` — refactored: `supervisor` + `memory_agent` nodes, `_should_continue` with ToolMessage-based loop guard
- [x] **Verify:** "what do you know about me?" → trace shows `supervisor → memory_agent → supervisor`
- [x] **Verify:** "write me a haiku" → supervisor responds directly (`supervisor → END`)

---

## PHASE 6.5 — Backend Conversation Persistence

> **Architecture:** Every chat session is tied to a `conversation` row in Supabase. Messages are stored in a separate `messages` table with `user_id` for RLS enforcement. History is replayed into `AxonState` on every request (last 40 rows = 20 turns). PII is masked before the LLM but the original text is persisted.

- [x] `app/features/chat/conversation_service.py` — full CRUD layer:
  - `get_or_create_conversation(user_id, conversation_id, model_id) -> str` — validates ownership; silently creates new on mismatch
  - `save_message(conv_id, user_id, role, content) -> None` — graceful degradation (logs on failure, never aborts the stream)
  - `load_history(conv_id, user_id, limit=40) -> list[BaseMessage]` — fetches newest-first, reverses for chronological LLM context
  - `list_conversations(user_id) -> list[ConversationOut]` — ordered by `updated_at DESC`
  - `get_messages(conv_id, user_id) -> list[MessageOut]` — raises `HTTPException(404)` when not found / not owned
  - `delete_conversation(conv_id, user_id) -> bool` — CASCADE deletes messages via FK
  - All Supabase calls wrapped in `try/except` with structured logging
- [x] `app/features/chat/schemas.py` — added `ConversationOut` + `MessageOut` with `Field` constraints (`min_length`, `max_length`); `role` typed as `Literal["user","assistant","system","tool"]`
- [x] `app/features/chat/router.py` — 3 new endpoints:
  - `GET /api/v1/chat/conversations` — list all conversations (newest first)
  - `GET /api/v1/chat/conversations/{conversation_id}/messages` — paginated message history; `conversation_id` validated as `UUID`
  - `DELETE /api/v1/chat/conversations/{conversation_id}` — 204 on success, 404 on not found
- [x] `app/features/chat/service.py` — wired conversation persistence into `stream_chat`:
  - Step 1: `get_or_create_conversation` (error → yield error+done frame)
  - Step 2: `load_history` (last 40 messages)
  - Step 3: `save_message("user", original_text)` — persists unmasked
  - Step 4: yield `start` frame with `conversation_id`
  - Step 5: mask PII via `mask_pii` + `asyncio.gather` on history; build `AxonState` with masked messages
  - Step 6 (finally): `save_message("assistant", joined_tokens)` + yield `done` frame
  - User ID anonymised in logs (`SHA-256[:8]`)
- [x] **Verify:** New conversation created on first message → `conversation_id` returned in `start` frame
- [x] **Verify:** Subsequent messages with same `conversation_id` → history replayed into graph
- [x] **Verify:** `GET /conversations` → list; `DELETE` → 204 + `GET /messages` → 404

---

- [x] `lib/supabase/client.ts` — `createBrowserClient` (`@supabase/ssr`)
- [x] `lib/supabase/server.ts` — `createServerClient` with cookies
- [x] `proxy.ts` — auth guard: redirect to `/login` if no session, redirect to `/chat` if already logged in
- [x] `app/providers.tsx` — `QueryClientProvider` wrapper
- [x] `app/layout.tsx` — root layout wrapping `providers.tsx`
- [x] `features/auth/components/LoginButton.tsx` — Google OAuth trigger
- [x] `app/(auth)/login/page.tsx` — login page
- [x] `app/(auth)/callback/route.ts` — Supabase OAuth callback handler
- [x] **Verify:** Google login → redirected to `/chat`

---

## PHASE 7 — Frontend Chat UI

- [x] `features/chat/types.ts` — `Message`, `Conversation`, `ChatModel`
- [x] `lib/api.ts` — typed fetch wrapper with Supabase JWT header injection + try/catch
- [x] `features/chat/hooks/useChat.ts` — `fetch()` + `ReadableStream` + `eventsource-parser`, appends tokens to state
- [x] `features/chat/hooks/useModels.ts` — TanStack Query for `GET /api/v1/models`
- [x] `features/chat/components/ChatInput.tsx` — textarea + send button
- [x] `features/chat/components/MessageBubble.tsx` — `react-markdown` + `remark-gfm`
- [x] `features/chat/components/ModelSelector.tsx` — shadcn `<Select>` driven by `useModels`
- [x] `features/chat/components/ChatWindow.tsx` — message list + auto-scroll
- [x] `app/(dashboard)/chat/page.tsx` — assembles all components
- [x] **Verify:** Send message → tokens stream in real time, model switching works

## PHASE 8 — Frontend Memory UI

- [x] `features/memory/types.ts`
- [x] `features/memory/hooks/useMemory.ts` — TanStack Query CRUD
- [x] `features/memory/components/MemoryView.tsx` — list + delete
- [x] `features/memory/components/MemoryItem.tsx` — single row + inline confirm-delete
- [x] `features/memory/components/MemoryCreateForm.tsx` — textarea + save
- [x] `features/memory/components/MemoryUploader.tsx` — file/drag-drop, 10 MB client check
- [x] `features/memory/components/MemorySearchBar.tsx` — query + threshold + limit
- [x] `lib/api.ts` — added `apiFetchVoid` (DELETE 204) + `apiFetchMultipart` (uploads)
- [x] `features/chat/components/ChatWindow.tsx` — added Memory link in header
- [x] `app/(dashboard)/memory/page.tsx`
- [x] **Verify:** Entries from chat appear in the list; delete works

---

## PHASE 9 — Frontend Chat History Visualisation

> **Goal:** Let the user browse past conversations from the sidebar, load a conversation and continue it, and delete old ones — without leaving `/chat`.

### 9A — API layer (`lib/api.ts`)

- [x] Add `listConversations()` — `GET /api/v1/chat/conversations` → `ConversationOut[]`
- [x] Add `getConversationMessages(id)` — `GET /api/v1/chat/conversations/{id}/messages` → `MessageOut[]`
- [x] Add `deleteConversation(id)` — `DELETE /api/v1/chat/conversations/{id}` → `void` (use `apiFetchVoid`)
- [x] Add TypeScript types `ConversationOut` and `MessageOut` to `features/chat/types.ts`

### 9B — TanStack Query hooks (`features/chat/hooks/useConversations.ts`)

- [x] `useConversations()` — query `listConversations`; stale after 30 s
- [x] `useConversationMessages(id)` — query `getConversationMessages(id)`; enabled only when `id` is set
- [x] `useDeleteConversation()` — mutation `deleteConversation`; on success invalidate `useConversations` + clear active conversation if deleted

### 9C — Sidebar component (`features/chat/components/ConversationSidebar.tsx`)

- [x] Collapsible panel (hidden on mobile, 260 px on desktop)
- [x] "New chat" button at top → clears `conversationId` in `useChat`
- [x] List of past conversations ordered by `updated_at DESC`
  - Each row shows: title (truncated 1 line), relative time (`date-fns/formatDistanceToNow`)
  - Active conversation highlighted
  - Hover → show delete icon (inline confirm: click once to mark red, second click deletes)
- [x] Loading skeleton (3 placeholder rows) while `useConversations` is fetching
- [x] Empty state: "No conversations yet"

### 9D — Load conversation into chat (`features/chat/hooks/useChat.ts`)

- [x] Export `loadConversation(id: string)` from `useChat` — sets `conversationId` + seeds `messages` state from `useConversationMessages` data
- [x] When a conversation is selected in the sidebar, call `loadConversation` and scroll to bottom

### 9E — Wire sidebar into `ChatWindow.tsx`

- [x] Add `ConversationSidebar` to the left of the message list
- [x] Pass `activeConversationId`, `onSelect` and `onNew` callbacks down
- [x] On mobile: hamburger icon in header toggles sidebar visibility (`useState`)

### 9F — Accessibility & UX polish

- [x] Sidebar items are `<button>` elements with `aria-current="page"` on the active one
- [x] Delete confirmation uses `aria-label="Delete conversation"`
- [x] Keyboard: `Escape` closes sidebar on mobile

### Verification

- [ ] Open `/chat` → sidebar lists past conversations
- [ ] Click a conversation → messages load; `conversationId` in `useChat` updated
- [ ] Send a new message in loaded conversation → appended correctly; `updated_at` bumps to top
- [ ] "New chat" → blank input, no conversation selected
- [ ] Delete conversation → removed from list; if active → chat resets to new

---

## PHASE 10 — YouTube Transcript Workflow Subagent

> **Goal:** When the user pastes a YouTube link in chat, the supervisor activates a dedicated `youtube_agent` subagent. The subagent fetches the video transcript, enriches it with metadata (title, channel, duration), and returns structured data to the supervisor. The supervisor presents a summary + key points, and offers to save the full transcript to Supabase (a new `video_transcripts` table) for later retrieval and visualisation.

### Architecture & Flow

```
User: "https://www.youtube.com/watch?v=..."
  → supervisor detects YouTube URL (regex)
  → handoff tool: transfer_to_youtube_agent
  → youtube_agent:
      1. extract video_id from URL
      2. fetch transcript via youtube-transcript-api (Python)
      3. fetch metadata via yt-dlp or pytube (title, channel, duration)
      4. chunk + structure transcript (timestamped paragraphs)
      5. return YouTubeTranscriptResult to supervisor
  → supervisor:
      - renders summary + key points to user
      - asks "Want me to save this?" (or user can ask explicitly)
      → if yes: call save_video_transcript tool → INSERT to video_transcripts table
```

### Ideas за workflow режими (избери един при имплементация)

| Режим                                                 | Описание                                                          | Плюсове                        |
| ----------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------ |
| **Transcript only**                                   | Само raw текст с timestamps                                       | Бързо, минимален LLM overhead  |
| **Transcript + Summary + Key Points** ✅ _препоръчан_ | Transcript + auto-generated summary + bullet key points           | Полезен изход, лесен за четене |
| **Study Notes**                                       | Transcript → структурирани бележки с heading-и, Q&A, action items | Идеален за образователни видеа |
| **Research Digest**                                   | Transcript → теми + цитати + препратки                            | За по-дълги/технически видеа   |

### 10A — Database (`supabase/migrations/`)

- [ ] New migration: create `video_transcripts` table:
  ```sql
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  youtube_url text NOT NULL,
  video_id    text NOT NULL,
  title       text,
  channel     text,
  duration_s  integer,
  transcript  text NOT NULL,
  summary     text,
  key_points  jsonb,          -- string[]
  metadata    jsonb DEFAULT '{}',
  created_at  timestamptz DEFAULT now()
  ```
- [ ] RLS: `user_id = auth.uid()` on SELECT / INSERT / DELETE
- [ ] Index on `(user_id, created_at DESC)`

### 10B — Backend subagent (`app/agents/subagents/youtube_agent.py`)

- [ ] New dependency: `uv add youtube-transcript-api yt-dlp` (or `pytube` for metadata)
- [ ] `YouTubeTranscriptResult` dataclass / TypedDict: `video_id`, `title`, `channel`, `duration_s`, `transcript_text`, `timestamped_chunks`
- [ ] `youtube_agent_node(state: AxonState)`:
  - Extract YouTube URL from last `HumanMessage` via regex
  - Fetch transcript via `YouTubeTranscriptApi.get_transcript()` — handle `TranscriptsDisabled`, `NoTranscriptFound`
  - Fetch metadata via `yt-dlp` (async, `asyncio.to_thread`)
  - Build structured `YouTubeTranscriptResult` and store in `AxonState["youtube_result"]`
  - Return `ToolMessage` to close handoff tool call

### 10C — Save tool (`app/features/youtube/tool.py`)

- [ ] `@tool async def save_video_transcript(runtime: ToolRuntime)`:
  - Reads `youtube_result` from `runtime.state`
  - `INSERT INTO video_transcripts (user_id, youtube_url, video_id, title, ...)` via Supabase client
  - Returns confirmation string with saved record id
- [ ] Wire tool into supervisor's `bind_tools` list

### 10D — Backend feature layer (`app/features/youtube/`)

- [ ] `schemas.py` — `VideoTranscriptOut(id, youtube_url, video_id, title, channel, duration_s, transcript, summary, key_points, created_at)`
- [ ] `service.py` — `list_transcripts(user_id)`, `get_transcript(id, user_id)`, `delete_transcript(id, user_id)`
- [ ] `router.py`:
  - `GET  /api/v1/youtube` — list saved transcripts (newest first)
  - `GET  /api/v1/youtube/{id}` — full transcript detail
  - `DELETE /api/v1/youtube/{id}` — 204 on success, 404 if not found/owned

### 10E — Supervisor wiring (`app/agents/supervisor.py` + `orchestrator.py`)

- [ ] Add `transfer_to_youtube_agent` handoff tool in supervisor's tool list
- [ ] Supervisor system prompt: detect YouTube URL pattern → use `transfer_to_youtube_agent`
- [ ] Add `youtube_agent` node to the LangGraph graph
- [ ] Add `youtube_result` field to `AxonState`
- [ ] Add `should_continue` edge cases for youtube_agent → supervisor path

### 10F — Frontend (`features/youtube/`)

- [ ] `features/youtube/types.ts` — `VideoTranscriptOut` interface
- [ ] `features/youtube/hooks/useYouTube.ts` — `useTranscripts()`, `useDeleteTranscript()`
- [ ] `features/youtube/components/YouTubeTranscriptCard.tsx` — shows title, channel, summary, key points, collapsible full transcript
- [ ] `features/youtube/components/YouTubeLibrary.tsx` — list of saved transcripts with delete
- [ ] `app/(dashboard)/youtube/page.tsx` — page route, guarded by auth
- [ ] Nav link in `ChatWindow.tsx` header (e.g. `<Film />` icon → `/youtube`)
- [ ] `lib/api.ts` — `listYouTubeTranscripts()`, `getYouTubeTranscript(id)`, `deleteYouTubeTranscript(id)`

### Verification

- [ ] Paste YouTube URL in chat → supervisor routes to youtube_agent → transcript fetched + summary shown
- [ ] "Save this" → transcript saved to `video_transcripts` → confirmed in chat
- [ ] Navigate to `/youtube` → saved transcripts listed
- [ ] Delete transcript → removed from list
- [ ] Video with disabled captions → graceful error message in chat

---

## End-to-End Verification Checklist

- [ ] Google OAuth → JWT validated on `/api/v1/auth/me` → 200
- [ ] `GET /api/v1/models` → JSON list of OpenRouter models
- [ ] `POST /api/v1/chat/stream` → tokens stream in real time in chat UI
- [ ] Chat with memory context → orchestrator retrieves relevant memory via tool, response includes personal context
