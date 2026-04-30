"""Models router — public endpoint returning available OpenRouter models."""

from fastapi import APIRouter, Request

from app.core.limiter import limiter
from app.features.models.schemas import ModelInfo
from app.features.models.service import get_models

# prefix="/models" combines with "/api/v1" in main.py → GET /api/v1/models
router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
@limiter.limit("60/minute")
async def list_models(request: Request) -> list[ModelInfo]:
    """Return all models available on OpenRouter. Results are cached for 5 minutes.

    Public endpoint — rate-limited by IP (no auth required).
    Returns 502 Bad Gateway if OpenRouter is unreachable or returns an error.
    """
    return await get_models()
