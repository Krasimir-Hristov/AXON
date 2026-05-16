"""Audio Library REST endpoints — list, delete, and temp-serve audio."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.audio import service
from app.features.audio.rename import rename_audio_entry as _rename_audio_entry
from app.features.audio.schemas import AudioEntryOut, AudioEntryPatch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/temp/{token}")
@limiter.limit("30/minute")
async def serve_temp_audio(token: UUID, request: Request) -> Response:
    """Serve a temporarily stored mp3 before the user confirms saving.

    No JWT auth — the UUID token itself acts as a short-lived capability URL
    (unguessable, 1-hour TTL).  The browser <audio> element cannot send custom
    headers, so cookie / bearer auth is not applicable here.
    """
    audio_bytes = await service.retrieve_temp_audio(str(token))
    if audio_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found or expired.",
        )
    return Response(content=audio_bytes, media_type="audio/mpeg")


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


@router.patch("/{entry_id}", response_model=AudioEntryOut)
@limiter.limit("60/minute")
async def rename_audio_entry_endpoint(
    entry_id: UUID,
    body: AudioEntryPatch,
    request: Request,
    current_user: UserSchema = Depends(get_current_user),
) -> AudioEntryOut:
    """Rename a saved audio entry's title."""
    updated = await _rename_audio_entry(entry_id, current_user.id, body.title)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio entry not found",
        )
    return updated
