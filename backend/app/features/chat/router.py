"""Chat router — streaming chat and conversation CRUD endpoints, JWT-protected."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.chat.conversation_service import (
    delete_conversation,
    get_messages,
    list_conversations,
)
from app.features.chat.schemas import ChatRequest, ConversationOut, MessageOut
from app.features.chat.service import stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
@limiter.limit("20/minute")
async def chat_stream(
    _request: Request,
    payload: ChatRequest,
    current_user: UserSchema = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the orchestrator response as Server-Sent Events.

    Frame types: start (conversation_id), token, error, done.
    The user_id passed downstream is derived strictly from the validated JWT,
    never from the request body.
    """
    return StreamingResponse(
        stream_chat(payload, current_user),
        media_type="text/event-stream",
        headers={
            # Disable caches and proxy buffering so tokens reach the client
            # in real time (Cloudflare/Nginx default to buffering text streams).
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=list[ConversationOut])
@limiter.limit("60/minute")
async def get_conversations(
    _request: Request,  # noqa: ARG001 — required by SlowAPI rate limiter
    current_user: UserSchema = Depends(get_current_user),
) -> list[ConversationOut]:
    """Return all conversations for the authenticated user, newest first."""
    return await list_conversations(current_user.id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
@limiter.limit("60/minute")
async def get_conversation_messages(
    _request: Request,  # noqa: ARG001 — required by SlowAPI rate limiter
    conversation_id: UUID,
    current_user: UserSchema = Depends(get_current_user),
) -> list[MessageOut]:
    """Return all messages in a conversation in chronological order.

    Returns 404 if the conversation does not exist or does not belong to the
    authenticated user. FastAPI validates the UUID shape and returns 422 for
    malformed identifiers before they reach the DB layer.
    """
    # get_messages raises HTTPException(404) when not found / not owned
    return await get_messages(str(conversation_id), current_user.id)


@router.delete("/conversations/{conversation_id}", status_code=204)
@limiter.limit("30/minute")
async def remove_conversation(
    _request: Request,  # noqa: ARG001 — required by SlowAPI rate limiter
    conversation_id: UUID,
    current_user: UserSchema = Depends(get_current_user),
) -> Response:
    """Delete a conversation and all its messages.

    Returns 204 on success, 404 if not found or not owned by the user.
    """
    deleted = await delete_conversation(str(conversation_id), current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)
