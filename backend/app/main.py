"""AXON FastAPI application — entry point, CORS, lifespan, router mounts."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.limiter import limiter
from app.features.auth.router import router as auth_router
from app.features.chat.router import router as chat_router
from app.features.memory.router import router as memory_router
from app.features.models.router import router as models_router

# basicConfig is a no-op when uvicorn has already added root handlers.
# Explicitly set the level on every app.* logger instead.
_log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.getLogger("app").setLevel(_log_level)
logging.basicConfig(level=_log_level)
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

# Rate limiting — must be set on app.state BEFORE SlowAPIMiddleware is added.
# SlowAPIMiddleware is required for @limiter.limit() to fire on APIRouter sub-routers.
# Without it the decorator is registered but never executed.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — added after SlowAPIMiddleware so it wraps the outside of the stack.
# Starlette executes middleware in LIFO order, meaning CORSMiddleware runs first
# (outermost), ensuring CORS headers are present even on 429 responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
app.include_router(memory_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["health"])
async def health_check() -> JSONResponse:
    """Liveness probe — returns 200 OK when the API process is running."""
    return JSONResponse({"status": "ok", "version": app.version})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions.

    Without this, Starlette's ServerErrorMiddleware (outermost layer) intercepts
    unhandled exceptions and returns a 500 response *directly*, bypassing
    CORSMiddleware entirely.  The browser then gets a CORS-blocked response and
    raises TypeError: Failed to fetch instead of a readable HTTP 500 error.

    Registering this handler in FastAPI's ExceptionMiddleware (which sits *inside*
    CORSMiddleware) ensures the 500 response travels through the CORS layer and
    receives the required Access-Control-Allow-Origin header.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
