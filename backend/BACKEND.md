# AXON Backend — Architecture Overview

## Stack

| Layer            | Technology                                 |
| ---------------- | ------------------------------------------ |
| Web framework    | FastAPI (async)                            |
| AI graph         | LangGraph (supervisor pattern)             |
| LLM / Embeddings | OpenRouter (OpenAI-compatible API)         |
| TTS              | OpenRouter `/audio/speech` endpoint        |
| Database         | Supabase (PostgreSQL + pgvector)           |
| File storage     | Supabase Storage (private `audio` bucket)  |
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
│   ├── supervisor.py        # Supervisor node + all handoff tools
│   └── subagents/
│       ├── memory_agent.py      # Memory retrieval node
│       ├── youtube_agent.py     # YouTube fetch + summarization node
│       ├── youtube_fetcher.py   # Transcript + oEmbed fetch utilities
│       ├── youtube_chunker.py   # Transcript → text chunks
│       └── youtube_summarizer.py # Hierarchical LLM summarization
└── features/
    ├── auth/                # GET /api/v1/auth/me
    ├── chat/                # POST /api/v1/chat/stream + conversation CRUD
    ├── memory/              # CRUD + search + file upload /api/v1/memory
    ├── models/              # GET /api/v1/models
    ├── youtube/             # save_transcript node + /api/v1/youtube CRUD
    └── audio/               # generate_tts node + TTS service (Phase 10C)
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
  "conversation_id": null,
  "memory_threshold": 0.35,
  "memory_limit": 5
}
```

**SSE frame types:**

| Type       | Content field                            | When                                       |
| ---------- | ---------------------------------------- | ------------------------------------------ |
| `start`    | `conversation_id` (UUID string)          | Immediately after conversation is resolved |
| `tool_use` | Human-readable status string (see below) | When a sub-agent node starts               |
| `token`    | Incremental text chunk from the LLM      | During supervisor pass-2 streaming         |
| `error`    | Error message string                     | On recoverable or fatal errors             |
| `done`     | `""` (empty)                             | Always last, even after errors             |

**`tool_use` content values:**

| Value                            | Trigger node      |
| -------------------------------- | ----------------- |
| `"Searching memory…"`            | `memory_agent`    |
| `"Fetching YouTube transcript…"` | `youtube_agent`   |
| `"Saving to library…"`           | `save_transcript` |
| `"Generating audio…"`            | `generate_tts`    |

The stream **always ends with `{"type":"done"}`** even on error. Clients should treat the `done` frame as the definitive end signal.

---

### Chat / Conversation endpoints — all JWT-protected

| Method   | Path                                       | Limit  | Description                                       |
| -------- | ------------------------------------------ | ------ | ------------------------------------------------- |
| `GET`    | `/api/v1/chat/conversations`               | 60/min | List all conversations, newest first              |
| `GET`    | `/api/v1/chat/conversations/{id}/messages` | 60/min | Chronological messages in a conversation          |
| `DELETE` | `/api/v1/chat/conversations/{id}`          | 30/min | Delete conversation + all messages (CASCADE). 204 |
| `PATCH`  | `/api/v1/chat/conversations/{id}`          | 30/min | Rename conversation title                         |

`conversation_id` is validated as UUID by FastAPI — malformed IDs return 422 before reaching the DB. All endpoints return 404 when the resource does not exist or is not owned by the authenticated user.

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

### YouTube transcript endpoints — all JWT-protected

| Method   | Path                   | Limit  | Description                                      |
| -------- | ---------------------- | ------ | ------------------------------------------------ |
| `GET`    | `/api/v1/youtube`      | 60/min | List saved transcripts, newest first (paginated) |
| `GET`    | `/api/v1/youtube/{id}` | 60/min | Full transcript detail                           |
| `DELETE` | `/api/v1/youtube/{id}` | 30/min | 204 + deletes cross-indexed memory entry         |

Query params on `GET /api/v1/youtube`: `limit` (1–200, default 50), `offset` (default 0).

---

## LangGraph Graph (Orchestrator)

```
START → supervisor ──(transfer_to_memory_agent)──► memory_agent    → supervisor → END
                  ──(transfer_to_youtube_agent)─► youtube_agent   → supervisor → END
                  ──(save_video_transcript)──────► save_transcript → supervisor → END
                  ──(generate_tts)───────────────► generate_tts   → supervisor → END
                  ──(responds directly)──────────────────────────────────────► END
```

### `AxonState`

```python
{
    "messages":         list[BaseMessage],  # add_messages reducer (append-only)
    "user_id":          str,                # from JWT, never from the client
    "model_id":         str,                # requested OpenRouter model
    "memory_context":   list[str],          # populated by memory_agent
    "memory_threshold": float,              # cosine similarity threshold (default 0.35)
    "memory_limit":     int,                # max memory search results (default 5)
    "youtube_context":  str,                # JSON payload from youtube_agent; persisted in DB
    "pending_audio":    str,                # JSON {filename, signed_url, text_preview} from generate_tts
}
```

### Supervisor node (`supervisor.py`)

- **First pass** (no `ToolMessage` in the current turn): uses model bound to all four handoff tools. The LLM decides whether to delegate. YouTube URLs are detected without calling the LLM (fast-path bypass emits an `AIMessage` with the youtube tool_call directly).
- **Second pass** (has `ToolMessage`): uses model with no tools and injects `memory_context` as a `SystemMessage` at the front. Cannot re-delegate (no tools bound).
- Both model variants are **lazy singletons** per `(model_id, with_tools)` pair — built on first call and cached in `_model_cache`.
- DeepSeek compatibility: regex post-processing converts text-format tool calls to structured `tool_calls` before returning from the node.

### Memory agent node (`memory_agent.py`)

- Takes the last `HumanMessage` as the query.
- Calls `service.search_memories(threshold, limit)` directly (no LLM).
- Returns a `ToolMessage` (closes the open `tool_call`) + updates `memory_context`.

### YouTube agent node (`youtube_agent.py`)

- Extracts video_id from URL via regex.
- Fetches transcript (`youtube-transcript-api` in `asyncio.to_thread`) + oEmbed metadata in parallel.
- Hierarchical LLM summarization: chunks transcript → parallel chunk summaries (semaphore=5) → single final summary + key_points.
- Uses `settings.youtube_summary_model` (default `google/gemini-2.5-flash`) — not the user's chat model.
- Returns `ToolMessage` + updates `youtube_context` in state.

### Save-transcript node (`features/youtube/tool.py`)

- Reads `state["youtube_context"]` (persisted in DB across turns).
- INSERTs into `video_transcripts` + cross-indexes summary in `memory_entries`.
- Returns confirmation `ToolMessage`.

### Generate-TTS node (`features/audio/tool.py`)

- Reads `text` arg from the supervisor's `generate_tts` tool_call.
- Calls `audio_service.generate_tts`: masks PII → POST to OpenRouter `/api/v1/audio/speech` → validates MP3 response.
- Calls `audio_service.upload_audio`: uploads to Supabase Storage `audio` bucket → returns 7-day signed URL.
- Stores result in `state["pending_audio"]` for Phase 10D save confirmation.
- Returns `ToolMessage` with a markdown `[Play audio](signed_url)` link.

---

## Chat Service — SSE Streaming Pipeline

`POST /api/v1/chat/stream` is handled by `features/chat/service.py`:

1. **Resolve conversation** — creates or fetches a `conversations` row.
2. **Load history** — fetches last N messages from `conversation_messages`.
3. **Emit `start`** — sends `{"type":"start","content":"<conversation_id>"}` so the client can link the stream to the conversation before the first token.
4. **Invoke graph** — `astream_events(inputs, version="v2")`.
5. **`on_chat_model_stream`** — collects tokens from the `supervisor_node` in a `pass1_buffer`. Tokens are **not** forwarded until we know if this is pass-2 (real response) or pass-1 (just tool selection).
6. **`on_chain_start`** — when a sub-agent node starts (identified by name), emit a `tool_use` SSE event and set `memory_agent_invoked = True` + clear `pass1_buffer` (prevents tool-routing tokens from leaking to the client).
7. **After graph completes** — if `memory_agent_invoked`, stream `pass1_buffer` contents as `token` events (they are now confirmed to be pass-2 tokens). If not invoked, stream them directly (single-turn, no delegation).
8. **`on_chain_end`** — detects `supervisor_node` end → persists the final `AIMessage` and the user `HumanMessage` to `conversation_messages`.
9. **Emit `done`** — always last.

### Anti-leak mechanism (pass1_buffer)

The supervisor calls the LLM twice in tool-delegation turns:

- **Pass 1** (tool selection): the model streams text while deciding which tool to call. These tokens must NOT be sent to the client.
- **Pass 2** (actual response): the model streams the real reply after the sub-agent result is injected.

The `pass1_buffer` accumulates tokens from both passes. When a sub-agent node fires (`on_chain_start`), the buffer is cleared. When the graph ends, the surviving buffer contains only pass-2 tokens.

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

## Audio Pipeline (Phase 10C)

```
generate_tts_node
  ├── mask_pii(text)
  ├── POST {openrouter_base}/api/v1/audio/speech
  │     body: { model: "openai/gpt-4o-mini-tts-2025-12-15",
  │             input: masked_text, voice: "alloy", response_format: "mp3" }
  ├── Validate: non-empty bytes + (Content-Type: audio/* OR MP3 magic bytes)
  ├── Upload mp3_bytes → Supabase Storage "audio" bucket  ({user_id}/{uuid}.mp3)
  ├── Create 7-day signed URL
  └── ToolMessage: "[Play audio](signed_url)\n\nWould you like me to save this?"
```

The signed URL is a **short-lived, opaque token** — it cannot be guessed and expires automatically. No user ID appears in any log entry; only the file UUID is logged.

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
TTS_MODEL=openai/gpt-4o-mini-tts-2025-12-15
TTS_VOICE=alloy
AUDIO_BUCKET=audio
YOUTUBE_SUMMARY_MODEL=google/gemini-2.5-flash
CORS_ORIGINS=http://localhost:3000
REDIS_URL=                    # optional, for multi-worker rate limiting
DEBUG=false
LOG_LEVEL=INFO
```
