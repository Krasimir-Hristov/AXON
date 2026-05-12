"""Pydantic schemas for the audio feature (Phase 10C)."""

from pydantic import BaseModel, Field


class AudioGenerateResult(BaseModel):
    """Result returned after generating and uploading a TTS audio file."""

    signed_url: str
    filename: str
    text_preview: str = Field(..., min_length=1, max_length=1024)
