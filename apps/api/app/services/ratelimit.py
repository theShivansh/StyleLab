"""Rate limiting for the two endpoints that spend money.

`docs/SECURITY-PRIVACY.md` has asked for "rate limiting on upload and extraction
specifically" since S0 and nothing implemented it. It matters more here than the sentence
suggests, because of what sits next to it: there is no real authentication (blocker B15).
`POST /session` mints a token for anyone who asks, and that token then reaches
`POST /wardrobe/items`, which calls a vision model per photograph on a metered key.

So the exposure is not "someone floods the API". It is **someone drains the provider
budget**, and does it without ever needing a credential, from a URL that is public by
design. Every other protection in this codebase is about one user reading another user's
wardrobe; this is the one that is about the deployment surviving the afternoon.

## Token bucket, and why not a fixed window

A fixed window is easier and has a hole at the boundary: a client gets its whole allowance
at 11:59:59 and the whole of the next one at 12:00:00, which is twice the intended burst at
the worst possible moment. A bucket that refills continuously has no edge to stand on.

The bucket also expresses the thing that matters here, which a request counter does not:
**cost is per image, not per request.** One POST carrying twelve photographs is twelve
provider calls. `take(n)` is the whole reason this is a bucket and not a counter.

## What it does not do

It is in-process, so the limit is per instance — two replicas allow twice as much. That is
the same seam as the job runner (blocker B14) and the same answer: the interface takes a
key and a cost and returns a decision, so Redis replaces the storage without touching a
caller. Recorded rather than hidden, because a limiter that is quietly per-instance is one
somebody will later size a deployment against.

It also trusts `request.client.host` to be the real peer. Behind a proxy that is the
proxy's address unless uvicorn is started with `--proxy-headers --forwarded-allow-ips=...`,
and reading `X-Forwarded-For` here without that would be worse than not limiting at all —
an attacker sets a different value on every request and the bucket never fills. Delegated
to uvicorn on purpose: it already knows which hops to trust, and this module should not
acquire a second opinion.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config import Settings

#: Above this many tracked keys, idle buckets are swept before a new one is created. The
#: dictionary is keyed by client address on the session endpoint, so an unbounded one would
#: itself be the denial of service — a few million requests from spoofed sources and the
#: limiter is the thing that exhausts the memory.
MAX_TRACKED_KEYS = 10_000


@dataclass(frozen=True, slots=True)
class Quota:
    """How much, how fast.

    `burst` is what a caller may spend at once after being idle; `per_second` is how fast
    the allowance comes back. Expressed this way rather than as "N per minute" because the
    two numbers answer different questions — the first is "can a real user upload a full
    batch", the second is "what does this cost us per hour if somebody scripts it".
    """

    burst: float
    per_second: float

    @classmethod
    def per_window(cls, amount: float, *, seconds: float) -> Quota:
        """`amount` units, refilling over `seconds`, burstable to the full amount."""
        if amount <= 0 or seconds <= 0:
            raise ValueError("a quota needs a positive amount and window")
        return cls(burst=amount, per_second=amount / seconds)


@dataclass(frozen=True, slots=True)
class Decision:
    """Allowed or not, and how long until it would be.

    `retry_after_s` is rounded **up** to a whole second and floored at one. A `Retry-After`
    of 0 invites an immediate retry that will also fail, and a client that honours it
    politely becomes the busy loop.
    """

    allowed: bool
    retry_after_s: int = 0


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """A keyed token bucket. One instance per protected operation.

    Separate instances rather than one shared store with namespaced keys: the quotas differ
    per operation, and a shared store would need the quota passed in at every call site,
    which is how two call sites for the same operation come to disagree about its limit.
    """

    def __init__(self, quota: Quota, *, now: Callable[[], float] | None = None) -> None:
        self._quota = quota
        # Injected so tests can drive time instead of sleeping through it. `monotonic`, not
        # `time()`: a clock adjustment must not hand out free allowance or freeze a bucket.
        self._now = now or time.monotonic
        self._buckets: dict[str, _Bucket] = {}

    @property
    def quota(self) -> Quota:
        return self._quota

    def check(self, key: str, *, cost: float = 1.0) -> Decision:
        """Spend `cost` against `key`, if it is there to spend.

        Nothing is deducted when the answer is no. A limiter that charges for refusals
        never lets a throttled client recover, which turns a burst into a lockout.
        """
        if cost <= 0:
            raise ValueError("a cost must be positive")

        now = self._now()
        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= MAX_TRACKED_KEYS:
                self._sweep(now)
            bucket = _Bucket(tokens=self._quota.burst, updated_at=now)
            self._buckets[key] = bucket

        self._refill(bucket, now)

        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return Decision(allowed=True)

        if cost > self._quota.burst:
            # Unpayable at any point in the future: even a full bucket is too small. The
            # arithmetic shortfall would be a small number implying the retry will work,
            # which is worse than useless — it turns a client bug into a polling loop. The
            # full window is the honest answer: wait it out and it still will not fit.
            seconds = self._quota.burst / self._quota.per_second
        else:
            seconds = (cost - bucket.tokens) / self._quota.per_second
        return Decision(allowed=False, retry_after_s=max(1, _ceil(seconds)))

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = max(0.0, now - bucket.updated_at)
        bucket.tokens = min(self._quota.burst, bucket.tokens + elapsed * self._quota.per_second)
        bucket.updated_at = now

    def _sweep(self, now: float) -> None:
        """Drop keys that have refilled completely — a full bucket is indistinguishable from
        one that never existed, so forgetting it loses nothing."""
        for key, bucket in list(self._buckets.items()):
            self._refill(bucket, now)
            if bucket.tokens >= self._quota.burst:
                del self._buckets[key]

    # Exposed for tests and for a future admin view; not read by any route.
    @property
    def tracked_keys(self) -> int:
        return len(self._buckets)


def _ceil(value: float) -> int:
    whole = int(value)
    return whole if value == whole else whole + 1


@dataclass(slots=True)
class Limits:
    """The three protected operations, and nothing else.

    Reads and corrections are not limited. They cost a database query, they are what a user
    does constantly while reviewing a wardrobe, and a limit there would produce a product
    that refuses to show somebody their own clothes — a bad trade against an attacker who
    could just as cheaply request the landing page.
    """

    #: Mutable on purpose, unlike everything else in this module. A test needs to shrink one
    #: quota without rebuilding the application, and a frozen container of mutable limiters
    #: would be protecting the box rather than what is in it.
    uploads: RateLimiter
    compositions: RateLimiter
    sessions: RateLimiter

    @classmethod
    def from_settings(cls, settings: Settings) -> Limits:
        window = settings.rate_limit_window_s
        return cls(
            uploads=RateLimiter(
                Quota.per_window(settings.rate_limit_images, seconds=window)
            ),
            compositions=RateLimiter(
                Quota.per_window(settings.rate_limit_composes, seconds=window)
            ),
            sessions=RateLimiter(
                Quota.per_window(settings.rate_limit_sessions, seconds=window)
            ),
        )


__all__ = [
    "MAX_TRACKED_KEYS",
    "Decision",
    "Limits",
    "Quota",
    "RateLimiter",
]
