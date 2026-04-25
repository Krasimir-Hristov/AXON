---
description: "Scaffold a new AXON feature. Use when adding a new tool or capability (e.g., calendar, web search) to AXON."
---
# New AXON Feature: ${featureName}

Create a complete feature scaffold for `${featureName}` following AXON feature-based architecture.

## Backend — create these files:

### `backend/app/features/${featureName}/schemas.py`
Pydantic v2 request/response models specific to this feature.

### `backend/app/features/${featureName}/service.py`
Async business logic. Use `Depends(get_current_user)` for auth, `httpx.AsyncClient` for HTTP.
Include try/except + logging for all external calls.

### `backend/app/features/${featureName}/router.py`
FastAPI `APIRouter` with prefix `/api/v1/${featureName}`.
Mount in `main.py` after creation.

### `backend/app/features/${featureName}/tool.py`
LangGraph `@tool` function if this feature should be callable by the orchestrator.
Wire into `orchestrator.py` ToolNode after creation.

## Frontend — create these files:

### `frontend/features/${featureName}/types.ts`
TypeScript types for this feature.

### `frontend/features/${featureName}/hooks/use${FeatureName}.ts`
TanStack Query hook for data fetching.

### `frontend/features/${featureName}/components/${FeatureName}View.tsx`
Main UI component (arrow function `const ${FeatureName}View = () => {}`).

## Rules
- No `type: any`
- All backend I/O: async
- Module docstring in every .py file
- Check Context7 for any library used
