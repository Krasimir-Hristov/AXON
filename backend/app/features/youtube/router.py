"""YouTube REST endpoints — read + delete saved transcripts."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.youtube import service
from app.features.youtube.schemas import VideoTranscriptOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("", response_model=list[VideoTranscriptOut])
@limiter.limit("60/minute")
async def list_transcripts_endpoint(
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> list[VideoTranscriptOut]:
    """Return all saved YouTube transcripts for the authenticated user."""
    return await service.list_transcripts(current_user.id)


@router.get("/{transcript_id}", response_model=VideoTranscriptOut)
@limiter.limit("60/minute")
async def get_transcript_endpoint(
    transcript_id: UUID,
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> VideoTranscriptOut:
    """Return a single saved transcript owned by the authenticated user."""
    row = await service.get_transcript(transcript_id, current_user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )
    return row


@router.delete("/{transcript_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_transcript_endpoint(
    transcript_id: UUID,
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> None:
    """Delete a saved transcript and its cross-indexed memory entry."""
    deleted = await service.delete_transcript(transcript_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )
