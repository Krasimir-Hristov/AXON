"""Chat schemas — request body, SSE event envelope, conversation and message outputs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/v1/chat/stream.

    Validated at the system boundary per OWASP A03 (input validation): the
    message length is bounded to prevent oversized payloads from reaching the
    LLM, and conversation_id, when provided, must parse as a UUID so that
    malformed identifiers are rejected with 422 before reaching the DB layer.
    """

    message: str = Field(min_length=1, max_length=10_000)
    model_id: str = Field(min_length=1, max_length=200)
    conversation_id: UUID | None = None
    memory_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    memory_limit: int = Field(default=5, ge=1, le=20)


class SSEEvent(BaseModel):
    """Internal envelope for events yielded by the chat streaming generator.

    Wire format on the client: each event is serialised as
        data: {"type":"...","content":"..."}\\n\\n

    Frame types:
        start    — first frame; content = conversation_id (UUID string)
        token    — incremental LLM token
        tool_use — memory agent started; content = human-readable status label
        error    — non-fatal upstream error; chat ends after this
        done     — terminal frame; always emitted in finally block
    """

    type: Literal["start", "token", "tool_use", "error", "done"]
    content: str = ""


class ConversationOut(BaseModel):
    """Response schema for a single conversation record."""

    id: UUID
    title: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=200)
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    """Response schema for a single persisted message."""

    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=0, max_length=100_000)
    created_at: datetime
