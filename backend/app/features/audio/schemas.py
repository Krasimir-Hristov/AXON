"""Pydantic schemas for the audio feature (Phase 10C)."""

from pydantic import BaseModel


class AudioGenerateResult(BaseModel):
    """Result returned after generating and uploading a TTS audio file."""

    signed_url: str
    filename: str
    text_preview: str
