---
description: 'Use when working with Supabase database, authentication, RLS, storage, or pgvector embeddings in AXON.'
applyTo:
  [
    'backend/app/db/**',
    'backend/app/features/**',
    'frontend/lib/supabase/**',
    'frontend/features/**',
  ]
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

## Security Checklist (from Supabase skill)

Run this checklist for any task touching auth, RLS, views, storage, or user data:

### Auth & Session Security

- **NEVER use `user_metadata` / `raw_user_meta_data` for authorization** — it is user-editable and appears in `auth.jwt()`. Use `raw_app_meta_data` / `app_metadata` instead.
- Deleting a user does NOT invalidate existing tokens — revoke sessions explicitly first.
- JWT claims are stale until the token is refreshed — don't rely on them for real-time auth decisions.

### API Keys

- **Never expose `service_role` key in frontend code.** Use publishable key (`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`) for browser.
- Any `NEXT_PUBLIC_` env var is sent to the browser — never put secrets there.

### RLS, Views & Functions

- **Enable RLS on every table in `public` schema.** Tables exposed to the Data API are reachable by `anon`/`authenticated` roles.
- **Views bypass RLS by default** — use `CREATE VIEW ... WITH (security_invoker = true)` (Postgres 15+).
- **UPDATE requires a SELECT policy** — without it, updates silently return 0 rows.
- **Do NOT put `security definer` functions in `public` schema** — use a private schema.
- Always pair `GRANT` access with RLS policies.

### Storage

- Storage upsert requires INSERT + SELECT + UPDATE policies — INSERT alone silently fails on replacement.

## Schema Changes via MCP

Use `execute_sql` (MCP) to iterate on schema — do NOT use `apply_migration` for iteration (it creates a history entry on every call). When ready to commit:

1. Run `get_advisors` (MCP) — fix any issues
2. Review Security Checklist above
3. Generate migration: `supabase db pull <name> --local --yes`
