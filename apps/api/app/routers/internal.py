"""Operational endpoints. Not product API, and not reachable by a product credential.

## Why this exists

A Supabase project on the free tier pauses after a stretch with no database activity, and a
paused project means the next visitor meets a cold start or an outage. The fix is to touch
the database on a schedule. `.github/workflows/db-activity.yml` calls this once a day.

**It is a real connectivity check, not a keep-alive that pretends to be one.** The request
opens a session against the configured database and executes `SELECT 1` through the same
engine every other request uses. If Postgres is unreachable, misconfigured, out of
connections or asleep, this fails — and it fails in a scheduled job that can page somebody,
rather than in front of a user. A workflow that pinged a static route would keep the project
awake and tell nobody anything, which is the version of this worth refusing to write.

## Why not `/health`

`/health` is liveness only, deliberately: it answers without touching the provider or the
database so that a dependency outage is reported through the error envelope rather than by
making the container look dead to an orchestrator that will then restart it. Giving it a
database query would make every Postgres hiccup a restart loop. Two questions, two
endpoints.

## What it may and may not do

It runs one statement and that statement is a constant. It reads no wardrobe, no user and no
owned row of any kind, so there is no ownership boundary here to respect or to bypass —
`app/repositories/` remains the only thing that reads owned data, and it remains scoped.

The response carries a dialect, a duration and a timestamp. It does not carry the database
URL, a host, a user, or anything else that would turn a monitoring endpoint into a
credential disclosure. A Postgres URL contains a password; the boot log records the dialect
only, for the same reason.

## The token

A dedicated header, `X-DB-Activity-Token`, checked against `DB_ACTIVITY_TOKEN` in constant
time. Dedicated rather than `Authorization: Bearer`, because a session token and an
operations credential should not be interchangeable at the point of comparison — and because
a browser will never send this one by accident.

**The token is checked before the database is touched.** That order is the whole security
property: without it, an unauthenticated flood would be a way to make this API hammer its own
database from the outside.
"""

from __future__ import annotations

import hmac
import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header
from sqlalchemy import text

from app.deps import FaultError, Sessions
from app.services.faults import Fault

logger = logging.getLogger("stylelab.internal")

router = APIRouter(prefix="/internal", tags=["internal"])

#: The header carrying the operations credential.
TOKEN_HEADER = "X-DB-Activity-Token"

#: One statement, constant, and the cheapest thing that proves a round trip actually
#: happened. Anything more would be reading data this endpoint has no business reading.
PROBE = text("SELECT 1")

_UNAUTHORISED = Fault(
    "ITEM_NOT_FOUND",
    "Not authorised.",
    retryable=False,
    status=401,
)

_NOT_CONFIGURED = Fault(
    "AI_UNAVAILABLE",
    "This endpoint is not configured.",
    retryable=False,
    status=503,
)


@router.get("/db-activity")
async def db_activity(
    sessions: Sessions,
    x_db_activity_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Prove the database answers. Returns 200, or fails the scheduled job.

    401 when the token is absent or wrong; 503 when no token is configured at all, which is
    a different problem and deserves a different answer — an operator who has set nothing
    should not spend an afternoon believing they set it wrongly.
    """
    from app.config import get_settings

    expected = get_settings().db_activity_token

    if not expected:
        # Unconfigured means closed, not open. The alternative — treating an empty expected
        # token as "no check required" — would leave an endpoint that touches the database
        # reachable by anyone the moment somebody forgets a variable.
        logger.warning("db-activity was called but DB_ACTIVITY_TOKEN is not set")
        raise FaultError(_NOT_CONFIGURED)

    # Constant time, and **before** any database work. An attacker who can make this API
    # open a connection per request has a way to exhaust its pool from the outside.
    supplied = x_db_activity_token or ""
    if not hmac.compare_digest(supplied, expected):
        logger.warning("db-activity rejected a request with a missing or invalid token")
        raise FaultError(_UNAUTHORISED)

    started = time.perf_counter()
    with sessions() as session:
        result = session.execute(PROBE).scalar_one()
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if result != 1:
        # Reachable only if something is answering that is not the database we think it is.
        raise FaultError(_NOT_CONFIGURED)

    dialect = session.get_bind().dialect.name

    logger.info("db-activity ok", extra={"dialect": dialect, "latency_ms": elapsed_ms})
    return {
        "database": "ok",
        # Safe to report, and the same thing the boot log records. The URL is not, and never
        # appears here: a Postgres URL carries a password.
        "dialect": dialect,
        "latency_ms": elapsed_ms,
        "checked_at": datetime.now(UTC).isoformat(),
    }


__all__ = ["TOKEN_HEADER", "router"]
