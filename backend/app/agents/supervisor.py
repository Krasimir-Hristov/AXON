"""Supervisor node — routes user requests to specialised sub-agents.

The supervisor is the entry point for every chat turn. It holds handoff tools
for each sub-agent and uses the LLM to decide:

- **Delegate to memory_agent**: calls ``transfer_to_memory_agent`` → orchestrator
  routes to memory_agent_node → memory results injected back → supervisor generates
  the final response with memory context.
- **Delegate to youtube_agent**: calls ``transfer_to_youtube_agent`` → orchestrator
  routes to youtube_agent_node → JSON payload injected back → supervisor presents
  summary + key points and asks to save.
- **Respond directly**: answers general questions without delegation.

Two model singletons are kept at module level:
- ``_routing_model``  — base model bound to both handoff tools.
  Used on the *first* pass (no ToolMessage in history yet).
- ``_response_model`` — same base model, *no* tools bound.
  Used on the *second* pass (after any sub-agent has added a ToolMessage) to
  guarantee the supervisor never re-delegates in a loop.
"""

import logging
from uuid import uuid4

from fastapi import HTTPException, status
from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import tool

from app.agents.state import AxonState
from app.agents.subagents.youtube_fetcher import extract_video_id
from app.core.config import settings

logger = logging.getLogger(__name__)

# Tool name constants — imported by the respective sub-agent modules and orchestrator.py.
HANDOFF_TOOL_NAME = "transfer_to_memory_agent"
YOUTUBE_HANDOFF_TOOL_NAME = "transfer_to_youtube_agent"

_SUPERVISOR_SYSTEM_PROMPT = """\
You are AXON, a helpful personal AI assistant.

Behaviour rules:
- Always answer the user's question directly. Do NOT ask the user to clarify
  the format of their request, do NOT propose templates, and do NOT echo
  fragments of their message back as a "format". If a request is ambiguous,
  pick the most reasonable interpretation and answer.
- ALWAYS reply in the EXACT language the user wrote their message in.
  If the user wrote in English → respond in English, no exceptions.
  If the user wrote in Bulgarian (Cyrillic or Latin) → respond in Bulgarian (Cyrillic).
  The language of retrieved memory context or documents does NOT affect your
  response language. Detect the user's language from their message only.
- Be concise by default. Use Markdown formatting where it helps readability
  (lists, code fences, bold). Do not over-format casual replies.

## Memory tool — MANDATORY usage rules

You MUST call `transfer_to_memory_agent` (do NOT answer from general knowledge)
whenever the user's message matches ANY of the following:

1. The user explicitly asks what you know, remember, or have stored about them
   — e.g. "what do you know about me", "what information do you have",
   "kakvo znaeш za men", "kakva informaciq imaш".
2. The user asks about a document, file, note, or PDF they have uploaded.
3. The user references a past event, preference, or fact they may have shared
   — e.g. "do you remember", "I told you", "as I mentioned".
4. The user asks a personal question that could be answered from stored notes
   — e.g. "what are my goals", "what's my schedule", "remind me of...".
5. The user explicitly asks you to search, check, or look something up in your
   DB / memory / database / notes — ANY phrasing like "search in your DB",
   "check your memory", "look it up", "search for", "can you find in your DB",
   "pretarsi", "proveri v bazata" — ALWAYS call the tool, no exceptions.
6. The user asks for a recommendation or suggestion that depends on personal
   context stored in memory — e.g. "what project should I build", "what should
   I learn next", "suggest something for me", "what do you recommend for me".
7. When in doubt whether memory is relevant — CALL THE TOOL. It is always
   better to search and find nothing than to miss stored information.

## CRITICAL output rule
When you decide to call `transfer_to_memory_agent`, your response MUST consist
ONLY of the tool call — zero text content before or after it. Do NOT write
phrases like "Let me check", "I will search", "Нека да проверя",
"Позволи ми" or anything similar. Silence + tool call only.

Do NOT call `transfer_to_memory_agent` only for:
- Pure math, coding, or writing tasks with zero personal component.
- Casual one-word greetings ("hi", "hello") answerable without any context.

## YouTube video results

When you receive a ToolMessage from the youtube_agent (it contains a JSON payload),
present the result as follows:
- **Title** and **Channel** on the first line.
- **Duration** in minutes (convert `duration_s` ÷ 60, round to nearest minute).
- **Summary** as a paragraph.
- **Key Points** as a numbered list.

If the ToolMessage content is an error string (not valid JSON), relay the error
to the user politely.

Do NOT call `transfer_to_youtube_agent` yourself — routing to the YouTube agent
is handled automatically before you are invoked.
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


@tool(YOUTUBE_HANDOFF_TOOL_NAME)
def transfer_to_youtube_agent() -> str:
    """Delegate to the YouTube specialist to fetch and summarise a video transcript.

    Call this when the user's message contains a YouTube URL
    (youtube.com/watch?v=, youtu.be/, or youtube.com/shorts/).
    """
    # The tool body is never executed — supervisor_node detects the tool_call
    # by name and routes to youtube_agent_node via _should_continue.
    return "YouTube agent activated."  # pragma: no cover


# ---------------------------------------------------------------------------
# Model cache (keyed by model_id + sorted tool names for exact cache hits)
# ---------------------------------------------------------------------------

_model_cache: dict[tuple[str, tuple[str, ...]], Runnable] = {}


def _get_model(model_id: str, tools: list) -> Runnable:
    """Return a (possibly cached) chat model optionally bound to *tools*.

    The cache key includes the actual tool names so that different tool-sets
    produce distinct cached models and no stale binding is ever reused.
    """
    tool_names: tuple[str, ...] = tuple(t.name for t in tools)
    key = (model_id, tool_names)
    if key not in _model_cache:
        base = init_chat_model(
            model_id,
            model_provider="openai",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            streaming=True,
        )
        _model_cache[key] = base.bind_tools(tools) if tools else base
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
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ),
        -1,
    )
    current_turn = messages[last_human_idx + 1 :]
    agent_ran = any(isinstance(m, ToolMessage) for m in current_turn)

    # -- Deterministic YouTube fast-path ------------------------------------
    # Detect a YouTube URL in the last HumanMessage without asking the LLM.
    # This avoids the failure mode where the model ignores the routing
    # instruction and hallucinates a summary from its training data.
    if not agent_ran:
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        if last_human:
            raw = (
                last_human.content
                if isinstance(last_human.content, str)
                else " ".join(
                    p
                    if isinstance(p, str)
                    else p.get("text", "")
                    if isinstance(p, dict)
                    else getattr(p, "text", "")
                    for p in last_human.content
                )
            )
            if extract_video_id(raw):
                logger.info(
                    "[supervisor] YouTube URL detected — fast-path to youtube_agent"
                )
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "id": str(uuid4()),
                                    "name": YOUTUBE_HANDOFF_TOOL_NAME,
                                    "args": {},
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ]
                }

    # Always prepend the AXON system prompt. Memory context is already present
    # in state["messages"] as a ToolMessage added by memory_agent_node — no
    # need to duplicate it as a SystemMessage (which would elevate tool output
    # to system-prompt priority).
    messages = [SystemMessage(content=_SUPERVISOR_SYSTEM_PROMPT), *messages]

    # On the second pass (after any sub-agent ran) tools must NOT be bound, or
    # the model may re-delegate in a loop. On the first pass only bind the
    # memory handoff tool — YouTube routing is handled by the deterministic
    # fast-path above, so transfer_to_youtube_agent must never be exposed to
    # the LLM (prevents it from hallucinating YouTube summaries).
    model = _get_model(
        state["model_id"],
        tools=[] if agent_ran else [transfer_to_memory_agent],
    )

    # Stream the model response so that graph.astream_events("v2") in the
    # chat service can pick up on_chat_model_stream events per token.
    # Tool-call chunks (routing decisions) don't have content, so they're
    # silently skipped — the client never sees internal routing.
    collected: list[AIMessageChunk] = []
    try:
        logger.info(
            "[supervisor] streaming model=%s with_tools=%s",
            state["model_id"],
            not agent_ran,
        )
        async for chunk in model.astream(messages, config):
            collected.append(chunk)
    except Exception as exc:
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
        "[supervisor] done content_len=%d has_tool_calls=%s",
        len(str(response.content)),
        bool(getattr(response, "tool_calls", None)),
    )
    return {"messages": [response]}
