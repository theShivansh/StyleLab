"""Case 21 — agent ablation. Every role must change the output, or it is decoration.

This is the test CI has been referencing and failing on since S4 (blocker B11). It was
deliberately never stubbed: an ablation test that cannot fail is worse than no ablation test,
because it converts "we have not checked" into "we have checked", and the whole point of the
exercise is that it must be able to condemn a role.

## What "changes the output materially" means here

Not "the bytes differ" — with a scripted provider they would differ for trivial reasons, and
with a real one they would differ every run. Each role is checked against the specific,
observable contribution it exists to make:

| role              | its contribution, if it has one                          |
|-------------------|----------------------------------------------------------|
| Style Profiler    | the Architect is told the user's aesthetic               |
| Trend Scout       | attributed trend notes reach the answer                  |
| Critic            | a critique is produced, and a weak draft is rebuilt      |
| Practical Advisor | pro tips, budget tricks and named gaps reach the answer  |

A role that can be switched off without that contribution disappearing is not pulling its
weight, and `docs/DECISIONS.md` says to delete it and record why. Nobody has had to yet.

The Architect and the Editor are not ablatable, and `CrewRoles.without` refuses to try.
Removing either does not degrade the crew, it removes the product: there would be no outfit,
or nothing to return it in. Asserting that they "change the output" would be theatre.
"""

from __future__ import annotations

import json

import pytest
from app.adapters.crew import REQUIRED_ROLES, CrewAIOutfitAdvisor, CrewRoles
from app.domain.models import AdviceRequest
from app.domain.models import GarmentCategory as C
from crew_fixtures import LOOK, crew_script
from harness import OWNED, U1
from stubs import MockGroqProvider, garment, trend_note

ABLATABLE = ("style_profiler", "trend_scout", "critic", "practical_advisor")

TREND_URL = "https://example-publication.test/neutral-palettes"


def request_for(*, with_trends: bool = False) -> AdviceRequest:
    notes = (
        [trend_note("Neutral palettes holding through AW26", url=TREND_URL)]
        if with_trends
        else []
    )
    return AdviceRequest(
        user_id=U1,
        candidates=[
            garment(item_id, U1, category=category, color_primary=colour)
            for item_id, category, colour in OWNED
        ],
        occasion="everyday",
        required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR],
        trend_notes=notes,
    )


def advisor(roles: CrewRoles, **script: str) -> tuple[CrewAIOutfitAdvisor, MockGroqProvider]:
    transport = MockGroqProvider(by_schema=crew_script(**script))
    return (
        CrewAIOutfitAdvisor(transport, model="eval/text", roles=roles),
        transport,
    )


# --- the roles that cannot be removed ------------------------------------------------------


@pytest.mark.parametrize("role", sorted(REQUIRED_ROLES))
def test_the_load_bearing_roles_refuse_to_be_ablated(role):
    with pytest.raises(ValueError, match="cannot be ablated"):
        CrewRoles.without(role)


# --- every other role must earn its tokens --------------------------------------------------


@pytest.mark.parametrize("role", ABLATABLE)
async def test_disabling_a_role_stops_it_being_called(role):
    """The floor: an ablated role does not speak. If this fails the switch does nothing and
    every assertion below it is meaningless."""
    subject, _ = advisor(CrewRoles.without(role))

    await subject.advise(request_for(with_trends=True))

    assert role not in subject.last_run.roles_run
    assert role in CrewRoles().enabled()  # it is on by default, so this is a real removal


async def test_the_style_profiler_changes_what_the_architect_is_told():
    """Its contribution is upstream, not in the response, so that is where it is asserted.

    The profile reaches the user only through the Architect's choice. Asserting on the final
    text would be asserting on the scripted Editor, which proves nothing about the Profiler.
    """
    with_profiler, on_transport = advisor(CrewRoles())
    without_profiler, off_transport = advisor(CrewRoles.without("style_profiler"))

    await with_profiler.advise(request_for())
    await without_profiler.advise(request_for())

    def architect_prompt(transport):
        return next(
            call.text for call in transport.calls if call.schema_name == "outfit_draft"
        )

    assert "STYLE PROFILE" in architect_prompt(on_transport)
    assert "softly tailored" in architect_prompt(on_transport)
    assert "STYLE PROFILE" not in architect_prompt(off_transport)


async def test_the_trend_scout_changes_whether_a_trend_reaches_the_answer():
    on, _ = advisor(
        CrewRoles(),
        trend_application=json.dumps(
            {"applied": [{"url": TREND_URL, "item_ids": ["own-top"], "why": "neutral"}]}
        ),
        editor_output=json.dumps(
            {
                "item_ids": LOOK,
                "name": "Quiet Weekday",
                "occasion": "everyday",
                "rationale": ["Neutral through."],
                "confidence": 0.8,
                "pro_tips": [],
                "budget_tricks": [],
                "wardrobe_gaps": [],
                "applied_trends": [{"url": TREND_URL, "item_ids": ["own-top"], "why": "neutral"}],
            }
        ),
    )
    off, _ = advisor(CrewRoles.without("trend_scout"))

    with_scout = await on.advise(request_for(with_trends=True))
    without_scout = await off.advise(request_for(with_trends=True))

    assert [note.url for note in with_scout.trend_notes] == [TREND_URL]
    assert without_scout.trend_notes == []


async def test_the_critic_changes_whether_a_weak_draft_is_rebuilt():
    """Its contribution is the revision, which is the expensive part of the crew and the
    part most worth being able to justify.

    Scripted so the first critique is a failing one with a concrete objection. With the
    Critic on, the Architect is asked again under that constraint; with it off, the first
    draft is served as-is.
    """
    weak = json.dumps(
        {
            "considered": ["proportion"],
            "tradeoffs": [],
            "objections": ["the footwear is too formal for the occasion"],
            "score": 41,
        }
    )
    on, on_transport = advisor(CrewRoles(), critique=weak)
    off, off_transport = advisor(CrewRoles.without("critic"))

    await on.advise(request_for())
    await off.advise(request_for())

    assert on.last_run.revised is True
    assert on_transport.schemas_called.count("outfit_draft") == 2
    revision = [c for c in on_transport.calls if c.schema_name == "outfit_draft"][1].text
    assert "REQUIREMENTS FROM THE CRITIC" in revision
    assert "too formal for the occasion" in revision

    assert off.last_run.revised is False
    assert off_transport.schemas_called.count("outfit_draft") == 1


async def test_the_practical_advisor_changes_the_advisory_content():
    on, on_transport = advisor(CrewRoles())
    off, off_transport = advisor(CrewRoles.without("practical_advisor"))

    await on.advise(request_for())
    await off.advise(request_for())

    def editor_prompt(transport):
        return next(
            call.text for call in transport.calls if call.schema_name == "editor_output"
        )

    assert "PRACTICAL ADVICE" in editor_prompt(on_transport)
    assert "Half-tuck" in editor_prompt(on_transport)
    assert "PRACTICAL ADVICE" not in editor_prompt(off_transport)


# --- the ladder uses the same switch ----------------------------------------------------------


async def test_rung_three_is_the_ablation_switch_with_four_roles_off():
    """Degradation rung 3 — "Architect + Editor only" — and the ablation mechanism are the
    same object. A test-only switch would mean this test exercises a path the product never
    takes."""
    subject, transport = advisor(CrewRoles.architect_and_editor_only())

    advice = await subject.advise(request_for(with_trends=True))

    assert subject.last_run.roles_run == ("outfit_architect", "editor")
    assert transport.schemas_called == ["outfit_draft", "editor_output"]
    assert advice.outfit is not None
