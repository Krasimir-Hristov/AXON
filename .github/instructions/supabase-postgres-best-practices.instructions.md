---
description: 'Use when writing, reviewing, or optimizing Postgres queries, schema designs, indexes, or database configurations for AXON.'
applyTo: ['backend/app/db/**', 'backend/app/features/**']
---

# Supabase Postgres Best Practices

Comprehensive Postgres optimization rules from Supabase. Apply when writing SQL, designing schemas, or reviewing query performance.

## Rule Categories by Priority

| Priority | Category | Impact | Reference prefix |
|----------|----------|--------|------------------|
| 1 | Query Performance | CRITICAL | `query-` |
| 2 | Connection Management | CRITICAL | `conn-` |
| 3 | Security & RLS | CRITICAL | `security-` |
| 4 | Schema Design | HIGH | `schema-` |
| 5 | Concurrency & Locking | MEDIUM-HIGH | `lock-` |
| 6 | Data Access Patterns | MEDIUM | `data-` |
| 7 | Monitoring & Diagnostics | LOW-MEDIUM | `monitor-` |
| 8 | Advanced Features | LOW | `advanced-` |

Detailed rules with SQL examples are in `.agents/skills/supabase-postgres-best-practices/references/`.

## Critical Rules (must follow)

### Indexes
- Always index foreign key columns — Postgres does NOT auto-index them (`schema-foreign-key-indexes`)
- Use partial indexes for filtered queries: `CREATE INDEX ON messages (conversation_id) WHERE role = 'user'`
- Use covering indexes to avoid table lookups: `CREATE INDEX ON messages (conversation_id) INCLUDE (content, created_at)`
- Prefer HNSW over IVFFlat for pgvector: `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)`

### Query Performance
- Avoid `SELECT *` — always name the columns you need
- Never call a function in a `WHERE` clause on a plain column — it prevents index use
- Use `EXPLAIN (ANALYZE, BUFFERS)` before and after adding indexes

### Schema Design
- Use `UUID` primary keys with `gen_random_uuid()` default — never serial int for user-facing IDs
- Use `TIMESTAMPTZ` not `TIMESTAMP` — always store timezone-aware datetimes
- Use `JSONB` not `JSON` — JSONB is stored binary and supports indexing
- Lowercase all identifiers — quoted mixed-case names are a maintenance trap

### Connection Management
- Set `idle_in_transaction_session_timeout` to prevent zombie transactions
- Use Supabase connection pooler (pgbouncer) for high-concurrency workloads — never open direct DB connections from serverless functions

### RLS Performance
- Add indexes on `user_id` columns used in RLS policies — unindexed RLS causes full table scans
- Keep RLS policies simple — complex subqueries in policies run on every row

### Concurrency & Locking
- Keep transactions short — acquire locks as late as possible, release as early as possible
- Use `SELECT ... FOR UPDATE SKIP LOCKED` for queue-style processing

### Data Access Patterns
- Batch inserts with a single `INSERT INTO ... VALUES (...)` — never loop single inserts
- Use keyset pagination (`WHERE id > $last_id ORDER BY id LIMIT n`) over offset pagination for large tables
- Avoid N+1 queries — use JOINs or single queries that return all needed data

## AXON-Specific Notes

- `document_chunks.embedding` — HNSW index with `vector_cosine_ops`, 1536 dims
- `conversations.user_id`, `document_chunks.user_id` — must be indexed for RLS performance
- Use `match_memories` RPC for vector similarity search — never raw `<=>` queries from application code
