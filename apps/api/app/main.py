"""FastAPI application.

Product routes arrive in later phases (wardrobe in S4/S6, composition in S8b). This module
establishes the app, the error envelope, and the boot-time checks that must fail loudly.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger("stylelab")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot checks.

    There is no demo mode, so a missing key must stop the app here rather than surface as a
    failure at a user's first request (AI-EVAL-CASES Case 25). Settings validation raises if
    GROQ_API_KEY is absent.

    The live model-availability check is wired in phase 12, once the Groq adapter exists.
    Groq deprecates models on weeks of notice, so a deployment that sat idle can wake up
    broken — that check belongs at boot too.
    """
    settings = get_settings()
    logger.info(
        "stylelab api starting: text=%s vision=%s fallback=%s trend_source=%s",
        settings.groq_text_model,
        settings.groq_vision_model,
        settings.groq_vision_fallback_model,
        settings.trend_source,
    )
    yield


app = FastAPI(
    title="STYLELAB API",
    version="0.1.0",
    description="Reads photos of clothes a user owns and styles outfits from them.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness only. Deliberately does not touch Groq — a provider outage is reported
    through the normal error envelope, not by making the container look dead."""
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/ping")
async def ping() -> dict[str, str]:
    return {"pong": "ok"}


def error_response(
    code: str, message: str, *, retryable: bool, status: int, request_id: str | None = None
) -> JSONResponse:
    """The single error envelope from docs/API-SPEC.md.

    Never expose a stack trace or a raw provider message (docs/SECURITY-PRIVACY.md).
    """
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                **({"request_id": request_id} if request_id else {}),
            }
        },
    )
