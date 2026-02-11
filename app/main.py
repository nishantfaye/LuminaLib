"""FastAPI application factory — entry point for LuminaLib."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.books import router as books_router
from app.api.routes.intelligence import router as intel_router
from app.api.routes.reviews import router as reviews_router
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    logger.info("LuminaLib starting up...")
    logger.info("Storage backend: %s", settings.storage_backend.value)
    logger.info("LLM provider: %s", settings.llm_provider.value)
    logger.info("Recommendation alpha: %.2f", settings.recommendation_alpha)
    yield
    logger.info("LuminaLib shutting down...")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title="LuminaLib",
        description="Intelligent Library System with GenAI & ML Recommendations",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── Middleware ──────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ─────────────────────────────────────
    application.include_router(auth_router)
    application.include_router(books_router)
    application.include_router(reviews_router)
    application.include_router(intel_router)

    # ── Health Check ───────────────────────────────
    @application.get("/health", tags=["System"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "luminalib"}

    return application


app = create_app()app/main.py
