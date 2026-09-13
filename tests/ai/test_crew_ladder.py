"""The degradation ladder, end to end, with the crew in place.

    1  full crew
    2  crew minus Trend Scout        (no trend supply)
    3  Architect + Editor only       (the latency circuit breaker)
    4  deterministic ranker          (the advisor failed or was refused)
    5  an honest statement of the gap

Rungs 4 and 5 are asserted in `tests/ai/test_grounding.py` and
`apps/api/tests/test_composition.py` against the single-call advisor, and they behave the
same way here because they are the service's ladder and not the advisor's — which is the
point of the `OutfitAdvisor` Protocol. This file covers the two rungs the crew introduces,
plus the one property that matters most about all of them: **no rung ever shows the user a
garment they do not own.**
"""

from __future__ import annotations

import json

import pytest
from app.adapters.crew import CrewAIOutfitAdvisor, CrewRoles
from app.domain.models import AdviceRequest
from app.domain.models import GarmentCategory as C
from app.services.circuit import LatencyCircuit
from crew_fixtures import LOOK, crew_script
from harness import OWNED, U1
from stubs import MockGroqProvider, garment, trend_note

TREND_URL = "https://example-publication.test/neutral-palettes"


def request_for(*, with_trends: bool) -> AdviceRequest:
    return AdviceRequest(
        user_id=U1,
        candidates=[
            garment(item_id, U1, category=category, color_primary=colour)
            for item_id, category, colour in OWNED
        ],
        occasion="everyday",
        required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR],
        trend_notes=(
            [trend_note("Neutral palettes holding through AW26", url=TREND_URL)]
            if with_trends
            else []
        ),
    )


def advisor(**script) -> tuple[CrewAIOutfitAdvisor, MockGroqProvider]:
    transport = MockGroqProvider(by_schema=crew_script(**script))
    return CrewAIOutfitAdvisor(transport, model="eval/text"), transport


# --- rungs 1 and 2 ---------------------------------------------------------------------------


async def test_rung_one_runs_every_role():
    subject, _ = advisor(
        trend_application=json.dumps(
            {"applied": [{"url": TREND_URL, "item_ids": ["own-top"], "why": "neutral"}]}
        )
    )

    await subject.advise(request_for(with_trends=True))

    assert subject.last_run.roles_run == (
        "style_profiler",
        "trend_scout",
        "outfit_architect",
        "critic",
        "practical_advisor",
        "editor",
    )


async def test_rung_two_is_the_crew_without_a_trend_supply():
    """No notes retrieved is not a failure of the Trend Scout; it is the absence of anything
    for it to do. Running it anyway would spend a call to be told there is nothing to map —
    `ExaTrendSource` has already recorded *why* there is nothing."""
    subject, transport = advisor()

    advice = await subject.advise(request_for(with_trends=False))

    assert "trend_scout" not in subject.last_run.roles_run
    assert "trend_application" not in transport.schemas_called
    assert advice.outfit is not None
    assert advice.trend_notes == []


# --- rung 3: the breaker (AI-EVAL-CASES Case 23) ---------------------------------------------


async def test_rung_three_drops_the_deliberation_and_keeps_the_outfit():
    subject, _ = advisor()
    reduced = subject.with_roles(CrewRoles.architect_and_editor_only(), degradation_level=3)

    advice = await reduced.advise(request_for(with_trends=True))

    assert reduced.last_run.roles_run == ("outfit_architect", "editor")
    assert advice.degradation_level == 3
    assert advice.outfit is not None
    assert advice.outfit.item_ids == LOOK


async def test_a_reduced_copy_does_not_degrade_the_original():
    """The advisor is long-lived and shared. A breaker that reached in and switched roles off
    would leave every later request shallow until something switched them back on."""
    subject, _ = advisor()

    subject.with_roles(CrewRoles.architect_and_editor_only(), degradation_level=3)
    await subject.advise(request_for(with_trends=False))

    assert "critic" in subject.last_run.roles_run
    assert subject.last_run.degradation_level == 1


# --- the property that holds on every rung ------------------------------------------------------


@pytest.mark.parametrize(
    "roles",
    [CrewRoles(), CrewRoles.without("critic"), CrewRoles.architect_and_editor_only()],
    ids=["full", "no-critic", "architect-and-editor"],
)
async def test_no_rung_serves_a_garment_the_user_does_not_own(roles):
    """The one rule the product rests on, checked at every depth.

    Not a duplicate of Case 20: that asserts a *forged* response is refused. This asserts the
    ordinary path never produces one, however few agents are looking — because "we removed
    the Critic to save time" must not be the sentence that precedes a wardrobe leak.
    """
    transport = MockGroqProvider(by_schema=crew_script())
    subject = CrewAIOutfitAdvisor(transport, model="eval/text", roles=roles)

    advice = await subject.advise(request_for(with_trends=False))

    owned = {item_id for item_id, _, _ in OWNED}
    assert advice.outfit is not None
    assert set(advice.outfit.item_ids) <= owned


# --- the breaker driving the choice ----------------------------------------------------------


def test_the_composer_reduces_the_crew_once_the_circuit_is_open(monkeypatch):
    """The wiring, asserted without composing: `_advisor_for_now` is the decision point.

    Driven directly rather than through two slow compositions, because the thing under test
    is which advisor gets chosen — making a test genuinely wait thirty seconds to prove that
    would be measuring `asyncio.sleep`.
    """
    from app.services.compose import OutfitComposer

    transport = MockGroqProvider(by_schema=crew_script())
    crew = CrewAIOutfitAdvisor(transport, model="eval/text")
    circuit = LatencyCircuit(budget_s=1.0)
    composer = OutfitComposer(
        sessions=None,  # type: ignore[arg-type]
        advisor=crew,
        jobs=None,  # type: ignore[arg-type]
        background=None,  # type: ignore[arg-type]
        circuit=circuit,
    )

    assert composer._advisor_for_now() is crew

    circuit.record(9.0)
    circuit.record(9.0)
    reduced = composer._advisor_for_now()

    assert reduced is not crew
    assert reduced._roles.enabled() == ("outfit_architect", "editor")

    circuit.record(0.2)
    assert composer._advisor_for_now() is crew


def test_an_advisor_that_cannot_reduce_is_left_alone():
    """The composer must keep working with the single-call advisor and with any stub a test
    hands it. An open circuit then costs nothing rather than raising."""
    from app.services.compose import OutfitComposer
    from stubs import ScriptedAdvisor

    plain = ScriptedAdvisor.naming(*LOOK)
    circuit = LatencyCircuit(budget_s=1.0)
    composer = OutfitComposer(
        sessions=None,  # type: ignore[arg-type]
        advisor=plain,
        jobs=None,  # type: ignore[arg-type]
        background=None,  # type: ignore[arg-type]
        circuit=circuit,
    )
    circuit.record(9.0)
    circuit.record(9.0)

    assert composer._advisor_for_now() is plain
