"""Pydantic schemas for the audio feature."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AudioGenerateResult(BaseModel):
    """Result returned after generating and uploading a TTS audio file."""

    signed_url: str
    filename: str
    text_preview: str = Field(..., min_length=1, max_length=1024)


class AudioEntryOut(BaseModel):
    """A saved audio entry from the audio_entries table."""

    id: UUID
    filename: str
    title: str
    source_type: str
    source_id: UUID | None = None
    duration_s: int | None = None
    created_at: datetime
    signed_url: str
