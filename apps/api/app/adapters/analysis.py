"""Provider-neutral extraction telemetry.

`WardrobeAnalyzer` (in `__init__.py`) is the interface the domain speaks: one image in, one
`GarmentExtraction` out, no provider concepts. That is the right interface for composition
and the wrong one for the upload pipeline, which has to write `item_extractions` — the audit
trail of what each model returned and what was rejected (docs/DATA-MODEL.md).

So there is a second, wider interface, and it lives here rather than in `groq_vision.py`
because the pipeline that consumes it must not import a provider-specific module. Nothing
in these types names a vendor: a model id is a string, latency is an integer, and a request
id is whatever the provider called it.

`model` and `latency_ms` on an audit row are not a leak of vendor concepts into the domain —
they are the evidence. An audit trail that cannot say which model said a thing is not one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.models import GarmentExtraction, GarmentImage


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    """What one call to a model produced, for the `item_extractions` audit trail.

    Written whether or not it was accepted (docs/DATA-MODEL.md): an audit trail that keeps
    only the successes cannot show that anything was ever caught.
    """

    model: str
    raw_output: str
    schema_valid: bool
    latency_ms: int
    rejected_reason: str | None = None
    request_id: str | None = None
    used_fallback: bool = False


@dataclass
class AnalysisOutcome:
    """The extraction plus every attempt it took to get there."""

    extraction: GarmentExtraction
    attempts: list[AnalysisAttempt]

    @property
    def model(self) -> str:
        return self.attempts[-1].model

    @property
    def used_fallback(self) -> bool:
        return self.attempts[-1].used_fallback


@runtime_checkable
class AuditingWardrobeAnalyzer(Protocol):
    """A `WardrobeAnalyzer` that also reports what it tried.

    `on_attempt` is the only route to the attempts of a **failing** analysis, because a
    failing analysis raises and has no return value. The upload pipeline passes a collector
    and persists whatever it holds in a `finally`.
    """

    async def analyze(self, image: GarmentImage) -> GarmentExtraction: ...

    async def analyze_with_audit(
        self,
        image: GarmentImage,
        *,
        on_attempt: Callable[[AnalysisAttempt], None] | None = None,
    ) -> AnalysisOutcome: ...


__all__ = ["AnalysisAttempt", "AnalysisOutcome", "AuditingWardrobeAnalyzer"]
