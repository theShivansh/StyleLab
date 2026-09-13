"""Starting a session.

`POST /session` creates an anonymous user and returns a signed token for it. There is no
password and no verification: this is an identity seam, not authentication — see
`app/security/identity.py` for what that means and what replaces it in S11.

The route creates the `users` row as well as the token. `wardrobe_items.user_id` is a
foreign key onto it, so a token whose subject has no row would produce an insert failure at
the user's first upload rather than here.

## Why the client cannot ask for a specific user

`POST /session` takes no body. If it accepted a `user_id` it would be a login with no
credential, which is the same thing as no ownership boundary at all — the one property this
whole layer exists to hold. A caller who wants their previous wardrobe presents their
previous token.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.deps import ClientKey, Rates, Sessions, Signer, enforce
from app.repositories.wardrobe import WardrobeRepository
from app.security.identity import SESSION_PURPOSE

router = APIRouter(tags=["session"])


@router.post("/session", status_code=201)
async def create_session(
    sessions: Sessions, signer: Signer, rates: Rates, client: ClientKey
) -> dict[str, Any]:
    """Mint an anonymous identity and a token for it.

    Limited per client address, and this is the limit that matters most: with no signup to
    throttle instead (blocker B15), an unlimited supply of identities is an unlimited supply
    of upload and composition quota. The address is the socket peer — see `deps.client_key`
    on why `X-Forwarded-For` is uvicorn's business and not this handler's.
    """
    enforce(rates.sessions, client)

    settings = get_settings()
    user_id = f"user_{uuid.uuid4().hex[:16]}"

    with sessions() as session:
        # A placeholder address, unique per user, and never shown or sent anywhere. The
        # column is `unique` and not null; real addresses arrive with real accounts.
        WardrobeRepository(session).add_user(user_id, f"{user_id}@anonymous.invalid")
        session.commit()

    return {
        "user_id": user_id,
        "token": signer.mint(user_id, purpose=SESSION_PURPOSE, ttl_s=settings.session_ttl_s),
        "expires_in": settings.session_ttl_s,
    }


__all__ = ["router"]
