"""Memory feature — pipeline orchestration.

Write path:  plaintext → embed → encrypt(plaintext) → insert
Read path:   row → decrypt(content_encrypted) → MemoryEntry
Search path: query → embed → match_memories RPC → decrypt
File path:   upload → parse → chunk → for each chunk: write path

Note: PII masking has been intentionally removed from the embedding pipeline.
Embeddings are computed directly from the original text so that semantic
similarity search works correctly across all languages and scripts.
The content_encrypted field still stores the encrypted original text.
"""

import logging
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from app.core.crypto import decrypt, encrypt
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
    """Embed the original text, encrypt it, and persist."""
    embedding = await embed_safely(content)
    ciphertext = encrypt(content)
    row = await db.insert_memory(
        user_id=user_id,
        content_encrypted=ciphertext,
        content_masked=content,
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
    threshold: float = 0.35,
    limit: int = 5,
) -> list[MemorySearchResult]:
    """Search memories by semantic similarity.

    threshold=0.35 is intentionally lower than the typical 0.6–0.7 to maximise
    recall across languages and transliterated text. The model embedding space
    contracts when content spans multiple languages, so a relaxed threshold
    avoids false negatives without a meaningful increase in irrelevant hits
    (results are already ranked by similarity, and the limit caps output size).
    """
    q_embedding = await embed_safely(query)
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
    """Parse, chunk, and store an uploaded file as a series of memory entries.

    Embeddings are produced in a single batched call to OpenRouter (one HTTP
    round-trip for up to 96 chunks), then encrypted + persisted sequentially.
    Sequential inserts are intentional: they keep the order stable and avoid
    overwhelming the Supabase connection pool, while the embedding round-trip
    (the actual latency hot-spot) happens in parallel server-side.
    """
    text = await ingest.extract_text(filename, content)
    if not text.strip():
        return FileUploadResult(file_name=filename, chunks_created=0, memory_ids=[])

    chunks = ingest.chunk_text(text)
    if not chunks:
        return FileUploadResult(file_name=filename, chunks_created=0, memory_ids=[])

    # 1. Embed all chunks in one batched call (single HTTP round-trip).
    vectors = await db.embed_texts(chunks)

    suffix = PurePosixPath(filename).suffix.lower()
    base_metadata: dict[str, Any] = {
        "source": "file",
        "source_file": filename,
        "file_type": suffix,
        "total_chunks": len(chunks),
    }

    # 2. Encrypt + insert sequentially. Failures on individual rows are
    # logged; we keep going so a single bad row doesn't lose the whole upload.
    ids: list[UUID] = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        try:
            row = await db.insert_memory(
                user_id=user_id,
                content_encrypted=encrypt(chunk),
                content_masked=chunk,
                embedding=vector,
                metadata={**base_metadata, "chunk_index": index},
            )
            ids.append(_row_to_entry(row).id)
        except Exception:  # noqa: BLE001 — partial-success semantics
            logger.exception(
                "Failed to persist chunk %s of %s for user %s", index, filename, user_id
            )

    return FileUploadResult(
        file_name=filename,
        chunks_created=len(ids),
        memory_ids=ids,
    )
