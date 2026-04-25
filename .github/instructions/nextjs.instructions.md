---
description: 'Use when writing Next.js frontend code: components, pages, server actions, route handlers, proxy, hooks, or any frontend TypeScript file in the AXON project.'
applyTo: 'frontend/**'
---

# Next.js 16 — AXON Frontend Rules

## Critical: File Naming (Next.js 16)

- `middleware.ts` is DEPRECATED in Next.js 16 — use `proxy.ts` instead
- Export: `export function proxy(request: NextRequest)` — NOT `export function middleware`
- SECURITY: Never rely solely on proxy for auth — always validate inside Server Functions too

## Component Syntax

Arrow functions for ALL React components (client and server):

```tsx
const ChatWindow = () => {
  return <div>...</div>;
};
export default ChatWindow;
```

Regular `function` declaration for Server Actions and utility functions:

```ts
async function createConversation(title: string) { ... }
export async function getAllUsers() { ... }
```

## Directives

- `'use client'` — at the top of every interactive component file
- `'use server'` — at the top of server action files (NOT on individual functions unless needed)
- `'use cache'` — for data fetching functions that should be cached (replaces fetch cache config)

## Async Params (Next.js 15+)

Params in pages and route handlers are Promises — always await:

```tsx
// page.tsx
const ChatPage = async ({ params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
};
// route.ts
export async function GET(
  _req: NextRequest,
  ctx: RouteContext<'/api/chat/[id]'>,
) {
  const { id } = await ctx.params;
}
```

## React Compiler

React Compiler is enabled — do NOT add `useMemo` or `useCallback` unless profiling proves it necessary.

## Feature-Based Structure

- Components, hooks, and types belong in `features/<name>/`
- Pages in `app/` ONLY import from `features/` — no business logic in pages
- Global shared components (shadcn/ui wrappers) go in `components/ui/`

## State & Data

- `@tanstack/react-query` for ALL server state (never useState for server data)
- `zod` for ALL user input validation — no raw form data without a schema
- Supabase client: browser → `lib/supabase/client.ts`, server → `lib/supabase/server.ts`

## Error Handling

Every `fetch()` call must be wrapped in `try/catch`. Always check `response.ok` before parsing:

```ts
try {
  const response = await fetch('/api/v1/models', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
} catch (error) {
  // handle or re-throw — never silently swallow errors
}
```

In TanStack Query hooks, throw from the `queryFn` on non-ok responses — errors surface via `isError`/`error` automatically.

## Streaming (SSE)

Use `fetch()` with `ReadableStream` — NOT `EventSource` (EventSource doesn't support POST or auth headers):

```ts
const response = await fetch('/api/chat/stream', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` },
  body: JSON.stringify(payload),
});
const reader = response.body!.getReader();
```

## TypeScript

- Never use `type: any`
- Prefer `interface` for object shapes, `type` for unions/intersections
- Use `RouteContext<'/path/[param]'>` for typed route handler params
