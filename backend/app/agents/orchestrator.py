"""Orchestrator graph — single-node LangGraph calling OpenRouter via init_chat_model.

This is the Phase 3 minimal graph: START → orchestrator → END. Tools, memory
retrieval, and conditional routing are wired in later phases.
"""

import logging

from fastapi import HTTPException, status
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agents.state import AxonState
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_chat_model() -> BaseChatModel:
    """Construct the chat model bound to OpenRouter via the OpenAI-compatible API.

    Per the langchain-core instructions, we must always go through
    init_chat_model — never instantiate provider classes directly. OpenRouter
    speaks the OpenAI API, so we use model_provider="openai" with a custom
    base_url.
    """
    return init_chat_model(
        settings.llm_model,
        model_provider="openai",
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        streaming=True,
    )


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
    """
    model = _get_model()
    try:
        response = await model.ainvoke(state["messages"])
    except Exception as exc:
        logger.error("Orchestrator LLM call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service unavailable",
        ) from exc
    return {"messages": [response]}


def _build_graph():
    """Build and compile the orchestrator graph."""
    builder = StateGraph(AxonState)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", END)
    return builder.compile()


# Compiled graph — exported singleton consumed by the chat service.
graph = _build_graph()
