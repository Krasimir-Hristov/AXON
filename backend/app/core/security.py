"""Security utilities — Supabase JWT validation for protected endpoints."""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings
from app.features.auth.schemas import UserSchema

logger = logging.getLogger(__name__)

# Extracts the Bearer token from the Authorization header.
# FastAPI returns 403 automatically if the header is missing entirely.
_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UserSchema:
    """Validate a Supabase JWT and return the authenticated user.

    Raises HTTP 401 if the token is missing, expired, or has an invalid signature.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        # Standard header that tells the client this endpoint requires Bearer auth
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload: dict = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            # Supabase does not set an "aud" claim in its JWTs
            options={"verify_aud": False},
        )
    except JWTError as exc_inner:
        logger.warning("JWT validation failed: %s", exc_inner)
        raise exc from exc_inner

    # "sub" (subject) is the standard JWT claim that Supabase uses for the user UUID
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise exc

    email: str = payload.get("email") or ""

    return UserSchema(id=user_id, email=email)
