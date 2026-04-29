"""Embedding + memory storage primitives.

Embeddings are produced via OpenRouter's OpenAI-compatible /embeddings endpoint
using `openai/text-embedding-3-large` with dimensions=1536 (Matryoshka), to
match the existing `extensions.vector(1536)` column.

This module owns:
- `embed_text` / `embed_texts` — async OpenRouter calls (httpx) with retry
  on transient 429/5xx errors via tenacity.
- `insert_memory` / `list_memories` / `delete_memory` — Supabase CRUD.
- `match_memories` — invokes the SQL RPC defined in
  `supabase/migrations/20260427211558_create_match_memories_rpc.sql`.

All callers must scope by user_id (server-side bypasses RLS).
"""

import logging
from typing import Any
from uuid import UUID

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Maximum batch size accepted by OpenAI embeddings API. We stay well below the
# documented 2048 limit because OpenRouter occasionally tightens it per-provider.
_EMBED_BATCH_SIZE = 96


class EmbeddingResponseError(RuntimeError):
    """Raised when OpenRouter returns a 200 response with a malformed body."""


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retry only on transient errors: connection issues, timeouts, 429, 5xx."""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return False


def _parse_embeddings(payload: dict[str, Any], expected_count: int) -> list[list[float]]:
    """Defensively extract embedding vectors from an OpenRouter response body.

    OpenAI's embeddings spec attaches an `index` field to each row matching
    the position of the corresponding string in the request `input` array.
    We sort by that index instead of relying on array order — providers /
    proxies are *allowed* to reorder rows and a silent reorder would associate
    embeddings with the wrong source chunks.
    """
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected_count:
        raise EmbeddingResponseError(
            f"Unexpected embeddings payload shape (expected {expected_count} rows)"
        )

    indexed: list[tuple[int, list[float]]] = []
    seen_indices: set[int] = set()
    for row in data:
        if not isinstance(row, dict):
            raise EmbeddingResponseError("Embeddings row is not an object")
        idx = row.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= expected_count:
            raise EmbeddingResponseError(
                f"Embeddings row has invalid 'index' field: {idx!r}"
            )
        if idx in seen_indices:
            raise EmbeddingResponseError(f"Duplicate embedding index {idx}")
        seen_indices.add(idx)
        vec = row.get("embedding")
        if not isinstance(vec, list) or len(vec) != settings.embedding_dimensions:
            raise EmbeddingResponseError(
                f"Embedding vector has wrong shape (expected {settings.embedding_dimensions} floats)"
            )
        indexed.append((idx, vec))

    indexed.sort(key=lambda pair: pair[0])
    return [vec for _, vec in indexed]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return 1536-dim embedding vectors for each text in `texts`.

    Splits input into chunks of `_EMBED_BATCH_SIZE` and dispatches one HTTP
    call per chunk. Retry/backoff is applied per-chunk inside `_embed_batch`,
    so a transient failure on the Nth sub-batch does not re-pay for the
    successful earlier ones.
    """
    if not texts:
        return []

    out: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        out.extend(await _embed_batch(texts[start : start + _EMBED_BATCH_SIZE]))
    return out


@retry(
    retry=retry_if_exception(_is_retryable_http_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    reraise=True,
)
async def _embed_batch(batch: list[str]) -> list[list[float]]:
    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    payload = {
        "model": settings.embedding_model,
        "input": batch,
        "dimensions": settings.embedding_dimensions,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    return _parse_embeddings(body, expected_count=len(batch))


async def embed_text(text: str) -> list[float]:
    """Return a single 1536-dim embedding vector for `text`."""
    vectors = await embed_texts([text])
    return vectors[0]


async def insert_memory(
    *,
    user_id: str,
    content_encrypted: str,
    content_masked: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Insert a memory row and return the persisted record."""
    client = await get_supabase_client()
    response = (
        await client.table("memory_entries")
        .insert(
            {
                "user_id": user_id,
                "content_encrypted": content_encrypted,
                "content_masked": content_masked,
                "embedding": embedding,
                "metadata": metadata,
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Failed to insert memory entry — empty response")
    return response.data[0]


async def list_memories(user_id: str) -> list[dict[str, Any]]:
    """Return all memory rows for a user, newest first."""
    client = await get_supabase_client()
    response = (
        await client.table("memory_entries")
        .select("id, content_encrypted, content_masked, metadata, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


async def delete_memory(user_id: str, memory_id: UUID) -> bool:
    """Delete a memory row owned by user_id. Returns True if a row was deleted."""
    client = await get_supabase_client()
    response = (
        await client.table("memory_entries")
        .delete()
        .eq("id", str(memory_id))
        .eq("user_id", user_id)
        .execute()
    )
    return bool(response.data)


async def match_memories(
    *,
    user_id: str,
    query_embedding: list[float],
    threshold: float = 0.7,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Run pgvector similarity search via the `match_memories` RPC."""
    client = await get_supabase_client()
    response = await client.rpc(
        "match_memories",
        {
            "query_embedding": query_embedding,
            "match_user_id": user_id,
            "match_threshold": threshold,
            "match_count": limit,
        },
    ).execute()
    return response.data or []
