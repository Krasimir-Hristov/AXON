# AXON

> A personal AI assistant with persistent, encrypted, semantically-searchable memory — built on a LangGraph supervisor agent, FastAPI, and Next.js.

AXON is a full-stack AI assistant that goes beyond a stateless chatbot. It remembers what you tell it (encrypted at rest, PII-masked before embedding), can ingest your documents, summarise YouTube videos, and synthesise speech — all behind your own Supabase auth.

---

## ✨ Features

- 💬 **Streaming chat** over Server-Sent Events with any model on [OpenRouter](https://openrouter.ai)
- 🧠 **Encrypted long-term memory** with semantic search (pgvector + HNSW, cosine similarity)
- 📄 **File ingestion** — upload `.txt`, `.md`, `.pdf`, `.docx`; auto-chunked and embedded
- 📺 **YouTube agent** — paste a link, get a hierarchical LLM summary saved to your library
- 🔊 **Text-to-speech** via OpenRouter, stored in a private Supabase bucket
- 🔐 **Privacy by design** — Microsoft Presidio masks PII before embedding; Fernet (AES-128-CBC + HMAC) encrypts stored plaintext
- 🚦 **Per-user rate limiting** with SlowAPI
- 🔑 **Supabase Auth** (Google OAuth) with row-level security on every table

---

## 🏗️ Architecture

```
┌──────────────────┐         ┌──────────────────────────┐         ┌─────────────────┐
│  Next.js 16      │  HTTPS  │  FastAPI + LangGraph     │  HTTPS  │  OpenRouter     │
│  (App Router)    │ ──────► │  Supervisor Agent        │ ──────► │  LLMs / TTS /   │
│  Server Functions│  SSE    │  + sub-agents            │         │  Embeddings     │
└──────────────────┘         └──────────────────────────┘         └─────────────────┘
         │                              │
         │ JWT                          │ pgvector / Storage / RLS
         ▼                              ▼
┌────────────────────────────────────────────────────────┐
│                Supabase (Postgres + Auth + Storage)    │
└────────────────────────────────────────────────────────┘
```

### LangGraph supervisor

```
START → supervisor ──► memory_agent     → supervisor → END
                  ──► youtube_agent    → supervisor → END
                  ──► save_transcript  → supervisor → END
                  ──► generate_tts     → supervisor → END
                  ──► (direct reply) ─────────────────► END
```

The **supervisor** is a tool-calling LLM that decides whether to delegate. Sub-agents return `ToolMessage`s that feed back into a second supervisor pass which streams the final answer to the user.

---

## 🧱 Tech Stack

### Backend (`backend/`)

| Layer         | Tool                                        |
| ------------- | ------------------------------------------- |
| Framework     | FastAPI (async)                             |
| Agents        | LangGraph + LangChain (supervisor pattern)  |
| LLM gateway   | OpenRouter                                  |
| Database      | Supabase Postgres + pgvector (HNSW)         |
| Storage       | Supabase Storage (private `audio` bucket)   |
| Auth          | Supabase JWT (HS256)                        |
| Encryption    | Fernet (AES-128-CBC + HMAC-SHA256)          |
| PII masking   | Microsoft Presidio + spaCy `en_core_web_sm` |
| Rate limiting | SlowAPI                                     |
| Package mgr   | [uv](https://github.com/astral-sh/uv)       |

### Frontend (`frontend/`)

| Layer         | Tool                               |
| ------------- | ---------------------------------- |
| Framework     | Next.js 16 (App Router, Turbopack) |
| UI            | React 19 + Tailwind v4 + shadcn/ui |
| Data fetching | TanStack Query v5                  |
| Validation    | Zod v4                             |
| SSE parsing   | `eventsource-parser`               |
| Auth client   | `@supabase/ssr`                    |
| Package mgr   | pnpm                               |

---

## 📂 Repository Layout

```
axon/
├── backend/
│   └── app/
│       ├── agents/        # LangGraph orchestrator, supervisor, sub-agents
│       ├── core/          # config, security, crypto, privacy, limiter
│       ├── db/            # Supabase client + embeddings
│       └── features/      # auth · chat · memory · models · youtube · audio
├── frontend/
│   ├── app/               # Next.js App Router (routing only)
│   ├── features/          # audio · auth · chat · memory · youtube
│   ├── components/ui/     # shadcn primitives
│   └── lib/               # api client, Supabase server/client helpers
└── supabase/
    └── migrations/        # Schema, RLS, pgvector, RPCs
```

Both halves follow a **feature-based** architecture — each feature owns its router, service, schemas, components, and hooks.

---

## 🚀 Getting Started

### Prerequisites

- Python ≥ 3.10, [uv](https://github.com/astral-sh/uv)
- Node.js ≥ 20, [pnpm](https://pnpm.io)
- A [Supabase](https://supabase.com) project (free tier works)
- An [OpenRouter](https://openrouter.ai) API key

### 1. Supabase

1. Create a project, copy the URL + anon key + service-role key.
2. Run the migrations in `supabase/migrations/` (in order) via the SQL editor or the Supabase CLI.
3. Enable Google OAuth and set the redirect URL.

### 2. Backend

```bash
cd backend
uv sync
uv run python -m spacy download en_core_web_sm
cp .env.example .env   # fill in keys
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the OpenAPI explorer.

### 3. Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local   # fill in Supabase + backend URL
pnpm dev
```

Open http://localhost:3000.

---

## 🔑 Environment Variables (overview)

**Backend** (`backend/.env`)

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
OPENROUTER_API_KEY=
ENCRYPTION_KEY=               # Fernet key (urlsafe base64, 32 bytes)
EMBEDDING_MODEL=openai/text-embedding-3-large
EMBEDDING_DIMENSIONS=1536
```

**Frontend** (`frontend/.env.local`)

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
BACKEND_URL=http://localhost:8000
```

---

## 🛡️ Security Notes

- Embeddings are computed on **PII-masked** text; stored plaintext is **Fernet-encrypted**.
- The user ID is **always derived from a validated JWT** server-side — never trusted from the client.
- Every table has **row-level security** enforced in Postgres; the backend uses the service-role key but consistently filters by `user_id`.
- Rate limits are keyed on the authenticated user (per-JWT), not IP.

---

## 📋 API Surface (selected)

| Method | Path                         | Notes                       |
| ------ | ---------------------------- | --------------------------- |
| GET    | `/api/v1/health`             | Liveness, public            |
| GET    | `/api/v1/auth/me`            | JWT-protected user info     |
| GET    | `/api/v1/models`             | Cached OpenRouter catalogue |
| POST   | `/api/v1/chat/stream`        | SSE stream from the agent   |
| GET    | `/api/v1/chat/conversations` | List conversations          |
| POST   | `/api/v1/memory` · `/search` | CRUD + semantic search      |
| POST   | `/api/v1/memory/upload`      | Multipart file ingestion    |
| GET    | `/api/v1/youtube`            | Saved video transcripts     |

See `backend/BACKEND.md` for the full reference.

---

## 📜 License

This is a personal project. No license granted; all rights reserved by the author.
