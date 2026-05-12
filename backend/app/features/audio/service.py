"""TTS generation + Supabase Storage upload service (Phase 10C).

Uses OpenRouter's /audio/speech endpoint (openai/gpt-4o-mini-tts-2025-12-15).
The existing openrouter_api_key is reused — no separate OpenAI key needed.

Public API
----------
generate_tts(text, user_id) -> tuple[bytes, str]
    Call OpenRouter TTS endpoint, return (mp3_bytes, storage_filename).

upload_audio(audio_bytes, filename) -> str
    Upload mp3 bytes to Supabase Storage and return a signed URL (1 week).
"""

import logging
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.privacy import mask_pii
from app.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

# OpenAI TTS hard limit — truncate with a warning rather than failing.
_MAX_TTS_CHARS = 4096

# Signed URL expiry: 7 days in seconds.
_SIGNED_URL_TTL = 7 * 24 * 60 * 60  # 604 800 s


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

    # Mask PII before forwarding text to the external TTS provider.
    masked_text = await mask_pii(text)

    # OpenRouter /audio/speech endpoint — returns raw MP3 bytes (not JSON).
    payload = {
        "model": settings.tts_model,
        "input": masked_text,
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

    try:
        await client.storage.from_(bucket).upload(
            path=filename,
            file=audio_bytes,
            file_options={"content-type": "audio/mpeg"},
        )
    except Exception as exc:
        logger.exception("[upload_audio] Storage upload failed filename=%s", filename)
        raise RuntimeError("Failed to upload audio to storage.") from exc

    try:
        result = await client.storage.from_(bucket).create_signed_url(
            filename, _SIGNED_URL_TTL
        )
        signed_url: str = result["signedURL"]
    except Exception as exc:
        logger.exception(
            "[upload_audio] Failed to create signed URL filename=%s", filename
        )
        raise RuntimeError("Audio uploaded but could not generate a signed URL.") from exc

    logger.info("[upload_audio] signed URL created filename=%s", filename)
    return signed_url
