"""Every refusal scenario, as a test.

The scenarios live in `scenarios.py` and are the same objects `runner.py` prints. This file
exists so they are a gate as well as a demonstration: a harness that only runs when somebody
remembers to run it stops being true within a fortnight.

Parameterised over the registry rather than written out, so a new scenario is a gate the
moment it is registered and cannot be added without one.
"""

from __future__ import annotations

import pytest
from scenarios import REGISTRY, Check, custom_response, run_all


@pytest.mark.parametrize(
    ("case", "name", "run"),
    REGISTRY,
    ids=[f"case{case}-{name}" for case, name, _ in REGISTRY],
)
async def test_the_scenario_holds(case: str, name: str, run) -> None:
    check: Check = await run()

    assert check.case == case
    assert check.held, (
        f"case {case} — {name}\n"
        f"  injected  {check.injected}\n"
        f"  expected  {check.expected}\n"
        f"  observed  {check.observed}"
    )


async def test_the_runner_and_the_suite_see_the_same_thing() -> None:
    """`run_all()` is what the CLI calls. If it drifted from the registry the demo could
    pass while the gate failed, or the other way round."""
    report = await run_all()

    assert len(report.checks) == len(REGISTRY)
    assert report.ok
    assert [check.case for check in report.checks] == [case for case, _, _ in REGISTRY]


async def test_selecting_one_case_runs_only_that_case() -> None:
    report = await run_all("11")

    assert {check.case for check in report.checks} == {"11"}
    assert len(report.checks) == 2


# --- the reviewer's own payload -------------------------------------------------------------


async def test_a_reviewer_can_forge_a_cross_user_response_and_watch_it_refused() -> None:
    """prompts/10's acceptance criterion, exercised the way a reviewer would.

    Not a fixture — a payload written here, in the test, so that what a reviewer types into
    a file and what this asserts are demonstrably the same path.
    """
    forged = """
    {"outfit": {"item_ids": ["own-top", "own-bottom", "u2-jacket"],
     "name": "Borrowed", "occasion": "everyday", "match_score": 99},
     "rationale": ["Trust me on the jacket."], "confidence": 0.99, "degradation_level": 1}
    """

    check = await custom_response(forged, label="a hand-written cross-user response")

    assert check.held
    assert "u2-jacket" not in check.observed
    assert "refused" in check.observed


async def test_a_reviewer_can_supply_nonsense_and_still_get_an_outfit() -> None:
    check = await custom_response("not JSON, not even close", label="nonsense")

    assert check.held
    assert "schema_invalid" in check.observed


async def test_a_reviewer_supplying_a_valid_response_sees_it_accepted() -> None:
    """The control. A harness that refuses everything proves nothing about refusal."""
    valid = """
    {"outfit": {"item_ids": ["own-top", "own-bottom", "own-shoe"],
     "name": "Quiet Navy", "occasion": "everyday", "match_score": 86},
     "rationale": ["It holds together."], "confidence": 0.84, "degradation_level": 1}
    """

    check = await custom_response(valid)

    assert check.held
    assert check.observed.startswith("accepted")
