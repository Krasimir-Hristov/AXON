"""Supervisor node — routes user requests to specialised sub-agents.

The supervisor is the entry point for every chat turn. It holds exactly one
handoff tool (``transfer_to_memory_agent``) and uses the LLM to decide:

- **Delegate**: calls ``transfer_to_memory_agent`` → orchestrator routes to the
  memory_agent node → memory results are injected back into state → supervisor
  generates the final response with memory context.
- **Respond directly**: answers general questions without a memory lookup.

Two model singletons are kept at module level:
- ``_routing_model``  — base model bound to ``[transfer_to_memory_agent]``.
  Used on the *first* pass (no ToolMessage in history yet).
- ``_response_model`` — same base model, *no* tools bound.
  Used on the *second* pass (after memory_agent has added a ToolMessage) to
  guarantee the supervisor never re-delegates in a loop.
"""

import logging

from fastapi import HTTPException, status
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.state import AxonState
from app.core.config import settings

logger = logging.getLogger(__name__)

# Tool name constant — imported by memory_agent.py to resolve tool_call_id.
HANDOFF_TOOL_NAME = "transfer_to_memory_agent"

_SUPERVISOR_SYSTEM_PROMPT = """\
You are AXON, a personal AI assistant. You help users with any task.

You have access to the user's long-term memory via `transfer_to_memory_agent`.
Call it when the user:
- Asks about themselves, personal preferences, or past interactions.
- References something they may have stored or shared previously.
- Uses phrases like "what do you know about me", "do you remember", "I told you".

Do NOT call `transfer_to_memory_agent` for:
- General knowledge, math, coding, or writing requests with no personal component.
- Casual greetings or questions answerable from the conversation alone.
"""


@tool(HANDOFF_TOOL_NAME)
def transfer_to_memory_agent() -> str:
    """Delegate to the memory specialist to retrieve relevant personal context.

    Call this when the user asks about personal information, preferences, prior
    interactions, or anything that may be stored in long-term memory.
    """
    # The tool body is never executed — supervisor_node detects the tool_call
    # by name and routes to memory_agent_node via _should_continue.
    return "Memory agent activated."  # pragma: no cover


# ---------------------------------------------------------------------------
# Model singletons (lazily constructed on first invocation)
# ---------------------------------------------------------------------------

_routing_model: BaseChatModel | None = None  # with handoff tool
_response_model: BaseChatModel | None = None  # without tools


def _build_base_model() -> BaseChatModel:
    return init_chat_model(
        settings.llm_model,
        model_provider="openai",
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        streaming=True,
    )


def _get_routing_model() -> BaseChatModel:
    global _routing_model  # noqa: PLW0603
    if _routing_model is None:
        _routing_model = _build_base_model().bind_tools([transfer_to_memory_agent])
    return _routing_model


def _get_response_model() -> BaseChatModel:
    global _response_model  # noqa: PLW0603
    if _response_model is None:
        _response_model = _build_base_model()
    return _response_model


# ---------------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------------


async def supervisor_node(state: AxonState) -> dict:
    """LangGraph node: supervisor LLM that routes or responds.

    - First pass (no ToolMessage in history): uses the routing model (bound to
      ``transfer_to_memory_agent``) so the LLM can signal a memory lookup.
    - Second pass (ToolMessage present): uses the response model (no tools) and
      prepends the retrieved memory context as a system message.
    """
    messages = list(state["messages"])

    # Detect whether memory_agent has already run this turn.
    memory_done = any(isinstance(m, ToolMessage) for m in messages)

    if memory_done:
        # Inject memory context into the system prompt so the LLM can reference it.
        if state.get("memory_context"):
            context_lines = "\n".join(state["memory_context"])
            messages = [
                SystemMessage(
                    content=(
                        "The following context was retrieved from long-term memory "
                        "and is relevant to the user's query:\n"
                        f"{context_lines}"
                    )
                )
            ] + messages
        model = _get_response_model()
    else:
        model = _get_routing_model()

    try:
        response = await model.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Supervisor LLM call failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service unavailable",
        ) from exc

    return {"messages": [response]}
