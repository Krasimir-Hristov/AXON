"""Chat service — async generator that streams orchestrator output as SSE frames."""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import BaseMessage, HumanMessage

from app.agents.orchestrator import graph
from app.agents.state import AxonState
from app.core.privacy import mask_pii
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

    # ── 5. Stream the graph ──────────────────────────────────────────
    # Mask PII from history and current message before sending to the model.
    # save_message above persists the original unmasked text as intended.
    masked_message = await mask_pii(request.message)
    if history:
        masked_contents = await asyncio.gather(
            *(mask_pii(str(msg.content)) for msg in history)
        )
        masked_history: list[BaseMessage] = [
            type(msg)(content=mc) for msg, mc in zip(history, masked_contents)
        ]
    else:
        masked_history = list(history)

    initial_state: AxonState = {
        "messages": [*masked_history, HumanMessage(content=masked_message)],
        "user_id": user.id,
        "model_id": request.model_id,
        "memory_context": [],
    }

    collected: list[str] = []

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            if event.get("event") != "on_chat_model_stream":
                continue
            chunk = event.get("data", {}).get("chunk")
            if chunk is None:
                continue
            content = getattr(chunk, "content", "")
            # AIMessageChunk.content can be a list of content blocks (e.g. for
            # tool-using models). For the current graph it is a plain string;
            # coerce to str defensively.
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
