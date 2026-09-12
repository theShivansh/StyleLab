"""AI-EVAL-CASES Case 11 — cross-user isolation.

The single most valuable test in the repository. It asserts three separate things, because
the invariant has three separate ways to fail:

1. **Retrieval is scoped.** U2's item is not in U1's candidate set.
2. **The query is the enforcement.** U2's item is never even asked for — asserted against
   the statements the engine actually executed, not against the returned objects.
3. **A forged response is refused.** An advisor returning a confident, schema-valid outfit
   containing U2's real item id is rejected by ownership re-validation, which runs in memory
   against the retrieved set and issues no query at all.

Point 3 is the one prompt wording cannot give you. An advisor that has been asked politely
to stay in scope, and an advisor that cannot leave it, look identical until this test runs.
"""

from __future__ import annotations

import logging

import pytest

from app.domain.errors import UngroundedItemError
from app.domain.models import AdviceRequest, GarmentCategory, ItemStatus, Outfit, OutfitAdvice
from app.domain.validation import validate_advice
from app.repositories.wardrobe import WardrobeRepository
from app.services.composition import CompositionService

U1, U2 = "user-1", "user-2"


@pytest.fixture
def two_wardrobes(session, stubs):
    """U1 owns a full outfit. U2 owns one item that would score well for U1."""
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    repo.add_user(U2, "two@example.test")

    for item in (
        stubs.garment("u1-top", U1, category=GarmentCategory.TOP, color_primary="white"),
        stubs.garment("u1-bottom", U1, category=GarmentCategory.BOTTOM, color_primary="navy"),
        stubs.garment("u1-shoe", U1, category=GarmentCategory.FOOTWEAR, color_primary="white"),
    ):
        repo.add_item(item)

    repo.add_item(
        stubs.garment(
            "u2-perfect-jacket",
            U2,
            category=GarmentCategory.OUTERWEAR,
            color_primary="black",
            style_tags=["minimal"],
        )
    )
    session.commit()
    return repo


def test_candidate_retrieval_returns_only_the_requesting_users_items(two_wardrobes):
    candidates = two_wardrobes.candidates(U1)
    ids = {c.item_id for c in candidates}

    assert ids == {"u1-top", "u1-bottom", "u1-shoe"}
    assert all(c.user_id == U1 for c in candidates)


def test_the_other_users_item_is_never_asked_for(two_wardrobes, executed):
    """Stronger than "was not returned": it was never in a query.

    A filter applied in Python after an unscoped SELECT would pass the test above and fail
    this one. That is the whole point.
    """
    two_wardrobes.candidates(U1)

    wardrobe_reads = [
        (sql, params) for sql, params in executed if "wardrobe_items" in sql and "SELECT" in sql
    ]
    assert wardrobe_reads, "expected at least one read to inspect"

    for sql, params in wardrobe_reads:
        flat = str(params)
        assert U1 in flat, f"unscoped read: {sql}"
        assert U2 not in flat
        assert "u2-perfect-jacket" not in flat


def test_a_forged_response_naming_another_users_item_is_rejected(two_wardrobes, stubs):
    """Case 11, second half. The id is real, the response is well-formed and confident, and
    the item belongs to somebody else."""
    request = AdviceRequest(
        user_id=U1,
        candidates=two_wardrobes.candidates(U1),
        occasion="everyday",
        required_roles=[GarmentCategory.TOP, GarmentCategory.BOTTOM, GarmentCategory.FOOTWEAR],
    )
    forged = OutfitAdvice(
        outfit=Outfit(
            item_ids=["u1-top", "u1-bottom", "u2-perfect-jacket"],
            name="Sharp Minimal",
            occasion="everyday",
            match_score=97,
        ),
        rationale=["The jacket pulls the whole look together."],
        confidence=0.98,
    )

    with pytest.raises(UngroundedItemError) as raised:
        validate_advice(forged, request=request)

    assert raised.value.item_ids == ["u2-perfect-jacket"]


def test_ownership_revalidation_issues_no_query(two_wardrobes, stubs, executed):
    """Rejected, not fetched (docs/AI-SYSTEM.md).

    Validation compares against the already-retrieved candidate set in memory. Looking the
    forged id up — even scoped — would put another user's id into a query, and the invariant
    is easier to defend if that never happens at all.
    """
    request = AdviceRequest(
        user_id=U1, candidates=two_wardrobes.candidates(U1), occasion="everyday"
    )
    executed.clear()

    with pytest.raises(UngroundedItemError):
        validate_advice(
            OutfitAdvice(
                outfit=Outfit(
                    item_ids=["u2-perfect-jacket"], name="x", occasion="everyday", match_score=90
                )
            ),
            request=request,
        )

    assert executed == []


async def test_the_service_never_serves_an_unowned_item(two_wardrobes, stubs, caplog):
    """End to end: a forged advisor response must not reach the user, and the event must be
    logged loudly rather than absorbed."""
    advisor = stubs.ScriptedAdvisor.naming("u1-top", "u1-bottom", "u2-perfect-jacket")
    service = CompositionService(two_wardrobes, advisor=advisor)

    with caplog.at_level(logging.CRITICAL):
        advice = await service.compose(U1, occasion="everyday")

    served = advice.outfit.item_ids if advice.outfit else []
    assert "u2-perfect-jacket" not in served
    assert all(i.startswith("u1-") for i in served)

    # Degraded rather than failed: the user still gets an outfit from their own wardrobe.
    assert advice.degradation_level == 4
    assert any("ungrounded" in r.message.lower() for r in caplog.records)


async def test_the_advisor_only_ever_sees_the_scoped_candidate_set(two_wardrobes, stubs):
    """U2's item never enters the prompt, because it never enters the request."""
    advisor = stubs.ScriptedAdvisor.naming("u1-top", "u1-bottom", "u1-shoe")
    service = CompositionService(two_wardrobes, advisor=advisor)

    await service.compose(U1, occasion="everyday")

    assert advisor.calls, "advisor was not called"
    seen = {c.item_id for call in advisor.calls for c in call.candidates}
    assert seen <= {"u1-top", "u1-bottom", "u1-shoe"}
    assert all(call.user_id == U1 for call in advisor.calls)


def test_an_item_still_analyzing_is_not_a_candidate(session, stubs):
    """Business validation: an item that has not finished extraction has no reliable
    metadata to style with."""
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    repo.add_item(stubs.garment("ready", U1))
    repo.add_item(stubs.garment("pending", U1, status=ItemStatus.ANALYZING))
    session.commit()

    assert {c.item_id for c in repo.candidates(U1)} == {"ready"}


def test_a_soft_deleted_item_is_not_a_candidate(session, stubs):
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    repo.add_item(stubs.garment("kept", U1))
    repo.add_item(stubs.garment("gone", U1))
    repo.soft_delete_item(U1, "gone")
    session.commit()

    assert {c.item_id for c in repo.candidates(U1)} == {"kept"}


def test_soft_delete_cannot_reach_another_users_item(session, stubs):
    """A write path is scoped too. Deletion is a read plus an update, and the read is the
    part that leaks."""
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    repo.add_user(U2, "two@example.test")
    repo.add_item(stubs.garment("u2-item", U2))
    session.commit()

    assert repo.soft_delete_item(U1, "u2-item") is False
    assert {c.item_id for c in repo.candidates(U2)} == {"u2-item"}
