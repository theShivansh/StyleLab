"""Generation telemetry — the event, the leak rule, and the rollup.

Prompt 10's tenth requirement is that "generation events expose enough telemetry to measure
quality and latency". That is a claim about *sufficiency*, which a test asserting the
presence of fields cannot check — a field list is satisfied by any field list. So the test
that matters here computes docs/OBSERVABILITY.md's AI metrics from a stream of events and
fails if any one of them is not computable.

The other half is the opposite property: an event must be *insufficient* to carry a user's
wardrobe. Telemetry is the surface that gets shipped to a third party.
"""

from __future__ import annotations

import logging
import typing

import pytest

from app.services.telemetry import (
    EVENT_FIELDS,
    GenerationEvent,
    LoggingGenerationLog,
    NullGenerationLog,
    generation_metrics,
)


def event(**over: object) -> GenerationEvent:
    payload: dict[str, object] = {
        "operation": "advice",
        "model": "eval/text",
        "outcome": "ok",
        "latency_ms": 400,
    }
    payload.update(over)
    return GenerationEvent(**payload)  # type: ignore[arg-type]


# --- what an event may carry -------------------------------------------------------------

#: The only types a field may have. A `dict`, a `list` or a free-form object is how a
#: garment description, a rationale or a raw completion would arrive here.
SCALARS = {str, int, bool, float}


def _leaves(annotation: object) -> set[object]:
    """The concrete types an annotation can actually hold.

    Unwraps unions and `| None`, and collapses a `Literal` of strings to a marker rather
    than to `str`: a closed set of spellings is an enum, and calling it a string would put
    it in the same bucket as a field free text could reach.
    """
    if typing.get_origin(annotation) is typing.Literal:
        values = typing.get_args(annotation)
        assert all(isinstance(value, str) for value in values), annotation
        return {typing.Literal}

    args = typing.get_args(annotation)
    if not args:
        return {annotation}
    return {
        leaf for part in args if part is not type(None) for leaf in _leaves(part)
    }


def test_no_field_can_hold_structured_content():
    """The leak rule, enforced against the annotations rather than against a habit.

    A `dict[str, Any]` field named `context` is how every telemetry payload eventually comes
    to contain the thing it promised not to. Adding one fails here.
    """
    for name, annotation in typing.get_type_hints(GenerationEvent).items():
        for leaf in _leaves(annotation):
            assert leaf in SCALARS or leaf is typing.Literal, (
                f"{name} may hold {leaf!r}, which could carry user content"
            )


def test_the_free_string_fields_are_identifiers_and_nothing_else():
    """A belt-and-braces reading of the same rule.

    Exactly four fields are unconstrained strings, and each one is an opaque id or a model
    name. There is no `message`, no `detail`, no `raw`, and no `reason` — the reason is a
    `Literal` (`outcome`), which is the difference between a countable metric and a place
    free text accumulates.
    """
    hints = typing.get_type_hints(GenerationEvent)
    free_strings = {name for name in EVENT_FIELDS if _leaves(hints[name]) == {str}}

    assert free_strings == {"model", "request_id", "job_id", "user_id"}


# --- sufficiency: the OBSERVABILITY list, computed ---------------------------------------


def test_every_ai_metric_in_the_spec_is_computable_from_the_stream():
    """docs/OBSERVABILITY.md, "Metrics / AI", line by line.

    Deliberately built from a stream with something wrong in it. A stream of successes makes
    every rate 1.0 and would pass whatever the code did.
    """
    stream = [
        event(latency_ms=300),
        event(latency_ms=900, outcome="schema_invalid"),
        event(latency_ms=120, outcome="ok", attempt=2),  # the re-ask that worked
        event(latency_ms=4000, outcome="ungrounded_item"),
        event(latency_ms=15000, outcome="timeout", model="unreported"),
        event(
            operation="extraction",
            latency_ms=700,
            model="eval/vision-fallback",
            used_fallback=True,
            prompt_tokens=1200,
            completion_tokens=205,
        ),
    ]

    metrics = generation_metrics(stream)

    assert metrics.calls == 6  # model calls
    assert metrics.success_rate == pytest.approx(3 / 6)  # success rate
    assert metrics.schema_failure_rate == pytest.approx(1 / 6)  # schema failure rate
    assert metrics.grounding_failures == 1  # unowned-item grounding failure
    assert metrics.median_latency_ms == pytest.approx(800)  # median latency
    assert metrics.retry_rate == pytest.approx(1 / 6)  # retry rate
    assert metrics.total_tokens == 1405  # estimated cost, in the unit we observe
    # Not in the spec's list and worth having: the two availability outcomes, separated.
    assert (metrics.timeouts, metrics.provider_errors) == (1, 0)
    assert metrics.fallback_calls == 1


def test_p95_of_a_short_stream_is_the_slowest_call():
    """Nearest rank, not interpolation.

    With four calls in a minute there is no meaningful 95th percentile, and the honest
    answer is the slowest one. `statistics.quantiles` would interpolate between the two
    slowest and report a latency that never happened.
    """
    metrics = generation_metrics([event(latency_ms=ms) for ms in (100, 200, 300, 9000)])

    assert metrics.p95_latency_ms == 9000
    assert metrics.median_latency_ms == 250


def test_an_empty_stream_reports_zero_rather_than_dividing_by_it():
    metrics = generation_metrics([])

    assert metrics.calls == 0
    assert metrics.success_rate == 0.0
    assert metrics.median_latency_ms == 0.0
    assert metrics.p95_latency_ms == 0.0


def test_a_refused_response_is_not_counted_as_a_success():
    """The one that makes `success_rate` mean what an operator will read it as meaning.

    A schema-valid, confident response naming another user's garment is a **failure** here.
    Counting it as a success because the provider returned 200 is how a dashboard ends up
    reporting perfect health through an incident.
    """
    metrics = generation_metrics([event(outcome="ungrounded_item")])

    assert metrics.success_rate == 0.0
    assert metrics.grounding_failures == 1


# --- the sinks ----------------------------------------------------------------------------


def test_the_default_sink_escalates_an_ungrounded_response_to_critical(caplog):
    """Same level `CompositionService` logs it at, for the same reason: an advisor naming an
    id we did not supply is a serious event whoever the id belongs to."""
    with caplog.at_level(logging.INFO, logger="stylelab.generation"):
        LoggingGenerationLog().record(event(outcome="ungrounded_item"))
        LoggingGenerationLog().record(event(outcome="schema_invalid"))
        LoggingGenerationLog().record(event())

    levels = {record.outcome: record.levelno for record in caplog.records}
    assert levels == {
        "ungrounded_item": logging.CRITICAL,
        "schema_invalid": logging.WARNING,
        "ok": logging.INFO,
    }


def test_the_null_sink_is_silent_and_harmless(caplog):
    with caplog.at_level(logging.DEBUG):
        NullGenerationLog().record(event())

    assert caplog.records == []
