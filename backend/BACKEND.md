# AXON Backend — Architecture Overview

## Stack

| Layer            | Technology                                 |
| ---------------- | ------------------------------------------ |
| Web framework    | FastAPI (async)                            |
| AI graph         | LangGraph (supervisor pattern)             |
| LLM / Embeddings | OpenRouter (OpenAI-compatible API)         |
| Database         | Supabase (PostgreSQL + pgvector)           |
| Authentication   | Supabase JWT (HS256)                       |
| Encryption       | Fernet (AES-128-CBC + HMAC-SHA256)         |
| PII masking      | Microsoft Presidio + spaCy                 |
| Rate limiting    | SlowAPI (per-user JWT key, optional Redis) |

---

## Directory Structure

```
backend/app/
├── main.py                  # FastAPI app, middleware, router mounts
├── core/
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── security.py          # JWT validation → get_current_user dependency
│   ├── crypto.py            # Fernet encrypt/decrypt
│   ├── privacy.py           # PII masking (Presidio)
│   └── limiter.py           # SlowAPI limiter singleton
├── db/
│   ├── supabase.py          # AsyncClient singleton
│   └── embeddings.py        # embed_text(s), insert/list/delete/match_memories
├── agents/
│   ├── state.py             # AxonState TypedDict
│   ├── orchestrator.py      # LangGraph StateGraph (compiled singleton)
│   ├── supervisor.py        # Supervisor node + handoff tool
│   └── subagents/
│       └── memory_agent.py  # Memory retrieval node
└── features/
    ├── auth/                # GET /api/v1/auth/me
    ├── chat/                # POST /api/v1/chat/stream (SSE)
    ├── memory/              # CRUD + search + file upload /api/v1/memory
    └── models/              # GET /api/v1/models
```

---

## Middleware Stack (LIFO order)

```
Request →  CORSMiddleware  →  SlowAPIMiddleware  →  FastAPI routes
Response ← CORSMiddleware  ← SlowAPIMiddleware  ← FastAPI routes
```

- **CORSMiddleware** — adds `Access-Control-*` headers; covers even 429 responses.
- **SlowAPIMiddleware** — activates `@limiter.limit()` decorators on routers.

---

## API Endpoints

### `GET /api/v1/health`

Liveness probe — public, no auth. Returns `{"status":"ok","version":"0.1.0"}`.

---

### `GET /api/v1/auth/me` — 60 req/min

Validates JWT → returns `{id, email}` of the current user. Only checks the token, does not touch the DB.

---

### `GET /api/v1/models` — 60 req/min (public)

Lists all models available on OpenRouter. **In-memory TTL cache 5 min** with `asyncio.Lock` (double-checked locking) — only 1 HTTP call to OpenRouter every 5 minutes regardless of concurrent requests.

---

### `POST /api/v1/chat/stream` — 20 req/min

**SSE stream** of the LangGraph graph response.

**Request body:**

```json
{
  "message": "...",
  "model_id": "anthropic/claude-3.5-sonnet",
  "conversation_id": null
}
```

**SSE format (each frame):**

```
data: {"type":"token"|"error"|"done","content":"..."}

```

The stream always ends with `{"type":"done"}` even on error.

---

### Memory endpoints — all JWT-protected

| Method   | Path                    | Limit  | Description                         |
| -------- | ----------------------- | ------ | ----------------------------------- |
| `POST`   | `/api/v1/memory`        | 30/min | Create a memory entry               |
| `GET`    | `/api/v1/memory`        | 60/min | List all entries                    |
| `POST`   | `/api/v1/memory/search` | 30/min | Semantic search                     |
| `DELETE` | `/api/v1/memory/{id}`   | 30/min | Delete an entry                     |
| `POST`   | `/api/v1/memory/upload` | 5/min  | Upload a file (.txt/.md/.pdf/.docx) |

---

## LangGraph Graph (Orchestrator)

```
START → supervisor ──(sees tool_call)──→ memory_agent → supervisor → END
                  ──(responds directly)────────────────────────────→ END
```

### `AxonState`

```python
{
    "messages": list[BaseMessage],   # add_messages reducer (append-only)
    "user_id": str,                  # from JWT, never from the client
    "model_id": str,                 # requested OpenRouter model
    "memory_context": list[str],     # populated by memory_agent
}
```

### Supervisor node (`supervisor.py`)

- **First pass** (no `ToolMessage` in the current turn): uses `_routing_model` bound to `transfer_to_memory_agent` — the LLM decides whether to delegate.
- **Second pass** (has `ToolMessage`): uses `_response_model` (no tools) and injects `memory_context` as a `SystemMessage` at the front.
- Both models are **lazy singletons** — built on first call, OpenRouter is invoked with `streaming=True`.

### Memory agent node (`memory_agent.py`)

- Takes the last `HumanMessage` as the query.
- Calls `service.search_memories(threshold=0.6, limit=5)` directly (no LLM).
- Returns a `ToolMessage` (closes the open `tool_call`) + updates `memory_context`.

---

## Memory Pipeline

### Write path

```
plaintext → mask_pii() → embed(masked_text) → encrypt(plaintext) → INSERT memory_entries
```

### Read path

```
DB row → decrypt(content_encrypted) → MemoryEntry
```

### Search path (semantic search)

```
query → mask_pii(query) → embed(masked_query) → match_memories RPC (pgvector cosine) → decrypt each hit
```

### File upload path

```
bytes → parse(pdf/docx/txt/md) → chunk_text(800 chars, 100 overlap)
      → mask_pii (batch, semaphore=8) → embed_texts (batch≤96, 1 HTTP call)
      → for each chunk: encrypt + INSERT
```

**Limits:** max 10 MB, max 500 chunks per file.

---

## Encryption & Privacy

### `crypto.py` — Fernet symmetric encryption

- Key from `ENCRYPTION_KEY` env var (urlsafe-base64, 32 bytes).
- Loaded once at import; invalid key → `RuntimeError` at startup.
- `encrypt(plaintext) → ciphertext_str`
- `decrypt(ciphertext_str) → plaintext`

### `privacy.py` — PII masking with Presidio

- Masked entities: PERSON, EMAIL, PHONE, CREDIT_CARD, IBAN, IP, LOCATION, SSN.
- **Important:** the masked text goes into embeddings; the original (encrypted) goes into the DB.
- Presidio/spaCy is CPU-bound → `asyncio.to_thread` to avoid blocking the event loop.
- Singleton initialisation with a threading `Lock`.

---

## Database (`db/`)

### `supabase.py`

- `AsyncClient` singleton with `asyncio.Lock` (double-checked locking).
- Uses `supabase_secret_key` (service role) → **bypasses RLS**.
- Every query **MUST** be scoped by `user_id`.

### `embeddings.py`

- `embed_text(text)` / `embed_texts(texts)` — OpenRouter `/embeddings`, model `openai/text-embedding-3-large`, 1536 dim.
- Batch size 96; retry with exponential backoff (tenacity, 3 attempts) on 429/5xx.
- `_parse_embeddings()` — sorts by `index` (does not rely on API response order).
- CRUD: `insert_memory`, `list_memories`, `delete_memory`, `match_memories` (pgvector RPC).

---

## Rate Limiter (`core/limiter.py`)

- Key function `_jwt_key`: decodes JWT payload **without verification** → extracts `sub` UUID → key `"user:<uuid>"`.
- Falls back to IP address for public routes or malformed tokens.
- UUID validation with regex before using as a key (prevents key injection).
- Optional Redis backend (`REDIS_URL` env var) for multi-worker deployments.

---

## Security (OWASP)

| Threat                  | Mitigation                                                                             |
| ----------------------- | -------------------------------------------------------------------------------------- |
| Broken Auth             | JWT validation on every request (`get_current_user`); `user_id` only from JWT          |
| Injection               | Pydantic validation on all input; parameterised Supabase queries                       |
| Sensitive Data Exposure | Fernet encryption at-rest; PII masking before embedding; secrets only in env vars      |
| Rate limiting           | SlowAPI per-user; `20/min` for chat, `5/min` for upload                                |
| Logging                 | Tokens, keys, and PII are never logged; user_id → SHA-256 hash in logs                 |
| Oversized payload       | File upload: Content-Length check + post-read check (10 MB); message: max 10 000 chars |

---

## Environment Variables

```env
SUPABASE_URL=
SUPABASE_SECRET_KEY=
OPENROUTER_API_KEY=
JWT_SECRET_KEY=               # must match Supabase Dashboard → Settings → API → JWT Secret
ENCRYPTION_KEY=               # Fernet key (generate with cryptography.fernet.Fernet)
LLM_MODEL=anthropic/claude-3.5-sonnet
EMBEDDING_MODEL=openai/text-embedding-3-large
EMBEDDING_DIMENSIONS=1536
CORS_ORIGINS=http://localhost:3000
REDIS_URL=                    # optional, for multi-worker rate limiting
DEBUG=false
LOG_LEVEL=INFO
```
