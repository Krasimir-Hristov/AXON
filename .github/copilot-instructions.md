# AXON — AI Personal Assistant

## Project Overview

AXON is a personal AI assistant built with Next.js 16 (frontend) and FastAPI + LangGraph (backend).
It uses Supabase for auth and database, OpenRouter for LLM calls, and pgvector for RAG memory.

## MANDATORY: Before Writing Any Code

Always check the official documentation via Context7 MCP before writing code for any library or framework.
Use the `mcp_context7_resolve-library-id` and `mcp_context7_get-library-docs` tools before generating code for:
Next.js, FastAPI, LangGraph, LangChain, Supabase, TanStack Query, Zod, Pydantic, shadcn/ui, pgvector.
This prevents using outdated APIs (e.g., Next.js 16 uses `proxy.ts` not `middleware.ts`).

## Architecture

Feature-based architecture on both frontend and backend.

- Backend: `backend/app/features/<name>/` — router.py, service.py, schemas.py, tool.py
- Frontend: `frontend/features/<name>/` — components/, hooks/, types.ts
- Shared infrastructure lives in `core/`, `db/`, `agents/` (backend) and `lib/` (frontend)
- `app/` directory in frontend is ROUTING ONLY — pages only import from `features/`

## Universal Rules (Frontend + Backend)

- NEVER use `type: any` — use proper types or `unknown` with type guards
- NEVER hardcode secrets — always use environment variables
- NEVER write synchronous I/O — all network/DB calls must be async
- Always modular: one responsibility per file
- No file longer than 300 lines — split into smaller modules

## Security (OWASP Top 10)

- Validate ALL user input at system boundaries (Zod on frontend, Pydantic on backend)
- Never trust client-provided user IDs — always derive from validated JWT
- Never log sensitive data (tokens, passwords, PII)
- Always authenticate inside Server Functions — never rely solely on proxy/middleware
