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

from ipaddress import ip_address
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from app.security.identity import user_id_from
from app.security.tokens import TokenError, TokenSigner
from app.services.compose import OutfitComposer
from app.services.faults import Fault
from app.services.ingest import WardrobeIngestService
from app.services.jobs import JobStore
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


def forwarded_peer(header: str | None, *, hops: int) -> str | None:
    """The caller's address according to `hops` trusted proxies, or `None`.

    `X-Forwarded-For` is a list that grows on the right: each proxy appends the address it
    received the connection from. So with one trusted proxy in front, the **last** entry is
    the address that proxy saw — which is the real caller, and is the one entry a client
    cannot write, because the proxy appends it after whatever the client sent. Everything to
    the left of it is hearsay the client may have invented.

    Hence counting from the right by the number of hops, rather than the thing that looks
    equivalent and is not: reading the leftmost entry is a rate limiter anybody switches off
    with a header, which is worse than no limiter because it looks like one.

    Two refusals, both toward over-throttling rather than toward an open door:

    * a chain shorter than `hops` means the request did not arrive the way the configuration
      says it does, so nothing here is trustworthy
    * an entry that is not an IP address is not used as a bucket key, so a caller cannot mint
      unlimited distinct keys out of arbitrary text, and a misconfiguration lands on the
      socket peer instead of on something a client chose
    """
    if hops <= 0 or not header:
        return None
    chain = [part.strip() for part in header.split(",") if part.strip()]
    if len(chain) < hops:
        return None
    candidate = chain[-hops]
    try:
        ip_address(candidate)
    except ValueError:
        return None
    return candidate


def client_key(request: Request) -> str:
    """Who to charge when there is no user yet.

    Only `POST /session` needs this, and only because there is no account to throttle
    instead (blocker B15). `request.client.host` is the socket peer, which is the right
    answer whenever this API is reachable directly.

    Behind a proxy the socket peer is the proxy, and the limiter becomes one bucket for the
    internet — ten sessions per fifteen minutes, shared by every visitor. `TRUSTED_PROXY_HOPS`
    is how a deployment says how many proxies it actually has; `forwarded_peer` explains why
    that is a count and not a boolean. Unset, this behaves exactly as it did before.
    """
    hops = getattr(request.app.state, "trusted_proxy_hops", 0)
    forwarded = forwarded_peer(request.headers.get("x-forwarded-for"), hops=hops)
    if forwarded is not None:
        return forwarded
    return request.client.host if request.client else "unknown"


def limits(request: Request) -> Limits:
    return request.app.state.limits


def signer(request: Request) -> TokenSigner:
    return request.app.state.signer


def sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.sessions


def store(request: Request) -> ObjectStore:
    return request.app.state.store


def jobs(request: Request) -> JobStore:
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
Jobs = Annotated[JobStore, Depends(jobs)]
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
    "forwarded_peer",
    "ingest",
    "jobs",
    "limits",
    "rate_limited",
    "sessions",
    "signer",
    "store",
]
