"""Chat service — async generator that streams orchestrator output as SSE frames."""

import hashlib
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage

from app.agents.orchestrator import graph
from app.agents.state import AxonState
from app.features.auth.schemas import UserSchema
from app.features.chat.conversation_service import (
    get_or_create_conversation,
    load_history,
    save_message,
)
from app.features.chat.schemas import ChatRequest, SSEEvent

logger = logging.getLogger(__name__)


def _format(event: SSEEvent) -> str:
    """Serialise an SSEEvent into a single SSE frame.

    The blank line terminator (\\n\\n) is mandatory — without it the browser's
    EventSource / eventsource-parser will buffer indefinitely.
    """
    return f"data: {event.model_dump_json()}\n\n"


async def stream_chat(
    request: ChatRequest,
    user: UserSchema,
) -> AsyncIterator[str]:
    """Yield SSE frames produced by streaming the orchestrator graph.

    Flow:
    1. Resolve or create a conversation in DB.
    2. Load last 40 messages (20 turns) of history from DB.
    3. Persist the incoming user message.
    4. Emit a `start` frame so the client learns the conversation_id.
    5. Build AxonState with history + current message and stream the graph.
    6. Collect all tokens; persist the full assistant reply in the finally block.

    Always emits a terminal `done` frame in the finally block so the client
    has a deterministic stop signal even when the upstream connection drops.
    """
    # Anonymise user id for logs — never log raw UUIDs (matches memory/tool.py pattern)
    _uid_tag = hashlib.sha256(user.id.encode()).hexdigest()[:8]

    # ── 1. Resolve conversation ──────────────────────────────────────────
    try:
        conversation_id = await get_or_create_conversation(
            user.id, request.conversation_id, request.model_id
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception("Failed to resolve conversation for user [uid:%s]", _uid_tag)
        yield _format(
            SSEEvent(type="error", content="Failed to initialise conversation")
        )
        yield _format(SSEEvent(type="done"))
        return

    # ── 2. Load history ───────────────────────────────────────────────────────
    history = await load_history(conversation_id, user.id, limit=40)

    # ── 3. Persist user message (original, unmasked) ────────────────────
    await save_message(conversation_id, user.id, "user", request.message)

    # ── 4. Emit start frame ───────────────────────────────────────
    yield _format(SSEEvent(type="start", content=conversation_id))
    logger.info(
        "[stream_chat] start frame sent, invoking graph with model=%s uid=%s",
        request.model_id,
        _uid_tag,
    )

    # ── 5. Stream the graph ──────────────────────────────────────────
    initial_state: AxonState = {
        "messages": [*history, HumanMessage(content=request.message)],
        "user_id": user.id,
        "model_id": request.model_id,
        "memory_context": [],
        "memory_threshold": request.memory_threshold,
        "memory_limit": request.memory_limit,
    }

    collected: list[str] = []

    try:
        logger.info("[stream_chat] starting astream_events (v2)")
        # supervisor_node uses model.astream() internally, which causes
        # graph.astream_events(v2) to emit on_chat_model_stream for every token.
        #
        # Some models (e.g. DeepSeek) emit text content on pass 1 *before* or
        # *alongside* a tool_call ("Let me check..."). We MUST NOT forward those
        # tokens — they are internal routing narration, not the final answer.
        # Strategy: buffer pass-1 supervisor tokens; discard the buffer if
        # memory_agent fires; flush it if supervisor responds directly.
        supervisor_invocation = 0
        memory_agent_invoked = False
        pass1_buffer: list[str] = []

        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            node = event.get("metadata", {}).get("langgraph_node", "")

            # Track supervisor invocations so we know which pass we're on.
            if kind == "on_chain_start" and node == "supervisor":
                supervisor_invocation += 1
                continue

            # Memory agent starting — discard pass-1 narration, emit tool_use.
            if kind == "on_chain_start" and node == "memory_agent":
                memory_agent_invoked = True
                pass1_buffer.clear()
                yield _format(SSEEvent(type="tool_use", content="Searching memory…"))
                continue

            if kind != "on_chat_model_stream":
                continue
            if node != "supervisor":
                continue
            chunk = event.get("data", {}).get("chunk")
            if chunk is None:
                continue
            content = getattr(chunk, "content", "")
            if isinstance(content, list):
                # Some models return content as a list of blocks.
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if not isinstance(content, str):
                content = str(content)
            if not content:
                continue

            if supervisor_invocation <= 1 and not memory_agent_invoked:
                # Pass 1 before we know if a tool will be called — buffer.
                pass1_buffer.append(content)
            else:
                # Pass 2 (after memory agent), or pass 1 direct response:
                # flush any buffered pass-1 tokens first, then stream normally.
                if pass1_buffer:
                    for buffered in pass1_buffer:
                        collected.append(buffered)
                        yield _format(SSEEvent(type="token", content=buffered))
                    pass1_buffer.clear()
                collected.append(content)
                yield _format(SSEEvent(type="token", content=content))

        # If supervisor responded directly (no tool call), flush the buffer.
        if pass1_buffer:
            for buffered in pass1_buffer:
                collected.append(buffered)
                yield _format(SSEEvent(type="token", content=buffered))
            pass1_buffer.clear()

    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception("Chat stream failed for user [uid:%s]", _uid_tag)
        yield _format(SSEEvent(type="error", content="AI service unavailable"))

    finally:
        # ── 6. Persist assistant reply ────────────────────────────────────────
        if collected:
            await save_message(
                conversation_id, user.id, "assistant", "".join(collected)
            )
        yield _format(SSEEvent(type="done"))
