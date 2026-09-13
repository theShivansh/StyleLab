"""Provider-neutral advice telemetry.

The mirror of `analysis.py`, for the other generating path, and it exists for the same
reason. `OutfitAdvisor` (in `__init__.py`) is what the domain speaks: a request in, an
`OutfitAdvice` out, no provider concepts. That is the right interface for composition and
too narrow for observability, which has to record which model answered and how long it took.

So there is a wider interface, and it lives here rather than in `groq_text.py` because
`app/services/composition.py` consumes it and must not import a provider-specific module.
Nothing in these types names a vendor: a model id is a string, latency is an integer.

`last_telemetry` is an attribute rather than a return value because it must be readable
after the call **raised**. A schema failure is the case we most want measured, and it has no
return value to hang figures on — the same problem `analysis.py` solves with `on_attempt`,
solved the other way because there is one call here rather than a chain of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import AdviceRequest, OutfitAdvice


@dataclass(frozen=True, slots=True)
class AdviceTelemetry:
    """Per-call figures `docs/OBSERVABILITY.md` asks us to record."""

    model: str
    latency_ms: int
    request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    #: 1-based. Above 1 means the advisor re-asked after a schema failure.
    attempt: int = 1


class ReportingOutfitAdvisor(Protocol):
    """An `OutfitAdvisor` that also says what the call cost.

    Not `runtime_checkable`: a Protocol with a non-method member cannot be used with
    `isinstance`, and pretending otherwise with a hasattr check dressed up as a type test
    would be worse than the honest `getattr` the caller does.
    """

    last_telemetry: AdviceTelemetry | None

    async def advise(self, request: AdviceRequest) -> OutfitAdvice: ...


def telemetry_of(advisor: object) -> AdviceTelemetry | None:
    """Read an advisor's last-call figures, if it keeps them.

    Deliberately tolerant. An advisor that reports nothing is a gap in the dashboard, never
    a failed composition — and the deterministic ranker, which is an advisor in every sense
    that matters here, genuinely has nothing to report because it called no model.
    """
    telemetry = getattr(advisor, "last_telemetry", None)
    return telemetry if isinstance(telemetry, AdviceTelemetry) else None


__all__ = ["AdviceTelemetry", "ReportingOutfitAdvisor", "telemetry_of"]
