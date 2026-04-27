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

- [ ] `app/agents/state.py` — `AxonState(TypedDict)`: `messages`, `user_id`, `model_id`, `memory_context`
- [ ] `app/db/supabase.py` — async Supabase client singleton (`get_supabase_client()`)
- [ ] `app/agents/orchestrator.py` — minimal LangGraph graph: single node calling OpenRouter via `httpx.AsyncClient`

---

## PHASE 4 — Backend Chat (SSE Streaming)

- [ ] `app/features/chat/schemas.py` — `ChatRequest(message, model_id, conversation_id?)` + `SSEEvent`
- [ ] `app/features/chat/service.py` — calls `orchestrator.graph.astream_events(version="v2")`, yields SSE tokens
- [ ] `app/features/chat/router.py` — `POST /api/v1/chat/stream` → `StreamingResponse(media_type="text/event-stream")`, protected
- [ ] Mount chat router in `main.py`
- [ ] **Verify /docs:** POST with JWT → see streamed `{"type":"token","content":"..."}` in response

---

## PHASE 5 — Backend Memory + RAG

- [ ] `app/core/privacy.py` — `mask_pii(text: str) -> str` using Presidio + `en_core_web_sm`
- [ ] `app/db/embeddings.py` — `embed_text()` (OpenAI API), `upsert_memory()`, `search_memory()` (pgvector `<=>`)
- [ ] `app/features/memory/schemas.py` — `MemoryCreate`, `MemoryEntry`, `MemorySearchRequest`
- [ ] `app/features/memory/service.py` — pipeline: mask → embed → store (AES-256 encrypt original); decrypt on retrieval
- [ ] `app/features/memory/router.py` — `POST /api/v1/memory`, `GET /api/v1/memory`, `DELETE /api/v1/memory/{id}` (all protected)
- [ ] `app/features/memory/tool.py` — `@tool async def search_memory(query: str) -> str`
- [ ] Wire `search_memory` tool into `orchestrator.py` via `ToolNode`
- [ ] **Verify /docs:** POST memory → GET list → DELETE works
- [ ] **Verify:** Chat message referencing stored memory → orchestrator uses memory tool

---

## PHASE 6 — Frontend Core & Auth

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
