"""The latency circuit breaker — rung 3 of the degradation ladder.

`docs/AGENT-SYSTEM.md`: *exceeding p95 twice in a row trips the circuit breaker*. Two things
about that sentence are load-bearing and easy to get wrong.

**Twice in a row, not twice.** One slow compose is a slow compose. A breaker that trips on a
single breach turns every hiccup into a visibly shallower product, and the user cannot tell
the difference between "the provider was busy for four seconds" and "we have decided to stop
trying". Consecutive breaches are evidence of a condition rather than of an event.

**It degrades depth, not correctness.** A tripped breaker runs Architect + Editor only: still
the user's own garments, still every validation, still an honest disclosure of the rung. It
is not a cache, not a stale answer, and not a curated fallback — there is no rung on this
ladder where the product shows somebody a garment they do not own.

Recovery is optimistic on purpose. One run inside budget closes it again, because the
alternative — a cool-down timer — means a provider that recovered in ten seconds keeps
serving reduced results for the length of whatever timer somebody guessed at.

State lives on the composer, which is built once per process. That makes this
per-instance rather than global: a second API instance forms its own opinion of the
provider's health, which is right, because latency is measured from where you are standing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("stylelab.circuit")

#: Consecutive breaches before the breaker opens.
BREACHES_TO_TRIP = 2


@dataclass
class LatencyCircuit:
    """Counts consecutive breaches of the p95 budget.

    Not thread-safe and does not need to be: it is touched from the event loop, once before
    and once after each composition.
    """

    budget_s: float
    breaches_to_trip: int = BREACHES_TO_TRIP
    _consecutive: int = field(default=0, init=False)

    @property
    def tripped(self) -> bool:
        return self._consecutive >= self.breaches_to_trip

    def record(self, elapsed_s: float) -> None:
        """One completed composition, and how long its advisor took."""
        if elapsed_s <= self.budget_s:
            if self._consecutive:
                logger.info(
                    "advisor back inside the latency budget; circuit closed",
                    extra={"elapsed_s": round(elapsed_s, 2)},
                )
            self._consecutive = 0
            return

        self._consecutive += 1
        logger.warning(
            "advisor exceeded the latency budget",
            extra={
                "elapsed_s": round(elapsed_s, 2),
                "budget_s": self.budget_s,
                "consecutive": self._consecutive,
                "tripped": self.tripped,
            },
        )

    def reset(self) -> None:
        self._consecutive = 0


__all__ = ["BREACHES_TO_TRIP", "LatencyCircuit"]
