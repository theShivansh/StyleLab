"""Token signing and caller identity.

The property under test throughout: **the caller cannot choose which user they are.** Every
other assertion here is a way of trying to and failing.
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from app.security.identity import (
    IMAGE_PURPOSE,
    SESSION_PURPOSE,
    bearer_token,
    user_id_from,
)
from app.security.tokens import MAX_TOKEN_CHARS, TokenError, TokenSigner

SECRET = "a-test-signing-key-that-is-long-enough"


@pytest.fixture
def signer():
    return TokenSigner(SECRET)


# --- the round trip -----------------------------------------------------------------------


def test_a_minted_token_verifies_and_carries_its_subject(signer):
    token = signer.mint("user_1", purpose=SESSION_PURPOSE, ttl_s=60)
    claims = signer.verify(token, purpose=SESSION_PURPOSE)

    assert claims.subject == "user_1"
    assert claims.purpose == SESSION_PURPOSE
    assert 0 < claims.seconds_remaining <= 60


def test_a_token_from_a_different_key_does_not_verify(signer):
    other = TokenSigner("a-different-key-entirely-and-long-enough")
    forged = other.mint("user_1", purpose=SESSION_PURPOSE, ttl_s=60)

    with pytest.raises(TokenError):
        signer.verify(forged, purpose=SESSION_PURPOSE)


def test_editing_the_payload_invalidates_the_signature(signer):
    """The attack the whole scheme exists to stop.

    An attacker holding their own valid token rewrites the subject to somebody else's id and
    presents it. The payload is readable — base64 is not encryption — and that is fine: the
    signature is over it, so a changed subject no longer verifies.
    """
    token = signer.mint("user_mine", purpose=SESSION_PURPOSE, ttl_s=60)
    body, _, signature = token.partition(".")

    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    assert claims["sub"] == "user_mine", "payload should be plainly readable"
    claims["sub"] = "user_theirs"

    rewritten = base64.urlsafe_b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")

    with pytest.raises(TokenError):
        signer.verify(f"{rewritten}.{signature}", purpose=SESSION_PURPOSE)


def test_an_expired_token_does_not_verify(signer):
    # Reach past the deadline rather than sleeping: the assertion is about the comparison,
    # and a test that sleeps for a second is a test that gets deleted.
    expired = json.dumps(
        {"sub": "user_1", "prp": SESSION_PURPOSE, "exp": int(time.time()) - 5},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    forged_body = base64.urlsafe_b64encode(expired).decode().rstrip("=")
    # Signed properly, by us, and still refused — expiry is checked after the signature.
    valid_signature_for_expired = TokenSigner(SECRET)._sign(forged_body)

    with pytest.raises(TokenError):
        signer.verify(f"{forged_body}.{valid_signature_for_expired}", purpose=SESSION_PURPOSE)


def test_an_image_token_cannot_be_presented_as_a_session(signer):
    """Why the purpose is inside the signed payload.

    One key signs both kinds of token. Without the purpose, an image capability — which
    travels in a URL and is therefore the one an attacker is most likely to obtain — would
    be a valid session token for whatever its subject named.
    """
    image_token = signer.mint("user_1/asset_1", purpose=IMAGE_PURPOSE, ttl_s=60)

    with pytest.raises(TokenError):
        signer.verify(image_token, purpose=SESSION_PURPOSE)


@pytest.mark.parametrize(
    "token", ["", "nonsense", "no-dot-separator", ".", "body.", ".signature", "a" * 9000]
)
def test_malformed_tokens_are_refused_without_parsing(signer, token):
    with pytest.raises(TokenError):
        signer.verify(token, purpose=SESSION_PURPOSE)


def test_an_absurdly_long_token_is_refused_by_length_first(signer):
    with pytest.raises(TokenError):
        signer.verify("x" * (MAX_TOKEN_CHARS + 1), purpose=SESSION_PURPOSE)


# --- the key ------------------------------------------------------------------------------


def test_an_unset_secret_produces_a_random_key_not_a_shared_one():
    """Two processes booted without `SESSION_SECRET` must not accept each other's tokens.

    A hardcoded fallback would be the convenient default and would make every deployment
    forgeable by anyone who read the source. Random is the safe direction: the cost is that
    sessions do not survive a restart, and `TokenSigner` says so at WARNING.
    """
    first, second = TokenSigner(""), TokenSigner("")

    assert first.ephemeral and second.ephemeral
    minted_by_first = first.mint("user_1", purpose=SESSION_PURPOSE, ttl_s=60)
    with pytest.raises(TokenError):
        second.verify(minted_by_first, purpose=SESSION_PURPOSE)


def test_a_configured_secret_is_not_marked_ephemeral():
    assert TokenSigner(SECRET).ephemeral is False


def test_minting_refuses_a_subjectless_or_expired_token(signer):
    with pytest.raises(ValueError):
        signer.mint("", purpose=SESSION_PURPOSE, ttl_s=60)
    with pytest.raises(ValueError):
        signer.mint("user_1", purpose=SESSION_PURPOSE, ttl_s=0)


# --- the header ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header", [None, "", "Basic abc", "Bearer", "Token abc", "bearerabc"]
)
def test_anything_that_is_not_a_bearer_token_is_refused(header):
    with pytest.raises(TokenError):
        bearer_token(header)


def test_the_bearer_scheme_is_matched_case_insensitively(signer):
    token = signer.mint("user_1", purpose=SESSION_PURPOSE, ttl_s=60)
    assert user_id_from(f"bearer {token}", signer) == "user_1"
    assert user_id_from(f"Bearer {token}", signer) == "user_1"
    assert user_id_from(f"BEARER {token}", signer) == "user_1"
