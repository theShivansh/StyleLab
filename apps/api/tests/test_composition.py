"""The composition service — the orchestration in docs/ARCHITECTURE.md section 6.

Steps 5 and 7 are separated on purpose: no amount of agent deliberation substitutes for the
ownership check. This file tests the seam between them, plus the degradation ladder in
docs/AI-SYSTEM.md.
"""

from __future__ import annotations

import logging

import pytest

from app.domain.models import GarmentCategory as C
from app.domain.models import Outfit, OutfitAdvice
from app.repositories.wardrobe import WardrobeRepository
from app.services.composition import CompositionService

U1 = "u1"


@pytest.fixture
def repo(session, stubs):
    r = WardrobeRepository(session)
    r.add_user(U1, "one@example.test")
    for item in (
        stubs.garment("top-1", U1, category=C.TOP, color_primary="white"),
        stubs.garment("bottom-1", U1, category=C.BOTTOM, color_primary="navy"),
        stubs.garment("shoe-1", U1, category=C.FOOTWEAR, color_primary="white"),
        stubs.garment("jacket-1", U1, category=C.OUTERWEAR, color_primary="navy"),
    ):
        r.add_item(item)
    session.commit()
    return r


async def test_a_valid_advisor_response_is_served_as_given(repo, stubs):
    advisor = stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1")
    advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["top-1", "bottom-1", "shoe-1"]
    assert advice.degradation_level == 1


async def test_the_final_score_is_recomputed_deterministically(repo, stubs):
    """Step 9. The advisor's own number is an opinion; the score shown to the user is
    computed from the items, so two identical wardrobes cannot show different totals."""
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="Advisor Pick",
                occasion="everyday",
                match_score=100,
            ),
            confidence=0.99,
        )
    )
    advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.outfit.match_score != 100
    # The name and rationale are the advisor's to write; the score is not.
    assert advice.outfit.name == "Advisor Pick"


async def test_an_id_outside_the_candidate_set_is_rejected(repo, stubs, caplog):
    """A plausible-looking id that simply does not exist (Case 01). No fetch, no retry."""
    advisor = stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-99-invented")

    with caplog.at_level(logging.CRITICAL):
        advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert "shoe-99-invented" not in advice.outfit.item_ids
    assert advice.degradation_level == 4


async def test_an_incompatible_combination_is_rejected(repo, stubs):
    """Case 02 through the service: two tops and no bottom, however confidently asserted."""
    advisor = stubs.ScriptedAdvisor.naming("top-1", "jacket-1")
    advice = await CompositionService(repo, advisor=advisor).compose(
        U1, occasion="everyday", required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR]
    )

    assert advice.degradation_level == 4
    assert advice.outfit is not None
    assert {"top-1", "bottom-1", "shoe-1"} >= set(advice.outfit.item_ids)


async def test_a_provider_failure_degrades_to_the_ranker_not_to_an_error(repo, stubs):
    """Rung 4. The user owns a complete outfit; a provider outage is not their problem."""
    advisor = stubs.FailingAdvisor()
    advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert advisor.calls >= 1
    assert advice.outfit is not None
    assert advice.degradation_level == 4
    assert advice.rationale, "a degraded answer still explains itself"


async def test_degradation_is_disclosed_rather_than_hidden(repo, stubs):
    """Case 23: "an honest note about reduced depth". A silently shallower answer that looks
    identical to a full one is the thing this project exists not to ship."""
    advice = await CompositionService(repo, advisor=stubs.FailingAdvisor()).compose(
        U1, occasion="everyday"
    )
    assert advice.degradation_level > 1
    assert any("without" in r.lower() or "reduced" in r.lower() for r in advice.rationale)


async def test_an_insufficient_wardrobe_names_the_gap_and_stops(session, stubs):
    """Case 12 / rung 5. Three tops and no bottoms — no partial outfit, no invented item."""
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    for index in range(3):
        repo.add_item(stubs.garment(f"top-{index}", U1, category=C.TOP))
    session.commit()

    advisor = stubs.ScriptedAdvisor.naming("top-0", "top-1", "top-2")
    advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert advice.outfit is None
    assert advice.missing_roles == [C.BOTTOM, C.FOOTWEAR]
    assert advice.wardrobe_gaps
    assert advice.degradation_level == 5
    # And the advisor was never called: there is nothing to deliberate about.
    assert advisor.calls == []


async def test_an_empty_wardrobe_is_a_gap_not_a_crash(session, stubs):
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    session.commit()

    advice = await CompositionService(repo, advisor=stubs.ScriptedAdvisor.naming()).compose(
        U1, occasion="everyday"
    )

    assert advice.outfit is None
    assert advice.missing_roles == [C.TOP, C.BOTTOM, C.FOOTWEAR]


async def test_a_trend_note_may_contextualise_an_owned_item(repo, stubs):
    """Case 16, the allowed half: the note survives because it points at something owned."""
    source = stubs.StaticTrendSource(stubs.trend_note(applies_to_items=["bottom-1"]))
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="x",
                occasion="everyday",
                match_score=80,
            ),
            trend_notes=[stubs.trend_note(applies_to_items=["bottom-1"])],
        )
    )
    advice = await CompositionService(repo, advisor=advisor, trend_source=source).compose(
        U1, occasion="everyday"
    )

    assert [n.trend for n in advice.trend_notes]
    assert advice.trend_notes[0].source
    assert advice.trend_notes[0].published_at


async def test_a_trend_note_pointing_at_an_unowned_item_is_dropped(repo, stubs):
    """Case 16, the forbidden half. Dropped rather than a hard failure: a note is context,
    not a slot, so it cannot put an unowned garment on the user — but it also must not be
    shown implying they own something they do not."""
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="x",
                occasion="everyday",
                match_score=80,
            ),
            trend_notes=[
                stubs.trend_note("Wide legs are current", applies_to_items=["not-owned"]),
                stubs.trend_note("Neutrals hold", applies_to_items=["top-1"]),
            ],
        )
    )
    advice = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert [n.trend for n in advice.trend_notes] == ["Neutrals hold"]
    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["top-1", "bottom-1", "shoe-1"]


async def test_an_unavailable_trend_source_drops_one_rung_not_the_answer(repo, stubs):
    """Rung 2. The crew runs without the Trend Scout rather than failing the request."""
    service = CompositionService(
        repo,
        advisor=stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1"),
        trend_source=stubs.UnavailableTrendSource(),
    )
    advice = await service.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.degradation_level == 2
    assert advice.trend_notes == []


async def test_the_request_handed_to_the_advisor_carries_only_ready_owned_items(repo, stubs):
    advisor = stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1")
    await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    request = advisor.calls[0]
    assert all(c.user_id == U1 for c in request.candidates)
    assert all(c.status == "ready" for c in request.candidates)


async def test_a_rejected_advisor_response_is_recorded_with_its_reason(repo, stubs):
    """prompts/04 requires audit writes for rejected attempts. The evidence trail is what
    makes the grounding story demonstrable rather than assertable."""
    advisor = stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "does-not-exist")
    service = CompositionService(repo, advisor=advisor)

    await service.compose(U1, occasion="everyday")

    assert len(service.rejections) == 1
    rejection = service.rejections[0]
    assert rejection.reason == "ungrounded_item"
    assert "does-not-exist" in rejection.detail
