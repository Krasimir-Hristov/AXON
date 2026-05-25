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

## PHASE 10 — YouTube Transcript Workflow Subagent

> **Architecture decision log:**
>
> - LangGraph: No prebuilt YouTube workflow exists — existing manual supervisor pattern is correct.
> - OpenRouter: TTS models available via `openai/gpt-audio-mini` with `modalities: ["audio"]` — uses existing `OPENROUTER_API_KEY`, no separate OpenAI key needed.
> - Metadata fetching: `youtube-transcript-api` for transcript + YouTube oEmbed API for title/channel (no extra dep/key needed). Duration calculated from transcript timestamps.
> - Summarization: `youtube_agent` handles hierarchical chunked summarization internally via `settings.youtube_summary_model` (default: `google/gemini-2.5-flash` via OpenRouter — not the user's selected chat model). Supervisor receives only the final summary — never the raw transcript.
> - Save: summary is indexed in `memory_entries` (vector DB) so `memory_agent` can recall it in future. Full transcript stored in separate `video_transcripts` table.
> - TTS tool is a simple `@tool`, not a subagent — it's one I/O operation with no multi-step logic.
> - Cross-turn state ("ask before save"): youtube_agent returns a structured JSON payload inside the ToolMessage. On the next turn, supervisor reads the payload from conversation history and calls `save_video_transcript` — no Redis/cache needed.

### Overall flow

````text
User pastes YouTube URL
  → supervisor (pас 1, with tools) detects URL → calls transfer_to_youtube_agent
  → youtube_agent:
      1. Extract video_id via regex
      2. Fetch transcript (youtube-transcript-api) — handle errors
      3. Fetch title/channel via YouTube oEmbed (httpx, no API key)
      4. Calculate duration_s from transcript timestamps
      5. Hierarchical summarization: chunk transcript → parallel LLM calls → final summary
      6. Return ToolMessage with JSON payload {video_id, title, channel, duration_s, summary, key_points, youtube_url}
  → supervisor (пас 2, no tools): presents summary + key points, asks "Want me to save this?"

User: "yes save it"
  → supervisor (пас 1) reads JSON from prior ToolMessage → calls save_video_transcript()
  → save_video_transcript tool:

```sql
      INSERT into video_transcripts
      -- Also embed + INSERT summary into memory_entries (so memory_agent can recall it)
````

→ supervisor: "Saved ✓ — also indexed in your memory for future recall"

User: "generate audio of the summary"
→ supervisor calls generate_tts()
→ generate_tts tool: 1. POST to OpenRouter TTS API (`openai/gpt-audio-mini`, `modalities: ["audio"]`) 2. Receive base64 audio, decode to bytes 3. Upload to Supabase Storage bucket "audio" 4. Return {public_url, filename, duration_estimate}
→ supervisor: "Audio ready — [link]. Want me to save it to your library?"

User: "yes"
→ supervisor calls save_audio_entry()
→ save_audio_entry tool:

```sql
      INSERT into audio_entries table
```

→ supervisor: "Saved to your audio library ✓"

````

---

## PHASE 10A — YouTube Agent: Fetch + Hierarchical Summarize

> **Goal:** youtube_agent fetches transcript + metadata, summarizes with its own LLM, returns structured JSON to supervisor. No save yet.

### 10A-1 — Dependencies

- [x] `uv add youtube-transcript-api` — transcript fetching
- [x] No yt-dlp/pytube — oEmbed used for metadata instead

### 10A-2 — State extension (`app/agents/state.py`)

- [x] Add `youtube_context: str` field to `AxonState` — holds the JSON payload string from youtube_agent (empty string default); persists in LangGraph state for cross-turn save

### 10A-3 — Backend subagent (`app/agents/subagents/youtube_agent.py`)

- [x] `_extract_youtube_url(text: str) -> str | None` — regex for `youtube.com/watch?v=`, `youtu.be/`, shorts
- [x] `_fetch_oEmbed(video_id: str) -> dict` — GET `https://www.youtube.com/oembed?url=...&format=json` via `httpx.AsyncClient`; returns `{title, author_name}`
- [x] `_fetch_transcript(video_id: str) -> list[dict]` — `YouTubeTranscriptApi.get_transcript()` in `asyncio.to_thread`; raises descriptive error on `TranscriptsDisabled` / `NoTranscriptFound`
- [x] `_build_chunks(transcript: list[dict], chunk_tokens: int = 4000) -> list[str]` — group transcript entries into ~4000-token text chunks (estimate ~4 chars/token)
- [x] `_summarize_chunks(chunks: list[str], model: str) -> list[str]` — `asyncio.gather` over chunks; each chunk → LLM call with "Summarize this section of a video transcript in 3-5 sentences"
- [x] `_final_summary(chunk_summaries: list[str], title: str, model: str) -> tuple[str, list[str]]` — combine chunk summaries → LLM call → `(final_summary_text, key_points_list)`
- [x] `youtube_agent_node(state: AxonState) -> dict`:
  - Extract URL from last `HumanMessage`
  - Fetch transcript + oEmbed in parallel (`asyncio.gather`)
  - Calculate `duration_s` from last transcript entry's `start + duration`
  - Run hierarchical summarization — use hardcoded `google/gemini-2.5-flash` (fast, large context) via OpenRouter for chunk summarization; configurable via `settings.youtube_summary_model`
  - Build JSON payload: `{video_id, youtube_url, title, channel, duration_s, summary, key_points}`
  - Store payload in `state["youtube_context"]`
  - Return `ToolMessage` (closes handoff tool call) + `youtube_context` state update

### 10A-4 — Supervisor wiring (`app/agents/supervisor.py` + `orchestrator.py`)

- [x] Add `transfer_to_youtube_agent` handoff `@tool` (same pattern as `transfer_to_memory_agent`)
- [x] Add to supervisor's `bind_tools` list alongside `transfer_to_memory_agent`
- [x] Supervisor system prompt addition: detect YouTube URL → MUST call `transfer_to_youtube_agent`; do not attempt to summarise a URL directly; after receiving ToolMessage with video data, present summary + key points and ask "Want me to save this?"
- [x] `orchestrator.py`: add `youtube_agent` node, extend `_should_continue` to route `transfer_to_youtube_agent` → `"youtube_agent"`; add edge `youtube_agent → supervisor`
- [x] `app/core/config.py`: add `youtube_summary_model: str = "google/gemini-2.5-flash"` setting

### 10A-5 — Verification

- [ ] Paste short YouTube URL (< 10 min) → supervisor routes → youtube_agent fetches + summarizes → supervisor presents summary + key points
- [ ] Paste 1h+ video → hierarchical chunking kicks in → summary still fits in context
- [ ] Video with disabled captions → graceful error message in chat
- [ ] Non-YouTube message → supervisor does NOT call youtube_agent

---

## PHASE 10B — Save Transcript (ask → confirm → save)

> **Goal:** On user confirmation, save transcript to `video_transcripts` table AND index summary in `memory_entries` vector DB for future recall.

### 10B-1 — Database (`supabase/migrations/`)

- [x] New migration: create `video_transcripts` table:
  ```sql
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  youtube_url text NOT NULL,
  video_id    text NOT NULL UNIQUE,
  title       text,
  channel     text,
  duration_s  integer,
  summary     text NOT NULL,
  key_points  jsonb DEFAULT '[]',   -- string[]
  created_at  timestamptz DEFAULT now()
````

- [x] RLS: `user_id = auth.uid()` on SELECT / INSERT / DELETE
- [x] Index on `(user_id, created_at DESC)`

### 10B-2 — Backend feature layer (`app/features/youtube/`)

- [x] `__init__.py`
- [x] `schemas.py` — `VideoTranscriptOut(id, youtube_url, video_id, title, channel, duration_s, summary, key_points, created_at)`
- [x] `service.py`:
  - `save_transcript(user_id, payload: dict) -> VideoTranscriptOut` — INSERT into `video_transcripts`; also calls `memory_service.add_memory(user_id, text=f"[YouTube] {title}: {summary}")` to index in vector DB
  - `list_transcripts(user_id) -> list[VideoTranscriptOut]`
  - `get_transcript(id, user_id) -> VideoTranscriptOut` — raises 404 if not owned
  - `delete_transcript(id, user_id) -> bool` — also deletes the corresponding `memory_entries` row (match by source tag)
- [x] `router.py`:
  - `GET  /api/v1/youtube` — list saved transcripts (newest first); protected; rate limit 60/min
  - `GET  /api/v1/youtube/{id}` — full transcript detail; protected
  - `DELETE /api/v1/youtube/{id}` — 204; protected; rate limit 30/min

### 10B-3 — Save tool (`app/features/youtube/tool.py`)

- [x] `save_transcript_node` LangGraph node (`app/features/youtube/tool.py`):
  - Reads `state["youtube_context"]` — parse JSON payload
  - Validates payload has required fields (raises if `youtube_context` is empty)
  - Calls `youtube_service.save_transcript(user_id, payload)`
  - Returns confirmation string with title + saved id
- [x] Wire `save_video_transcript` handoff tool into supervisor's `bind_tools` list
- [x] Supervisor system prompt: when user confirms save ("yes", "save it", "запази") and prior assistant YouTube summary exists → call `save_video_transcript`; do not call `transfer_to_youtube_agent` again
- [x] Rate limits on GET (60/min) and DELETE (30/min) REST endpoints

### 10B-4 — Mount router in `app/main.py`

- [x] Import and mount youtube router

### 10B-5 — Verification

- [ ] After youtube summary shown: "save it" → `save_video_transcript` tool called → confirmation in chat
- [ ] `GET /api/v1/youtube` → saved transcript in list
- [ ] `memory_agent` can now recall video: "what was that video about X?" → memory search returns video summary
- [ ] "no" / ignore → transcript NOT saved
- [ ] `DELETE /api/v1/youtube/{id}` → 204 + memory entry removed

---

## PHASE 10C — TTS Generation

> **Goal:** Supervisor can call `generate_tts` tool on any text (usually the video summary). Uses OpenAI TTS API directly (NOT via OpenRouter — TTS models are unavailable on OpenRouter). Returns audio bytes uploaded to Supabase Storage `audio` bucket.

### 10C-1 — OpenRouter TTS research finding

> OpenRouter **does** offer audio output models via the standard chat completions endpoint (`/api/v1/chat/completions`) with `"modalities": ["audio"]`.
> Available models (confirmed active):
>
> - `openai/gpt-audio-mini` — $0.60/$2.40 per M tokens — **default choice** (fast, cost-efficient)
> - `openai/gpt-audio` — $2.50/$10 per M tokens — higher quality option
>
> These use the existing `OPENROUTER_API_KEY` — **no separate `OPENAI_API_KEY` needed**.
> API request format: chat completions with `modalities: ["text", "audio"]` + `audio: {voice, format}`.
> Response: audio returned as **base64-encoded mp3** in `choices[0].message.audio.data`.
> Default voice: `alloy`. Configurable via `settings.tts_voice`.
> Output format: `mp3` — universal browser support.

### 10C-2 — Config (`app/core/config.py`)

- [x] Add `tts_model: str = "openai/gpt-4o-mini-tts-2025-12-15"` — uses OpenRouter `/audio/speech` endpoint (not chat completions); correct model confirmed via direct API test
- [x] Add `tts_voice: str = "alloy"` — alloy / echo / fable / onyx / nova / shimmer
- [x] Add `audio_bucket: str = "audio"` — Supabase Storage bucket name

### 10C-3 — Supabase Storage setup

- [x] Create `audio` bucket in Supabase (private, not public) via migration `20260512100000_create_audio_bucket_and_policies.sql`
- [x] Bucket RLS policies: INSERT/SELECT/DELETE for authenticated users scoped to `{user_id}/*`; predicates use `(select auth.uid())` subquery form (avoids per-row re-evaluation)

### 10C-4 — TTS service (`app/features/audio/service.py`)

- [x] `generate_tts(text: str, user_id: str) -> tuple[bytes, str]`:
  - Masks PII via `mask_pii(text)` before forwarding to external API
  - POST to OpenRouter `/api/v1/audio/speech` (not chat completions)
  - Body: `{"model": settings.tts_model, "input": masked_text, "voice": settings.tts_voice, "response_format": "mp3"}`
  - Response: raw MP3 bytes (not base64 JSON) — validated via `Content-Type: audio/*` or MP3 magic bytes (`ID3` / `0xFF` sync word)
  - Error handling: `httpx.HTTPStatusError` + `httpx.RequestError` caught, logged without PII, re-raised as `RuntimeError`
  - Returns `(audio_bytes, filename)` where `filename = f"{user_id}/{uuid4()}.mp3"`; UUID logged only (never user_id)
- [x] `upload_audio(audio_bytes: bytes, filename: str) -> str`:
  - Upload to Supabase Storage `audio` bucket
  - Returns signed URL (7-day expiry); logs only UUID basename (never full path)
- [x] Text length guard: max 4096 chars; truncate with warning log if exceeded

### 10C-5 — Generate TTS tool (`app/features/audio/tool.py`)

- [x] `generate_tts_node(state: AxonState) -> dict` — LangGraph node (not `@tool`-executed; invoked directly by orchestrator, same pattern as `save_transcript_node`):
  - Reads `text` arg from supervisor's `generate_tts` tool_call in last AIMessage
  - Calls `audio_service.generate_tts` + `audio_service.upload_audio`
  - Stores `{filename, signed_url, text_preview}` JSON in `state["pending_audio"]`
  - Returns `ToolMessage` with markdown `[Play audio](signed_url)` link + save prompt
- [x] `generate_tts` stub `@tool` bound to supervisor (`bind_tools`); body never executes
- [x] Supervisor system prompt: when user asks for audio/TTS → call `generate_tts(text=<text>)`; present signed URL as clickable link; ask "Want me to save this?"
- [x] Frontend `MessageBubble.tsx`: custom `<a>` renderer — if href ends with `.mp3`, renders inline `<audio controls src={href}>` player
- [x] Frontend `ChatWindow.tsx`: purple animated `Volume2` icon shown during `Generating audio…` tool_use SSE event

### 10C-6 — State extension

- [x] Add `pending_audio: str` to `AxonState` — JSON string with `{filename, signed_url, text_preview}` for Phase 10D cross-turn save confirmation

### 10C-7 — Verification

- [x] "Generate audio of the summary" → `generate_tts` called → signed URL returned in chat → inline audio player rendered → audio playable
- [x] Text > 4096 chars → truncated with warning, audio still generated
- [x] Invalid/empty text → tool returns descriptive error message
- [x] DeepSeek text-format tool call bug fixed: regex post-processing in `supervisor_node` converts plain-text tool calls to structured `tool_calls` before returning

---

## PHASE 10D — Audio Library (save + browse + delete)

> **Goal:** On user confirmation, save audio entry to `audio_entries` table. Frontend: dedicated `/audio` page to browse, play, and delete saved audio files.

### 10D-1 — Database (`supabase/migrations/`)

- [x] New migration: create `audio_entries` table:
  ```sql
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  filename      text NOT NULL,          -- path in storage: {user_id}/{uuid}.mp3
  title         text NOT NULL,          -- user-facing label (video title or custom)
  source_type   text DEFAULT 'youtube', -- 'youtube' | 'custom'
  source_id     uuid REFERENCES video_transcripts(id) ON DELETE SET NULL,
  duration_s    integer,                -- estimated from text length
  created_at    timestamptz DEFAULT now()
  ```
- [x] RLS: `user_id = auth.uid()` on SELECT / INSERT / DELETE
- [x] Index on `(user_id, created_at DESC)`

### 10D-2 — Backend feature layer (`app/features/audio/`)

- [x] `__init__.py`
- [x] `schemas.py` — `AudioEntryOut(id, filename, title, source_type, source_id, duration_s, created_at, signed_url)`
- [x] `service.py` additions:
  - [x] `save_audio_entry(user_id, filename, title, source_type, source_id) -> AudioEntryOut`
  - [x] `list_audio_entries(user_id) -> list[AudioEntryOut]` — for each entry, generate fresh signed URL (1 week)
  - [x] `delete_audio_entry(id, user_id) -> bool` — DELETE from table + `storage.remove([filename])`
- [x] `router.py`:
  - [x] `GET  /api/v1/audio` — list saved audio (newest first); protected; rate limit 60/min
  - [x] `DELETE /api/v1/audio/{id}` — 204 + deletes from Storage; protected; rate limit 30/min

### 10D-3 — Save audio tool (`app/features/audio/tool.py` addition)

- [x] `save_audio_entry_node` LangGraph node — reads `pending_audio`, calls service, returns ToolMessage
- [x] `save_audio_entry` stub `@tool` bound to supervisor (`bind_tools`)
- [x] Supervisor system prompt: when user confirms save of audio → call `save_audio_entry(title=<video_title_or_user_provided>)`

### 10D-4 — Mount router in `app/main.py`

- [x] Import and mount audio router

### 10D-5 — Frontend Audio Library (`features/audio/`)

- [x] `features/audio/types.ts` — `AudioEntryOut` interface
- [x] `features/audio/hooks/useAudio.ts` — `useAudioEntries()` (TanStack Query, stale 60s), `useDeleteAudio()` mutation
- [x] `features/audio/components/AudioCard.tsx` — shows title, date; HTML5 `<audio>` player with signed URL; delete button (inline confirm)
- [x] `features/audio/components/AudioLibrary.tsx` — grid of `AudioCard`s; loading skeleton; empty state
- [x] `app/(dashboard)/audio/page.tsx` — page route, guarded by auth
- [x] Nav link in `ChatWindow.tsx` header (`<Headphones />` icon → `/audio`)
- [x] `lib/api.ts` — `listAudioEntries()`, `deleteAudioEntry(id)`

### 10D-6 — Verification

- [ ] "Save the audio" → `save_audio_entry` called → confirmation in chat
- [ ] Navigate to `/audio` → saved entries listed with player
- [ ] `<audio>` element plays correctly from signed URL
- [ ] Delete audio → removed from list + deleted from Supabase Storage
- [ ] Signed URL expiry: after 1 week, `list_audio_entries` regenerates fresh URLs on each fetch

---

## PHASE 11 — Deep Search Agent

> **Architecture decision log:**
>
> - **Search provider:** Tavily API — purpose-built for LLM/agent workflows; `search_depth="advanced"` returns full page content (not just snippets), structured results, and optionally a pre-generated answer. Free tier: 1 000 searches/month. Uses its own `TAVILY_API_KEY` — existing `OPENROUTER_API_KEY` unchanged.
> - **Agent pattern:** Same supervisor handoff as YouTube — `transfer_to_deepsearch_agent` → `deepsearch_agent_node` → supervisor. No new graph topology needed.
> - **Save flow:** After presenting results, supervisor asks "Want to save this research?" → user confirms → `save_deep_search` tool node → INSERT into `deep_searches` table + embed `query + summary` → INSERT into `memory_entries` (so memory_agent can recall it in future conversations).
> - **Delete:** Must remove from BOTH `deep_searches` table AND the corresponding `memory_entries` row. `memory_entry_id` FK stored directly in the row (cleaner than pattern-matching).
> - **Edit:** `title` change — free (no re-embed). `summary` change — re-embed → update `memory_entries.embedding` in place.

### Overall flow

```text
User: "deep search quantum computing breakthroughs 2025"
  → supervisor detects research intent → calls transfer_to_deepsearch_agent
  → deepsearch_agent:
      1. Extract query from last HumanMessage
      2. TavilyClient.search(query, search_depth="advanced", max_results=10) via asyncio.to_thread
      3. Build synthesis context (each result capped at 2000 chars, total 20 000)
      4. LLM call → synthesize summary + key_findings: list[str]
      5. Build sources: [{title, url, snippet: content[:300]}]
      6. Store JSON in state["deepsearch_context"]; return ToolMessage
  → supervisor: presents summary + key findings + numbered source list
                asks "Want me to save this research?"

User: "yes"
  → supervisor calls save_deep_search()
  → save_deep_search node:
      INSERT deep_searches; embed(query + "\n\n" + summary) → INSERT memory_entries
      UPDATE deep_searches.memory_entry_id = <new_id>
  → supervisor: "Research saved ✓ — also indexed in your memory for future recall"

User later: "what did I find about quantum computing?"
  → memory_agent → vector search → returns saved summary
```

---

### 11A — Dependencies + Config

- [ ] `uv add tavily-python` — official Tavily Python client
- [ ] `app/core/config.py`: add `tavily_api_key: str` + `deepsearch_model: str = "google/gemini-2.5-flash"` + `deepsearch_max_results: int = 10`
- [ ] `backend/.env.example`: add `TAVILY_API_KEY=`

### 11B — Database (`supabase/migrations/`)

- [ ] New migration: create `deep_searches` table:
  ```sql
  CREATE TABLE public.deep_searches (
      id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id          UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
      query            TEXT        NOT NULL,
      title            TEXT        NOT NULL,          -- editable; defaults to query
      summary          TEXT        NOT NULL,          -- AI-synthesized answer
      key_findings     JSONB       NOT NULL DEFAULT '[]', -- string[]
      sources          JSONB       NOT NULL DEFAULT '[]', -- [{title, url, snippet}]
      memory_entry_id  UUID        REFERENCES memory_entries(id) ON DELETE SET NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE INDEX deep_searches_user_created_idx
      ON public.deep_searches (user_id, created_at DESC);
  ```
- [ ] RLS: `user_id = (select auth.uid())` on SELECT / INSERT / DELETE / UPDATE — subquery form (same pattern as all other tables)
- [ ] `memory_entry_id ON DELETE SET NULL` — deep search row survives if memory entry is independently cleaned up

### 11C — Backend feature layer (`app/features/deepsearch/`)

- [ ] `__init__.py`
- [ ] `schemas.py`: `SourceItem(title, url, snippet)` · `DeepSearchOut(id, query, title, summary, key_findings, sources, created_at)` · `DeepSearchCreate(query, title: str = Field(..., max_length=200), summary: str = Field(..., max_length=10000), key_findings, sources)` · `DeepSearchPatch(title: str | None = Field(None, max_length=200), summary: str | None = Field(None, max_length=10000))` with `model_validator` requiring at least one field; service layer must accept these schemas for create/update so direct API calls cannot bypass the limits
- [ ] `service.py`:
  - `save_deep_search(user_id, payload: dict) -> DeepSearchOut` — INSERT row; attempt embed `f"[Deep Search] {query}: {summary}"` → INSERT `memory_entries` → UPDATE row with `memory_entry_id`; if embedding or `memory_entries` INSERT fails, log the error with context (deep_search id, query, exception) and continue with `memory_entry_id = NULL` (non-fatal, same resilience pattern as YouTube)
  - `list_deep_searches(user_id, limit=50, offset=0) -> list[DeepSearchOut]` — ordered by `created_at DESC`
  - `get_deep_search(id, user_id) -> DeepSearchOut | None`
  - `delete_deep_search(id, user_id) -> bool` — fetch `memory_entry_id` → `delete_memory()` if set → DELETE row
  - `update_deep_search(id, user_id, patch) -> DeepSearchOut | None` — if `summary` changed: re-embed → update `memory_entries.embedding`; if `memory_entry_id` is NULL attempt to create a new memory entry and set it; if that fails log and keep the row updated without `memory_entry_id`; UPDATE row; all log messages must reference `update_deep_search` and include `memory_entry_id` context
- [ ] `router.py`:
  - `GET    /api/v1/deepsearch` — list paginated; `@limiter.limit("60/minute")`
  - `GET    /api/v1/deepsearch/{id}` — single; `@limiter.limit("60/minute")`
  - `DELETE /api/v1/deepsearch/{id}` — 204; `@limiter.limit("30/minute")`
  - `PATCH  /api/v1/deepsearch/{id}` — edit title/summary; `@limiter.limit("30/minute")`

### 11D — Agent subagent (`app/agents/subagents/deepsearch_agent.py`)

- [ ] `deepsearch_agent_node(state: AxonState) -> dict`:
  1. Extract query from last `HumanMessage` (strip intent phrases: "deep search", "research", "find out about")
  2. `asyncio.to_thread(TavilyClient(api_key=settings.tavily_api_key).search, query, search_depth="advanced", max_results=settings.deepsearch_max_results)`
  3. Build synthesis context: each result capped at 2 000 chars; total cap 20 000 chars
  4. LLM call (`settings.deepsearch_model` via OpenRouter) → `summary` + `key_findings: list[str]`
  5. Build `sources`: `[{title, url, snippet: content[:300]}]`
  6. Validate with Pydantic `DeepSearchPayload`; fallback to raw concat on parse error
  7. Store JSON in `state["deepsearch_context"]`; return ToolMessage closing handoff tool call
- [ ] Error handling:
  - `TavilyAPIError` / network errors → log internally, return descriptive error ToolMessage; never expose raw API errors or tracebacks
  - LLM synthesis call (`settings.deepsearch_model` via OpenRouter): wrap in `try/except`; catch timeouts, rate-limit errors, and HTTP errors; apply exponential backoff with 2 retries; on persistent failure return a descriptive error ToolMessage without raw exception details
  - Malformed/unparseable LLM response (including `JSONDecodeError`): log internally; fall back to raw concatenation strategy (step 6) instead of crashing
  - All internal exceptions must be logged with context (query, model) but must NOT be leaked to the returned ToolMessage

### 11E — Save tool (`app/features/deepsearch/tool.py`)

- [ ] `save_deep_search_node(state: AxonState) -> dict` — LangGraph node (same pattern as `save_transcript_node`):
  - Read + parse `state["deepsearch_context"]`; validate required fields
  - Call `deepsearch_service.save_deep_search(user_id, payload)`
  - Return confirmation ToolMessage; clear `state["deepsearch_context"]`
- [ ] `save_deep_search` stub `@tool` (body never executes)

### 11F — State + Supervisor + Orchestrator wiring

- [ ] `app/agents/state.py`: add `deepsearch_context: str` (empty string default)
- [ ] `app/agents/supervisor.py`:
  - Add `transfer_to_deepsearch_agent` + `save_deep_search` stubs to `bind_tools`
  - System prompt: trigger phrases → `transfer_to_deepsearch_agent`; after ToolMessage present summary + ask to save; on confirmation call `save_deep_search`; do NOT re-call agent if `deepsearch_context` already populated
- [ ] `app/agents/orchestrator.py`: add `deepsearch_agent` node + `save_deep_search_node`; extend `_should_continue` routing; add edge `deepsearch_agent → supervisor`
- [ ] Mount deepsearch router in `app/main.py`

### 11G — Frontend Deep Search Library (`features/deepsearch/`)

- [ ] `features/deepsearch/types.ts` — `SourceItem`, `DeepSearchOut`
- [ ] `features/deepsearch/hooks/useDeepSearch.ts` — `useDeepSearches()` (user-scoped key `['deep-searches', userId]`) · `useDeleteDeepSearch()` · `useUpdateDeepSearch()` (optimistic title)
- [ ] `features/deepsearch/components/DeepSearchCard.tsx`:
  - Inline-editable title (`useOptimistic` — same pattern as `AudioCard`)
  - Summary: `line-clamp-4` + expand/collapse (same pattern as `VideoTranscriptCard`)
  - Summary edit mode: click → textarea → Save/Cancel → `useUpdateDeepSearch` (re-embed server-side on summary change)
  - Key findings: bullet list, first 4 visible + expand
  - Sources: collapsed accordion ("N sources") → numbered `<a target="_blank">` links
  - Delete dialog: warns that the linked memory entry will also be removed
- [ ] `features/deepsearch/components/DeepSearchLibrary.tsx` — grid, skeleton, empty state
- [ ] `app/(dashboard)/deepsearch/page.tsx` — back-to-chat header
- [ ] `features/chat/components/ChatWindow.tsx` — add `Search` icon link to `/deepsearch` in toolbar
- [ ] `lib/api.ts`: `listDeepSearches()` · `deleteDeepSearch(id)` (Zod UUID) · `updateDeepSearch(id, patch)` (Zod: title max 200, summary max 10 000, at least one field)

### 11H — Verification

- [ ] "deep search latest AI models 2025" → deepsearch_agent calls Tavily → summary + key findings + sources in chat
- [ ] "yes save it" → `save_deep_search` called → entry visible in `GET /api/v1/deepsearch`
- [ ] `/deepsearch` page → cards with summary, findings, collapsible source links
- [ ] Edit title → optimistic update → persisted
- [ ] Edit summary → `PATCH` → re-embed triggered → memory_agent finds updated content in future chat
- [ ] Delete → row removed from `deep_searches` + `memory_entries` → UI updates
- [ ] Future chat "what did I research?" → memory_agent returns saved summary
- [ ] Tavily 429/down → graceful error message, no crash
- [ ] `PATCH` with empty body → 422

---

## End-to-End Verification Checklist

- [ ] Google OAuth → JWT validated on `/api/v1/auth/me` → 200
- [ ] `GET /api/v1/models` → JSON list of OpenRouter models
- [ ] `POST /api/v1/chat/stream` → tokens stream in real time in chat UI
- [ ] Chat with memory context → orchestrator retrieves relevant memory via tool, response includes personal context
