"""Models service — TTL-cached OpenRouter model listing (business logic)."""

import asyncio
import logging
import time

import httpx
from fastapi import HTTPException, status

from pydantic import ValidationError

from app.core.config import settings
from app.features.models.schemas import (
    ModelInfo,
    _RawOpenRouterResponse,
    _modality_to_category,
)

logger = logging.getLogger(__name__)

# ── In-memory TTL cache ───────────────────────────────────────────────────────
# Why cache? OpenRouter's /models endpoint is slow (~500 ms) and the list rarely
# changes. Caching for 5 minutes means only the first request per server process
# per 5-minute window hits OpenRouter.
#
# Why asyncio.Lock? Prevents "cache stampede": when the TTL expires and 10
# concurrent requests arrive simultaneously, only ONE coroutine fetches from
# OpenRouter; the other 9 wait behind the lock and receive the freshly cached data.
#
# Why time.monotonic()? Unlike time.time(), monotonic clocks never go backwards
# due to DST changes or NTP corrections, so TTL calculations are always accurate.

_CACHE_TTL: float = 300.0  # 5 minutes in seconds
_cache_data: list[ModelInfo] | None = None  # None = not yet populated
_cache_ts: float = 0.0  # monotonic timestamp of last successful fetch
_cache_lock: asyncio.Lock = (
    asyncio.Lock()
)  # guards the slow path (one fetcher at a time)


async def _fetch_models_from_openrouter() -> list[ModelInfo]:
    """Fetch and parse the current model list from OpenRouter.

    Separated from get_models() so it can be unit-tested independently of the
    cache. Raises HTTPException 502 on any network or HTTP error.
    """
    try:
        # httpx.AsyncClient is required — never use the blocking `requests` library.
        # The client is created per-call here because this function is only called
        # once every 5 minutes; connection pooling would not provide meaningful gains.
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.openrouter_base_url}/models",
                # OpenRouter requires Authorization even for the public /models endpoint.
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                # Without timeout a hung OpenRouter response blocks the event loop worker.
                timeout=10.0,
            )
            # raise_for_status() raises httpx.HTTPStatusError for any 4xx or 5xx
            # response, preventing us from parsing a body that signals an error.
            response.raise_for_status()

    except httpx.HTTPStatusError as exc:
        # 4xx/5xx from OpenRouter (e.g. 401 if the API key is invalid or revoked)
        logger.warning("OpenRouter /models HTTP error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch models from OpenRouter",
        ) from exc

    except httpx.RequestError as exc:
        # Network-level error: timeout, DNS failure, connection refused, etc.
        logger.warning("OpenRouter /models connection error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to OpenRouter",
        ) from exc

    # model_validate() parses the raw dict into our Pydantic schema.
    # Extra fields returned by OpenRouter are silently ignored.
    try:
        raw = _RawOpenRouterResponse.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        logger.warning("OpenRouter /models parse error: %s (status=%s)", exc, response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bad gateway: malformed OpenRouter response",
        ) from exc

    # Transform _RawOpenRouterModel → public ModelInfo.
    # provider: split on "/" and take the first segment.
    #   "openai/gpt-4o"  → "openai"
    #   "anthropic/claude-3.5-sonnet" → "anthropic"
    #   "some-model-without-slash"    → "unknown"
    return [
        ModelInfo(
            id=m.id,
            name=m.name,
            provider=m.id.split("/")[0] if "/" in m.id else "unknown",
            context_length=m.context_length,
            category=_modality_to_category(m.architecture.modality),
        )
        for m in raw.data
    ]


async def get_models() -> list[ModelInfo]:
    """Return all available OpenRouter models, using the in-memory TTL cache.

    Thread-safe via asyncio.Lock with double-checked locking to prevent stampedes.
    Raises HTTPException 502 if OpenRouter is unreachable or returns an error.
    """
    global _cache_data, _cache_ts  # noqa: PLW0603 — intentional module-level cache state

    # ── Fast path ────────────────────────────────────────────────────────────
    # If the cache is populated and still within TTL, return immediately without
    # acquiring the lock. The vast majority of requests take this path.
    if _cache_data is not None and time.monotonic() - _cache_ts < _CACHE_TTL:
        return _cache_data

    # ── Slow path ────────────────────────────────────────────────────────────
    # Acquire the lock so only one coroutine reaches OpenRouter at a time.
    async with _cache_lock:
        # Double-checked locking: another coroutine may have refreshed the cache
        # while we were waiting for the lock. Re-check before making the network call.
        if _cache_data is not None and time.monotonic() - _cache_ts < _CACHE_TTL:
            return _cache_data

        # Cache is stale or empty — fetch from OpenRouter.
        models = await _fetch_models_from_openrouter()

        # Update module-level cache state.
        _cache_data = models
        _cache_ts = time.monotonic()

        return _cache_data
