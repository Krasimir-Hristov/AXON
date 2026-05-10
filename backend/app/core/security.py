"""Security utilities — Supabase JWT validation for protected endpoints."""

import logging
import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.features.auth.schemas import UserSchema

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()

# ── JWKS cache ────────────────────────────────────────────────────────────────
# Fetched once and cached for 1 hour. Supabase rotates keys rarely.
_jwks_cache: dict | None = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL: float = 3600.0


async def _get_jwks() -> dict:
    """Fetch Supabase JWKS with a 1-hour in-memory cache."""
    global _jwks_cache, _jwks_cache_ts
    if _jwks_cache and (time.monotonic() - _jwks_cache_ts) < _JWKS_TTL:
        return _jwks_cache
    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_cache_ts = time.monotonic()
            logger.info("JWKS refreshed from %s", url)
            return _jwks_cache
    except Exception as exc:
        logger.exception("JWKS fetch failed for %s: %s", url, exc)
        if _jwks_cache:
            return _jwks_cache
        return {}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UserSchema:
    """Validate a Supabase JWT (ES256 or HS256) and return the authenticated user."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials

    # Try ES256 via JWKS first (current Supabase default since key rotation)
    try:
        jwks = await _get_jwks()
        payload: dict = jwt.decode(
            token,
            jwks,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
    except JWTError:
        # Fall back to legacy HS256 shared secret
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError as exc_inner:
            logger.warning(
                "JWT validation failed (both ES256 and HS256): %s", exc_inner
            )
            raise exc from exc_inner

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise exc

    email: str = payload.get("email") or ""
    return UserSchema(id=user_id, email=email)
