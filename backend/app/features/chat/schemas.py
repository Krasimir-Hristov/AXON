"""Chat schemas — request body and SSE event envelope."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat/stream.

    Validated at the system boundary per OWASP A03 (input validation): the
    message length is bounded to prevent oversized payloads from reaching the
    LLM, and conversation_id is optional until persistence is wired up.
    """

    message: str = Field(min_length=1, max_length=10_000)
    model_id: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = None


class SSEEvent(BaseModel):
    """Internal envelope for events yielded by the chat streaming generator.

    Wire format on the client: each event is serialised as
        data: {"type":"...","content":"..."}\\n\\n
    """

    type: Literal["token", "error", "done"]
    content: str = ""
