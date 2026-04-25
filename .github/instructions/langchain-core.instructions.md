---
description: 'Use when writing LangChain code in AXON backend: chat models, tools, messages, chains, embeddings, or any langchain_core / langchain import.'
applyTo: 'backend/app/**'
---

# LangChain — AXON Rules

## Chat Model Initialization

Use `init_chat_model` for configurable models — never hardcode provider-specific classes:

```python
from langchain.chat_models import init_chat_model

model = init_chat_model(
    "openai/gpt-4.1",          # format: "provider/model-id"
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
    temperature=0.7,
    streaming=True,
)
```

For OpenRouter (AXON uses OpenRouter for ALL LLM calls):

```python
model = init_chat_model(
    settings.llm_model,        # from config, e.g. "openai/gpt-4.1"
    model_provider="openai",   # OpenRouter uses OpenAI-compatible API
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
    streaming=True,
)
```

## Binding Tools to a Model

```python
model_with_tools = model.bind_tools(tools)
```

Always pass the same `tools` list to both `model.bind_tools(tools)` and `ToolNode(tools)` in LangGraph.

## Message Types

Import from `langchain_core.messages` — always use typed message objects:

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

messages = [
    SystemMessage("You are AXON, a personal AI assistant."),
    HumanMessage("What can you help me with?"),
]
response = model.invoke(messages)   # Returns AIMessage
```

- `SystemMessage` — system prompt
- `HumanMessage` — user input
- `AIMessage` — model response (may contain `.tool_calls`)
- `ToolMessage` — result of a tool call (must include `tool_call_id`)

## Tools

Use `@tool` decorator from `langchain_core.tools`:

```python
from langchain_core.tools import tool

@tool
async def search_memory(query: str) -> str:
    """Search AXON memory for relevant context.

    Args:
        query: The search query to find relevant memories.
    """
    # implementation
    ...
```

Rules:

- One tool per file: `features/<name>/tool.py`
- Always write a docstring — it becomes the tool's description for the LLM
- Type-annotate all parameters — they become the tool's JSON schema
- Prefer `async def` for tools that do I/O

## Accessing State from Inside a Tool (LangGraph integration)

```python
from langchain.tools import tool, ToolRuntime

@tool
def get_thread_context(runtime: ToolRuntime) -> str:
    """Get current conversation context."""
    messages = runtime.state["messages"]
    return str(messages[-5:])   # last 5 messages
```

`runtime: ToolRuntime` is automatically hidden from the LLM schema.

## Streaming

Use `.astream()` for async streaming in FastAPI endpoints:

```python
async for chunk in model.astream(messages):
    yield chunk.content
```

## Embeddings (via OpenRouter)

AXON uses OpenRouter for embeddings — NOT a separate OpenAI key:

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=settings.openrouter_api_key,
    dimensions=1536,
)

vector = await embeddings.aembed_query(text)
```

## Accessing Tool Calls from AIMessage

```python
response = model_with_tools.invoke(messages)

for tool_call in response.tool_calls:
    print(tool_call["name"])   # tool name
    print(tool_call["args"])   # dict of arguments
    print(tool_call["id"])     # tool_call_id (needed for ToolMessage)
```

## Error Handling

Always wrap model calls in try/except — never let LLM exceptions bubble to the user:

```python
try:
    response = await model.ainvoke(messages)
except Exception as e:
    logger.error("LLM call failed", error=str(e))
    raise HTTPException(status_code=502, detail="AI service unavailable")
```

## Middleware (Prompt & Request Transformation)

LangChain has a built-in middleware system for agents. Use it to modify system prompts, log requests, or inject context — without polluting node logic.

### Before/after hooks (logging, metrics)

```python
from langchain.agents.middleware import before_model, after_model, ModelRequest
from langgraph.runtime import Runtime

@before_model
def log_request(state, runtime: Runtime) -> None:
    logger.info("llm_request", user_id=runtime.context.get("user_id"))

@after_model
def log_response(state, runtime: Runtime) -> None:
    logger.info("llm_response_complete")
```

### Class-based middleware (for complex system prompt injection)

```python
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from collections.abc import Callable

class InjectContextMiddleware(AgentMiddleware):
    """Appends static context (e.g. user profile, character config) to the system prompt."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        user_name = request.runtime.context.get("user_name", "User")
        character = request.runtime.context.get("character_id", "assistant")
        extra = {"type": "text", "text": (
            f"\n\nUser name: {user_name}. Character personality: {character}."
        )}
        new_content = list(request.system_message.content_blocks) + [extra]
        new_system = SystemMessage(content=new_content)
        return handler(request.override(system_message=new_system))
```

> **RAG / long-term memory is NOT injected here.** It is a `@tool` that the LLM calls only when it decides it needs context. This avoids polluting every prompt with irrelevant memory chunks.

### Wiring middleware into an agent

Pass all middleware as a list to `create_agent`:

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=tools,
    middleware=[axon_system_prompt, log_request, log_after_model, InjectMemoryMiddleware()],
    context_schema=AxonContext,   # TypedDict with user_id, user_name, character_id
)
```

### Rules

- `@before_model` / `@after_model` — use for logging, metrics, or state mutations
- `AgentMiddleware` subclass — use when you need full control over the model request
- Never do DB calls in middleware without `async` — use `AsyncAgentMiddleware` if available
- Keep middleware stateless — store context in `runtime.context`, not in instance variables
