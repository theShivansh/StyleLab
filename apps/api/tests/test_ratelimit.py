"""The token bucket, and the two properties that make it worth having.

`docs/SECURITY-PRIVACY.md` has asked for rate limiting on upload and extraction since S0.
What makes it urgent rather than tidy is what sits beside it: there is no authentication
(blocker B15), so `POST /session` hands a token to anyone, and that token reaches an
endpoint that calls a metered vision model once per photograph.

Time is injected rather than slept through. A limiter tested with `sleep` is a limiter
tested at one speed, and the interesting cases — a bucket refilling part way, a cost larger
than the whole bucket — are the ones a real clock makes slow and flaky.
"""

from __future__ import annotations

import pytest

from app.services.ratelimit import MAX_TRACKED_KEYS, Limits, Quota, RateLimiter


class Clock:
    """A hand-cranked monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def limiter(amount: float = 10, seconds: float = 100) -> tuple[RateLimiter, Clock]:
    clock = Clock()
    return RateLimiter(Quota.per_window(amount, seconds=seconds), now=clock), clock


# --- the bucket ----------------------------------------------------------------------------


def test_a_fresh_key_may_spend_its_whole_burst_at_once():
    """A real user's first action is a full batch of photographs, not a trickle."""
    bucket, _ = limiter(amount=10)

    assert bucket.check("user", cost=10).allowed
    assert not bucket.check("user", cost=1).allowed


def test_cost_is_per_image_not_per_request():
    """The reason this is a bucket and not a counter.

    One POST carrying twelve photographs is twelve provider calls. Priced per request, the
    cheapest way to drain the key would be to send them all in one.
    """
    bucket, _ = limiter(amount=10)

    assert bucket.check("user", cost=6).allowed
    assert bucket.check("user", cost=4).allowed
    assert not bucket.check("user", cost=1).allowed


def test_the_allowance_comes_back_continuously_rather_than_all_at_once():
    """The hole a fixed window has and a bucket does not.

    A fixed window hands a client its whole allowance at 11:59:59 and the whole of the next
    one a second later — twice the intended burst at the worst possible moment.
    """
    bucket, clock = limiter(amount=10, seconds=100)
    assert bucket.check("user", cost=10).allowed

    clock.advance(50)  # half a window

    assert bucket.check("user", cost=5).allowed
    assert not bucket.check("user", cost=1).allowed


def test_a_refusal_costs_nothing_so_a_throttled_client_can_recover():
    """A limiter that charges for refusals never lets anyone back in.

    A client retrying every second against a bucket that debits on failure is a client that
    stays locked out for as long as it keeps trying, which is exactly what a well-behaved
    retry loop does.
    """
    bucket, clock = limiter(amount=10, seconds=100)
    assert bucket.check("user", cost=10).allowed

    for _ in range(20):
        assert not bucket.check("user", cost=1).allowed

    clock.advance(10)  # one token's worth
    assert bucket.check("user", cost=1).allowed


def test_keys_do_not_share_a_bucket():
    bucket, _ = limiter(amount=10)
    assert bucket.check("user_a", cost=10).allowed

    assert bucket.check("user_b", cost=10).allowed


def test_the_clock_is_monotonic_so_a_time_adjustment_grants_nothing():
    """`time.monotonic`, not `time.time`.

    A wall clock that jumps backwards freezes every bucket; one that jumps forward hands out
    free allowance. Asserted here as the property a caller can rely on — elapsed time is
    never negative — because the alternative is discovering it during a daylight-saving
    change.
    """
    bucket, clock = limiter(amount=10, seconds=100)
    assert bucket.check("user", cost=10).allowed

    clock.now -= 3600  # a clock that went backwards

    assert not bucket.check("user", cost=1).allowed


# --- retry-after ---------------------------------------------------------------------------


def test_retry_after_says_when_the_next_unit_is_available():
    bucket, _ = limiter(amount=10, seconds=100)  # one token per 10 seconds
    assert bucket.check("user", cost=10).allowed

    assert bucket.check("user", cost=1).retry_after_s == 10


def test_retry_after_is_never_zero():
    """A `Retry-After: 0` invites an immediate retry that will also fail.

    A client that honours it politely becomes the busy loop the header exists to prevent.
    """
    bucket, clock = limiter(amount=10, seconds=1)  # ten tokens a second
    assert bucket.check("user", cost=10).allowed
    clock.advance(0.05)

    assert bucket.check("user", cost=1).retry_after_s == 1


def test_a_cost_larger_than_the_whole_bucket_reports_the_window_not_a_fantasy():
    """It can never be paid, however long the caller waits.

    Reporting the arithmetic answer would produce a number that implies the retry will work.
    The full window is the honest one: come back when the bucket is full and it still will
    not fit, which is a client bug and should look like one rather than like a wait.
    """
    bucket, _ = limiter(amount=10, seconds=100)

    decision = bucket.check("user", cost=50)

    assert not decision.allowed
    assert decision.retry_after_s == 100


# --- the limiter is not itself a denial of service -----------------------------------------


def test_idle_keys_are_swept_so_the_limiter_cannot_be_made_to_exhaust_memory():
    """The session bucket is keyed by client address, which an attacker chooses.

    An unbounded dictionary keyed by untrusted input is the denial of service the limiter
    was added to prevent, arriving through the limiter. A fully refilled bucket is
    indistinguishable from one that never existed, so dropping it loses nothing.
    """
    bucket, clock = limiter(amount=1, seconds=1)
    for index in range(MAX_TRACKED_KEYS):
        bucket.check(f"addr-{index}")
    assert bucket.tracked_keys == MAX_TRACKED_KEYS

    clock.advance(60)  # everything has refilled
    bucket.check("one-more")

    assert bucket.tracked_keys == 1


def test_a_busy_key_survives_the_sweep():
    """Only *idle* keys are forgotten. Sweeping an active one would reset its allowance,
    which is the same thing as having no limiter for whoever is loudest."""
    bucket, clock = limiter(amount=10, seconds=1000)
    assert bucket.check("busy", cost=10).allowed
    for index in range(MAX_TRACKED_KEYS - 1):
        bucket.check(f"addr-{index}", cost=10)

    clock.advance(1)  # not enough for anyone to refill fully
    bucket.check("one-more", cost=1)

    assert not bucket.check("busy", cost=5).allowed


# --- construction ---------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "seconds"), [(0, 60), (-1, 60), (10, 0), (10, -1)])
def test_a_nonsense_quota_is_refused_at_construction(amount, seconds):
    with pytest.raises(ValueError):
        Quota.per_window(amount, seconds=seconds)


def test_a_nonpositive_cost_is_refused():
    """A zero-cost check would be a free pass, and a negative one would refill the bucket."""
    bucket, _ = limiter()

    with pytest.raises(ValueError):
        bucket.check("user", cost=0)


def test_limits_are_built_from_settings_so_a_deployment_can_tune_them():
    from app.config import Settings

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        groq_api_key="not-a-real-key",
        rate_limit_window_s=600,
        rate_limit_images=60,
        rate_limit_composes=6,
        rate_limit_sessions=3,
    )

    limits = Limits.from_settings(settings)

    assert limits.uploads.quota.burst == 60
    assert limits.compositions.quota.burst == 6
    assert limits.sessions.quota.burst == 3
    # Same window, three allowances — the shape the settings describe.
    assert limits.uploads.quota.per_second == pytest.approx(0.1)
