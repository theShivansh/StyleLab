"""HMAC-signed, expiring tokens.

Two things need them and they share one key:

* **session tokens** — the caller's identity, so `user_id` is server-asserted rather than
  request-supplied (`app/security/identity.py`)
* **image references** — a short-lived capability to fetch one stored image, so the browser
  can render a private photograph without a session cookie crossing origins
  (`app/services/storage.py`)

## Why the key may be generated at startup

`SESSION_SECRET` is read from the environment. When it is absent a random key is generated
for the process and the fact is logged at WARNING.

That is a deliberate default, and it is the *safe* direction: a random key means no token
can be forged, and the only cost is that existing tokens stop verifying after a restart —
a visitor starts a new wardrobe. The alternative defaults are both worse. A hardcoded
fallback key would make every deployment forgeable by anyone who read this file. Refusing
to boot would make a fresh clone unusable for a reason unrelated to the product.

It is not the "silent fallback" the project forbids elsewhere. That rule is about product
truth — never serving fabricated AI output (AI-EVAL-CASES Case 25). Nothing here affects
what the model said or which wardrobe was read; the degradation is session lifetime, and it
is announced rather than hidden. Set `SESSION_SECRET` for anything that must survive a
deploy or run on more than one instance.

## Shape

    <base64url payload>.<base64url hmac-sha256>

The payload is compact JSON holding the subject, the purpose and an absolute expiry. The
purpose is inside the signed payload, so a token minted to fetch an image cannot be
presented as a session — signing the same subject for two uses with one key would otherwise
let one be swapped for the other.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

logger = logging.getLogger("stylelab.security")

#: Rejected rather than parsed. A token is machine-minted and never near this long, so
#: anything bigger is someone probing.
MAX_TOKEN_CHARS = 4096


class TokenError(Exception):
    """A token was absent, malformed, expired, or not signed by us.

    One exception for every failure on purpose: a caller that can tell "expired" from
    "bad signature" from "wrong purpose" learns something about the key. The log line says
    which; the caller is told only that it did not verify.
    """


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    purpose: str
    expires_at: int

    @property
    def seconds_remaining(self) -> int:
        return max(0, self.expires_at - int(time.time()))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class TokenSigner:
    """Mints and verifies the tokens above.

    Holds the key. Nothing else in the application reads `SESSION_SECRET`, so there is one
    place to change when a key manager replaces the environment variable.
    """

    def __init__(self, secret: str | None = None) -> None:
        if secret:
            self._key = secret.encode("utf-8")
            self.ephemeral = False
        else:
            self._key = secrets.token_bytes(32)
            self.ephemeral = True
            logger.warning(
                "SESSION_SECRET is not set: signing with a key generated for this process. "
                "Sessions and image links will not survive a restart, and a second instance "
                "will reject this one's tokens. Set SESSION_SECRET for anything deployed."
            )

    def mint(self, subject: str, *, purpose: str, ttl_s: int) -> str:
        if not subject:
            raise ValueError("a token needs a subject")
        if ttl_s <= 0:
            raise ValueError("a token needs a positive lifetime")

        payload = json.dumps(
            {"sub": subject, "prp": purpose, "exp": int(time.time()) + ttl_s},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        body = _b64encode(payload)
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str, *, purpose: str) -> TokenClaims:
        """Return the claims, or raise `TokenError`.

        Order matters: signature first, then expiry, then purpose. Nothing inside an
        unverified payload is read as data before the signature has been checked.
        """
        if not token or len(token) > MAX_TOKEN_CHARS:
            raise TokenError("no token")

        body, _, signature = token.partition(".")
        if not body or not signature:
            raise TokenError("malformed token")

        # Constant time, and before the payload is parsed at all.
        if not hmac.compare_digest(signature, self._sign(body)):
            raise TokenError("bad signature")

        try:
            claims = json.loads(_b64decode(body))
            parsed = TokenClaims(
                subject=str(claims["sub"]),
                purpose=str(claims["prp"]),
                expires_at=int(claims["exp"]),
            )
        except (ValueError, KeyError, TypeError) as error:
            # Signed by us and still unreadable — a deploy skew, not an attacker.
            raise TokenError("unreadable payload") from error

        if parsed.expires_at <= int(time.time()):
            raise TokenError("expired")
        if not hmac.compare_digest(parsed.purpose, purpose):
            raise TokenError("wrong purpose")

        return parsed

    def _sign(self, body: str) -> str:
        return _b64encode(hmac.new(self._key, body.encode("ascii"), sha256).digest())


__all__ = ["MAX_TOKEN_CHARS", "TokenClaims", "TokenError", "TokenSigner"]
