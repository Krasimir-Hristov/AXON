"""Supabase async client singleton — lazy, double-checked-lock initialised."""

import asyncio
import logging

from supabase import AsyncClient, create_async_client

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton state.
# Why singleton? The Supabase client owns an httpx connection pool; constructing
# one per request would defeat pooling and exhaust sockets under load.
_client: AsyncClient | None = None
_lock: asyncio.Lock = asyncio.Lock()


async def get_supabase_client() -> AsyncClient:
    """Return the process-wide Supabase async client, creating it on first call.

    Uses double-checked locking: the fast path returns the cached client without
    acquiring the lock; only the first concurrent caller (when _client is None)
    pays the lock + construction cost.

    Authenticated with the server-side secret key (settings.supabase_secret_key),
    so this client bypasses RLS — every caller MUST scope queries by the
    JWT-derived user_id passed down from the request layer.
    """
    global _client  # noqa: PLW0603 — intentional module-level singleton

    if _client is not None:
        return _client

    async with _lock:
        if _client is not None:
            return _client
        logger.info("Initialising Supabase async client")
        _client = await create_async_client(
            settings.supabase_url,
            settings.supabase_secret_key,
        )
        return _client
