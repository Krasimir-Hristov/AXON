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
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.state import AxonState
from app.core.config import settings

logger = logging.getLogger(__name__)

# Tool name constant — imported by memory_agent.py to resolve tool_call_id.
HANDOFF_TOOL_NAME = "transfer_to_memory_agent"

_SUPERVISOR_SYSTEM_PROMPT = """\
You are AXON, a helpful personal AI assistant.

Behaviour rules:
- Always answer the user's question directly. Do NOT ask the user to clarify
  the format of their request, do NOT propose templates, and do NOT echo
  fragments of their message back as a "format". If a request is ambiguous,
  pick the most reasonable interpretation and answer.
- Reply in the same language the user wrote in (Bulgarian, English, etc.).
  Bulgarian written with Latin letters (transliteration) is still Bulgarian —
  reply in Bulgarian (Cyrillic).
- Be concise by default. Use Markdown formatting where it helps readability
  (lists, code fences, bold). Do not over-format casual replies.

You have access to the user's long-term memory via `transfer_to_memory_agent`.
Call it when the user:
- Asks about themselves, personal preferences, or past interactions.
- References something they may have stored or shared previously.
- Uses phrases like "what do you know about me", "do you remember", "I told you".
- Asks about content from documents, files, or notes they have uploaded or stored.
- Asks a question where stored personal notes or uploaded files might contain the answer.

Do NOT call `transfer_to_memory_agent` for:
- Pure general knowledge, math, coding, or writing requests that have no connection to anything the user could have stored.
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
# Model cache (keyed by model_id × has_tools to avoid rebuilding per request)
# ---------------------------------------------------------------------------

_model_cache: dict[tuple[str, bool], Runnable] = {}


def _get_model(model_id: str, with_tools: bool) -> Runnable:
    key = (model_id, with_tools)
    if key not in _model_cache:
        base = init_chat_model(
            model_id,
            model_provider="openai",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            streaming=True,
        )
        _model_cache[key] = base.bind_tools([transfer_to_memory_agent]) if with_tools else base
    return _model_cache[key]


# ---------------------------------------------------------------------------
# Supervisor node
# ---------------------------------------------------------------------------


async def supervisor_node(state: AxonState, config: RunnableConfig) -> dict:
    """LangGraph node: supervisor LLM that routes or responds.

    Uses model.astream() so that graph.astream_events("v2") can intercept
    on_chat_model_stream events per token — needed for SSE token streaming.
    The node still returns a single merged AIMessage to update graph state.
    """
    messages = list(state["messages"])

    # Detect whether memory_agent has already run *this turn* by scoping the
    # check to messages after the last HumanMessage. Historical ToolMessages
    # from previous turns must not lock the supervisor into _get_response_model().
    last_human_idx = next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)),
        -1,
    )
    current_turn = messages[last_human_idx + 1:]
    memory_done = any(isinstance(m, ToolMessage) for m in current_turn)

    # Build the system prompt(s). The base AXON system prompt is always
    # prepended so the model has a stable role definition; without it Grok and
    # similar models try to "guess" the user's intent (e.g. interpreting a
    # plain question as a template request).
    # Always prepend the AXON system prompt. Memory context is already present
    # in state["messages"] as a ToolMessage added by memory_agent_node — no
    # need to duplicate it as a SystemMessage (which would elevate tool output
    # to system-prompt priority).
    messages = [SystemMessage(content=_SUPERVISOR_SYSTEM_PROMPT)] + messages

    # On the second pass (after memory_agent ran) tools must NOT be bound, or
    # the model may re-delegate in a loop. Otherwise bind the handoff tool so
    # it can route to memory_agent.
    model = _get_model(state["model_id"], with_tools=not memory_done)

    # Stream the model response so that graph.astream_events("v2") in the
    # chat service can pick up on_chat_model_stream events per token.
    # Tool-call chunks (routing decisions) don't have content, so they're
    # silently skipped — the client never sees internal routing.
    collected: list[AIMessageChunk] = []
    try:
        logger.info("[supervisor] streaming model=%s with_tools=%s", state["model_id"], not memory_done)
        async for chunk in model.astream(messages, config):
            collected.append(chunk)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Supervisor LLM streaming failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service unavailable",
        ) from exc

    # Merge all chunks into a single message for the graph state.
    if not collected:
        logger.warning("[supervisor] model returned no chunks")
        return {"messages": [AIMessage(content="")]}

    response: AIMessageChunk = collected[0]
    for c in collected[1:]:
        response = response + c  # type: ignore[assignment]

    logger.info(
        "[supervisor] done, content_len=%d, has_tool_calls=%s",
        len(str(response.content)),
        bool(getattr(response, "tool_calls", None)),
    )
    return {"messages": [response]}
