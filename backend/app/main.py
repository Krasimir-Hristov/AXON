"""AXON FastAPI application — entry point, CORS, lifespan, router mounts."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.features.auth.router import router as auth_router
from app.features.chat.router import router as chat_router
from app.features.models.router import router as models_router

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup before yield, shutdown after yield."""
    logger.info("AXON API starting up (debug=%s)", settings.debug)
    # Future phases: initialise Supabase client and LangGraph here
    yield
    logger.info("AXON API shutting down")


app = FastAPI(
    title="AXON API",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# Allow requests from the Next.js dev server.
# allow_credentials=True is required for Supabase session cookies to pass through.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers.
# Final paths = middleware prefix + router prefix:
#   /api/v1 + /auth + /me     →  GET /api/v1/auth/me
#   /api/v1 + /models + ""   →  GET /api/v1/models
#   /api/v1 + /chat + /stream →  POST /api/v1/chat/stream
app.include_router(auth_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
