"""`classify` — internal failures to the error contract, and which of them a user can retry.

The retry button on a failed upload card is drawn from `retryable` and nothing else, so this
mapping decides whether a user is offered a way forward or left looking at a dead card.
"""

from __future__ import annotations

import pytest

from app.adapters.provider_errors import (
    ProviderContractError,
    ProviderError,
    ProviderModelMissingError,
    ProviderOutputInvalidError,
    ProviderRateLimitedError,
    ProviderRefusedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.faults import classify


def test_an_answer_the_provider_refused_as_invalid_can_be_read_again():
    """Found on the deployed site. A photo's extraction came back `json_validate_failed`, which
    the provider sends as a 400, and the card said "We couldn't reach the model service" with
    no way to try again. The request was fine; the generation was not, and a re-ask is exactly
    what fixes that."""
    fault = classify(ProviderOutputInvalidError("cut off", model="m"))

    assert fault.retryable is True
    assert fault.code == "EXTRACTION_FAILED"
    assert "Try it again" in fault.message


def test_a_genuine_refusal_is_still_not_offered_as_retryable():
    """The half that must not loosen: a rejected key is rejected on every attempt."""
    fault = classify(ProviderRefusedError("the provider rejected our credentials", model="m"))

    assert fault.retryable is False


@pytest.mark.parametrize(
    "error_type",
    [
        ProviderTimeoutError,
        ProviderRateLimitedError,
        ProviderUnavailableError,
        ProviderModelMissingError,
        ProviderRefusedError,
        ProviderOutputInvalidError,
        ProviderContractError,
    ],
)
def test_every_provider_error_has_a_deliberate_fault(error_type: type[ProviderError]):
    """No provider error reaches the generic fallback, whose `retryable` is whatever the
    exception's own flag happens to say. Each one is a decision someone made on purpose."""
    fault = classify(error_type("x", model="m"))

    assert fault.code in {"AI_UNAVAILABLE", "PROVIDER_TIMEOUT", "EXTRACTION_FAILED"}
    assert fault.message
