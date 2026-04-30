"""Rate limiter singleton — JWT-keyed slowapi Limiter for all AXON routes."""

import base64
import json
import logging
import re
from urllib.parse import urlparse

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


def _redact_redis_url(url: str) -> str:
    """Return the Redis URL with credentials replaced by <redacted>.

    Prevents accidental logging of passwords embedded in connection strings
    such as ``redis://user:password@host:6379/0``.
    """
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            host_port = parsed.hostname or ""
            if parsed.port:
                host_port += f":{parsed.port}"
            safe_netloc = f"<redacted>@{host_port}"
            return parsed._replace(netloc=safe_netloc).geturl()
        return url
    except Exception:  # noqa: BLE001 — never let a log helper raise
        return "<unparseable-redis-url>"


def _jwt_key(request: Request) -> str:
    """Extract a per-user rate-limit key from the Bearer token.

    Decodes the JWT *payload* segment without cryptographic verification —
    full verification already happens inside ``get_current_user`` (security.py).

    Design note — why not verify the JWT here?
    ``_jwt_key`` is a synchronous function called by SlowAPIMiddleware before
    any route handler or FastAPI Depends() chain runs, so calling the async
    ``get_current_user`` dependency is not possible at this point.

    Residual risk: an attacker could craft a Bearer token containing a valid
    UUID ``sub`` belonging to another user, which would consume that user's
    rate-limit bucket.  The impact is limited — all such requests are rejected
    with 401 by the route handler before they touch any backend resource, so
    the worst outcome is a transient rate-limit DoS on that specific bucket.
    The UUID format validation already prevents arbitrary string injection.

    Returns ``"user:<sub>"`` when the payload is a dict with a valid UUID sub.
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

        # Guard against non-object JWT payloads (e.g. a bare JSON array).
        # json.loads() can return any JSON type; .get() only exists on dict.
        if not isinstance(payload, dict):
            return get_remote_address(request)

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
        # Redact credentials before logging — Redis URLs can contain passwords.
        logger.info(
            "Rate limiter: using Redis storage at %s",
            _redact_redis_url(settings.redis_url),
        )
    else:
        logger.info("Rate limiter: using in-memory storage (single-process mode)")
    return Limiter(**kwargs)


# Singleton — imported by main.py (to register middleware) and by every router
# that needs a @limiter.limit() decorator.
limiter: Limiter = _build_limiter()
