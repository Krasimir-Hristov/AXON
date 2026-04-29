"""Embedding + memory storage primitives.

Embeddings are produced via OpenRouter's OpenAI-compatible /embeddings endpoint
using `openai/text-embedding-3-large` with dimensions=1536 (Matryoshka), to
match the existing `extensions.vector(1536)` column.

This module owns:
- `embed_text` — async OpenRouter call (httpx).
- `insert_memory` / `list_memories` / `delete_memory` — Supabase CRUD.
- `match_memories` — invokes the SQL RPC defined in
  `supabase/migrations/20260427211558_create_match_memories_rpc.sql`.

All callers must scope by user_id (server-side bypasses RLS).
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def embed_text(text: str) -> list[float]:
    """Return a 1536-dim embedding vector for `text` via OpenRouter."""
    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    payload = {
        "model": settings.embedding_model,
        "input": text,
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
        data = response.json()
    embedding = data["data"][0]["embedding"]
    if len(embedding) != settings.embedding_dimensions:
        raise ValueError(
            f"Embedding dim mismatch: got {len(embedding)}, expected {settings.embedding_dimensions}"
        )
    return embedding


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
