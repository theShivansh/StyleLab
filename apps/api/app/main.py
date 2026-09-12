"""FastAPI application.

Product routes arrive in later phases (wardrobe upload in S6, composition in S7). This
module establishes the app, the error envelope, and the boot-time checks that must fail
loudly.

## Why `create_app` takes a transport

The boot check calls the provider, so an app constructed one way in production and another
way in tests would mean the check is only ever exercised in production. Passing the
transport in makes it injectable without a global that product code can reach: tests build
the app with `MockGroqProvider` and the real verification logic runs against it.

The alternative — a `verify_models_at_boot` setting defaulting to on — was rejected. A flag
whose only purpose is to switch off a safety check is a flag that eventually ships off.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.adapters.boot import default_transport, verify_models
from app.adapters.transport import ChatTransport
from app.config import get_settings

logger = logging.getLogger("stylelab")

API_PREFIX = "/api/v1"


def create_app(*, transport: ChatTransport | None = None) -> FastAPI:
    """Build the application.

    `transport` defaults to the real provider. Supply one to run the same boot checks
    against a test double.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Boot checks.

        There is no demo mode, so a missing key must stop the app here rather than surface
        as a failure at a user's first request (AI-EVAL-CASES Case 25). Settings validation
        raises if GROQ_API_KEY is absent — that happens on the next line, before anything
        else is attempted.

        Then the configured model ids are checked against the provider's list. A model that
        does not resolve is fatal; a list call that fails is logged loudly and tolerated.
        `app/adapters/boot.py` explains why those two are not treated alike.
        """
        settings = get_settings()
        logger.info(
            "stylelab api starting: text=%s vision=%s fallback=%s trend_source=%s",
            settings.groq_text_model,
            settings.groq_vision_model,
            settings.groq_vision_fallback_model,
            settings.trend_source,
        )

        app.state.transport = transport or default_transport(settings)
        app.state.verified_models = await verify_models(app.state.transport, settings)
        yield

    app = FastAPI(
        title="STYLELAB API",
        version="0.1.0",
        description="Reads photos of clothes a user owns and styles outfits from them.",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness only. Deliberately does not touch the provider — an outage is reported
        through the normal error envelope, not by making the container look dead."""
        return {"status": "ok"}

    @app.get(f"{API_PREFIX}/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    return app


app = create_app()


def error_response(
    code: str, message: str, *, retryable: bool, status: int, request_id: str | None = None
) -> JSONResponse:
    """The single error envelope from docs/API-SPEC.md.

    Never expose a stack trace or a raw provider message (docs/SECURITY-PRIVACY.md).
    `ProviderError.code` and `.message` are already sanitised for exactly this use.
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
