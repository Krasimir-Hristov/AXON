"""rename_audio_entry — extracted from service.py to stay under the 300-line limit."""

import logging
from uuid import UUID

from app.core.config import settings
from app.db.supabase import get_supabase_client
from app.features.audio.schemas import AudioEntryOut
from app.features.audio.service import (
    _SELECT_COLS,
    _SIGNED_URL_TTL,
    _row_to_entry,
)

logger = logging.getLogger(__name__)


async def rename_audio_entry(
    entry_id: UUID, user_id: str, title: str
) -> AudioEntryOut | None:
    """Rename an audio entry's title.

    Returns the updated AudioEntryOut, or None if the entry was not found.
    Raises RuntimeError on DB or Storage failure.
    """
    client = await get_supabase_client()

    # UPDATE — postgrest-py's FilterRequestBuilder has no .select() after .eq(),
    # so we do the update and re-fetch in a separate query.
    try:
        await (
            client.table("audio_entries")
            .update({"title": title})
            .eq("id", str(entry_id))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception("[rename_audio_entry] UPDATE failed id=%s", entry_id)
        raise RuntimeError("Failed to rename audio entry.") from None

    # Re-fetch the updated row (also confirms the entry belongs to this user).
    try:
        fetch = (
            await client.table("audio_entries")
            .select(_SELECT_COLS)
            .eq("id", str(entry_id))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "[rename_audio_entry] SELECT after UPDATE failed id=%s", entry_id
        )
        raise RuntimeError("Failed to fetch renamed audio entry.") from None

    if not fetch.data:
        return None

    row = fetch.data[0]
    filename: str = row["filename"]
    safe_log = filename.split("/")[-1] if "/" in filename else filename

    try:
        result = await client.storage.from_(settings.audio_bucket).create_signed_url(
            filename, _SIGNED_URL_TTL
        )
        signed_url: str = result["signedURL"]
    except Exception:
        logger.exception("[rename_audio_entry] signed URL failed uuid=%s", safe_log)
        raise RuntimeError("Title updated but failed to generate signed URL.") from None

    logger.info("[rename_audio_entry] renamed uuid=%s", safe_log)
    return _row_to_entry(row, signed_url)
