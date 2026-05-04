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
        yield _format(SSEEvent(type="error", content="Failed to initialise conversation"))
        yield _format(SSEEvent(type="done"))
        return

    # ── 2. Load history ───────────────────────────────────────────────────────
    history = await load_history(conversation_id, user.id, limit=40)

    # ── 3. Persist user message (original, unmasked) ────────────────────
    await save_message(conversation_id, user.id, "user", request.message)

    # ── 4. Emit start frame ───────────────────────────────────────
    yield _format(SSEEvent(type="start", content=conversation_id))
    logger.info("[stream_chat] start frame sent, invoking graph with model=%s uid=%s", request.model_id, _uid_tag)

    # ── 5. Stream the graph ──────────────────────────────────────────
    initial_state: AxonState = {
        "messages": [*history, HumanMessage(content=request.message)],
        "user_id": user.id,
        "model_id": request.model_id,
        "memory_context": [],
    }

    collected: list[str] = []

    try:
        logger.info("[stream_chat] starting astream_events (v2)")
        # supervisor_node uses model.astream() internally, which causes
        # graph.astream_events(v2) to emit on_chat_model_stream for every token.
        # We filter to the supervisor node only (skip memory_agent LLM calls).
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            if kind != "on_chat_model_stream":
                continue
            # Only forward tokens from the supervisor node.
            node = event.get("metadata", {}).get("langgraph_node")
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
            collected.append(content)
            yield _format(SSEEvent(type="token", content=content))

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
