"""Chat service — async generator that streams orchestrator output as SSE frames."""

import logging
from typing import AsyncIterator

from langchain_core.messages import HumanMessage

from app.agents.orchestrator import graph
from app.agents.state import AxonState
from app.features.auth.schemas import UserSchema
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

    Uses graph.astream_events(version="v2") and filters the
    `on_chat_model_stream` event, whose `data["chunk"]` is an AIMessageChunk
    carrying incremental token content. This decouples token streaming from
    graph topology: future nodes/tools won't disturb the wire format.

    Always emits a terminal `done` frame in the finally block so the client
    has a deterministic stop signal even when the upstream connection drops.
    """
    initial_state: AxonState = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": user.id,
        "model_id": request.model_id,
        "memory_context": [],
    }

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            if event.get("event") != "on_chat_model_stream":
                continue
            chunk = event.get("data", {}).get("chunk")
            if chunk is None:
                continue
            content = getattr(chunk, "content", "")
            # AIMessageChunk.content can be a list of content blocks (e.g. for
            # tool-using models). For the Phase 4 single-node graph it is a
            # plain string; coerce to str defensively.
            if not isinstance(content, str):
                content = str(content)
            if not content:
                continue
            yield _format(SSEEvent(type="token", content=content))

    except (
        Exception
    ) as exc:  # noqa: BLE001 — convert any upstream failure into an SSE error frame instead of a mid-stream 500
        # Log the full exception, but expose only a generic message to the
        # client to avoid leaking internal details.
        logger.error("Chat stream failed for user %s: %s", user.id, exc)
        yield _format(SSEEvent(type="error", content="AI service unavailable"))

    finally:
        yield _format(SSEEvent(type="done"))
