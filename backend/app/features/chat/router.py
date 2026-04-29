"""Chat router — POST /api/v1/chat/stream (SSE), JWT-protected."""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.chat.schemas import ChatRequest
from app.features.chat.service import stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: UserSchema = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the orchestrator response as Server-Sent Events.

    Each frame is `data: {"type":"token"|"error"|"done","content":"..."}\\n\\n`.
    The user_id passed downstream is derived strictly from the validated JWT,
    never from the request body.
    """
    return StreamingResponse(
        stream_chat(request, current_user),
        media_type="text/event-stream",
        headers={
            # Disable caches and proxy buffering so tokens reach the client
            # in real time (Cloudflare/Nginx default to buffering text streams).
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
