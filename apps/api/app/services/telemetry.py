"""Generation telemetry — one event per model call, and the rollup it feeds.

docs/OBSERVABILITY.md lists what the AI layer has to be measurable on: model calls, success
rate, schema failure rate, grounding failures, median latency, retry rate, token usage. Up
to S7 every one of those was *derivable in principle* from something — a log line here, an
`item_extractions` row there, an `AdviceTelemetry` object the advisor set and nobody read —
and computable in practice from none of them.

So there is one event type, emitted by both generating paths, and one function that turns a
stream of them into that list. The function is product code rather than a test helper on
purpose: a metric nothing computes is a metric nobody can be shown.

## What an event may carry

Scalars, and nothing else. No garment text, no rationale, no raw model output, no storage
key, no image reference. That is not a convention — `tests/test_telemetry.py` walks the
annotations and fails on any field that is not a bounded scalar or one of the named
identifiers, which is the same trick `apps/web/src/lib/analytics.ts` uses on the browser
side. Telemetry is the surface that gets shipped to a third party, and the cheapest moment
to make a leak unrepresentable is before the first one.

`raw_output` lives on `AnalysisAttempt` instead, which goes to `item_extractions` — our own
table, under the same retention as the wardrobe it describes. The distinction is deliberate:
an audit trail keeps the evidence, telemetry keeps the count.

## The metric we do not emit

OBSERVABILITY asks for "cross-user ownership rejection" as a metric distinct from
"unowned-item grounding failure". The domain cannot tell them apart, and that is a design
decision rather than an omission: `app/domain/validation.py` refuses an unexpected id
*without looking it up*, precisely so that no other user's id enters a query on the request
path. Both arrive here as `ungrounded_item`. Attribution belongs to the alerting layer,
which has admin scope; see docs/DECISIONS.md.

## And the one we deliberately report in the wrong unit

"Estimated cost" is tokens here, never currency. A price per token hardcoded in this file
would be correct for one plan on one day, would go stale silently, and would be believed.
Tokens are the thing we actually observe.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from typing import Literal, Protocol, runtime_checkable

logger = logging.getLogger("stylelab.generation")

#: What the model was asked to produce. Not the model id — that is `model`.
Operation = Literal["extraction", "advice"]

#: How the call ended, from the system's point of view rather than the provider's.
#:
#: `ok` means the response survived every gate that applies to it, ownership included. A
#: schema-valid response that named somebody else's garment is not a success with a caveat;
#: it is an `ungrounded_item`.
Outcome = Literal[
    "ok",
    "schema_invalid",
    "ungrounded_item",
    "incompatible_outfit",
    "timeout",
    "provider_error",
]

#: Outcomes that mean the response was produced and refused by us, as opposed to never
#: arriving. The distinction matters on a dashboard: the first is a model-quality problem,
#: the second is an availability one, and they have different people to wake up.
REFUSED_OUTCOMES: frozenset[str] = frozenset(
    {"schema_invalid", "ungrounded_item", "incompatible_outfit"}
)


@dataclass(frozen=True, slots=True)
class GenerationEvent:
    """One call to a model, as measured from our side of it.

    One event per *call*, not per request: an advice request that failed the schema once and
    succeeded on the re-ask emits two, which is the only way `retry_rate` means anything.
    """

    operation: Operation
    #: The model that actually answered, which is not always the one requested — the
    #: availability fallback may have moved. A string, not an enum: model ids are
    #: configuration and this module is not allowed to know them (CLAUDE.md).
    model: str
    outcome: Outcome
    latency_ms: int
    #: 1-based. Anything above 1 is a re-ask after a schema failure on the same model.
    attempt: int = 1
    used_fallback: bool = False
    #: 1 = full depth, 5 = an honest statement of what is missing. Only on `advice`.
    degradation_level: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    #: The provider's id for the call, for correlating with their dashboard.
    request_id: str | None = None
    job_id: str | None = None
    #: Who the work was for. Present because "one user is generating all the failures" is a
    #: question an operator has to be able to answer; it is an opaque id and nothing else.
    user_id: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome == "ok"

    @property
    def total_tokens(self) -> int:
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


@runtime_checkable
class GenerationLog(Protocol):
    """Where events go. Synchronous and expected not to raise.

    Narrow on purpose: an analytics vendor lands behind this, and the one thing that must
    never happen is a telemetry sink taking a user's outfit down with it.
    """

    def record(self, event: GenerationEvent) -> None: ...


class LoggingGenerationLog:
    """The default sink: one structured line per call.

    INFO for a successful call, WARNING for a refusal, CRITICAL for `ungrounded_item` —
    which docs/AI-SYSTEM.md calls a serious event whoever the id belongs to, and which
    `CompositionService` already logs at that level for the same reason.
    """

    def record(self, event: GenerationEvent) -> None:
        level = logging.INFO
        if event.outcome == "ungrounded_item":
            level = logging.CRITICAL
        elif event.outcome != "ok":
            level = logging.WARNING

        logger.log(
            level,
            "generation %s %s",
            event.operation,
            event.outcome,
            extra={
                "operation": event.operation,
                "model": event.model,
                "outcome": event.outcome,
                "duration_ms": event.latency_ms,
                "attempt": event.attempt,
                "used_fallback": event.used_fallback,
                "degradation_level": event.degradation_level,
                "prompt_tokens": event.prompt_tokens,
                "completion_tokens": event.completion_tokens,
                "request_id": event.request_id,
                "job_id": event.job_id,
                "user_id": event.user_id,
            },
        )


class NullGenerationLog:
    """Records nothing. The default where a sink has not been wired.

    Not a silent downgrade of a product path — no user-visible behaviour depends on
    telemetry — but it is the thing to check first when a dashboard is empty.
    """

    def record(self, event: GenerationEvent) -> None:
        return None


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    """docs/OBSERVABILITY.md's AI list, computed from a stream of events.

    Rates are fractions in [0, 1] and are `0.0` for an empty stream rather than undefined:
    a dashboard panel that renders "NaN" on a quiet minute teaches people to ignore it.
    """

    calls: int
    success_rate: float
    schema_failure_rate: float
    #: Responses naming an id we did not supply. See the module docstring on why this does
    #: not separate "another user's item" from "an item that does not exist".
    grounding_failures: int
    incompatible_outfits: int
    timeouts: int
    provider_errors: int
    median_latency_ms: float
    p95_latency_ms: float
    #: Calls that were a re-ask after a schema failure, over all calls.
    retry_rate: float
    fallback_calls: int
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def generation_metrics(events: Iterable[GenerationEvent]) -> GenerationMetrics:
    """Roll a stream of events up into the measurements the spec asks for.

    Pure, so a dashboard query and a test compute the same numbers from the same code.
    """
    collected: Sequence[GenerationEvent] = list(events)
    calls = len(collected)

    def rate(matching: int) -> float:
        # Unrounded. Rounding here would be formatting, and formatting in a metric is how
        # two dashboards come to disagree about the same minute.
        return matching / calls if calls else 0.0

    def count(outcome: str) -> int:
        return sum(1 for event in collected if event.outcome == outcome)

    latencies = sorted(event.latency_ms for event in collected)

    return GenerationMetrics(
        calls=calls,
        success_rate=rate(count("ok")),
        schema_failure_rate=rate(count("schema_invalid")),
        grounding_failures=count("ungrounded_item"),
        incompatible_outfits=count("incompatible_outfit"),
        timeouts=count("timeout"),
        provider_errors=count("provider_error"),
        median_latency_ms=statistics.median(latencies) if latencies else 0.0,
        p95_latency_ms=_percentile(latencies, 0.95),
        retry_rate=rate(sum(1 for event in collected if event.attempt > 1)),
        fallback_calls=sum(1 for event in collected if event.used_fallback),
        prompt_tokens=sum(event.prompt_tokens or 0 for event in collected),
        completion_tokens=sum(event.completion_tokens or 0 for event in collected),
    )


def _percentile(sorted_values: Sequence[int], fraction: float) -> float:
    """Nearest-rank percentile. Small-sample honest: with four calls, p95 is the slowest.

    `statistics.quantiles` interpolates and needs at least two points, which makes it wrong
    for exactly the case this runs in most often — a handful of calls in a minute.
    """
    if not sorted_values:
        return 0.0
    rank = max(1, min(len(sorted_values), math.ceil(fraction * len(sorted_values))))
    return float(sorted_values[rank - 1])


#: Every field an event carries, for the leak test and for a sink's schema.
EVENT_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(GenerationEvent))


__all__ = [
    "EVENT_FIELDS",
    "REFUSED_OUTCOMES",
    "GenerationEvent",
    "GenerationLog",
    "GenerationMetrics",
    "LoggingGenerationLog",
    "NullGenerationLog",
    "Operation",
    "Outcome",
    "generation_metrics",
]
