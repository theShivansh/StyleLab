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
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.boot import default_transport, verify_models
from app.adapters.exa_search import ExaSearchTransport
from app.adapters.exa_trends import ExaTrendSource
from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.adapters.transport import ChatTransport
from app.config import Settings, get_settings
from app.db.session import create_all, get_engine, session_factory
from app.deps import FaultError
from app.logging_setup import install_log_redaction
from app.preflight import log_findings, verify_deployment, verify_schema
from app.routers import assets as assets_router
from app.routers import internal as internal_router
from app.routers import jobs as jobs_router
from app.routers import outfits as outfits_router
from app.routers import session as session_router
from app.routers import wardrobe as wardrobe_router
from app.security.tokens import TokenSigner
from app.services.compose import OutfitComposer
from app.services.ingest import UploadLimits, WardrobeIngestService
from app.services.jobs import BackgroundJobs, InMemoryJobStore
from app.services.ratelimit import Limits
from app.services.retention import RetentionSweeper
from app.services.storage import (
    DatabaseObjectStore,
    InlineImageSource,
    LocalObjectStore,
    ObjectStore,
)
from app.services.telemetry import LoggingGenerationLog, LoggingTrendLog

logger = logging.getLogger("stylelab")

API_PREFIX = "/api/v1"


def _trend_source(settings, trend_log):
    """The Trend Scout's supply, or `None` and a loud line saying why not.

    Exa is a **required runtime dependency for the Trend Scout and for nothing else**. Absent
    a key the crew runs without that role and discloses degradation level 2, which is the
    honest state of affairs rather than a silent omission.

    Deliberately not a boot failure, unlike `GROQ_API_KEY`. The distinction is what the
    product can still do: it composes perfectly good outfits with no trend context, and it
    cannot compose anything at all without a vision and a text model. A boot check that
    refused to start over a missing trend key would be treating a nice-to-have as the
    product.
    """
    if not settings.exa_api_key:
        logger.warning(
            "EXA_API_KEY is not set: the Trend Scout is disabled and every composition "
            "will report degradation level 2. Outfits are unaffected."
        )
        return None

    logger.info("trend source: exa (region=%s)", settings.trend_region)
    return ExaTrendSource(
        transport=ExaSearchTransport(
            api_key=settings.exa_api_key, timeout_s=settings.exa_timeout_s
        ),
        max_results=settings.exa_max_results,
        search_type=settings.exa_search_type,
        region=settings.trend_region,
        max_age_days=settings.trend_max_age_days,
        cache_ttl_s=settings.trend_cache_ttl_s,
        telemetry=trend_log,
    )


def _object_store(settings: Settings, sessions: sessionmaker[Session]) -> ObjectStore:
    """The store this deployment asked for.

    Two lines of dispatch kept out of the lifespan because the lifespan is already the
    longest function in the project, and because `STORAGE_BACKEND` is a choice worth being
    able to point at. `app/services/storage.py` carries the reasoning for the choice itself.
    """
    if settings.storage_backend == "database":
        logger.info("image store: database")
        return DatabaseObjectStore(sessions)
    logger.info("image store: filesystem")
    return LocalObjectStore(settings.storage_root)


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
        # Before the provider check, because this one costs nothing and catches the errors
        # an operator can actually fix. Raises in production when a local default survived
        # into a deployment; warns about all of them either way.
        log_findings(verify_deployment(settings))
        logger.info(
            "stylelab api starting: env=%s text=%s vision=%s fallback=%s trends=%s",
            settings.app_env,
            settings.groq_text_model,
            settings.groq_vision_model,
            settings.groq_vision_fallback_model,
            # Whether the Trend Scout has a supply, not the key. Logging a key, or enough of
            # one to recognise it, is the sort of thing that happens once and is in a log
            # aggregator forever.
            "exa" if settings.exa_api_key else "disabled",
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
            if settings.app_env == "production":
                # Migrations own the schema here (blocker B12, closed in S11). `create_all`
                # would be actively harmful: it creates whatever is missing, which quietly
                # papers over a migration that did not run and leaves the database in a
                # state no revision describes. `alembic upgrade head` is a deploy step, and
                # a deploy step that failed should look like a failed deploy.
                logger.info("schema: managed by alembic (run `alembic upgrade head`)")
            else:
                # Local and test only. It means a fresh clone has somewhere to put a
                # wardrobe rather than failing on the first insert with a message about a
                # missing table.
                create_all(engine)

            # After create_all, because create_all is what makes a fresh clone correct — and
            # is also what cannot fix a database that is merely *behind*. It adds missing
            # tables and never missing columns, so a database created before a column was
            # added stays silently wrong until a query touches it.
            verify_schema(engine)
            app.state.engine = engine
            app.state.sessions = session_factory(engine)

        # After `app.state.sessions`, because one of the two stores is built from it.
        app.state.store = store or _object_store(settings, app.state.sessions)

        app.state.jobs = InMemoryJobStore()
        app.state.background = BackgroundJobs()
        # Per instance, not per deployment (docs/SECURITY-PRIVACY.md, and the note in
        # app/services/ratelimit.py). Built here with everything else so a test can reach in
        # and exhaust a bucket without waiting fifteen minutes for one to refill.
        app.state.limits = Limits.from_settings(settings)
        # Read once at boot rather than per request: `app/deps.py` is the only reader, and a
        # settings lookup on the hot path to learn a number that cannot change is a lookup
        # with no purpose.
        app.state.trusted_proxy_hops = settings.trusted_proxy_hops
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

        # Blocker B16, closed here. Soft deletion stops a photograph being served; this is
        # what eventually makes it stop existing. Started after the store is built and
        # stopped in the shutdown below, so a test gets a deterministic app with no timer
        # firing underneath it.
        app.state.retention = RetentionSweeper(app.state.sessions, app.state.store)
        app.state.retention.start()

        app.state.trend_log = LoggingTrendLog()
        app.state.trends = _trend_source(settings, app.state.trend_log)

        # Imported here, not at module scope. CrewAI costs about thirteen seconds to import,
        # and `create_app` is called by every test that touches the HTTP surface — paying it
        # at the one place that actually builds a crew keeps the fast suites fast.
        from app.adapters.crew import CrewAIOutfitAdvisor

        app.state.composer = OutfitComposer(
            sessions=app.state.sessions,
            # The crew (docs/AGENT-SYSTEM.md), behind the same `OutfitAdvisor` Protocol the
            # single-call advisor implements. `CompositionService` cannot tell which it has,
            # which is what lets the ladder fall from one to the other.
            advisor=CrewAIOutfitAdvisor(
                app.state.transport,
                model=settings.groq_text_model,
                max_tokens=settings.agent_max_output_tokens,
            ),
            jobs=app.state.jobs,
            background=app.state.background,
            trend_source=app.state.trends,
            # The ceiling on the whole advisor call. Without it the waits compound — three
            # transport attempts inside two advisor attempts, each with its own 30-second
            # client timeout — and a compose nobody cancels can run for minutes.
            latency_budget_s=settings.agent_latency_budget_ms / 1000,
            telemetry=app.state.generation_log,
        )

        yield

        await app.state.retention.stop()
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

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        """Stamp every response with an id, and put it where an error handler can find it.

        docs/API-SPEC.md has carried `request_id` in the error envelope since S0 and nothing
        ever set one, so the field was documentation of an intention. It is worth having for
        one specific reason: the user-facing messages in `app/services/faults.py` are
        deliberately vague — they never quote a provider and never say which quota was hit —
        which means a user reporting a problem has nothing to give support but the time of
        day. An id they can read off the screen is the thing that connects their sentence to
        our log line.

        Accepted from the caller when supplied, so a trace started at the web tier keeps one
        id end to end. Bounded and filtered on the way in: it is echoed in a response header
        and into logs, and an unvalidated header that reaches both is a header-injection and
        log-forging primitive.
        """
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if _usable_request_id(supplied) else f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(FaultError)
    async def _fault(request: Request, error: FaultError) -> JSONResponse:
        fault = error.fault
        return error_response(
            fault.code,
            fault.message,
            retryable=fault.retryable,
            status=fault.status,
            request_id=getattr(request.state, "request_id", None),
            retry_after_s=fault.retry_after_s,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, error: Exception) -> JSONResponse:
        """Anything not classified. Logged in full, reported as an outage.

        The log gets the traceback; the caller gets the envelope. docs/API-SPEC.md: never
        expose a stack trace — and the only way to hold that for the unexpected case is to
        have a handler for it.
        """
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled error", extra={"path": request.url.path, "request_id": request_id}
        )
        return error_response(
            "AI_UNAVAILABLE",
            "Something went wrong on our side. Try again in a moment.",
            retryable=True,
            status=500,
            request_id=request_id,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness only. Deliberately does not touch the provider — an outage is reported
        through the normal error envelope, not by making the container look dead."""
        return {"status": "ok"}

    @app.get(f"{API_PREFIX}/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    # Root, not `API_PREFIX`. It is an operations endpoint alongside `/health`, not part of
    # the product API — nothing a browser calls, nothing versioned with the wardrobe
    # contract, and nothing a session token can reach.
    app.include_router(internal_router.router)

    app.include_router(session_router.router, prefix=API_PREFIX)
    app.include_router(wardrobe_router.router, prefix=API_PREFIX)
    app.include_router(outfits_router.router, prefix=API_PREFIX)
    app.include_router(jobs_router.router, prefix=API_PREFIX)
    app.include_router(assets_router.router, prefix=API_PREFIX)

    return app


app = create_app()


#: A caller-supplied request id is echoed back and written to logs, so it is filtered to
#: characters that cannot forge a header or a log line. Anything else gets ours instead —
#: refusing the request would be a 400 for a field nobody has to send.
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _usable_request_id(value: str) -> bool:
    return bool(_REQUEST_ID.match(value))


def error_response(
    code: str,
    message: str,
    *,
    retryable: bool,
    status: int,
    request_id: str | None = None,
    retry_after_s: int | None = None,
) -> JSONResponse:
    """The single error envelope from docs/API-SPEC.md.

    Never expose a stack trace or a raw provider message (docs/SECURITY-PRIVACY.md).
    `ProviderError.code` and `.message` are already sanitised for exactly this use.
    """
    headers = {"Retry-After": str(retry_after_s)} if retry_after_s else None
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                **({"request_id": request_id} if request_id else {}),
            }
        },
    )
