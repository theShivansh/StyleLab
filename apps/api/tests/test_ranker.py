"""The deterministic ranker — rung 4 of the fallback ladder.

It ranks items the user owns, without an LLM, when the crew is unavailable. It is not a
demo mode and not a product path: docs/AI-SYSTEM.md puts it below the crew, and the app must
never route to it while the provider is healthy.
"""

from __future__ import annotations

import pytest

from app.domain.compatibility import CORE_ROLES
from app.domain.models import AdviceRequest, Formality
from app.domain.models import GarmentCategory as C
from app.domain.ranker import MAX_CANDIDATES_PER_ROLE, DeterministicRanker
from app.domain.scoring import match_score, score_outfit


@pytest.fixture
def g(stubs):
    return stubs.garment


def request_for(items, **over):
    payload = {
        "user_id": "u1",
        "candidates": list(items),
        "occasion": "everyday",
        "required_roles": list(CORE_ROLES),
    }
    payload.update(over)
    return AdviceRequest(**payload)


def test_it_is_not_an_outfit_advisor(stubs):
    """Guard against it quietly becoming one.

    If `DeterministicRanker` grew an `advise()` method it would satisfy the `OutfitAdvisor`
    Protocol and could be injected as the advisor — which is exactly how a fallback turns
    into a demo mode. Keeping it structurally incompatible makes that impossible.
    """
    from app.adapters import OutfitAdvisor

    assert not isinstance(DeterministicRanker(), OutfitAdvisor)


def test_it_composes_only_from_the_candidate_set(g):
    items = [g("t", category=C.TOP), g("b", category=C.BOTTOM), g("s", category=C.FOOTWEAR)]
    advice = DeterministicRanker().compose(request_for(items))

    assert advice.outfit is not None
    assert set(advice.outfit.item_ids) <= {"t", "b", "s"}
    assert advice.degradation_level == 4


def test_it_reports_the_gap_rather_than_returning_a_partial_outfit(g):
    """Case 12. A one-item "outfit" is worse than an honest answer."""
    advice = DeterministicRanker().compose(request_for([g("t", category=C.TOP)]))

    assert advice.outfit is None
    assert advice.missing_roles == [C.BOTTOM, C.FOOTWEAR]
    assert advice.wardrobe_gaps
    # Rung 5: an honest statement of the gap.
    assert advice.degradation_level == 5


def test_it_is_stable_across_runs(g):
    """"Deterministic filtering is stable" — same wardrobe, same answer, including ties."""
    items = [
        g("a", category=C.TOP),
        g("b", category=C.TOP),
        g("c", category=C.BOTTOM),
        g("d", category=C.BOTTOM),
        g("e", category=C.FOOTWEAR),
    ]
    ranker = DeterministicRanker()
    runs = [ranker.compose(request_for(items)).outfit for _ in range(5)]

    assert all(r is not None for r in runs)
    assert len({tuple(r.item_ids) for r in runs if r}) == 1


def test_ties_break_on_item_id_not_insertion_order(g):
    """Two identical garments must not produce a different answer depending on which was
    uploaded first — otherwise "stable" only holds for one ordering of the same wardrobe."""
    a = [
        g("aaa", category=C.TOP),
        g("zzz", category=C.TOP),
        g("b", category=C.BOTTOM),
        g("s", category=C.FOOTWEAR),
    ]
    ranker = DeterministicRanker()

    forward = ranker.compose(request_for(a)).outfit
    reverse = ranker.compose(request_for(list(reversed(a)))).outfit

    assert forward and reverse
    assert forward.item_ids == reverse.item_ids


def test_it_prefers_the_occasion_it_was_asked_for(g):
    """Preference adherence without claiming certainty (Case 03/04)."""
    items = [
        g("casual-top", category=C.TOP, formality=Formality.CASUAL),
        g("formal-top", category=C.TOP, formality=Formality.FORMAL),
        g("formal-bottom", category=C.BOTTOM, formality=Formality.FORMAL),
        g("formal-shoe", category=C.FOOTWEAR, formality=Formality.FORMAL),
    ]
    advice = DeterministicRanker().compose(request_for(items, occasion="interview"))

    assert advice.outfit is not None
    assert "formal-top" in advice.outfit.item_ids


def test_it_prefers_the_requested_fit(g):
    items = [
        g("slim", category=C.TOP, fit="slim"),
        g("relaxed", category=C.TOP, fit="relaxed"),
        g("b", category=C.BOTTOM, fit="relaxed"),
        g("s", category=C.FOOTWEAR),
    ]
    advice = DeterministicRanker().compose(request_for(items, fit_preference="relaxed"))

    assert advice.outfit is not None
    assert "relaxed" in advice.outfit.item_ids


def test_it_offers_more_than_one_look_when_the_wardrobe_allows(g):
    """Case 10 — diversity. Not the same combination every time when alternatives exist."""
    items = [
        g("t1", category=C.TOP),
        g("t2", category=C.TOP, color_primary="white"),
        g("b1", category=C.BOTTOM),
        g("b2", category=C.BOTTOM, color_primary="black"),
        g("s", category=C.FOOTWEAR),
    ]
    ranked = DeterministicRanker().rank(request_for(items), limit=3)

    assert len(ranked) >= 2
    combinations = {tuple(item.item_id for item in look.items) for look in ranked}
    assert len(combinations) == len(ranked)
    # Ordered best-first, so the UI can present "another option" honestly.
    assert [look.breakdown.total for look in ranked] == sorted(
        (look.breakdown.total for look in ranked), reverse=True
    )


def test_it_bounds_the_search_on_a_large_wardrobe(g):
    """Enumeration is a product of per-role counts, so it must be capped or a 200-garment
    wardrobe becomes a timeout."""
    items = (
        [g(f"t{i:03}", category=C.TOP) for i in range(40)]
        + [g(f"b{i:03}", category=C.BOTTOM) for i in range(40)]
        + [g(f"s{i:03}", category=C.FOOTWEAR) for i in range(40)]
    )
    ranker = DeterministicRanker()
    shortlist = ranker.shortlist(request_for(items))

    for role in CORE_ROLES:
        assert len(shortlist[role]) <= MAX_CANDIDATES_PER_ROLE

    advice = ranker.compose(request_for(items))
    assert advice.outfit is not None


def test_the_score_is_bounded_and_explained(g):
    items = [g("t", category=C.TOP), g("b", category=C.BOTTOM), g("s", category=C.FOOTWEAR)]
    request = request_for(items)

    breakdown = score_outfit(items, request)
    assert 0.0 <= breakdown.total <= 1.0
    for dimension in ("style", "color", "silhouette", "occasion", "preference", "variety"):
        assert 0.0 <= getattr(breakdown, dimension) <= 1.0

    assert 0 <= match_score(items, request) <= 100


def test_a_head_to_toe_clash_scores_below_a_coherent_look(g):
    coherent = [
        g("t", category=C.TOP, color_primary="white", fit="regular"),
        g("b", category=C.BOTTOM, color_primary="navy", fit="relaxed"),
        g("s", category=C.FOOTWEAR, color_primary="white", fit="regular"),
    ]
    clashing = [
        g("t", category=C.TOP, color_primary="red", fit="oversized", style_tags=["sporty"]),
        g("b", category=C.BOTTOM, color_primary="green", fit="oversized", style_tags=["formal"]),
        g("s", category=C.FOOTWEAR, color_primary="yellow", fit="oversized", style_tags=["preppy"]),
    ]
    request = request_for(coherent)

    assert score_outfit(coherent, request).total > score_outfit(clashing, request).total


def test_rationale_never_asserts_material_as_fact(g):
    """Case 22 / Case 08. The ranker writes its own copy, so it must obey the rule too."""
    items = [
        g("t", category=C.TOP, material_guess="wool"),
        g("b", category=C.BOTTOM),
        g("s", category=C.FOOTWEAR),
    ]
    advice = DeterministicRanker().compose(request_for(items))

    joined = " ".join(advice.rationale).lower()
    if "wool" in joined:
        assert "looks like" in joined or "probabl" in joined or "guess" in joined
