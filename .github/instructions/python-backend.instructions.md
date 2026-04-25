---
description: 'Use when writing Python backend code: FastAPI routes, services, schemas, database access, agents, or any .py file in the AXON backend.'
applyTo: 'backend/**/*.py'
---

# Python Backend — AXON Rules

## Module Docstring (Required)

Every .py file must start with a one-line docstring describing its role:

```python
"""Chat feature router — SSE streaming endpoint for AXON orchestrator."""
```

## Type Hints (Required)

Every function parameter and return type must be annotated:

```python
async def get_user(user_id: str) -> UserSchema:
    ...
```

Never use `Any` from typing unless absolutely unavoidable (and add a comment explaining why).

## Async (Required)

All I/O operations must be async:

```python
async def call_openrouter(messages: list[MessageSchema]) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
```

Use `httpx.AsyncClient` for ALL HTTP calls — never `requests`.

## Schemas (Pydantic v2)

All data structures must be Pydantic v2 `BaseModel`:

```python
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    model_id: str
    conversation_id: str | None = None
```

## Package Management

- Add packages: `uv add <package>`
- Run scripts: `uv run <script>`
- NEVER use `pip install` directly

## Authentication (Required on every protected route)

Always use FastAPI `Depends()` — never trust raw request data:

```python
@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: UserSchema = Depends(get_current_user),
):
```

`get_current_user` lives in `core/security.py` and validates the Supabase JWT.

## Error Handling

All external calls (OpenRouter, Supabase, Presidio, OpenAI) must have try/except + logging:

```python
import logging
logger = logging.getLogger(__name__)

try:
    result = await call_openrouter(messages)
except httpx.HTTPError as exc:
    logger.error("OpenRouter call failed: %s", exc)
    raise HTTPException(status_code=502, detail="AI service unavailable")
```

## Feature Structure

New features follow this layout:

```
features/<name>/
├── router.py    # FastAPI APIRouter, mounts in main.py
├── schemas.py   # Pydantic request/response models
├── service.py   # Business logic (no HTTP concerns here)
└── tool.py      # LangGraph @tool (if this feature is an agent tool)
```

## Privacy (Critical)

NEVER send raw user input to OpenAI embeddings or OpenRouter without first calling `mask_pii()` from `core/privacy.py`.
