"""Memory REST endpoints — all protected by Supabase JWT."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema
from app.features.memory import service
from app.features.memory.ingest import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.features.memory.schemas import (
    FileUploadResult,
    MemoryCreate,
    MemoryEntry,
    MemorySearchRequest,
    MemorySearchResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", response_model=MemoryEntry, status_code=status.HTTP_201_CREATED)
async def create_memory_endpoint(
    payload: MemoryCreate,
    current_user: UserSchema = Depends(get_current_user),
) -> MemoryEntry:
    return await service.create_memory(
        user_id=current_user.id,
        content=payload.content,
        metadata=payload.metadata,
    )


@router.get("", response_model=list[MemoryEntry])
async def list_memories_endpoint(
    current_user: UserSchema = Depends(get_current_user),
) -> list[MemoryEntry]:
    return await service.list_memories(current_user.id)


@router.post("/search", response_model=list[MemorySearchResult])
async def search_memories_endpoint(
    payload: MemorySearchRequest,
    current_user: UserSchema = Depends(get_current_user),
) -> list[MemorySearchResult]:
    return await service.search_memories(
        user_id=current_user.id,
        query=payload.query,
        threshold=payload.threshold,
        limit=payload.limit,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_endpoint(
    memory_id: UUID,
    current_user: UserSchema = Depends(get_current_user),
) -> None:
    deleted = await service.delete_memory(current_user.id, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found"
        )


@router.post("/upload", response_model=FileUploadResult)
async def upload_file_endpoint(
    file: UploadFile = File(...),
    current_user: UserSchema = Depends(get_current_user),
) -> FileUploadResult:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename"
        )
    content = await file.read()
    try:
        return await service.ingest_file(
            user_id=current_user.id,
            filename=file.filename,
            content=content,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_FILE_SIZE_BYTES} bytes",
        ) from exc
