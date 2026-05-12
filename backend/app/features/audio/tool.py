"""Generate-TTS LangGraph node (Phase 10C).

Called by the orchestrator when the supervisor emits a ``generate_tts``
tool_call.  Synthesizes the requested text via OpenRouter TTS, uploads the
resulting mp3 to Supabase Storage, stores the result in ``state["pending_audio"]``
for the cross-turn save confirmation (Phase 10D), and returns a ToolMessage with
a markdown link the supervisor can present to the user.

The node body is never called via LangChain tool execution — it is invoked
directly by the orchestrator graph (same pattern as save_transcript_node).
"""

import json
import logging

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.state import AxonState
from app.features.audio import service as audio_service

logger = logging.getLogger(__name__)

# Imported by supervisor.py (tool name) and orchestrator.py (routing key).
GENERATE_TTS_TOOL_NAME = "generate_tts"


async def generate_tts_node(state: AxonState) -> dict:
    """LangGraph node: synthesize text to speech and upload to Storage.

    Reads the ``text`` argument from the supervisor's ``generate_tts`` tool_call,
    calls the audio service, and returns:
    - A ToolMessage closing the open tool_call (required for valid message history).
    - ``pending_audio`` state update with JSON ``{filename, signed_url, text_preview}``
      for the Phase 10D save confirmation flow.
    """
    # -- Resolve tool_call_id and text arg -----------------------------------
    tool_call_id: str | None = None
    text: str = ""

    last_msg = state["messages"][-1] if state["messages"] else None
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == GENERATE_TTS_TOOL_NAME:
                tool_call_id = tc["id"]
                text = tc.get("args", {}).get("text", "")
                break

    def _error(msg: str) -> dict:
        messages = []
        if tool_call_id:
            messages.append(ToolMessage(content=msg, tool_call_id=tool_call_id))
        return {"messages": messages}

    # -- Validate input -------------------------------------------------------
    if not text or not text.strip():
        logger.warning("[generate_tts_node] called with empty text")
        return _error(
            "No text provided for audio generation. "
            "Please specify what text you would like me to convert to speech."
        )

    user_id: str = state["user_id"]

    # -- Generate TTS + upload ------------------------------------------------
    try:
        audio_bytes, filename = await audio_service.generate_tts(text, user_id)
        signed_url = await audio_service.upload_audio(audio_bytes, filename)
    except RuntimeError as exc:
        logger.error("[generate_tts_node] service error: %s", exc)
        return _error(f"Audio generation failed: {exc}")
    except Exception:
        logger.exception("[generate_tts_node] unexpected error")
        return _error(
            "Audio generation failed due to an unexpected error. Please try again."
        )

    # -- Build pending_audio payload for Phase 10D save ----------------------
    pending = {
        "filename": filename,
        "signed_url": signed_url,
        "text_preview": text[:100],
    }
    pending_audio_json = json.dumps(pending)

    result_msg = (
        f"Audio generated successfully.\n\n"
        f"[Play audio]({signed_url})\n\n"
        f"Would you like me to save this to your audio library?"
    )

    logger.info(
        "[generate_tts_node] audio ready filename=%s user=%s",
        filename,
        user_id,
    )

    messages = []
    if tool_call_id:
        messages.append(ToolMessage(content=result_msg, tool_call_id=tool_call_id))

    return {"messages": messages, "pending_audio": pending_audio_json}
