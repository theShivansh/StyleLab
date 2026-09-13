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
    identical to a full one is the thing this project exists not to ship.

    **The disclosure moved in S11, and the requirement did not.** This test used to look for
    the words in `rationale`, where the ranker wrote a sentence of its own. The result screen
    was therefore saying it twice, in two wordings, stacked — once from here and once from
    the client's `degradation_level` footer, which covers every rung rather than only this
    one.

    So the assertion follows the signal to the field that is typed for it. The rendering half
    is held by `apps/web/e2e/outfit.spec.ts` — *"a degraded look discloses its depth once, not
    twice"* — because whether a user is told is a fact about a screen, and asserting it
    against a string in a list here was always a proxy for that.
    """
    advice = await CompositionService(repo, advisor=stubs.FailingAdvisor()).compose(
        U1, occasion="everyday"
    )

    assert advice.degradation_level > 1
    # And the rationale still explains the *outfit*, which is what a rationale is for.
    assert advice.rationale
    assert not any("advisory crew" in line.lower() for line in advice.rationale)


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
    """Case 16, the allowed half: the note survives because it points at something owned —
    and because the trend source is the one that supplied it."""
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
    wide = stubs.trend_note("Wide legs are current", url="https://pub.test/wide")
    neutral = stubs.trend_note("Neutrals hold", url="https://pub.test/neutral")
    source = stubs.StaticTrendSource(wide, neutral)
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="x",
                occasion="everyday",
                match_score=80,
            ),
            trend_notes=[
                wide.model_copy(update={"applies_to_items": ["not-owned"]}),
                neutral.model_copy(update={"applies_to_items": ["top-1"]}),
            ],
        )
    )
    advice = await CompositionService(repo, advisor=advisor, trend_source=source).compose(
        U1, occasion="everyday"
    )

    assert [n.trend for n in advice.trend_notes] == ["Neutrals hold"]
    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["top-1", "bottom-1", "shoe-1"]


async def test_a_trend_note_the_source_never_supplied_is_dropped(repo, stubs):
    """Case 15 with teeth, and a hole S8b found open.

    The invented note below is schema-valid: a claim, a publication, a date, a link, and it
    points at a garment the user owns. The trend source returned one note and the advisor
    returned two. Before this check, model recall dressed as a citation was rendered to the
    user, which is exactly what the trend rules in CLAUDE.md exist to prevent.
    """
    real = stubs.trend_note("Neutrals hold", url="https://pub.test/neutral")
    invented = stubs.trend_note(
        "Chrome is the colour of the season",
        source="A Real Magazine",
        url="https://magazine.test/chrome-ss27",
    )
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="x",
                occasion="everyday",
                match_score=80,
            ),
            trend_notes=[
                real.model_copy(update={"applies_to_items": ["top-1"]}),
                invented.model_copy(update={"applies_to_items": ["top-1"]}),
            ],
        )
    )

    advice = await CompositionService(
        repo, advisor=advisor, trend_source=stubs.StaticTrendSource(real)
    ).compose(U1, occasion="everyday")

    assert [n.trend for n in advice.trend_notes] == ["Neutrals hold"]


async def test_the_citation_comes_from_the_source_not_from_the_advisor(repo, stubs):
    """An advisor may map a note onto garments. It may not restate the claim.

    Rewording is how a citation drifts away from what the article actually said while keeping
    the link that makes it look checkable.
    """
    from datetime import date

    real = stubs.trend_note("Neutrals hold", url="https://pub.test/neutral")
    reworded = real.model_copy(
        update={
            "trend": "Neutrals are over, everyone is wearing chrome",
            "source": "Somebody Else Weekly",
            "published_at": date(2020, 1, 1),
            "applies_to_items": ["top-1"],
        }
    )
    advisor = stubs.ScriptedAdvisor(
        OutfitAdvice(
            outfit=Outfit(
                item_ids=["top-1", "bottom-1", "shoe-1"],
                name="x",
                occasion="everyday",
                match_score=80,
            ),
            trend_notes=[reworded],
        )
    )

    advice = await CompositionService(
        repo, advisor=advisor, trend_source=stubs.StaticTrendSource(real)
    ).compose(U1, occasion="everyday")

    kept = advice.trend_notes[0]
    assert (kept.trend, kept.source, kept.published_at) == (
        real.trend,
        real.source,
        real.published_at,
    )
    # The one thing the advisor is allowed to decide survives.
    assert kept.applies_to_items == ["top-1"]


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


# --- the latency budget (AI-EVAL-CASES Case 23) ------------------------------------------


async def test_an_advisor_that_exceeds_the_budget_degrades_to_the_ranker(repo, stubs):
    """The floor of Case 23: an outfit and an honest note, never an unresolving spinner.

    Worth stating why this ceiling exists at all, since the transport already has one. The
    waits compound — three transport attempts inside two advisor attempts, each with its own
    30-second client timeout — so "the provider is slow" can hold a compose open for minutes
    with nothing above it aware that a person is watching.
    """
    advisor = stubs.SlowAdvisor(delay_s=5.0)
    service = CompositionService(repo, advisor=advisor, latency_budget_s=0.02)

    advice = await service.compose(U1, occasion="everyday")

    assert advice.outfit is not None  # from the deterministic ranker, over the same items
    assert advice.degradation_level == 4
    assert [r.reason for r in service.rejections] == ["advisor_timeout"]


async def test_the_budget_cancels_the_call_rather_than_abandoning_it(repo, stubs):
    """An orphaned provider request holds a connection open and is still billed."""
    advisor = stubs.SlowAdvisor(delay_s=5.0)

    await CompositionService(repo, advisor=advisor, latency_budget_s=0.02).compose(
        U1, occasion="everyday"
    )

    assert advisor.cancelled
    assert not advisor.completed


async def test_a_timeout_is_a_different_rejection_from_an_outage(repo, stubs):
    """Both degrade; they are not the same problem and must not share a bucket.

    A slow model is a capacity or prompt-size question. A failing one is an availability
    question. A dashboard that merges them tells you an incident is happening and nothing
    about which incident.
    """
    slow = CompositionService(repo, advisor=stubs.SlowAdvisor(delay_s=5.0), latency_budget_s=0.02)
    broken = CompositionService(repo, advisor=stubs.FailingAdvisor())

    await slow.compose(U1, occasion="everyday")
    await broken.compose(U1, occasion="everyday")

    assert [r.reason for r in slow.rejections] == ["advisor_timeout"]
    assert [r.reason for r in broken.rejections] == ["advisor_unavailable"]


async def test_no_budget_means_the_advisor_is_awaited_as_long_as_it_takes(repo, stubs):
    """`latency_budget_s=None` is the default and is only ever right in a test.

    Asserted so that the wiring in `app/main.py` is load-bearing: if the budget stopped
    being passed, composition would silently go back to waiting forever and nothing else
    would notice.
    """
    advisor = stubs.SlowAdvisor(
        delay_s=0.0, response=stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1").response
    )
    service = CompositionService(repo, advisor=advisor)

    advice = await service.compose(U1, occasion="everyday")

    assert advisor.completed
    assert advice.outfit is not None
    assert service.rejections == []


# --- generation telemetry ------------------------------------------------------------------


async def test_a_successful_compose_records_one_event_with_its_depth(repo, stubs):
    log = stubs.CollectingGenerationLog()
    service = CompositionService(
        repo,
        advisor=stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1"),
        telemetry=log,
        job_id="job_1",
    )

    await service.compose(U1, occasion="everyday")

    assert log.outcomes == ["ok"]
    event = log.events[0]
    assert (event.operation, event.degradation_level, event.job_id) == ("advice", 1, "job_1")
    assert event.user_id == U1


async def test_every_refusal_records_its_own_outcome(repo, stubs):
    """A dashboard that only sees the calls that worked reports 100% forever."""
    log = stubs.CollectingGenerationLog()

    for advisor in (
        stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "does-not-exist"),  # ungrounded
        stubs.ScriptedAdvisor.naming("top-1", "top-1", "shoe-1"),  # duplicate garment
        stubs.SlowAdvisor(delay_s=5.0),  # over budget
        stubs.FailingAdvisor(),  # provider outage
    ):
        await CompositionService(
            repo, advisor=advisor, telemetry=log, latency_budget_s=0.02
        ).compose(U1, occasion="everyday")

    assert log.outcomes == [
        "ungrounded_item",
        "incompatible_outfit",
        "timeout",
        "provider_error",
    ]


async def test_a_call_that_never_reached_the_provider_is_not_given_the_last_ones_figures(
    repo, stubs
):
    """The advisor outlives the request; its telemetry is the *last* call's.

    Without the identity check in `_emit`, a provider outage would be recorded against
    whatever model answered the previous user, with that call's latency — a fabricated
    measurement, in the module whose entire purpose is not fabricating measurements.
    """
    from app.adapters.advice import AdviceTelemetry
    from app.services.composition import UNREPORTED_MODEL

    advisor = stubs.FailingAdvisor()
    advisor.last_telemetry = AdviceTelemetry(model="eval/text", latency_ms=900)
    log = stubs.CollectingGenerationLog()

    await CompositionService(repo, advisor=advisor, telemetry=log).compose(
        U1, occasion="everyday"
    )

    event = log.events[0]
    assert event.model == UNREPORTED_MODEL
    assert event.latency_ms == 0


async def test_telemetry_is_optional_and_its_absence_changes_nothing(repo, stubs):
    """No sink is a gap in a dashboard, never a difference in what the user is served."""
    advisor = stubs.ScriptedAdvisor.naming("top-1", "bottom-1", "shoe-1")

    with_log = await CompositionService(
        repo, advisor=advisor, telemetry=stubs.CollectingGenerationLog()
    ).compose(U1, occasion="everyday")
    without = await CompositionService(repo, advisor=advisor).compose(U1, occasion="everyday")

    assert with_log == without
