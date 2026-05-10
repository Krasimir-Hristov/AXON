"""Conversation service — DB CRUD for conversations and chat message history."""

import logging
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.db.supabase import get_supabase_client
from app.features.chat.schemas import ConversationOut, MessageOut

logger = logging.getLogger(__name__)

# Only user/assistant messages are replayed as LangChain history.
# System and tool messages are transient graph internals — not persisted.
_HISTORY_ROLES = {"user", "assistant"}
_ROLE_TO_MESSAGE: dict[str, type[BaseMessage]] = {
    "user": HumanMessage,
    "assistant": AIMessage,
}


async def get_or_create_conversation(
    user_id: str,
    conversation_id: UUID | None,
    model_id: str,
) -> str:
    """Return the validated conversation id, or create a new one.

    If conversation_id is provided but does not exist or does not belong to the
    user, silently creates a new conversation rather than leaking existence info.
    Returns the conversation id as a string.
    """
    client = await get_supabase_client()

    if conversation_id is not None:
        try:
            result = (
                await client.table("conversations")
                .select("id")
                .eq("id", str(conversation_id))
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.exception(
                "get_or_create_conversation: select failed conversation_id=%s",
                conversation_id,
            )
            raise
        if result.data:
            rows = cast(list[dict[str, Any]], result.data)
            return str(rows[0]["id"])

    try:
        result = (
            await client.table("conversations")
            .insert({"user_id": user_id, "model_id": model_id})
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "get_or_create_conversation: insert failed model_id=%s", model_id
        )
        raise
    inserted = cast(list[dict[str, Any]], result.data)
    return str(inserted[0]["id"])


async def save_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
) -> None:
    """Insert a message row. Logs on failure but does not raise.

    Graceful degradation: a DB write failure must not prevent the user from
    receiving the AI response. History gaps are preferable to broken chat.
    """
    client = await get_supabase_client()
    try:
        await (
            client.table("messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "role": role,
                    "content": content,
                }
            )
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "Failed to save %s message for conversation %s", role, conversation_id
        )


async def load_history(
    conversation_id: str,
    user_id: str,
    limit: int = 40,
) -> list[BaseMessage]:
    """Return the last `limit` user/assistant messages in chronological order.

    Default limit=40 covers 20 full turns (20 user + 20 assistant messages),
    matching the requirement of last 20 exchanges for model context window.
    Fetches newest-first, then reverses to give the LLM chronological order.
    """
    client = await get_supabase_client()
    try:
        result = (
            await client.table("messages")
            .select("role, content")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .in_("role", list(_HISTORY_ROLES))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception("Failed to load history for conversation %s", conversation_id)
        return []

    rows: list[dict[str, Any]] = cast(
        list[dict[str, Any]], list(reversed(result.data or []))
    )
    messages: list[BaseMessage] = []
    for row in rows:
        cls = _ROLE_TO_MESSAGE.get(str(row["role"]))
        if cls is not None:
            messages.append(cls(content=str(row["content"])))
    return messages


async def get_conversation_youtube_context(
    conversation_id: str,
    user_id: str,
) -> str:
    """Return the persisted youtube_context for a conversation, or '' if none."""
    client = await get_supabase_client()
    try:
        result = (
            await client.table("conversations")
            .select("youtube_context")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "get_conversation_youtube_context: query failed conversation_id=%s",
            conversation_id,
        )
        return ""
    rows = cast(list[dict[str, Any]], result.data or [])
    return str(rows[0].get("youtube_context") or "") if rows else ""


async def update_conversation_youtube_context(
    conversation_id: str,
    user_id: str,
    youtube_context: str,
) -> None:
    """Persist the youtube_context payload on the conversation row.

    Non-fatal: a failure is logged but does not raise so the main stream
    continues uninterrupted.
    """
    client = await get_supabase_client()
    try:
        await (
            client.table("conversations")
            .update({"youtube_context": youtube_context})
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "update_conversation_youtube_context: update failed conversation_id=%s",
            conversation_id,
        )


async def list_conversations(user_id: str, limit: int = 50) -> list[ConversationOut]:
    """Return conversations for a user, ordered by most recent activity first."""
    client = await get_supabase_client()
    try:
        result = (
            await client.table("conversations")
            .select("id, title, model_id, created_at, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception("list_conversations: query failed")
        raise
    rows: list[dict[str, Any]] = cast(list[dict[str, Any]], result.data or [])
    return [ConversationOut.model_validate(row) for row in rows]


async def get_messages(
    conversation_id: str,
    user_id: str,
    limit: int = 200,
) -> list[MessageOut]:
    """Return all messages for a conversation in chronological order.

    Raises HTTPException(404) when the conversation does not exist or does not
    belong to user_id.
    """
    client = await get_supabase_client()

    # Verify ownership before returning messages.
    try:
        conv = (
            await client.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "get_messages: ownership check failed conversation_id=%s", conversation_id
        )
        raise
    if not conv.data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        result = (
            await client.table("messages")
            .select("id, conversation_id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "get_messages: messages query failed conversation_id=%s", conversation_id
        )
        raise
    rows: list[dict[str, Any]] = cast(list[dict[str, Any]], result.data or [])
    return [MessageOut.model_validate(row) for row in rows]


async def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """Delete a conversation and all its messages via CASCADE.

    Returns True if a row was deleted, False if not found or not owned by user.
    """
    client = await get_supabase_client()
    try:
        result = (
            await client.table("conversations")
            .delete()
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "delete_conversation: failed conversation_id=%s", conversation_id
        )
        raise
    return bool(result.data)


async def update_conversation_title(
    conversation_id: str,
    user_id: str,
    title: str,
) -> ConversationOut | None:
    """Update a conversation's title.

    Returns the updated ConversationOut, or None if not found / not owned.

    Note: supabase-py v2 (postgrest-py) does not support .select() chaining
    after .update() on AsyncFilterRequestBuilder. Two queries are required:
    update first, then fetch the updated row.
    See: https://github.com/supabase-community/postgrest-py/issues/394
    """
    client = await get_supabase_client()
    try:
        # First query: apply the update. supabase-py v2 returns no data here.
        update_result = (
            await client.table("conversations")
            .update({"title": title})
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "update_conversation_title: update failed conversation_id=%s",
            conversation_id,
        )
        raise
    try:
        # Second query: fetch the freshly-updated row.
        select_result = (
            await client.table("conversations")
            .select("id, title, model_id, created_at, updated_at")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.exception(
            "update_conversation_title: select failed conversation_id=%s",
            conversation_id,
        )
        raise
    if not select_result.data:
        return None
    return ConversationOut.model_validate(select_result.data[0])
