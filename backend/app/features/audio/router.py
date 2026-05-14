"""Audio Library REST endpoints — list and delete saved audio entries."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.audio import service
from app.features.audio.schemas import AudioEntryOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("", response_model=list[AudioEntryOut])
@limiter.limit("60/minute")
async def list_audio_entries_endpoint(
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> list[AudioEntryOut]:
    """Return all saved audio entries for the authenticated user (newest first)."""
    return await service.list_audio_entries(current_user.id)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_audio_entry_endpoint(
    entry_id: UUID,
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> None:
    """Delete a saved audio entry and its file from Supabase Storage."""
    deleted = await service.delete_audio_entry(entry_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio entry not found",
        )
