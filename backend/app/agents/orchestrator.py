"""Orchestrator graph — LLM node + tool node + conditional routing.

Phase 5 evolution: the graph now binds the `search_memory` tool. Flow:

    START → orchestrator → (has tool_calls?) → tools → orchestrator → END
                          └────────────── no ────────────────────────→ END
"""

import logging

from fastapi import HTTPException, status
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.agents.state import AxonState
from app.core.config import settings
from app.features.memory.tool import search_memory

logger = logging.getLogger(__name__)

# Tools available to the orchestrator. Adding a new tool? Append it here AND
# create the @tool function in features/<name>/tool.py.
_TOOLS = [search_memory]


def _build_chat_model() -> BaseChatModel:
    """Construct the chat model bound to OpenRouter and to the tool list."""
    base = init_chat_model(
        settings.llm_model,
        model_provider="openai",
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        streaming=True,
    )
    return base.bind_tools(_TOOLS)


# Module-level model singleton — lazily constructed on first node invocation
# so that import time does not hit the network.
_model: BaseChatModel | None = None


def _get_model() -> BaseChatModel:
    global _model  # noqa: PLW0603 — intentional module-level singleton
    if _model is None:
        _model = _build_chat_model()
    return _model


async def orchestrator_node(state: AxonState) -> dict:
    """LangGraph node: invoke the LLM with the current message history.

    Returns a partial-state update dict. The `add_messages` reducer on
    AxonState["messages"] appends the response to the existing history.

    Errors from OpenRouter surface as HTTPException 502; FastAPI converts them
    to a JSON error response (or, in the streaming path, the chat service
    catches them and emits an SSE error frame).

    Both model initialisation and invocation are guarded by the same try/except
    so that a failure during init_chat_model (e.g. invalid API key on first
    call) is surfaced through the same 502 mapping as a runtime LLM error,
    instead of bubbling up as a raw 500.
    """
    try:
        model = _get_model()
        response = await model.ainvoke(state["messages"])
    except Exception as exc:  # noqa: BLE001 — uniform 502 mapping for any LLM-side failure
        logger.exception("Orchestrator LLM call failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service unavailable",
        ) from exc
    return {"messages": [response]}


def _should_continue(state: AxonState) -> str:
    """Route to the tools node if the LLM produced tool_calls, else stop."""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def _build_graph() -> CompiledStateGraph:
    """Build and compile the orchestrator graph with tool routing."""
    builder = StateGraph(AxonState)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("tools", ToolNode(_TOOLS))
    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges(
        "orchestrator",
        _should_continue,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "orchestrator")
    return builder.compile()


# Compiled graph — exported singleton consumed by the chat service.
graph: CompiledStateGraph = _build_graph()
