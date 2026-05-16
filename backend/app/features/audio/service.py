"""TTS generation + Supabase Storage upload + Audio Library service.

Uses OpenRouter's /audio/speech endpoint (openai/gpt-4o-mini-tts-2025-12-15).
The existing openrouter_api_key is reused — no separate OpenAI key needed.

Public API
----------
generate_tts(text, user_id) -> tuple[bytes, str]
    Call OpenRouter TTS endpoint, return (mp3_bytes, storage_filename).

store_temp_audio(audio_bytes) -> str
    Write mp3 bytes to a system temp file and return a token (UUID).
    TTL: 3600 s.  Survives uvicorn --reload (file system is persistent).

retrieve_temp_audio(token) -> bytes | None
    Return bytes for the given token, or None if missing / expired.

delete_temp_audio(token) -> None
    Remove an entry from the temp store (called after successful upload).

upload_audio(audio_bytes, filename) -> str
    Upload mp3 bytes to Supabase Storage and return a signed URL (1 week).

save_audio_entry(user_id, filename, title, source_type, source_id) -> AudioEntryOut
    Persist a saved audio entry to the audio_entries table.

list_audio_entries(user_id) -> list[AudioEntryOut]
    Return all saved audio entries for a user with fresh signed URLs.

delete_audio_entry(id, user_id) -> bool
    Delete an audio entry from the DB and its file from Storage.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from uuid import UUID, uuid4
from typing import Any

import httpx

from app.core.config import settings
from app.db.supabase import get_supabase_client
from app.features.audio.schemas import AudioEntryOut

logger = logging.getLogger(__name__)

# OpenAI TTS hard limit — truncate with a warning rather than failing.
_MAX_TTS_CHARS = 4096

# Signed URL expiry: 7 days in seconds.
_SIGNED_URL_TTL = 7 * 24 * 60 * 60  # 604 800 s

# ---------------------------------------------------------------------------
# Temp audio store — bytes written to the system temp directory.
# Survives uvicorn --reload (file system is persistent across restarts).
# TTL enforced at retrieval time via file mtime.
# ---------------------------------------------------------------------------

_TEMP_DIR = Path(tempfile.gettempdir())
_TEMP_PREFIX = "axon_audio_"
_TEMP_TTL = 3600  # 1 hour


async def store_temp_audio(audio_bytes: bytes) -> str:
    """Write mp3 bytes to a temp file and return a UUID token."""
    token = str(uuid4())
    path = _TEMP_DIR / f"{_TEMP_PREFIX}{token}.mp3"
    await asyncio.to_thread(path.write_bytes, audio_bytes)
    return token


async def retrieve_temp_audio(token: str) -> bytes | None:
    """Return mp3 bytes for the given token, or None if missing / expired."""
    path = _TEMP_DIR / f"{_TEMP_PREFIX}{token}.mp3"

    def _read() -> bytes | None:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > _TEMP_TTL:
            path.unlink(missing_ok=True)
            return None
        return path.read_bytes()

    return await asyncio.to_thread(_read)


async def delete_temp_audio(token: str) -> None:
    """Delete the temp file after a successful Storage upload."""
    path = _TEMP_DIR / f"{_TEMP_PREFIX}{token}.mp3"
    await asyncio.to_thread(lambda: path.unlink(missing_ok=True))


async def generate_tts(text: str, user_id: str) -> tuple[bytes, str]:
    """Call OpenRouter TTS endpoint and return (mp3_bytes, storage_filename).

    Args:
        text:     The text to synthesize. Truncated to 4 096 chars if longer.
        user_id:  Authenticated user UUID — used to scope the storage path.

    Returns:
        A tuple of (raw mp3 bytes, storage filename scoped to user_id).

    Raises:
        RuntimeError: If the OpenRouter API call fails or the response is malformed.
    """
    if len(text) > _MAX_TTS_CHARS:
        logger.warning(
            "[generate_tts] text length %d exceeds limit %d — truncating",
            len(text),
            _MAX_TTS_CHARS,
        )
        text = text[:_MAX_TTS_CHARS]

    if not text.strip():
        raise RuntimeError("Cannot generate TTS for empty text.")

    # OpenRouter /audio/speech endpoint — returns raw MP3 bytes (not JSON).
    payload = {
        "model": settings.tts_model,
        "input": text,
        "voice": settings.tts_voice,
        "response_format": "mp3",
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    tts_url = f"{settings.openrouter_base_url}/audio/speech"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(tts_url, json=payload, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "[generate_tts] OpenRouter returned %d url=%s",
            exc.response.status_code,
            tts_url,
        )
        raise RuntimeError(
            f"TTS API request failed with status {exc.response.status_code}."
        ) from exc
    except httpx.RequestError as exc:
        logger.error("[generate_tts] request error url=%s: %s", tts_url, exc)
        raise RuntimeError("TTS API request failed due to a network error.") from exc

    audio_bytes = response.content

    # Validate the response is non-empty and looks like an MP3 before uploading.
    content_type = response.headers.get("content-type", "")
    mp3_magic = audio_bytes[:3] if len(audio_bytes) >= 3 else b""
    is_mp3_magic = mp3_magic == b"ID3" or (
        len(audio_bytes) >= 2
        and audio_bytes[0] == 0xFF
        and (audio_bytes[1] & 0xE0) == 0xE0
    )
    if not audio_bytes or (not content_type.startswith("audio/") and not is_mp3_magic):
        logger.error(
            "[generate_tts] unexpected TTS response status=%d content-type=%s bytes=%d",
            response.status_code,
            content_type,
            len(audio_bytes),
        )
        raise RuntimeError("TTS API returned an invalid or empty audio response.")

    file_uuid = uuid4()
    filename = f"{user_id}/{file_uuid}.mp3"
    logger.info(
        "[generate_tts] synthesized %d bytes uuid=%s", len(audio_bytes), file_uuid
    )
    return audio_bytes, filename


async def upload_audio(audio_bytes: bytes, filename: str) -> str:
    """Upload mp3 bytes to Supabase Storage and return a signed URL (1 week).

    Args:
        audio_bytes: Raw MP3 bytes to upload.
        filename:    Storage path in the form ``{user_id}/{uuid}.mp3``.

    Returns:
        A signed URL valid for 7 days.

    Raises:
        RuntimeError: If the Supabase Storage upload or URL generation fails.
    """
    client = await get_supabase_client()
    bucket = settings.audio_bucket

    # Use only the basename (UUID part) in logs — never the full path (contains user_id).
    safe_log_name = filename.split("/")[-1] if "/" in filename else filename

    try:
        await client.storage.from_(bucket).upload(
            path=filename,
            file=audio_bytes,
            file_options={"content-type": "audio/mpeg"},
        )
    except Exception as exc:
        logger.exception("[upload_audio] Storage upload failed uuid=%s", safe_log_name)
        raise RuntimeError("Failed to upload audio to storage.") from exc

    try:
        result = await client.storage.from_(bucket).create_signed_url(
            filename, _SIGNED_URL_TTL
        )
        signed_url: str = result["signedURL"]
    except Exception as exc:
        logger.exception(
            "[upload_audio] Failed to create signed URL uuid=%s", safe_log_name
        )
        raise RuntimeError(
            "Audio uploaded but could not generate a signed URL."
        ) from exc

    logger.info("[upload_audio] signed URL created uuid=%s", safe_log_name)
    return signed_url


# ---------------------------------------------------------------------------
# Audio Library CRUD (Phase 10D)
# ---------------------------------------------------------------------------

_SELECT_COLS = "id, filename, title, source_type, source_id, duration_s, created_at"


def _row_to_entry(row: dict[str, Any], signed_url: str) -> AudioEntryOut:
    return AudioEntryOut(
        id=row["id"],
        filename=row["filename"],
        title=row["title"],
        source_type=row.get("source_type", "custom"),
        source_id=row.get("source_id"),
        duration_s=row.get("duration_s"),
        created_at=row["created_at"],
        signed_url=signed_url,
    )


async def save_audio_entry(
    *,
    user_id: str,
    filename: str,
    title: str,
    source_type: str = "custom",
    source_id: str | None = None,
) -> AudioEntryOut:
    """Persist a saved audio entry to the audio_entries table.

    Raises RuntimeError on DB failure.
    """
    client = await get_supabase_client()

    row_data: dict[str, Any] = {
        "user_id": user_id,
        "filename": filename,
        "title": title,
        "source_type": source_type,
    }
    if source_id:
        row_data["source_id"] = source_id

    try:
        response = await client.table("audio_entries").insert(row_data).execute()
    except Exception as exc:
        logger.exception("[save_audio_entry] INSERT failed user=%s", user_id[:8])
        raise RuntimeError("Failed to save audio entry to database.") from exc

    if not response.data:
        raise RuntimeError("INSERT returned no data.")

    row = response.data[0]

    # Generate a fresh signed URL for the returned entry.
    safe_log_name = filename.split("/")[-1] if "/" in filename else filename
    try:
        result = await client.storage.from_(settings.audio_bucket).create_signed_url(
            filename, _SIGNED_URL_TTL
        )
        signed_url: str = result["signedURL"]
    except Exception as exc:
        logger.exception("[save_audio_entry] signed URL failed uuid=%s", safe_log_name)
        raise RuntimeError("Entry saved but could not generate a signed URL.") from exc

    logger.info("[save_audio_entry] saved uuid=%s", safe_log_name)
    return _row_to_entry(row, signed_url)


async def list_audio_entries(user_id: str) -> list[AudioEntryOut]:
    """Return all saved audio entries for a user with fresh signed URLs (1 week).

    Ordered by created_at DESC.
    """
    client = await get_supabase_client()

    try:
        response = (
            await client.table("audio_entries")
            .select(_SELECT_COLS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.exception("[list_audio_entries] SELECT failed user=%s", user_id[:8])
        return []

    rows = response.data or []
    if not rows:
        return []

    # Sign all URLs concurrently instead of sequentially.
    async def _sign_row(row: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
        try:
            result = await client.storage.from_(
                settings.audio_bucket
            ).create_signed_url(row["filename"], _SIGNED_URL_TTL)
            return row, result["signedURL"]
        except Exception:
            safe = (
                row["filename"].split("/")[-1]
                if "/" in row["filename"]
                else row["filename"]
            )
            logger.warning(
                "[list_audio_entries] signed URL failed uuid=%s — skipping", safe
            )
            return None

    results = await asyncio.gather(*(_sign_row(row) for row in rows))
    entries: list[AudioEntryOut] = []
    for item in results:
        if item is not None:
            entries.append(_row_to_entry(item[0], item[1]))
    return entries


async def delete_audio_entry(entry_id: UUID, user_id: str) -> bool:
    """Delete audio entry from DB and its file from Supabase Storage.

    Returns True if the entry was found and deleted, False otherwise.
    """
    client = await get_supabase_client()

    # Fetch the row first to get the filename (needed for Storage deletion).
    try:
        fetch = (
            await client.table("audio_entries")
            .select("id, filename")
            .eq("id", str(entry_id))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception("[delete_audio_entry] SELECT failed id=%s", entry_id)
        return False

    if not fetch.data:
        return False

    filename: str = fetch.data[0]["filename"]
    safe_log_name = filename.split("/")[-1] if "/" in filename else filename

    # Delete from Storage first — if this fails the DB row is preserved (consistent state).
    try:
        await client.storage.from_(settings.audio_bucket).remove([filename])
    except Exception:
        logger.warning(
            "[delete_audio_entry] Storage remove failed uuid=%s — aborting delete",
            safe_log_name,
        )
        return False

    # Only remove the DB row after successful Storage deletion.
    try:
        await (
            client.table("audio_entries")
            .delete()
            .eq("id", str(entry_id))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        logger.exception(
            "[delete_audio_entry] DB DELETE failed after storage removal id=%s uuid=%s",
            entry_id,
            safe_log_name,
        )
        return False

    logger.info("[delete_audio_entry] deleted uuid=%s", safe_log_name)
    return True
