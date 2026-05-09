"""YouTube subagent node — fetches transcript, summarizes hierarchically, returns ToolMessage.

Called by the orchestrator when the supervisor delegates a YouTube URL.

Workflow:
  1. Extract video_id from the last HumanMessage via regex.
  2. Fetch transcript (youtube-transcript-api) + oEmbed metadata in parallel.
  3. Split transcript into ~4 000-token text chunks.
  4. Parallel LLM calls (concurrency-limited) to summarize each chunk.
  5. Final LLM call combining chunk summaries → summary + key_points JSON.
  6. Return ToolMessage with JSON payload + update state["youtube_context"].

The subagent never streams — all LLM calls are fire-and-await using ainvoke().
The supervisor receives the condensed JSON payload, never the raw transcript.
"""

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.state import AxonState
from app.core.config import settings

logger = logging.getLogger(__name__)

# Imported by orchestrator.py to route the handoff tool call.
YOUTUBE_HANDOFF_TOOL_NAME = "transfer_to_youtube_agent"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:youtube\.com/watch\?(?:[^&\s]*&)*v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})"
)

# ~4 chars per token — rough but reliable for mixed-language transcripts.
_CHARS_PER_TOKEN = 4
_CHUNK_SIZE_CHARS = 4_000 * _CHARS_PER_TOKEN  # ≈16 000 chars per chunk
_MAX_CONCURRENT_SUMMARIES = 5  # rate-limit parallel chunk LLM calls

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CHUNK_SUMMARY_SYSTEM = "You are a precise, concise summarizer."

_CHUNK_SUMMARY_USER = """\
Summarize the following section of a video transcript in 3-5 concise sentences.
Focus on key ideas, facts, and takeaways. Do NOT include filler phrases like
"This section discusses" — go straight to the content.

TRANSCRIPT SECTION:
{chunk}
"""

_FINAL_SUMMARY_USER = """\
You are creating a final summary of a YouTube video titled "{title}" by "{channel}".
Below are summaries of each transcript section.

Produce:
1. A concise overall summary (3-6 sentences) covering the main thesis and key takeaways.
2. A list of 5-8 key points (the most important ideas, facts, or conclusions).

Respond ONLY with valid JSON — no markdown fences, no extra text:
{{"summary": "...", "key_points": ["...", "...", "..."]}}

SECTION SUMMARIES:
{section_summaries}
"""

# ---------------------------------------------------------------------------
# Model singleton (lazy init, non-streaming)
# ---------------------------------------------------------------------------

_summary_model: Any = None


def _get_summary_model() -> Any:
    """Return (or build) the cached non-streaming summarization model."""
    global _summary_model
    if _summary_model is None:
        _summary_model = init_chat_model(
            settings.youtube_summary_model,
            model_provider="openai",
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            streaming=False,
        )
    return _summary_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_video_id(text: str) -> str | None:
    """Extract the 11-character YouTube video ID from arbitrary text."""
    match = _YOUTUBE_URL_RE.search(text)
    return match.group(1) if match else None


async def _fetch_oembed(video_id: str) -> dict[str, str]:
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
        logger.warning("[youtube_agent] oEmbed fetch failed for video_id=%s", video_id)
        return {"title": "Unknown Title", "channel": "Unknown Channel"}


async def _fetch_transcript(video_id: str) -> list[dict[str, Any]]:
    """Fetch transcript entries; runs the blocking API call in a thread pool."""
    from youtube_transcript_api import YouTubeTranscriptApi  # local import — heavy dep

    def _sync() -> list[dict[str, Any]]:
        return YouTubeTranscriptApi.get_transcript(video_id)  # type: ignore[no-any-return]

    return await asyncio.to_thread(_sync)


def _build_chunks(transcript: list[dict[str, Any]]) -> list[str]:
    """Group transcript entries into text chunks of at most _CHUNK_SIZE_CHARS."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for entry in transcript:
        text = entry.get("text", "").strip()
        if not text:
            continue
        if current_len + len(text) > _CHUNK_SIZE_CHARS and current_parts:
            chunks.append(" ".join(current_parts))
            current_parts = []
            current_len = 0
        current_parts.append(text)
        current_len += len(text) + 1

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


async def _summarize_chunks(chunks: list[str]) -> list[str]:
    """Summarize each chunk with a concurrency-limited set of parallel LLM calls."""
    model = _get_summary_model()
    sem = asyncio.Semaphore(_MAX_CONCURRENT_SUMMARIES)

    async def _one(chunk: str, idx: int) -> str:
        async with sem:
            try:
                resp = await model.ainvoke(
                    [
                        SystemMessage(content=_CHUNK_SUMMARY_SYSTEM),
                        HumanMessage(content=_CHUNK_SUMMARY_USER.format(chunk=chunk)),
                    ]
                )
                content = resp.content if isinstance(resp.content, str) else str(resp.content)
                logger.debug("[youtube_agent] chunk %d summarized (%d chars)", idx, len(content))
                return content
            except Exception:
                logger.exception("[youtube_agent] chunk %d summarization failed", idx)
                return ""

    results = await asyncio.gather(*[_one(c, i) for i, c in enumerate(chunks)])
    return [r for r in results if r]


async def _build_final_summary(
    chunk_summaries: list[str],
    title: str,
    channel: str,
) -> tuple[str, list[str]]:
    """Combine chunk summaries into a final (summary, key_points) via one LLM call."""
    model = _get_summary_model()
    section_text = "\n\n".join(
        f"Section {i + 1}:\n{s}" for i, s in enumerate(chunk_summaries)
    )
    prompt = _FINAL_SUMMARY_USER.format(
        title=title,
        channel=channel,
        section_summaries=section_text,
    )
    try:
        resp = await model.ainvoke(
            [
                SystemMessage(content="You are a precise summarizer. Always respond with valid JSON only."),
                HumanMessage(content=prompt),
            ]
        )
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        # Strip markdown code fences if the model wraps its output.
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```[a-z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content.strip())
        data: dict[str, Any] = json.loads(content)
        return str(data.get("summary", "")), list(data.get("key_points", []))
    except Exception:
        logger.exception("[youtube_agent] final summary LLM call failed")
        # Graceful degradation: use the first few chunk summaries as the summary.
        fallback_summary = " ".join(chunk_summaries[:3])
        return fallback_summary, []


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def youtube_agent_node(state: AxonState) -> dict:
    """LangGraph node: fetch + hierarchically summarize a YouTube video.

    Returns a ToolMessage that closes the open ``transfer_to_youtube_agent``
    tool_call, plus a ``youtube_context`` state update containing the JSON
    payload for the supervisor to present and optionally save.
    """
    # -- Resolve tool_call_id so the ToolMessage closes the handoff ----------
    tool_call_id: str | None = None
    last_msg = state["messages"][-1] if state["messages"] else None
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == YOUTUBE_HANDOFF_TOOL_NAME:
                tool_call_id = tc["id"]
                break

    # -- Extract YouTube URL from the last HumanMessage ----------------------
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    raw_text: str = ""
    if last_human:
        raw_text = (
            last_human.content
            if isinstance(last_human.content, str)
            else " ".join(
                p
                if isinstance(p, str)
                else p.get("text", "")
                if isinstance(p, dict)
                else getattr(p, "text", "")
                for p in last_human.content
            )
        )

    video_id = _extract_video_id(raw_text)

    def _error_response(msg: str) -> dict:
        messages = []
        if tool_call_id:
            messages.append(
                ToolMessage(
                    content=msg,
                    tool_call_id=tool_call_id,
                    name=YOUTUBE_HANDOFF_TOOL_NAME,
                )
            )
        return {"messages": messages, "youtube_context": ""}

    if not video_id:
        logger.warning("[youtube_agent] no YouTube URL found in message")
        return _error_response("No valid YouTube URL found in your message.")

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("[youtube_agent] processing video_id=%s", video_id)

    # -- Fetch transcript + metadata in parallel -----------------------------
    try:
        from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

        transcript_entries, oembed = await asyncio.gather(
            _fetch_transcript(video_id),
            _fetch_oembed(video_id),
        )
    except TranscriptsDisabled:  # type: ignore[possibly-undefined]
        logger.warning("[youtube_agent] transcripts disabled for video_id=%s", video_id)
        return _error_response(
            "This video has transcripts/captions disabled — I can't fetch the content."
        )
    except NoTranscriptFound:  # type: ignore[possibly-undefined]
        logger.warning("[youtube_agent] no transcript found for video_id=%s", video_id)
        return _error_response(
            "No transcript was found for this video. It may not have captions available."
        )
    except Exception:
        logger.exception("[youtube_agent] fetch failed for video_id=%s", video_id)
        return _error_response(
            "Failed to fetch the video transcript. The video may be unavailable or private."
        )

    title: str = oembed["title"]
    channel: str = oembed["channel"]

    # -- Calculate duration from the last transcript entry -------------------
    duration_s = 0
    if transcript_entries:
        last_entry = transcript_entries[-1]
        duration_s = int(
            last_entry.get("start", 0) + last_entry.get("duration", 0)
        )

    logger.info(
        "[youtube_agent] title=%r channel=%r entries=%d duration_s=%d",
        title,
        channel,
        len(transcript_entries),
        duration_s,
    )

    # -- Hierarchical summarization ------------------------------------------
    chunks = _build_chunks(transcript_entries)
    logger.info("[youtube_agent] built %d chunks for video_id=%s", len(chunks), video_id)

    chunk_summaries = await _summarize_chunks(chunks)
    if not chunk_summaries:
        logger.error("[youtube_agent] all chunk summaries failed for video_id=%s", video_id)
        return _error_response(
            "Failed to summarize the video transcript. Please try again."
        )

    summary, key_points = await _build_final_summary(chunk_summaries, title, channel)

    # -- Build JSON payload --------------------------------------------------
    payload: dict[str, Any] = {
        "video_id": video_id,
        "youtube_url": youtube_url,
        "title": title,
        "channel": channel,
        "duration_s": duration_s,
        "summary": summary,
        "key_points": key_points,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    logger.info(
        "[youtube_agent] done video_id=%s summary_len=%d key_points=%d",
        video_id,
        len(summary),
        len(key_points),
    )

    messages: list[ToolMessage] = []
    if tool_call_id:
        messages.append(
            ToolMessage(
                content=payload_json,
                tool_call_id=tool_call_id,
                name=YOUTUBE_HANDOFF_TOOL_NAME,
            )
        )

    return {"messages": messages, "youtube_context": payload_json}
