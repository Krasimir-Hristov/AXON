"""Generate-TTS and Save-Audio LangGraph nodes (Phase 10C + 10D).

generate_tts_node  — synthesizes text to speech via OpenRouter TTS, writes the
                     mp3 bytes to a system temp file (NOT in Supabase Storage),
                     stores a temp token in ``state["pending_audio"]``
                     for the cross-turn save confirmation, and returns a
                     ToolMessage with a playable /audio/temp/{token} URL.

save_audio_entry_node — reads ``state["pending_audio"]``, retrieves the bytes
                        from the temp store, uploads to Supabase Storage, saves
                        the DB entry, and returns a ToolMessage confirming the save.

Neither node is called via LangChain tool execution — both are invoked directly
by the orchestrator graph (same pattern as save_transcript_node).
"""

import logging

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.state import AxonState
from app.features.audio import service as audio_service

logger = logging.getLogger(__name__)

# Imported by supervisor.py (tool name) and orchestrator.py (routing key).
GENERATE_TTS_TOOL_NAME = "generate_tts"


async def generate_tts_node(state: AxonState) -> dict:
    """LangGraph node: synthesize text to speech and store bytes in temp store.

    Reads the ``text`` argument from the supervisor's ``generate_tts`` tool_call,
    calls the audio service, and returns:
    - A ToolMessage with a playable /api/v1/audio/temp/{token} URL.
    - ``pending_audio`` state update with ``{filename, temp_token, text_preview}``
      for the Phase 10D save confirmation flow.

    The mp3 is NOT uploaded to Supabase Storage until the user confirms saving.
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

    # -- Generate TTS + store in temp (no Storage upload yet) ---------------
    try:
        audio_bytes, filename = await audio_service.generate_tts(text, user_id)
        temp_token = await audio_service.store_temp_audio(audio_bytes)
    except RuntimeError as exc:
        logger.error("[generate_tts_node] service error: %s", exc)
        return _error(f"Audio generation failed: {exc}")
    except Exception:
        logger.exception("[generate_tts_node] unexpected error")
        return _error(
            "Audio generation failed due to an unexpected error. Please try again."
        )

    # -- Build pending_audio payload for Phase 10D save ----------------------
    pending: dict[str, str] = {
        "filename": filename,
        "temp_token": temp_token,
        "text_preview": text[:100],
    }

    temp_url = f"/api/v1/audio/temp/{temp_token}"
    result_msg = (
        f"Audio generated successfully.\n\n"
        f"[Play audio]({temp_url})\n\n"
        f"Would you like me to save this to your audio library?"
    )

    logger.info(
        "[generate_tts_node] audio ready token=%s filename=%s",
        temp_token[:8],
        filename,
    )

    messages = []
    if tool_call_id:
        messages.append(ToolMessage(content=result_msg, tool_call_id=tool_call_id))

    return {"messages": messages, "pending_audio": pending}


# ---------------------------------------------------------------------------
# Save-audio-entry node (Phase 10D)
# ---------------------------------------------------------------------------

SAVE_AUDIO_TOOL_NAME = "save_audio_entry"


async def save_audio_entry_node(state: AxonState) -> dict:
    """LangGraph node: persist the pending audio entry to audio_entries.

    Reads ``state["pending_audio"]`` (set by generate_tts_node) and
    ``state["user_id"]``, calls the audio service, and returns a ToolMessage
    that closes the open ``save_audio_entry`` tool_call.
    """
    # -- Resolve tool_call_id -----------------------------------------------
    tool_call_id: str | None = None
    title: str = ""

    last_msg = state["messages"][-1] if state["messages"] else None
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        for tc in last_msg.tool_calls:
            if tc["name"] == SAVE_AUDIO_TOOL_NAME:
                tool_call_id = tc["id"]
                title = tc.get("args", {}).get("title", "")
                break

    def _error(msg: str) -> dict:
        messages = []
        if tool_call_id:
            messages.append(ToolMessage(content=msg, tool_call_id=tool_call_id))
        return {"messages": messages}

    # -- Validate pending_audio ---------------------------------------------
    pending_audio: dict | None = state.get("pending_audio")
    if not pending_audio:
        logger.warning("[save_audio_entry_node] pending_audio is empty")
        return _error(
            "No audio data found to save. "
            "Please generate audio first before asking me to save it."
        )

    filename: str = pending_audio.get("filename", "")
    temp_token: str = pending_audio.get("temp_token", "")
    if not filename or not temp_token:
        return _error("Audio data is incomplete — please regenerate and try again.")

    # Fall back to text_preview if no title was provided.
    if not title:
        title = pending_audio.get("text_preview", "Audio")[:80]

    user_id: str = state["user_id"]

    # -- Retrieve bytes from temp store -------------------------------------
    audio_bytes = await audio_service.retrieve_temp_audio(temp_token)
    if audio_bytes is None:
        logger.warning(
            "[save_audio_entry_node] temp audio expired token=%s",
            temp_token[:8],
        )
        return _error(
            "The audio preview has expired (> 1 hour). "
            "Please regenerate the audio and try saving again."
        )

    # -- Upload to Storage + persist DB entry (both or neither) ---------------
    try:
        await audio_service.upload_audio(audio_bytes, filename)
        saved = await audio_service.save_audio_entry(
            user_id=user_id,
            filename=filename,
            title=title,
            source_type="custom",
        )
    except RuntimeError as exc:
        logger.error("[save_audio_entry_node] upload/save error: %s", exc)
        return _error(f"Failed to save audio: {exc}")
    except Exception:
        logger.exception("[save_audio_entry_node] unexpected error")
        return _error("An unexpected error occurred while saving the audio.")

    # -- Clean up temp store -------------------------------------------------
    await audio_service.delete_temp_audio(temp_token)

    result_msg = f"Audio saved to your library ✓ — **{saved.title}**"
    logger.info("[save_audio_entry_node] saved id=%s", saved.id)

    messages = []
    if tool_call_id:
        messages.append(ToolMessage(content=result_msg, tool_call_id=tool_call_id))

    # Clear pending_audio from state after successful save.
    return {"messages": messages, "pending_audio": None}
