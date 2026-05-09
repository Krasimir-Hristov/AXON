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

```text
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
```

  → supervisor: "Saved ✓ — also indexed in your memory for future recall"

User: "generate audio of the summary"
  → supervisor calls generate_tts()
  → generate_tts tool:
      1. POST to OpenRouter TTS API (`openai/gpt-audio-mini`, `modalities: ["audio"]`)
      2. Receive base64 audio, decode to bytes
      3. Upload to Supabase Storage bucket "audio"
      4. Return {public_url, filename, duration_estimate}
  → supervisor: "Audio ready — [link]. Want me to save it to your library?"

User: "yes"
  → supervisor calls save_audio_entry()
  → save_audio_entry tool:

```sql
      INSERT into audio_entries table
```

  → supervisor: "Saved to your audio library ✓"
```

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

- [ ] New migration: create `video_transcripts` table:
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
  ```
- [ ] RLS: `user_id = auth.uid()` on SELECT / INSERT / DELETE
- [ ] Index on `(user_id, created_at DESC)`

### 10B-2 — Backend feature layer (`app/features/youtube/`)

- [ ] `__init__.py`
- [ ] `schemas.py` — `VideoTranscriptOut(id, youtube_url, video_id, title, channel, duration_s, summary, key_points, created_at)`
- [ ] `service.py`:
  - `save_transcript(user_id, payload: dict) -> VideoTranscriptOut` — INSERT into `video_transcripts`; also calls `memory_service.add_memory(user_id, text=f"[YouTube] {title}: {summary}")` to index in vector DB
  - `list_transcripts(user_id) -> list[VideoTranscriptOut]`
  - `get_transcript(id, user_id) -> VideoTranscriptOut` — raises 404 if not owned
  - `delete_transcript(id, user_id) -> bool` — also deletes the corresponding `memory_entries` row (match by source tag)
- [ ] `router.py`:
  - `GET  /api/v1/youtube` — list saved transcripts (newest first); protected; rate limit 60/min
  - `GET  /api/v1/youtube/{id}` — full transcript detail; protected
  - `DELETE /api/v1/youtube/{id}` — 204; protected; rate limit 30/min

### 10B-3 — Save tool (`app/features/youtube/tool.py`)

- [ ] `@tool async def save_video_transcript(state: AxonState) -> str`:
  - Reads `state["youtube_context"]` — parse JSON payload
  - Validates payload has required fields (raises if `youtube_context` is empty)
  - Calls `youtube_service.save_transcript(user_id, payload)`
  - Returns confirmation string with title + saved id
- [ ] Wire tool into supervisor's `bind_tools` list
- [ ] Supervisor system prompt: when user confirms save ("yes", "save it", "запази") and `youtube_context` is non-empty → call `save_video_transcript`; do not call `transfer_to_youtube_agent` again
- [ ] Rate limit `POST /api/v1/youtube` (if REST needed) — 10/minute

### 10B-4 — Mount router in `app/main.py`

- [ ] Import and mount youtube router

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

- [ ] Add `tts_model: str = "openai/gpt-audio-mini"` — configurable; `openai/gpt-audio` for higher quality
- [ ] Add `tts_voice: str = "alloy"` — alloy / echo / fable / onyx / nova / shimmer
- [ ] Add `audio_bucket: str = "audio"` — Supabase Storage bucket name

### 10C-3 — Supabase Storage setup

- [ ] Create `audio` bucket in Supabase (private, not public)
- [ ] Bucket policy: authenticated users can INSERT their own files; SELECT only their own; path pattern `{user_id}/*`

### 10C-4 — TTS service (`app/features/audio/service.py`)

- [ ] `generate_tts(text: str, user_id: str) -> tuple[bytes, str]`:
  - POST to OpenRouter `/api/v1/chat/completions` via existing `httpx.AsyncClient`
  - Body: `{"model": settings.tts_model, "modalities": ["text", "audio"], "audio": {"voice": settings.tts_voice, "format": "mp3"}, "messages": [{"role": "user", "content": text}]}`
  - Header: `Authorization: Bearer {settings.openrouter_api_key}` (same key as LLM calls)
  - Decode `choices[0].message.audio.data` (base64) → raw mp3 bytes
  - Returns `(audio_bytes, filename)` where `filename = f"{user_id}/{uuid4()}.mp3"`
- [ ] `upload_audio(audio_bytes: bytes, filename: str) -> str`:
  - Upload to Supabase Storage `audio` bucket
  - Returns signed URL (1 week expiry) via `storage.create_signed_url(bucket, filename, 604800)`
- [ ] Text length guard: max 4096 chars (OpenAI TTS limit); truncate with warning log if exceeded

### 10C-5 — Generate TTS tool (`app/features/audio/tool.py`)

- [ ] `@tool async def generate_tts(text: str, state: AxonState) -> str`:
  - Calls `audio_service.generate_tts(text, state["user_id"])`
  - Calls `audio_service.upload_audio(bytes, filename)`
  - Stores `{filename, signed_url, text_preview}` JSON in `state["pending_audio"]`
  - Returns markdown string with signed URL for supervisor to present to user
- [ ] Wire tool into supervisor's `bind_tools` list
- [ ] Supervisor system prompt: when user asks for audio/TTS of summary or any text → call `generate_tts(text=<summary_or_requested_text>)`; present the signed URL as a clickable link; ask "Want me to save this to your audio library?"

### 10C-6 — State extension

- [ ] Add `pending_audio: str` to `AxonState` — JSON string with `{filename, signed_url, title}` for cross-turn save confirmation

### 10C-7 — Verification

- [ ] "Generate audio of the summary" → `generate_tts` called → signed URL returned in chat → audio playable
- [ ] Text > 4096 chars → truncated with warning, audio still generated
- [ ] Invalid/empty text → tool returns descriptive error message

---

## PHASE 10D — Audio Library (save + browse + delete)

> **Goal:** On user confirmation, save audio entry to `audio_entries` table. Frontend: dedicated `/audio` page to browse, play, and delete saved audio files.

### 10D-1 — Database (`supabase/migrations/`)

- [ ] New migration: create `audio_entries` table:
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
- [ ] RLS: `user_id = auth.uid()` on SELECT / INSERT / DELETE
- [ ] Index on `(user_id, created_at DESC)`

### 10D-2 — Backend feature layer (`app/features/audio/`)

- [ ] `__init__.py`
- [ ] `schemas.py` — `AudioEntryOut(id, filename, title, source_type, source_id, duration_s, created_at, signed_url)`
- [ ] `service.py` additions:
  - `save_audio_entry(user_id, filename, title, source_type, source_id) -> AudioEntryOut`
  - `list_audio_entries(user_id) -> list[AudioEntryOut]` — for each entry, generate fresh signed URL (1 week)
  - `delete_audio_entry(id, user_id) -> bool` — DELETE from table + `storage.remove([filename])`
- [ ] `router.py`:
  - `GET  /api/v1/audio` — list saved audio (newest first); protected; rate limit 60/min
  - `DELETE /api/v1/audio/{id}` — 204 + deletes from Storage; protected; rate limit 30/min

### 10D-3 — Save audio tool (`app/features/audio/tool.py` addition)

- [ ] `@tool async def save_audio_entry(title: str, state: AxonState) -> str`:
  - Reads `state["pending_audio"]` — parse JSON
  - Calls `audio_service.save_audio_entry(user_id, filename, title, ...)`
  - Returns confirmation with title
- [ ] Wire tool into supervisor's `bind_tools` list
- [ ] Supervisor system prompt: when user confirms save of audio → call `save_audio_entry(title=<video_title_or_user_provided>)`

### 10D-4 — Mount router in `app/main.py`

- [ ] Import and mount audio router

### 10D-5 — Frontend Audio Library (`features/audio/`)

- [ ] `features/audio/types.ts` — `AudioEntryOut` interface
- [ ] `features/audio/hooks/useAudio.ts` — `useAudioEntries()` (TanStack Query, stale 60s), `useDeleteAudio()` mutation
- [ ] `features/audio/components/AudioCard.tsx` — shows title, date, duration estimate; HTML5 `<audio>` player with signed URL; delete button (inline confirm)
- [ ] `features/audio/components/AudioLibrary.tsx` — grid/list of `AudioCard`s; loading skeleton; empty state
- [ ] `app/(dashboard)/audio/page.tsx` — page route, guarded by auth
- [ ] Nav link in `ChatWindow.tsx` header (`<Headphones />` icon → `/audio`)
- [ ] `lib/api.ts` — `listAudioEntries()`, `deleteAudioEntry(id)`

### 10D-6 — Verification

- [ ] "Save the audio" → `save_audio_entry` called → confirmation in chat
- [ ] Navigate to `/audio` → saved entries listed with player
- [ ] `<audio>` element plays correctly from signed URL
- [ ] Delete audio → removed from list + deleted from Supabase Storage
- [ ] Signed URL expiry: after 1 week, `list_audio_entries` regenerates fresh URLs on each fetch

---

## End-to-End Verification Checklist

- [ ] Google OAuth → JWT validated on `/api/v1/auth/me` → 200
- [ ] `GET /api/v1/models` → JSON list of OpenRouter models
- [ ] `POST /api/v1/chat/stream` → tokens stream in real time in chat UI
- [ ] Chat with memory context → orchestrator retrieves relevant memory via tool, response includes personal context
