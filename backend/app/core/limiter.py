"""Rate limiter singleton — JWT-keyed slowapi Limiter for all AXON routes."""

import base64
import json
import logging
import re

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Supabase user IDs are UUIDs — this regex lets us validate the decoded `sub`
# before using it as a rate-limit key so that a malformed Bearer token cannot
# inject an arbitrary string into the key space.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _jwt_key(request: Request) -> str:
    """Extract a per-user rate-limit key from the Bearer token.

    Decodes the JWT *payload* segment without cryptographic verification —
    full verification already happens inside `get_current_user` (security.py).
    This is intentional: the key function must be fast and must never raise,
    so we take what the token says at face value for *bucketing* purposes only.

    Returns ``"user:<sub>"`` when a valid UUID `sub` is present.
    Falls back to the remote IP address for public routes or malformed tokens.
    """
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return get_remote_address(request)

        token = auth.split(" ", 1)[1]
        parts = token.split(".")
        if len(parts) != 3:  # noqa: PLR2004 — 3 is the JWT segment count, not magic
            return get_remote_address(request)

        # Base64url decode the payload segment; add padding as required by spec.
        payload_b64 = parts[1]
        padding = (4 - len(payload_b64) % 4) % 4
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))

        sub = str(payload.get("sub", ""))
        if sub and _UUID_RE.match(sub):
            return f"user:{sub}"
    except (ValueError, KeyError, UnicodeDecodeError):
        # Covers: binascii.Error (bad base64) → subclass of ValueError,
        # json.JSONDecodeError → subclass of ValueError,
        # missing/wrong-type keys → KeyError, decode errors → UnicodeDecodeError.
        logger.debug("_jwt_key: failed to decode Bearer token, falling back to IP")

    return get_remote_address(request)


def _build_limiter() -> Limiter:
    """Construct the Limiter, optionally backed by Redis.

    When ``REDIS_URL`` is set in the environment the limiter uses Redis storage
    so rate-limit counters are shared across multiple workers / Gunicorn forks.
    Without it the default in-memory storage is used — correct for a single
    process (``uvicorn app.main:app``) and requires no external dependency.
    """
    kwargs: dict = {"key_func": _jwt_key}
    if settings.redis_url:
        kwargs["storage_uri"] = settings.redis_url
        logger.info("Rate limiter: using Redis storage at %s", settings.redis_url)
    else:
        logger.info("Rate limiter: using in-memory storage (single-process mode)")
    return Limiter(**kwargs)


# Singleton — imported by main.py (to register middleware) and by every router
# that needs a @limiter.limit() decorator.
limiter: Limiter = _build_limiter()
