---
description: 'Use when working on LangGraph agents, orchestrator, tools, subagents, or AxonState in the AXON backend.'
applyTo: 'backend/app/agents/**'
---

# LangGraph Agents — AXON Rules

## AxonState (Single Source of Truth)

Always import from `agents/state.py` — never define state locally:

```python
from app.agents.state import AxonState
```

## Node Functions

All graph nodes must be async and return a partial state dict:

```python
async def orchestrator_node(state: AxonState) -> dict:
    # ... logic
    return {"messages": updated_messages}
```

## Streaming

Use `astream_events` with `version="v2"` — never `ainvoke` for endpoints:

```python
async for event in graph.astream_events(input_state, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content
```

## Tools

Decorate with `@tool` from `langchain_core.tools`, one tool per file in `features/<name>/tool.py`:

```python
from langchain_core.tools import tool

@tool
async def search_memory(query: str) -> str:
    """Search AXON memory for relevant context."""
    ...
```

Wire tools into orchestrator via `ToolNode` in `orchestrator.py`.

## Adding a New Tool/Subagent

1. Create `features/<name>/tool.py` with the `@tool` function
2. Import and add to `ToolNode` in `orchestrator.py`
3. Add edge in graph if needed

Never put tool business logic inside `orchestrator.py`.

## Privacy (Mandatory)

Always call `mask_pii()` before embedding or adding to LLM context:

```python
from app.core.privacy import mask_pii

masked_query = mask_pii(user_query)
# now safe to embed or pass to LLM
```
