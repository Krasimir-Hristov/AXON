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
- [ ] Verify: `uv run uvicorn app.main:app --reload` → `http://localhost:8000/docs` loads

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
- [ ] **Verify /docs:** POST memory → GET list → DELETE works
- [ ] **Verify:** Chat message referencing stored memory → orchestrator uses memory tool
- [ ] **Verify:** Upload PDF → multiple chunks created → searchable

---

## PHASE 5.5 — Backend Rate Limiting

> **Решение:** in-memory storage по подразбиране (без external dependency, работи перфектно при single-process). Redis се включва само ако зададеш `REDIS_URL` env var — нужен единствено при multiple workers или horizontal scaling. `slowapi` е вече в `pyproject.toml`.

- [x] `app/core/limiter.py` — `Limiter(key_func=_jwt_key)` singleton; `_jwt_key` декодира `sub` от Bearer token без пълна JWT верификация (верификацията е в `security.py`); fallback към `remote_address` за публичните routes
- [x] Register `RateLimitExceeded` → 429 handler в `app/main.py` с `Retry-After` header
- [x] Apply limits per route (decorator `@limiter.limit(...)`) — вижте таблицата по-долу
- [x] Env var `REDIS_URL` в `config.py` (optional, default None) — ако е зададен, `storage_uri=settings.redis_url`, иначе in-memory
- [ ] **Verify:** Hammer `/api/v1/chat/stream` → 429 след лимита с `Retry-After`

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
- [ ] **Verify:** "what do you know about me?" → trace shows `supervisor → memory_agent → supervisor`
- [ ] **Verify:** "write me a haiku" → supervisor responds directly (`supervisor → END`)

---

## PHASE 7 — Frontend Core & Auth

- [ ] `lib/supabase/client.ts` — `createBrowserClient` (`@supabase/ssr`)
- [ ] `lib/supabase/server.ts` — `createServerClient` with cookies
- [ ] `proxy.ts` — auth guard: redirect to `/login` if no session, redirect to `/chat` if already logged in
- [ ] `app/providers.tsx` — `QueryClientProvider` wrapper
- [ ] `app/layout.tsx` — root layout wrapping `providers.tsx`
- [ ] `features/auth/components/LoginButton.tsx` — Google OAuth trigger
- [ ] `app/(auth)/login/page.tsx` — login page
- [ ] `app/(auth)/callback/route.ts` — Supabase OAuth callback handler
- [ ] **Verify:** Google login → redirected to `/chat`

---

## PHASE 7 — Frontend Chat UI

- [ ] `features/chat/types.ts` — `Message`, `Conversation`, `ChatModel`
- [ ] `lib/api.ts` — typed fetch wrapper with Supabase JWT header injection + try/catch
- [ ] `features/chat/hooks/useChat.ts` — `fetch()` + `ReadableStream` + `eventsource-parser`, appends tokens to state
- [ ] `features/chat/hooks/useModels.ts` — TanStack Query for `GET /api/v1/models`
- [ ] `features/chat/components/ChatInput.tsx` — textarea + send button
- [ ] `features/chat/components/MessageBubble.tsx` — `react-markdown` + `remark-gfm`
- [ ] `features/chat/components/ModelSelector.tsx` — shadcn `<Select>` driven by `useModels`
- [ ] `features/chat/components/ChatWindow.tsx` — message list + auto-scroll
- [ ] `app/(dashboard)/chat/page.tsx` — assembles all components
- [ ] **Verify:** Send message → tokens stream in real time, model switching works

---

## PHASE 8 — Frontend Memory UI

- [ ] `features/memory/types.ts`
- [ ] `features/memory/hooks/useMemory.ts` — TanStack Query CRUD
- [ ] `features/memory/components/MemoryView.tsx` — list + delete
- [ ] `app/(dashboard)/memory/page.tsx`
- [ ] **Verify:** Entries from chat appear in the list; delete works

---

## End-to-End Verification Checklist

- [ ] Google OAuth → JWT validated on `/api/v1/auth/me` → 200
- [ ] `GET /api/v1/models` → JSON list of OpenRouter models
- [ ] `POST /api/v1/chat/stream` → tokens stream in real time in chat UI
- [ ] `POST /api/v1/memory` → DB stores masked version, UI shows decrypted original
- [ ] PII test: store "My name is John, call me at 555-1234" → DB shows `<PERSON>`, `<PHONE_NUMBER>`
- [ ] Chat with memory context → orchestrator retrieves relevant memory via tool, response includes personal context
