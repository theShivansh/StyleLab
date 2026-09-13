"""Telling "the provider is full" apart from "the product is broken".

`AI_UNAVAILABLE` is what the API answers for a rate limit — deliberately the same code it
answers for an outage, because the difference is our capacity problem and a user can do
nothing with it (`app/services/faults.py`). That collapse is right for the product and
unhelpful for a canary suite, so the helper below reads the code and stops the test rather
than reporting a red that says nothing about the contract it exists to check.

Measured on this account in S7, from the response headers of a live call: 1000 requests per
minute and 8000 **input** tokens per minute, plus a separate **output** tokens-per-minute
ceiling of 1000 per model that the headers do not report. The configured vision ceiling is
2048, so one extraction can ask for more output than the whole minute allows and the provider
refuses it up front on expected output — `Limit 1000, Requested 1579`, before the model runs.

Each module passes on its own; the suite exceeded the budget as a set. `conftest.VISION_PACING_S`
paces the modules apart and this is the backstop for when that is not enough.

Skipping on a genuine outage is the cost of the collapse. `test_model_availability.py` is the
canary for that case and does not go through this path.

A separate module rather than a conftest import: `tests/live/` is not a package, so
`from tests.live.conftest import ...` does not resolve from the repository root — which is
the same trap `apps/api/tests/support.py` was created to get out of.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest

CAPACITY_CODE = "AI_UNAVAILABLE"
#: What the adapter records on an attempt the provider rate-limited.
PROVIDER_CAPACITY_CODE = "AI_RATE_LIMITED"


def skip_if_at_capacity(job: dict) -> None:
    """Skip when a finished job failed because the provider was at capacity."""
    error = job.get("error") or {}
    if job.get("status") == "failed" and error.get("code") == CAPACITY_CODE:
        pytest.skip(
            "provider at capacity (tier output-tokens-per-minute limit) — run this module "
            "on its own, or raise STYLELAB_LIVE_PACING_S"
        )


@contextlib.contextmanager
def tolerating_capacity() -> Iterator[None]:
    """The same rule for tests that call the provider directly.

    They never reach the fault classifier, so the refusal arrives as
    `ProviderRateLimitedError` rather than as a job error code. The judgement is identical:
    the provider being full is not evidence about our schema.
    """
    from app.adapters.provider_errors import ProviderRateLimitedError

    try:
        yield
    except ProviderRateLimitedError:
        pytest.skip(
            "provider at capacity (tier output-tokens-per-minute limit) — run this module "
            "on its own, or raise STYLELAB_LIVE_PACING_S"
        )


def skip_if_the_fallback_covered_capacity(outcome) -> None:
    """A fallback that ran because the primary was *full* proves nothing about deprecation.

    `used_fallback` is the assertion "the primary answered on a healthy day", and it is worth
    keeping. But the availability chain treats a rate limit as a reason to move on — correctly,
    since a busy model and a retired one look identical from here and both are answered by
    trying the other one. So a red on that assertion during a capacity squeeze is the chain
    working, reported as a failure.

    The attempt record is what tells them apart: a refusal carries the provider's own code.
    """
    if not getattr(outcome, "used_fallback", False):
        return
    attempts = getattr(outcome, "attempts", ())
    first = attempts[0] if attempts else None
    if first is not None and first.rejected_reason == PROVIDER_CAPACITY_CODE:
        pytest.skip(
            "the primary model was rate-limited and the fallback answered — capacity, not "
            "deprecation; re-run this module on its own"
        )


__all__ = [
    "CAPACITY_CODE",
    "PROVIDER_CAPACITY_CODE",
    "skip_if_at_capacity",
    "skip_if_the_fallback_covered_capacity",
    "tolerating_capacity",
]
