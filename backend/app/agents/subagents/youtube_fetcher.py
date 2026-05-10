"""YouTube data fetching: video ID extraction, oEmbed metadata, transcript retrieval.

Note on thread-pool usage in fetch_transcript:
  YouTubeTranscriptApi.fetch() is a synchronous call offloaded via
  asyncio.to_thread. Each concurrent transcript request consumes one thread from
  asyncio's default executor (default: min(32, cpu_count+4) threads). For the
  current single-video-per-request pattern this is acceptable. If high concurrency
  is expected, add an asyncio.Semaphore at the call site (e.g. in youtube_agent_node)
  to cap the number of simultaneous transcript fetches and avoid exhausting the pool.
"""

import asyncio
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?"
    r"(?:(?:www|m)\.youtube\.com/"
    r"(?:watch\?(?:[^&\s]*&)*v=|shorts/|live/|embed/)"
    r"|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_video_id(text: str) -> str | None:
    """Return the 11-char YouTube video ID extracted from arbitrary text, or None."""
    match = _YOUTUBE_URL_RE.search(text)
    return match.group(1) if match else None


async def fetch_oembed(video_id: str) -> dict[str, str]:
    """Fetch title + channel name via YouTube oEmbed (no API key required)."""
    url = (
        "https://www.youtube.com/oembed"
        f"?url=https://www.youtube.com/watch%3Fv%3D{video_id}&format=json"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "title": data.get("title", "Unknown Title"),
                "channel": data.get("author_name", "Unknown Channel"),
            }
    except Exception:
        logger.warning(
            "[youtube_fetcher] oEmbed fetch failed for video_id=%s", video_id
        )
        return {"title": "Unknown Title", "channel": "Unknown Channel"}


async def fetch_transcript(video_id: str) -> list[dict[str, Any]]:
    """Fetch transcript entries using the youtube-transcript-api v1.x instance API.

    Lists all available transcripts for the video (any language), prefers manual
    over auto-generated captions, and returns the first available one.
    The synchronous call is offloaded to a thread pool via asyncio.to_thread.

    Raises:
        TranscriptsDisabled: if the video has captions disabled.
        NoTranscriptFound: if no transcript is available for the video.
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # local import — heavy dep

    def _sync() -> list[dict[str, Any]]:
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            # Collect all available language codes — manual transcripts are yielded
            # before auto-generated ones by the library, so find_transcript() will
            # prefer manual captions when both exist for the same language.
            available_languages = [t.language_code for t in transcript_list]
            logger.debug(
                "[youtube_fetcher] video_id=%s available transcript languages: %s",
                video_id,
                available_languages,
            )
            return (
                transcript_list.find_transcript(available_languages).fetch().to_raw_data()  # type: ignore[no-any-return]
            )
        except Exception as exc:
            logger.exception(
                "[youtube_fetcher] transcript fetch failed video_id=%s: %s",
                video_id,
                exc,
            )
            raise

    return await asyncio.to_thread(_sync)
