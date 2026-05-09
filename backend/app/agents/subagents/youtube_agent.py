"""YouTube subagent node — orchestrates fetch + summarization, returns ToolMessage.

Delegates to:
- youtube_fetcher:    video ID extraction, oEmbed metadata, transcript retrieval
- youtube_chunker:    split transcript into fixed-size text chunks
- youtube_summarizer: parallel chunk LLM summaries + Pydantic-validated final summary

The supervisor receives a condensed JSON payload, never the raw transcript.
"""

import asyncio
import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

from app.agents.state import AxonState
from app.agents.subagents.youtube_chunker import build_chunks
from app.agents.subagents.youtube_fetcher import extract_video_id, fetch_oembed, fetch_transcript
from app.agents.subagents.youtube_summarizer import (
    YouTubeVideoPayload,
    build_final_summary,
    summarize_chunks,
)

logger = logging.getLogger(__name__)

# Exported constant — imported by supervisor.py and orchestrator.py to route the handoff.
YOUTUBE_HANDOFF_TOOL_NAME = "transfer_to_youtube_agent"


async def youtube_agent_node(state: AxonState) -> dict:
    """LangGraph node: fetch + hierarchically summarize a YouTube video.

    Returns a ToolMessage that closes the open ``transfer_to_youtube_agent``
    tool_call, plus a ``youtube_context`` state update containing the validated
    JSON payload for the supervisor to present.
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

    video_id = extract_video_id(raw_text)

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
        transcript_entries, oembed = await asyncio.gather(
            fetch_transcript(video_id),
            fetch_oembed(video_id),
        )
    except TranscriptsDisabled:
        logger.warning("[youtube_agent] transcripts disabled for video_id=%s", video_id)
        return _error_response(
            "This video has transcripts/captions disabled — I can't fetch the content."
        )
    except NoTranscriptFound:
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
        duration_s = int(last_entry.get("start", 0) + last_entry.get("duration", 0))

    logger.info(
        "[youtube_agent] title=%r channel=%r entries=%d duration_s=%d",
        title, channel, len(transcript_entries), duration_s,
    )

    # -- Hierarchical summarization ------------------------------------------
    chunks = build_chunks(transcript_entries)
    logger.info("[youtube_agent] built %d chunks for video_id=%s", len(chunks), video_id)

    chunk_summaries = await summarize_chunks(chunks)
    if not chunk_summaries:
        logger.error("[youtube_agent] all chunk summaries failed for video_id=%s", video_id)
        return _error_response("Failed to summarize the video transcript. Please try again.")

    summary, key_points = await build_final_summary(chunk_summaries, title, channel)

    # -- Build and validate the full payload ---------------------------------
    payload = YouTubeVideoPayload(
        video_id=video_id,
        youtube_url=youtube_url,
        title=title,
        channel=channel,
        duration_s=duration_s,
        summary=summary,
        key_points=key_points,
    )
    payload_json = payload.model_dump_json()

    logger.info(
        "[youtube_agent] done video_id=%s summary_len=%d key_points=%d",
        video_id, len(summary), len(key_points),
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
