"""YouTube feature — DB CRUD for saved video transcripts.

Write path:
  1. INSERT into video_transcripts.
  2. Cross-index: call memory_service.create_memory() so memory_agent can
     surface the summary during future RAG recall.

Delete path:
  1. Query memory_entries for a row whose metadata->>'video_id' matches.
  2. Delete that memory entry (so search stops returning it).
  3. DELETE the video_transcripts row.
"""

import json
import logging
from typing import Any
from uuid import UUID

from app.db.supabase import get_supabase_client
from app.features.memory import service as memory_service
from app.features.youtube.schemas import VideoTranscriptOut

logger = logging.getLogger(__name__)

_SELECT_COLS = "id, youtube_url, video_id, title, channel, duration_s, summary, key_points, created_at"


def _row_to_out(row: dict[str, Any]) -> VideoTranscriptOut:
    return VideoTranscriptOut(
        id=row["id"],
        youtube_url=row["youtube_url"],
        video_id=row["video_id"],
        title=row.get("title"),
        channel=row.get("channel"),
        duration_s=row.get("duration_s"),
        summary=row["summary"],
        key_points=row.get("key_points") or [],
        created_at=row["created_at"],
    )


async def save_transcript(
    *,
    user_id: str,
    payload: dict[str, Any],
) -> VideoTranscriptOut:
    """Persist a YouTube video payload and cross-index its summary in memory.

    ``payload`` must conform to ``YouTubeVideoPayload`` fields:
    video_id, youtube_url, title, channel, duration_s, summary, key_points.

    Raises RuntimeError on DB failure (callers should catch and relay as a
    tool error string — not a 500).
    """
    client = await get_supabase_client()

    key_points = payload.get("key_points", [])
    if isinstance(key_points, str):
        try:
            key_points = json.loads(key_points)
        except json.JSONDecodeError:
            key_points = []

    row_data: dict[str, Any] = {
        "user_id": user_id,
        "youtube_url": payload["youtube_url"],
        "video_id": payload["video_id"],
        "title": payload.get("title"),
        "channel": payload.get("channel"),
        "duration_s": payload.get("duration_s"),
        "summary": payload["summary"],
        "key_points": key_points,
    }

    try:
        response = await client.table("video_transcripts").insert(row_data).execute()
    except Exception:
        logger.exception(
            "save_transcript: INSERT failed for video_id=%s user=%s",
            payload.get("video_id"),
            user_id,
        )
        raise

    if not response.data:
        raise RuntimeError("save_transcript: empty response from INSERT")

    saved = _row_to_out(response.data[0])

    # Cross-index: embed the summary in memory_entries so memory_agent can
    # recall it.  Failure is non-fatal — the transcript itself is already saved.
    title = payload.get("title") or "YouTube video"
    memory_text = f"[YouTube] {title}: {payload['summary']}"
    try:
        await memory_service.create_memory(
            user_id=user_id,
            content=memory_text,
            metadata={"source": "youtube", "video_id": payload["video_id"]},
        )
    except Exception:
        logger.exception(
            "save_transcript: cross-index into memory_entries failed video_id=%s",
            payload.get("video_id"),
        )
        # Non-fatal: transcript row was already committed.

    return saved


async def list_transcripts(user_id: str) -> list[VideoTranscriptOut]:
    """Return all saved transcripts for a user, newest first."""
    client = await get_supabase_client()
    try:
        response = (
            await client.table("video_transcripts")
            .select(_SELECT_COLS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.exception("list_transcripts: query failed user=%s", user_id)
        raise
    return [_row_to_out(row) for row in (response.data or [])]


async def get_transcript(
    transcript_id: UUID,
    user_id: str,
) -> VideoTranscriptOut | None:
    """Return a single transcript owned by user_id, or None if not found."""
    client = await get_supabase_client()
    try:
        response = (
            await client.table("video_transcripts")
            .select(_SELECT_COLS)
            .eq("id", str(transcript_id))
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception(
            "get_transcript: query failed id=%s user=%s", transcript_id, user_id
        )
        raise
    if not response.data:
        return None
    return _row_to_out(response.data[0])


async def delete_transcript(
    transcript_id: UUID,
    user_id: str,
) -> bool:
    """Delete a transcript and its cross-indexed memory entry.

    Returns True if the transcript row was found and deleted, False otherwise.
    Memory entry deletion is best-effort (failure is logged but not raised).
    """
    client = await get_supabase_client()

    # Fetch before deleting so we know the video_id for the memory lookup.
    row = await get_transcript(transcript_id, user_id)
    if row is None:
        return False

    # 1. Delete the cross-indexed memory entry (best-effort).
    try:
        mem_response = (
            await client.table("memory_entries")
            .delete()
            .eq("user_id", user_id)
            .eq("metadata->>video_id", row.video_id)
            .execute()
        )
        deleted_count = len(mem_response.data or [])
        if deleted_count:
            logger.debug(
                "delete_transcript: removed %d memory_entries for video_id=%s",
                deleted_count,
                row.video_id,
            )
    except Exception:
        logger.exception(
            "delete_transcript: memory_entries cleanup failed video_id=%s",
            row.video_id,
        )

    # 2. Delete the video_transcripts row.
    try:
        del_response = (
            await client.table("video_transcripts")
            .delete()
            .eq("id", str(transcript_id))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "delete_transcript: DELETE failed id=%s user=%s", transcript_id, user_id
        )
        raise

    return bool(del_response.data)
