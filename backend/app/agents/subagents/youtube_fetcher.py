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
    r"(?:https?://)?(?:www\.)?"
    r"(?:youtube\.com/watch\?(?:[^&\s]*&)*v=|youtu\.be/|youtube\.com/shorts/)"
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

    Uses YouTubeTranscriptApi().fetch(video_id).to_raw_data() — compatible with
    youtube-transcript-api >= 1.2.0. The synchronous call is offloaded to a thread
    pool via asyncio.to_thread (see module docstring for concurrency notes).

    Raises:
        TranscriptsDisabled: if the video has captions disabled.
        NoTranscriptFound: if no transcript is available for the video.
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # local import — heavy dep

    def _sync() -> list[dict[str, Any]]:
        api = YouTubeTranscriptApi()
        return api.fetch(video_id).to_raw_data()  # type: ignore[no-any-return]

    return await asyncio.to_thread(_sync)
