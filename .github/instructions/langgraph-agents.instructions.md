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

## StateGraph Setup

```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

builder = StateGraph(AxonState)
builder.add_node("orchestrator", orchestrator_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "orchestrator")
builder.add_conditional_edges("orchestrator", should_continue)
builder.add_edge("tools", "orchestrator")
graph = builder.compile()
```

## Node Functions

All graph nodes must be async and return a partial state dict:

```python
async def orchestrator_node(state: AxonState) -> dict:
    # ... logic
    return {"messages": [new_message]}
```

## Conditional Edges

Return the next node name from a routing function:

```python
def should_continue(state: AxonState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END
```

## Streaming

Use `graph.stream()` with `stream_mode="messages"` and `version="v2"` for SSE endpoints:

```python
async for chunk in graph.astream(
    input_state,
    config={"configurable": {"thread_id": thread_id}},
    stream_mode="messages",
    version="v2",
):
    if chunk["type"] == "messages":
        token, metadata = chunk["data"]
        yield token.content
```

For full state updates (debugging/internal use), use `stream_mode="updates"`.

## Tools

Decorate with `@tool` from `langchain_core.tools`, one tool per file in `features/<name>/tool.py`:

```python
from langchain_core.tools import tool

@tool
async def search_memory(query: str) -> str:
    """Search AXON memory for relevant context."""
    ...
```

Wire tools via `ToolNode` — pass list to both `ToolNode(tools)` and `model.bind_tools(tools)`.

## Accessing State Inside a Tool

Use `ToolRuntime` to read graph state from within a tool:

```python
from langchain.tools import tool, ToolRuntime

@tool
def get_conversation_context(runtime: ToolRuntime) -> str:
    """Get the current conversation messages."""
    return runtime.state["messages"]
```

`runtime` parameter is hidden from the LLM's tool schema automatically.

## Updating State from a Tool

Use `Command` to update graph state and route from inside a tool:

```python
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

@tool
def enrich_state(data: str, runtime: ToolRuntime):
    """Enrich agent state with external data."""
    return Command(update={"messages": [ToolMessage(data, tool_call_id=runtime.tool_call_id)]})
```

## Adding a New Tool/Subagent

1. Create `features/<name>/tool.py` with the `@tool` function
2. Import and add to `ToolNode` list in `orchestrator.py`
3. Add to `model.bind_tools(tools)` list
4. Add edge in graph if needed

Never put tool business logic inside `orchestrator.py`.

## Checkpointing (Persistence)

Use `InMemorySaver` for development, swap for Postgres-backed saver in production:

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())
```

## Privacy (Mandatory)

Always call `mask_pii()` before embedding or adding to LLM context:

```python
from app.core.privacy import mask_pii

masked_query = mask_pii(user_query)
# now safe to embed or pass to LLM
```
