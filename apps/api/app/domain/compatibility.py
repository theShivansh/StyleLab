"""Role and category compatibility — the deterministic half of composition.

The model ranks and explains. It does not get to decide that two tops and no bottom is an
outfit; that is settled here, structurally, before any score is computed. docs/AI-SYSTEM.md
lists these as business validations, and AI-EVAL-CASES Case 02 is the regression.

Two kinds of role live in this module:

* **core roles** (top, bottom, footwear) — exactly one item each. A second one is a
  conflict, because two shirts do not layer into one slot.
* **additive roles** (outerwear, accessory) — a jacket and a belt do not compete. Outerwear
  is capped at one, accessories are not capped at all.

Everything here is a pure function over domain objects. No SQL, no provider, no I/O.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from app.domain.models import GarmentCategory, ItemStatus, WardrobeGap, WardrobeItem

#: The roles an outfit needs before it is an outfit. Requested by default.
CORE_ROLES: tuple[GarmentCategory, ...] = (
    GarmentCategory.TOP,
    GarmentCategory.BOTTOM,
    GarmentCategory.FOOTWEAR,
)

#: Roles that add to a look rather than filling a slot in it.
ADDITIVE_ROLES: tuple[GarmentCategory, ...] = (
    GarmentCategory.OUTERWEAR,
    GarmentCategory.ACCESSORY,
)

#: The only role with a cap but no requirement: two coats at once is a mistake, not a layer.
MAX_PER_ROLE: dict[GarmentCategory, int] = {
    GarmentCategory.TOP: 1,
    GarmentCategory.BOTTOM: 1,
    GarmentCategory.FOOTWEAR: 1,
    GarmentCategory.OUTERWEAR: 1,
}

#: Stable presentation order. The UI renders these strings, so the order must not wobble.
ROLE_ORDER: tuple[GarmentCategory, ...] = CORE_ROLES + ADDITIVE_ROLES

#: Generic, non-commercial descriptions for a named gap. No brand, price, merchant or link
#: anywhere — the product sells nothing, so a gap cannot become a recommendation to buy.
GAP_DESCRIPTIONS: dict[GarmentCategory, str] = {
    GarmentCategory.TOP: "a plain mid-weight top in a neutral colour",
    GarmentCategory.BOTTOM: "a straight-leg trouser or jean in a neutral colour",
    GarmentCategory.FOOTWEAR: "a clean low-profile shoe in a neutral colour",
    GarmentCategory.OUTERWEAR: "an unstructured jacket that layers over a shirt",
    GarmentCategory.ACCESSORY: "a simple leather belt or a plain cap",
}


def is_ready(item: WardrobeItem) -> bool:
    """An item still being analysed has no metadata worth styling with, and a failed or
    archived one is not in the wardrobe any more."""
    return item.status == ItemStatus.READY


def role_of(item: WardrobeItem) -> GarmentCategory | None:
    """The role an item can fill. `None` when extraction produced no category — which is a
    real outcome on a bad photo, not an error."""
    return item.extraction.category


def group_by_role(items: Iterable[WardrobeItem]) -> dict[GarmentCategory, list[WardrobeItem]]:
    """Ready items bucketed by role, each bucket sorted by id.

    Sorted rather than insertion-ordered so that the same wardrobe produces the same
    grouping regardless of upload order — the ranker's stability depends on it.
    """
    grouped: dict[GarmentCategory, list[WardrobeItem]] = defaultdict(list)
    for item in items:
        if not is_ready(item):
            continue
        role = role_of(item)
        if role is not None:
            grouped[role].append(item)
    return {role: sorted(bucket, key=lambda i: i.item_id) for role, bucket in grouped.items()}


def missing_roles(
    items: Iterable[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
) -> list[GarmentCategory]:
    """Requested roles with nothing ready to fill them, in `ROLE_ORDER`."""
    grouped = group_by_role(items)
    return [role for role in ROLE_ORDER if role in required and not grouped.get(role)]


def conflicts(
    items: Sequence[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
) -> list[str]:
    """Every reason this set of items is not a valid outfit.

    Returns all of them rather than the first, so the UI and the log can say what is wrong
    instead of what is wrong *first*.
    """
    reasons: list[str] = []
    grouped = group_by_role(items)

    for role in ROLE_ORDER:
        count = len(grouped.get(role, []))
        cap = MAX_PER_ROLE.get(role)
        if role in required and count == 0:
            reasons.append(f"no {role.value}: the look needs one")
        if cap is not None and count > cap:
            reasons.append(f"{count} {role.value} items: only {cap} fits the look")

    unready = [i.item_id for i in items if not is_ready(i)]
    if unready:
        reasons.append(f"not ready to style: {', '.join(sorted(unready))}")

    uncategorised = [i.item_id for i in items if is_ready(i) and role_of(i) is None]
    if uncategorised:
        reasons.append(f"no category extracted: {', '.join(sorted(uncategorised))}")

    return reasons


def is_valid_combination(
    items: Sequence[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
) -> bool:
    return not conflicts(items, required)


def name_gaps(
    items: Iterable[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
) -> list[WardrobeGap]:
    """AI-EVAL-CASES Case 12 — say what is missing instead of inventing it.

    `unlocks_outfits` is the number of complete looks that become possible once that one
    role is filled: the product of the counts of every *other* required role. When another
    role is also empty that product is zero, and it is reported as zero. Rounding it up to
    make the suggestion feel more useful would be exactly the invented urgency this product
    is meant not to have.
    """
    grouped = group_by_role(items)
    gaps: list[WardrobeGap] = []

    for role in ROLE_ORDER:
        if role not in required or grouped.get(role):
            continue
        unlocks = 1
        for other in required:
            if other == role:
                continue
            unlocks *= len(grouped.get(other, []))
        gaps.append(
            WardrobeGap(
                category=role,
                generic_description=GAP_DESCRIPTIONS[role],
                unlocks_outfits=unlocks,
            )
        )
    return gaps


def can_compose(
    items: Iterable[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
) -> bool:
    """Whether a complete outfit exists in this wardrobe at all."""
    return not missing_roles(items, required)


__all__ = [
    "ADDITIVE_ROLES",
    "CORE_ROLES",
    "GAP_DESCRIPTIONS",
    "MAX_PER_ROLE",
    "ROLE_ORDER",
    "can_compose",
    "conflicts",
    "group_by_role",
    "is_ready",
    "is_valid_combination",
    "missing_roles",
    "name_gaps",
    "role_of",
]
