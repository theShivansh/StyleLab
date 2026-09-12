"""Who is calling.

Every wardrobe route is ownership-scoped (docs/API-SPEC.md), which means every route needs
a `user_id` — and where that id comes from decides whether the ownership boundary is real.

## The rule this module exists to keep

**The caller never names the user.** A `X-User-Id` header or a `user_id` in the body would
have been three lines and would have handed every wardrobe to anyone who could type
somebody else's id. It would also have made every ownership test in S4 vacuous: a scoped
query is worth nothing if the scope is chosen by the requester.

So identity arrives as a **bearer token this API minted and signed**. The server reads the
subject out of its own signature. A caller can hold a token or not hold one; it cannot
choose what is inside one.

## What this is not

It is not authentication. `POST /session` hands a token to anyone who asks and creates an
anonymous user to go with it — there is no password, no email verification, no revocation.
It is an *identity seam* of the right shape: an opaque credential in an `Authorization`
header, verified server-side, with `user_id` derived from it.

Real accounts land in S11 with Supabase auth. The token gets longer and someone else mints
it; the seam, the header and every scoped query below it stay exactly as they are. That is
the point of building it this way now rather than passing the id around and fixing it later.

Deliberately a bearer header rather than a cookie: the browser calls this API cross-origin
in development (`localhost:3000` to `localhost:8000`), and a cookie that works there needs
`SameSite=None; Secure`, which needs HTTPS, which a local run does not have. A header has
none of that coupling and the same forgery resistance.
"""

from __future__ import annotations

from app.security.tokens import TokenError, TokenSigner

#: Signed into every token so one purpose's token cannot be presented as another's.
SESSION_PURPOSE = "session"
IMAGE_PURPOSE = "image"

_BEARER = "bearer "


def bearer_token(authorization: str | None) -> str:
    """Pull the credential out of an `Authorization` header.

    Raises `TokenError` when there is nothing usable, so a missing header and a malformed
    one take the same path — the caller is told to start a session either way.
    """
    if not authorization:
        raise TokenError("no authorization header")
    if not authorization.lower().startswith(_BEARER):
        raise TokenError("not a bearer token")
    return authorization[len(_BEARER) :].strip()


def user_id_from(authorization: str | None, signer: TokenSigner) -> str:
    """The calling user's id, taken from our own signature. Raises `TokenError`."""
    return signer.verify(bearer_token(authorization), purpose=SESSION_PURPOSE).subject


__all__ = ["IMAGE_PURPOSE", "SESSION_PURPOSE", "bearer_token", "user_id_from"]
