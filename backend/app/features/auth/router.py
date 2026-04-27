"""Auth router — identity endpoint for the authenticated user."""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.features.auth.schemas import UserSchema

# prefix="/auth" is combined with the "/api/v1" prefix in main.py
# → final path: GET /api/v1/auth/me
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserSchema)
async def get_me(
    current_user: UserSchema = Depends(get_current_user),
) -> UserSchema:
    """Return the identity of the authenticated user.

    Returns 401 if the Bearer token is missing, expired, or invalid.
    Returns 200 + UserSchema if the token is valid.
    """
    return current_user
