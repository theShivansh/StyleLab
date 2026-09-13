"""The latency circuit breaker — AI-EVAL-CASES Case 23, rung 3 of the ladder.

The unit is here; that the composer actually falls to a reduced crew when it opens is
asserted in `tests/ai/test_crew_ladder.py`, where the crew exists.
"""

from __future__ import annotations

import logging

from app.services.circuit import LatencyCircuit


def test_one_slow_run_is_not_a_condition():
    """A breaker that trips on a single breach turns every hiccup into a visibly shallower
    product, and the user cannot tell that from a decision to stop trying."""
    circuit = LatencyCircuit(budget_s=1.0)

    circuit.record(4.0)

    assert circuit.tripped is False


def test_two_consecutive_breaches_open_it():
    circuit = LatencyCircuit(budget_s=1.0)

    circuit.record(4.0)
    circuit.record(4.0)

    assert circuit.tripped is True


def test_a_run_inside_budget_closes_it_again():
    """Recovery is optimistic on purpose. A cool-down timer means a provider that recovered
    in ten seconds keeps serving reduced results for however long somebody guessed."""
    circuit = LatencyCircuit(budget_s=1.0)
    circuit.record(4.0)
    circuit.record(4.0)

    circuit.record(0.4)

    assert circuit.tripped is False


def test_breaches_have_to_be_consecutive():
    circuit = LatencyCircuit(budget_s=1.0)

    circuit.record(4.0)
    circuit.record(0.2)
    circuit.record(4.0)

    assert circuit.tripped is False


def test_a_run_exactly_on_budget_is_not_a_breach():
    circuit = LatencyCircuit(budget_s=1.0)

    circuit.record(1.0)
    circuit.record(1.0)

    assert circuit.tripped is False


def test_opening_and_closing_are_both_logged(caplog):
    """An operator has to be able to see the product get shallower and recover. A breaker
    that trips silently is indistinguishable from a model that got worse."""
    circuit = LatencyCircuit(budget_s=1.0)

    with caplog.at_level(logging.INFO, logger="stylelab.circuit"):
        circuit.record(4.0)
        circuit.record(4.0)
        circuit.record(0.1)

    levels = [record.levelno for record in caplog.records]
    assert levels.count(logging.WARNING) == 2
    assert logging.INFO in levels


def test_a_timeout_opens_it_on_its_own():
    """A breach and a timeout are not the same event, which S11 found by watching rather than
    by reading.

    A breach is a measurement: the advisor answered and took too long. A timeout is a failure
    to answer at all — the call was cancelled at the budget and the whole of it bought
    nothing. Requiring two of those in a row made the middle rung of the ladder unreachable
    in exactly the conditions it exists for: the observed sequence was fifteen seconds to the
    deterministic ranker, fifteen more to the ranker again, and only then the reduced crew
    that takes about four.
    """
    circuit = LatencyCircuit(budget_s=15.0)

    circuit.trip()

    assert circuit.tripped is True


def test_a_good_run_still_closes_a_breaker_a_timeout_opened():
    """Recovery stays optimistic. A timeout is stronger evidence of a problem, not a
    different kind of problem — one run inside budget is still the end of it."""
    circuit = LatencyCircuit(budget_s=1.0)
    circuit.trip()

    circuit.record(0.5)

    assert circuit.tripped is False


def test_tripping_an_open_breaker_is_a_no_op():
    circuit = LatencyCircuit(budget_s=1.0)
    circuit.trip()

    circuit.trip()

    assert circuit.tripped is True
