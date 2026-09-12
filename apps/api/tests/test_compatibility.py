"""Category and role compatibility — AI-EVAL-CASES Case 02 and Case 12.

These rules are the deterministic half of the system. The model may rank and explain; it may
not decide that two tops and no bottom is an outfit.
"""

from __future__ import annotations

import pytest

from app.domain.compatibility import (
    CORE_ROLES,
    conflicts,
    group_by_role,
    is_valid_combination,
    missing_roles,
    name_gaps,
)
from app.domain.models import GarmentCategory as C


@pytest.fixture
def g(stubs):
    return stubs.garment


def test_a_top_bottom_and_shoe_is_a_valid_look(g):
    items = [
        g("t", category=C.TOP),
        g("b", category=C.BOTTOM),
        g("s", category=C.FOOTWEAR),
    ]
    assert is_valid_combination(items, CORE_ROLES) is True
    assert conflicts(items, CORE_ROLES) == []


def test_two_tops_and_no_bottom_is_rejected(g):
    """Case 02's stated failure. It must be refused structurally, not scored low."""
    items = [g("t1", category=C.TOP), g("t2", category=C.TOP), g("s", category=C.FOOTWEAR)]

    assert is_valid_combination(items, CORE_ROLES) is False
    reasons = conflicts(items, CORE_ROLES)
    assert any("bottom" in r for r in reasons)
    assert any("top" in r for r in reasons)


def test_a_role_filled_by_the_wrong_category_is_rejected(g):
    """docs/AI-SYSTEM.md business validation: "a required role is filled by an item of the
    wrong category"."""
    items = [g("t", category=C.TOP), g("b", category=C.BOTTOM), g("hat", category=C.ACCESSORY)]

    assert is_valid_combination(items, CORE_ROLES) is False
    assert any("footwear" in r for r in conflicts(items, CORE_ROLES))


def test_outerwear_and_accessories_are_additive_not_conflicting(g):
    """A jacket and a belt do not compete for a slot. Only one of each core role does."""
    items = [
        g("t", category=C.TOP),
        g("b", category=C.BOTTOM),
        g("s", category=C.FOOTWEAR),
        g("j", category=C.OUTERWEAR),
        g("belt", category=C.ACCESSORY),
        g("cap", category=C.ACCESSORY),
    ]
    assert is_valid_combination(items, CORE_ROLES) is True


def test_two_jackets_do_conflict(g):
    items = [
        g("t", category=C.TOP),
        g("b", category=C.BOTTOM),
        g("s", category=C.FOOTWEAR),
        g("j1", category=C.OUTERWEAR),
        g("j2", category=C.OUTERWEAR),
    ]
    assert is_valid_combination(items, CORE_ROLES) is False


def test_missing_roles_are_named_in_a_stable_order(g):
    items = [g("t", category=C.TOP)]
    assert missing_roles(items, CORE_ROLES) == [C.BOTTOM, C.FOOTWEAR]
    # Called twice, same answer — the UI renders this string.
    assert missing_roles(items, CORE_ROLES) == missing_roles(items, CORE_ROLES)


def test_grouping_ignores_items_that_are_not_ready(g, stubs):
    from app.domain.models import ItemStatus

    items = [g("ready", category=C.TOP), g("pending", category=C.TOP, status=ItemStatus.ANALYZING)]
    grouped = group_by_role(items)
    assert [i.item_id for i in grouped[C.TOP]] == ["ready"]


def test_a_named_gap_is_generic_and_counts_what_it_unlocks(g):
    """Case 12. Three tops and no bottoms: say what is missing, and be honest about how
    much it would unlock rather than inventing urgency."""
    items = [g(f"t{i}", category=C.TOP) for i in range(3)] + [g("s", category=C.FOOTWEAR)]

    gaps = name_gaps(items, CORE_ROLES)

    assert [gap.category for gap in gaps] == [C.BOTTOM]
    gap = gaps[0]
    # 3 tops x 1 shoe = 3 outfits become possible once a bottom exists.
    assert gap.unlocks_outfits == 3
    assert gap.generic_description
    # No brand, price, merchant or link — anywhere.
    text = gap.generic_description.lower()
    assert not any(token in text for token in ("$", "£", "buy", "shop", "http"))


def test_no_gap_is_named_when_every_role_is_covered(g):
    items = [g("t", category=C.TOP), g("b", category=C.BOTTOM), g("s", category=C.FOOTWEAR)]
    assert name_gaps(items, CORE_ROLES) == []


def test_a_gap_that_unlocks_nothing_still_reports_zero_rather_than_guessing(g):
    """One top only: a bottom unlocks nothing on its own, because there are no shoes either.
    Report 0 — do not round up to make the suggestion look better."""
    gaps = name_gaps([g("t", category=C.TOP)], CORE_ROLES)
    assert {gap.category: gap.unlocks_outfits for gap in gaps} == {C.BOTTOM: 0, C.FOOTWEAR: 0}
