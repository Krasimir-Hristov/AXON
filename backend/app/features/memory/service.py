"""Memory feature — pipeline orchestration.

Write path:  plaintext → mask_pii → embed(masked) → encrypt(plaintext) → insert
Read path:   row → decrypt(content_encrypted) → MemoryEntry
Search path: query → mask_pii → embed → match_memories RPC → decrypt
File path:   upload → parse → chunk → for each chunk: write path
"""

import logging
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from app.core.crypto import decrypt, encrypt
from app.core.privacy import mask_pii
from app.db import embeddings as db
from app.features.memory import ingest
from app.features.memory.schemas import (
    FileUploadResult,
    MemoryEntry,
    MemorySearchResult,
)

logger = logging.getLogger(__name__)


def _row_to_entry(row: dict[str, Any]) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        content=decrypt(row["content_encrypted"]),
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
    )


async def create_memory(
    *,
    user_id: str,
    content: str,
    metadata: dict[str, Any],
) -> MemoryEntry:
    """Mask PII, embed the masked text, encrypt the original, persist."""
    masked = await mask_pii(content)
    embedding = await embed_safely(masked)
    ciphertext = encrypt(content)
    row = await db.insert_memory(
        user_id=user_id,
        content_encrypted=ciphertext,
        content_masked=masked,
        embedding=embedding,
        metadata=metadata,
    )
    return _row_to_entry(row)


async def embed_safely(text: str) -> list[float]:
    """Thin wrapper to keep service-level error semantics in one place."""
    return await db.embed_text(text)


async def list_memories(user_id: str) -> list[MemoryEntry]:
    rows = await db.list_memories(user_id)
    entries: list[MemoryEntry] = []
    for row in rows:
        try:
            entries.append(_row_to_entry(row))
        except Exception:  # noqa: BLE001 — skip individual unreadable rows
            logger.exception("Failed to decrypt memory row id=%s", row.get("id"))
    return entries


async def search_memories(
    *,
    user_id: str,
    query: str,
    threshold: float = 0.7,
    limit: int = 5,
) -> list[MemorySearchResult]:
    masked_q = await mask_pii(query)
    q_embedding = await embed_safely(masked_q)
    rows = await db.match_memories(
        user_id=user_id,
        query_embedding=q_embedding,
        threshold=threshold,
        limit=limit,
    )
    out: list[MemorySearchResult] = []
    for row in rows:
        try:
            entry = _row_to_entry(row)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to decrypt search hit id=%s", row.get("id"))
            continue
        out.append(
            MemorySearchResult(
                **entry.model_dump(),
                similarity=float(row.get("similarity", 0.0)),
            )
        )
    return out


async def delete_memory(user_id: str, memory_id: UUID) -> bool:
    return await db.delete_memory(user_id, memory_id)


async def ingest_file(
    *,
    user_id: str,
    filename: str,
    content: bytes,
) -> FileUploadResult:
    """Parse, chunk, and store an uploaded file as a series of memory entries."""
    text = await ingest.extract_text(filename, content)
    if not text.strip():
        return FileUploadResult(file_name=filename, chunks_created=0, memory_ids=[])

    chunks = ingest.chunk_text(text)
    suffix = PurePosixPath(filename).suffix.lower()
    base_metadata: dict[str, Any] = {
        "source": "file",
        "source_file": filename,
        "file_type": suffix,
        "total_chunks": len(chunks),
    }

    ids: list[UUID] = []
    for index, chunk in enumerate(chunks):
        entry = await create_memory(
            user_id=user_id,
            content=chunk,
            metadata={**base_metadata, "chunk_index": index},
        )
        ids.append(entry.id)

    return FileUploadResult(
        file_name=filename,
        chunks_created=len(ids),
        memory_ids=ids,
    )
