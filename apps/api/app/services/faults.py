"""Error classification — internal failures to the error contract in docs/API-SPEC.md.

Two vocabularies meet here and neither should be the other.

`ProviderError.code` is diagnostic: `AI_RATE_LIMITED`, `AI_CONTRACT`, `AI_MODEL_MISSING`.
Those distinctions drive retry and fallback decisions inside the adapter, and they say
things about our provider relationship that a user has no use for and no business knowing.

The API's codes are the ones docs/API-SPEC.md enumerates. They are a closed set the web
client switches on, and they describe what happened *to the user's request*.

So the mapping collapses detail on purpose. A rate limit and an outage are both
`AI_UNAVAILABLE` to a caller: the difference is our capacity problem, the response is the
same, and "rate limited" invites a user to retry into a wall.

## `retryable` is about this request, not about the system

It answers "would doing this again plausibly work?". A timeout, yes. A model id that does
not resolve, no — that is a deployment misconfiguration and no amount of retrying fixes it,
so the honest answer is to stop rather than to spin a card.

## No message here quotes a provider

`ProviderError.message` is already sanitised at the transport (`_sanitised`), because a
provider's own error text can quote the request, and the request contains text recovered
from a photograph of the user's home. This module does not undo that: the user-facing
strings below are written here, in full, and none of them interpolate anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.provider_errors import (
    ProviderContractError,
    ProviderError,
    ProviderModelMissingError,
    ProviderRateLimitedError,
    ProviderRefusedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.domain.errors import ConfigurationError, SchemaInvalidError
from app.services.images import ImageRejectedError
from app.services.storage import StorageError


@dataclass(frozen=True, slots=True)
class Fault:
    """One failure, in the shape the error contract wants."""

    code: str
    message: str
    retryable: bool
    status: int = 500
    #: Rendered as a `Retry-After` header when present. Only the rate limiter sets it: a
    #: provider outage has no honest number to put here, and inventing one would tell a
    #: client to come back at a moment nobody has any reason to expect.
    retry_after_s: int | None = None


#: Kept beside the mapping so a new provider error cannot quietly pick up a default that
#: tells the user to try again forever.
_PROVIDER_FAULTS: dict[type[ProviderError], Fault] = {
    ProviderTimeoutError: Fault(
        "PROVIDER_TIMEOUT",
        "Reading that photo took too long. Try it again.",
        retryable=True,
        status=504,
    ),
    ProviderRateLimitedError: Fault(
        "AI_UNAVAILABLE",
        "We're at capacity right now. Give it a moment and try again.",
        retryable=True,
        status=503,
    ),
    ProviderUnavailableError: Fault(
        "AI_UNAVAILABLE",
        "The model service is unavailable right now. This isn't something you did.",
        retryable=True,
        status=503,
    ),
    ProviderModelMissingError: Fault(
        # Not retryable: the configured model does not exist. Retrying cannot fix a
        # deployment problem, and pretending it might wastes the user's time instead of ours.
        "AI_UNAVAILABLE",
        "Something is misconfigured on our side. We've been told about it.",
        retryable=False,
        status=503,
    ),
    ProviderRefusedError: Fault(
        "AI_UNAVAILABLE",
        "We couldn't reach the model service. This isn't something you did.",
        retryable=False,
        status=503,
    ),
    ProviderContractError: Fault(
        "EXTRACTION_FAILED",
        "We couldn't read that photo clearly. Retake it, or add the details by hand.",
        retryable=True,
        status=502,
    ),
}

_EXTRACTION_FAILED = Fault(
    "EXTRACTION_FAILED",
    "We couldn't read that photo clearly. Retake it, or add the details by hand.",
    retryable=True,
    status=502,
)

_UNKNOWN = Fault(
    "AI_UNAVAILABLE",
    "Something went wrong on our side. Try again in a moment.",
    retryable=True,
    status=500,
)


def classify(error: Exception) -> Fault:
    """The API-facing fault for an internal failure."""
    if isinstance(error, ImageRejectedError):
        # Already user-facing: `ImageRejectedError` carries the actionable copy because the copy
        # is the whole point of refusing an image politely. 422, not 500 — the request was
        # understood and the file was the problem.
        return Fault(error.code, error.message, retryable=False, status=422)

    if isinstance(error, SchemaInvalidError):
        # The model answered and would not follow the schema. Retryable because a re-ask
        # genuinely often works, and the adapter has already used its one automatic attempt.
        return _EXTRACTION_FAILED

    if isinstance(error, ProviderError):
        for error_type, fault in _PROVIDER_FAULTS.items():
            if isinstance(error, error_type):
                return fault
        # A `ProviderError` that is not one of the subclasses above. Treated as an outage
        # rather than assumed benign.
        return Fault(
            "AI_UNAVAILABLE",
            "The model service is unavailable right now. This isn't something you did.",
            retryable=error.retryable,
            status=503,
        )

    if isinstance(error, StorageError):
        return Fault(
            "IMAGE_UNREADABLE",
            "We couldn't read that photo back. Try uploading it again.",
            retryable=True,
            status=500,
        )

    if isinstance(error, ConfigurationError):
        return Fault(
            "AI_UNAVAILABLE",
            "Something is misconfigured on our side. We've been told about it.",
            retryable=False,
            status=503,
        )

    return _UNKNOWN


__all__ = ["Fault", "classify"]
