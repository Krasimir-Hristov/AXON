"""Models router — public endpoint returning available OpenRouter models."""

from fastapi import APIRouter

from app.features.models.schemas import ModelInfo
from app.features.models.service import get_models

# prefix="/models" combines with "/api/v1" in main.py → GET /api/v1/models
router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
async def list_models() -> list[ModelInfo]:
    """Return all models available on OpenRouter. Results are cached for 5 minutes.

    Public endpoint — no authentication required.
    Returns 502 Bad Gateway if OpenRouter is unreachable or returns an error.
    """
    return await get_models()
