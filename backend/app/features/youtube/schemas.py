"""Pydantic schemas for the YouTube feature."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class VideoTranscriptOut(BaseModel):
    """Read model returned by all YouTube REST endpoints."""

    id: UUID
    youtube_url: str
    video_id: str
    title: str | None
    channel: str | None
    duration_s: int | None
    summary: str
    key_points: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
