"""Serving a private photograph to the browser that owns it.

One route, and it is the only way an uploaded image leaves the server.

## Why it is a capability and not a session check

The obvious design is `GET /assets/{asset_id}` authorised by the caller's session. It does
not work in a browser: an `<img src>` pointing at another origin sends no `Authorization`
header and no `SameSite=Lax` cookie, and relaxing the cookie to `SameSite=None` requires
HTTPS, which a local run does not have.

So the capability travels in the URL — a signed, expiring token naming the owner and the
asset, which is what every object store does and what docs/SECURITY-PRIVACY.md asks for.
It sits in the **path** rather than the query string, because that spec says signed URLs are
never placed in a query string and there is no reason to argue with it: a path segment
satisfies the rule literally and behaves identically.

## The scoped read survives

The token's subject carries the owner, so the handler still reads the asset through
`AssetRepository.get(user_id, asset_id)` — the same scoped query as everything else. This
route is not a primary-key load with a signature bolted on; it is a normal scoped read
whose `user_id` came from our own HMAC instead of from a session header.

## What is not logged

Not the token, not the storage key, not the bytes. The path contains a live credential, so
an access log that records paths records credentials — which is what
`app/logging_setup.py` exists to prevent, at the logging layer rather than by asking
callers to remember.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.config import get_settings
from app.deps import NOT_FOUND, FaultError, Sessions, Signer, Store
from app.repositories.wardrobe import AssetRepository
from app.security.identity import IMAGE_PURPOSE
from app.security.tokens import TokenError
from app.services.storage import StorageError, split_image_subject

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}/{token}")
async def get_asset(
    asset_id: str,
    token: str,
    sessions: Sessions,
    signer: Signer,
    store: Store,
) -> Response:
    """One stored image. 404 for anything that does not verify.

    Expired, forged, wrong-purpose, wrong-asset and not-found all answer identically. A
    distinct "expired" response would be friendlier and would also tell an attacker which
    of their guesses was structurally correct; the client's answer to all five is the same
    anyway — re-read the item and get a fresh URL.
    """
    try:
        claims = signer.verify(token, purpose=IMAGE_PURPOSE)
        user_id, signed_asset_id = split_image_subject(claims.subject)
    except (TokenError, ValueError) as error:
        raise FaultError(NOT_FOUND) from error

    # The token is authority for the asset it names. Trusting the path instead would let a
    # valid token for one image be pointed at another.
    if signed_asset_id != asset_id:
        raise FaultError(NOT_FOUND)

    with sessions() as session:
        asset = AssetRepository(session).get(user_id, asset_id)
    if asset is None:
        raise FaultError(NOT_FOUND)

    try:
        data = await store.get(asset.storage_key)
    except StorageError as error:
        raise FaultError(NOT_FOUND) from error

    # Cacheable for as long as the token is valid and no longer, so a revoked or expired
    # link cannot be served from a shared cache after the fact.
    cache_s = min(claims.seconds_remaining, get_settings().image_url_ttl_s)

    return Response(
        content=data,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": f"private, max-age={cache_s}",
            "X-Content-Type-Options": "nosniff",
            # The bytes are a photograph of someone's home. Nothing embeds them, and nothing
            # should be able to script against them.
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


__all__ = ["router"]
