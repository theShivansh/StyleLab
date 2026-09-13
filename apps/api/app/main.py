"""FastAPI application.

## Why `create_app` takes a transport

The boot check calls the provider, so an app constructed one way in production and another
way in tests would mean the check is only ever exercised in production. Passing the
transport in makes it injectable without a global that product code can reach: tests build
the app with `MockGroqProvider` and the real verification logic runs against it.

The alternative — a `verify_models_at_boot` setting defaulting to on — was rejected. A flag
whose only purpose is to switch off a safety check is a flag that eventually ships off.

`store` and `sessions` are injectable for the same reason and no other: a test needs a
temporary directory and a temporary database, and the alternative is a suite that writes
into the developer's real wardrobe.

## The wiring is all here

Every long-lived object is built once in the lifespan and hung on `app.state`, and
`app/deps.py` is the only thing that reads it. So this function is the complete picture of
what talks to what — which store the analyzer reads through, which transport it speaks to,
which limits the ingest service enforces. Nothing else constructs a dependency, and there is
no module-level singleton for a route to reach around the injection and find.

## Errors

`FaultError` is the only documented route to an error response, and the handler below is the
only thing that renders one. The catch-all beneath it exists so that an unanticipated
exception becomes the same envelope rather than a stack trace: docs/API-SPEC.md says never
expose one, and a handler is the only way to mean it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.boot import default_transport, verify_models
from app.adapters.groq_text import GroqOutfitAdvisor
from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.adapters.transport import ChatTransport
from app.config import get_settings
from app.db.session import create_all, get_engine, session_factory
from app.deps import FaultError
from app.logging_setup import install_log_redaction
from app.routers import assets as assets_router
from app.routers import jobs as jobs_router
from app.routers import outfits as outfits_router
from app.routers import session as session_router
from app.routers import wardrobe as wardrobe_router
from app.security.tokens import TokenSigner
from app.services.compose import OutfitComposer
from app.services.ingest import UploadLimits, WardrobeIngestService
from app.services.jobs import BackgroundJobs, InMemoryJobStore
from app.services.storage import InlineImageSource, LocalObjectStore, ObjectStore
from app.services.telemetry import LoggingGenerationLog

logger = logging.getLogger("stylelab")

API_PREFIX = "/api/v1"


def create_app(
    *,
    transport: ChatTransport | None = None,
    store: ObjectStore | None = None,
    sessions: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Build the application. Supply dependencies to run the same code against doubles."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Boot checks, then wiring.

        There is no demo mode, so a missing key must stop the app here rather than surface
        as a failure at a user's first request (AI-EVAL-CASES Case 25). Settings validation
        raises if GROQ_API_KEY is absent — that happens on the next line, before anything
        else is attempted.

        Then the configured model ids are checked against the provider's list. A model that
        does not resolve is fatal; a list call that fails is logged loudly and tolerated.
        `app/adapters/boot.py` explains why those two are not treated alike.
        """
        settings = get_settings()
        # Before the first request is served: the access log would otherwise record a
        # working link to a user's photograph on every image the wardrobe renders.
        install_log_redaction()
        logger.info(
            "stylelab api starting: text=%s vision=%s fallback=%s trend_source=%s",
            settings.groq_text_model,
            settings.groq_vision_model,
            settings.groq_vision_fallback_model,
            settings.trend_source,
        )

        app.state.transport = transport or default_transport(settings)
        app.state.verified_models = await verify_models(app.state.transport, settings)

        app.state.signer = TokenSigner(settings.session_secret)

        if sessions is not None:
            app.state.sessions = sessions
        else:
            engine = get_engine()
            # The dialect, never the URL: a Postgres URL carries a password, and this line
            # goes to a log (docs/SECURITY-PRIVACY.md — never log secrets). Logged at all
            # because the local default is only acceptable while it is visible.
            logger.info("wardrobe store: %s", engine.dialect.name)
            # Not a migration strategy — blocker B12. Enough for local work, and it means a
            # fresh clone has somewhere to put a wardrobe rather than failing on the first
            # insert with a message about a missing table.
            create_all(engine)
            app.state.engine = engine
            app.state.sessions = session_factory(engine)

        app.state.store = store or LocalObjectStore(settings.storage_root)

        app.state.jobs = InMemoryJobStore()
        app.state.background = BackgroundJobs()
        # One sink for both generating paths, so `success_rate` means the same thing on
        # each of them (docs/OBSERVABILITY.md, and `app/services/telemetry.py` on why the
        # rollup is product code rather than a query somebody writes later).
        app.state.generation_log = LoggingGenerationLog()
        app.state.ingest = WardrobeIngestService(
            sessions=app.state.sessions,
            store=app.state.store,
            analyzer=GroqWardrobeAnalyzer(
                app.state.transport,
                model=settings.groq_vision_model,
                fallback_model=settings.groq_vision_fallback_model,
                # The provider gets an inlined, downscaled copy: the storage directory is
                # private and this API is not reachable from Groq's network.
                urls=InlineImageSource(
                    app.state.store, max_edge_px=settings.analysis_max_edge_px
                ),
                max_tokens=settings.groq_vision_max_tokens,
            ),
            jobs=app.state.jobs,
            background=app.state.background,
            telemetry=app.state.generation_log,
            limits=UploadLimits(
                max_bytes=settings.max_upload_bytes,
                max_images_per_batch=settings.max_images_per_batch,
                min_edge_px=settings.min_image_edge_px,
                max_pixels=settings.max_image_pixels,
            ),
        )

        app.state.composer = OutfitComposer(
            sessions=app.state.sessions,
            advisor=GroqOutfitAdvisor(
                app.state.transport,
                model=settings.groq_text_model,
                max_tokens=settings.agent_max_output_tokens,
            ),
            jobs=app.state.jobs,
            background=app.state.background,
            # No trend source yet: the corpus is blocker B8 and lands with the crew in S8b.
            # `None` costs a rung (2) and is disclosed as one, which is the honest state of
            # affairs — a source that returned nothing would report full depth for advice
            # that had no trend input.
            trend_source=None,
            # The ceiling on the whole advisor call. Without it the waits compound — three
            # transport attempts inside two advisor attempts, each with its own 30-second
            # client timeout — and a compose nobody cancels can run for minutes.
            latency_budget_s=settings.agent_latency_budget_ms / 1000,
            telemetry=app.state.generation_log,
        )

        yield

        # Let outstanding extractions finish rather than cutting them mid-provider-call: a
        # job killed after the model answered and before the row was written costs the user
        # a card and costs us the call.
        await app.state.background.drain()

    app = FastAPI(
        title="STYLELAB API",
        version="0.1.0",
        description="Reads photos of clothes a user owns and styles outfits from them.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        # One origin, named. Not a wildcard: the API answers with a caller's wardrobe, and
        # `allow_credentials` plus `*` is the combination that makes any page on the
        # internet able to read it.
        allow_origins=[get_settings().web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(FaultError)
    async def _fault(_: Request, error: FaultError) -> JSONResponse:
        fault = error.fault
        return error_response(
            fault.code, fault.message, retryable=fault.retryable, status=fault.status
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, error: Exception) -> JSONResponse:
        """Anything not classified. Logged in full, reported as an outage.

        The log gets the traceback; the caller gets the envelope. docs/API-SPEC.md: never
        expose a stack trace — and the only way to hold that for the unexpected case is to
        have a handler for it.
        """
        logger.exception("unhandled error", extra={"path": request.url.path})
        return error_response(
            "AI_UNAVAILABLE",
            "Something went wrong on our side. Try again in a moment.",
            retryable=True,
            status=500,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness only. Deliberately does not touch the provider — an outage is reported
        through the normal error envelope, not by making the container look dead."""
        return {"status": "ok"}

    @app.get(f"{API_PREFIX}/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    app.include_router(session_router.router, prefix=API_PREFIX)
    app.include_router(wardrobe_router.router, prefix=API_PREFIX)
    app.include_router(outfits_router.router, prefix=API_PREFIX)
    app.include_router(jobs_router.router, prefix=API_PREFIX)
    app.include_router(assets_router.router, prefix=API_PREFIX)

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
