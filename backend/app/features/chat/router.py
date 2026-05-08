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
    update_conversation_title,
)
from app.features.chat.schemas import (
    ChatRequest,
    ConversationOut,
    MessageOut,
    UpdateConversationRequest,
)
from app.features.chat.service import stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
@limiter.limit("20/minute")
async def chat_stream(
    request: Request,
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
    request: Request,
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
    request: Request,
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
    request: Request,
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


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
@limiter.limit("60/minute")
async def update_conversation(
    request: Request,
    conversation_id: UUID,
    payload: UpdateConversationRequest,
    current_user: UserSchema = Depends(get_current_user),
) -> ConversationOut:
    """Update a conversation's title.

    Returns the updated conversation, or 404 if not found or not owned by the user.
    """
    updated = await update_conversation_title(
        str(conversation_id), current_user.id, payload.title
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Fetch and return the updated conversation
    from app.db.supabase import get_supabase_client

    client = await get_supabase_client()
    result = (
        await client.table("conversations")
        .select("id, title, model_id, created_at, updated_at")
        .eq("id", str(conversation_id))
        .eq("user_id", current_user.id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    row = result.data[0]
    return ConversationOut.model_validate(row)
