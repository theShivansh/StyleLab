"""Request dependencies.

Everything long-lived is built once in the lifespan and hung on `app.state`; the functions
here hand it to routes. Nothing is constructed per request, and nothing is read from a
module-level global — an object a route can reach without being given it is an object a
test cannot replace.

`FaultError` is the bridge between the internal failure vocabulary
(`app/services/faults.py`) and the HTTP error envelope. Routes raise it; one handler in
`app/main.py` renders it. That is the only route to an error response, so a stack trace
cannot reach a user through a path that forgot to catch something.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from app.security.identity import user_id_from
from app.security.tokens import TokenError, TokenSigner
from app.services.compose import OutfitComposer
from app.services.faults import Fault
from app.services.ingest import WardrobeIngestService
from app.services.jobs import InMemoryJobStore
from app.services.ratelimit import Limits, RateLimiter
from app.services.storage import ObjectStore


class FaultError(Exception):
    """A failure that should become the documented error envelope."""

    def __init__(self, fault: Fault) -> None:
        super().__init__(fault.code)
        self.fault = fault


#: The two faults the routes raise most, written once so the copy cannot drift between them.
NOT_FOUND = Fault(
    "ITEM_NOT_FOUND", "We couldn't find that item in your wardrobe.", retryable=False, status=404
)
NO_SESSION = Fault(
    "ITEM_NOT_FOUND",
    "Your session has expired. Reload the page to start a new one.",
    retryable=False,
    status=401,
)
#: An outfit the caller does not own reads exactly like one that was never composed. Same
#: rule as `NOT_FOUND`, different noun — an item message on an outfit route is a small lie
#: that eventually shows up in a screenshot.
OUTFIT_NOT_FOUND = Fault(
    "ITEM_NOT_FOUND", "We couldn't find that look.", retryable=False, status=404
)


def rate_limited(retry_after_s: int) -> Fault:
    """429, and a number the client can act on.

    One message for every limit. A caller learning *which* quota it hit learns the shape of
    our provider spend, and a real user only ever needs to know to wait — which the message
    says, in the one place a user might actually be reading it.
    """
    return Fault(
        "RATE_LIMITED",
        "That's a lot at once. Give it a minute and try again.",
        retryable=True,
        status=429,
        retry_after_s=retry_after_s,
    )


def enforce(limiter: RateLimiter, key: str, *, cost: float = 1.0) -> None:
    """Spend `cost` against `key`, or raise the 429.

    A function rather than a FastAPI dependency because the cost is not known until the
    request body has been read — an upload of twelve photographs costs twelve, and a
    dependency runs before anyone has counted them.
    """
    decision = limiter.check(key, cost=cost)
    if not decision.allowed:
        raise FaultError(rate_limited(decision.retry_after_s))


def client_key(request: Request) -> str:
    """Who to charge when there is no user yet.

    Only `POST /session` needs this, and only because there is no account to throttle
    instead (blocker B15). `request.client.host` is the socket peer: behind a proxy that is
    the proxy unless uvicorn is run with `--proxy-headers --forwarded-allow-ips=...`.
    Reading `X-Forwarded-For` here instead would be a limiter an attacker turns off by
    setting a header, which is worse than none because it looks like protection.
    """
    return request.client.host if request.client else "unknown"


def limits(request: Request) -> Limits:
    return request.app.state.limits


def signer(request: Request) -> TokenSigner:
    return request.app.state.signer


def sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.sessions


def store(request: Request) -> ObjectStore:
    return request.app.state.store


def jobs(request: Request) -> InMemoryJobStore:
    return request.app.state.jobs


def ingest(request: Request) -> WardrobeIngestService:
    return request.app.state.ingest


def composer(request: Request) -> OutfitComposer:
    return request.app.state.composer


def current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """The calling user's id, from a token this API signed.

    401 when there is no usable token, with one message for every reason it failed — see
    `app/security/tokens.py` on why the caller is not told which. The web client treats a
    401 as "start a session and retry", so the distinction would be unused as well as
    leaky.
    """
    try:
        return user_id_from(authorization, request.app.state.signer)
    except TokenError as error:
        raise FaultError(NO_SESSION) from error


CurrentUser = Annotated[str, Depends(current_user)]
ClientKey = Annotated[str, Depends(client_key)]
Rates = Annotated[Limits, Depends(limits)]
Composer = Annotated[OutfitComposer, Depends(composer)]
Sessions = Annotated["sessionmaker[Session]", Depends(sessions)]
Ingest = Annotated[WardrobeIngestService, Depends(ingest)]
Jobs = Annotated[InMemoryJobStore, Depends(jobs)]
Signer = Annotated[TokenSigner, Depends(signer)]
Store = Annotated[ObjectStore, Depends(store)]


__all__ = [
    "NOT_FOUND",
    "NO_SESSION",
    "OUTFIT_NOT_FOUND",
    "ClientKey",
    "Composer",
    "CurrentUser",
    "FaultError",
    "Ingest",
    "Jobs",
    "Rates",
    "Sessions",
    "Signer",
    "Store",
    "client_key",
    "composer",
    "current_user",
    "enforce",
    "ingest",
    "jobs",
    "limits",
    "rate_limited",
    "sessions",
    "signer",
    "store",
]
