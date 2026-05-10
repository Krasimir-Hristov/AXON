"""Save-transcript LangGraph node.

Called by the orchestrator when the supervisor emits a ``save_video_transcript``
tool_call. Reads the JSON payload from ``state["youtube_context"]``, persists
it to ``video_transcripts``, and cross-indexes the summary in ``memory_entries``.

The node body is never called via LangChain tool execution — it is invoked
directly by the orchestrator graph (same pattern as memory_agent_node and
youtube_agent_node).
"""

import json
import logging

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.state import AxonState
from app.features.youtube import service

logger = logging.getLogger(__name__)

# Imported by supervisor.py (tool name) and orchestrator.py (routing key).
SAVE_TRANSCRIPT_TOOL_NAME = "save_video_transcript"


async def save_transcript_node(state: AxonState) -> dict:
    """LangGraph node: save the pending YouTube transcript to the DB.

    Reads ``state["youtube_context"]`` (set by youtube_agent_node) and
    ``state["user_id"]``, calls the youtube service, and returns a ToolMessage
    that closes the open ``save_video_transcript`` tool_call so the message
    history remains valid for downstream LLM calls.
    """
    # -- Resolve tool_call_id to close the open tool_call --------------------
    tool_call_id: str | None = None
    last_msg = state["messages"][-1] if state["messages"] else None
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == SAVE_TRANSCRIPT_TOOL_NAME:
                tool_call_id = tc["id"]
                break

    def _error(msg: str) -> dict:
        messages = []
        if tool_call_id:
            messages.append(ToolMessage(content=msg, tool_call_id=tool_call_id))
        return {"messages": messages}

    # -- Validate youtube_context -------------------------------------------
    youtube_context = state.get("youtube_context", "")
    if not youtube_context:
        logger.warning(
            "[save_transcript_node] youtube_context is empty — nothing to save"
        )
        return _error(
            "No YouTube video data found to save. "
            "Please share a YouTube URL first so I can fetch and summarize it."
        )

    try:
        payload = json.loads(youtube_context)
    except json.JSONDecodeError:
        logger.exception("[save_transcript_node] youtube_context is not valid JSON")
        return _error(
            "Failed to parse video data — please try fetching the video again."
        )

    required = ("video_id", "youtube_url", "summary")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        logger.error("[save_transcript_node] payload missing fields: %s", missing)
        return _error(f"Video data is incomplete (missing: {', '.join(missing)}).")

    # -- Persist ------------------------------------------------------------
    user_id: str = state["user_id"]
    try:
        saved = await service.save_transcript(user_id=user_id, payload=payload)
    except Exception:
        logger.exception(
            "[save_transcript_node] save_transcript failed video_id=%s",
            payload.get("video_id"),
        )
        return _error("Failed to save the transcript. Please try again in a moment.")

    title = saved.title or "the video"
    result_msg = (
        f"Saved ✓ — **{title}** has been added to your library "
        f"and indexed in your memory for future recall.\n"
        f"Transcript ID: `{saved.id}`"
    )

    logger.info(
        "[save_transcript_node] saved transcript id=%s video_id=%s user=%s",
        saved.id,
        saved.video_id,
        user_id,
    )

    messages = []
    if tool_call_id:
        messages.append(ToolMessage(content=result_msg, tool_call_id=tool_call_id))

    return {"messages": messages}
