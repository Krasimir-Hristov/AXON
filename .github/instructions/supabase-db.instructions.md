---
description: 'Use when working with Supabase database, authentication, or pgvector embeddings in AXON (backend db/ files or frontend lib/supabase/ files).'
applyTo: ['backend/app/db/**', 'frontend/lib/supabase/**']
---

# Supabase & Database — AXON Rules

## Backend Client

Use the async Supabase Python client from `db/supabase.py` — never instantiate directly in feature code:

```python
from app.db.supabase import get_supabase_client
client = await get_supabase_client()
```

## Frontend Clients

- Browser (client components): import from `lib/supabase/client.ts`
- Server (Server Components, Server Actions): import from `lib/supabase/server.ts`
- Use `@supabase/ssr` — NOT `@supabase/auth-helpers` (deprecated)

## User Isolation (Critical)

Every query MUST filter by `user_id`. Never return data for all users:

```python
# CORRECT
result = await client.table("memory_entries").select("*").eq("user_id", user_id).execute()
# WRONG — never do this
result = await client.table("memory_entries").select("*").execute()
```

RLS is a safety net, not the primary control — always filter in code too.

## pgvector

- Embedding dimensions: 1536 (OpenAI text-embedding-3-small)
- Similarity search: cosine distance with `<=>` operator
- Index type: HNSW on `embedding` column

```python
# Similarity search via RPC
result = await client.rpc("match_memories", {
    "query_embedding": embedding,
    "match_user_id": user_id,
    "match_threshold": 0.7,
    "match_count": 5,
}).execute()
```

## Auth

- Google OAuth is handled by Supabase Auth — no custom OAuth code
- JWT validation in `core/security.py` using `python-jose`
- Never store JWT tokens in localStorage on frontend — use Supabase session cookies via `@supabase/ssr`
