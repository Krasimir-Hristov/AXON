"""Schemas for the memory feature."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    id: UUID
    content: str  # decrypted on read
    metadata: dict[str, Any]
    created_at: datetime


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=5, ge=1, le=20)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class MemorySearchResult(MemoryEntry):
    similarity: float


class FileUploadResult(BaseModel):
    file_name: str
    chunks_created: int
    memory_ids: list[UUID]
