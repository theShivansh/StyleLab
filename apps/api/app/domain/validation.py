"""Ownership re-validation — AI-EVAL-CASES Case 11, the second half.

This is the check that makes the grounding claim true rather than asserted. Retrieval is
scoped in SQL before the model is called; this runs after it returns, over the same
candidate set, and refuses anything the model added.

## Why it issues no query

Every comparison here is against `request.candidates`, in memory. Looking an unexpected id
up — even scoped to the requesting user — would put another user's id into a query, and
`docs/AI-SYSTEM.md` is explicit: such an id is "rejected, not fetched". Keeping validation
query-free means the isolation property can be asserted against the statements the engine
actually executed, which is what `tests/test_ownership.py` does.

## Why the error does not say whose item it was

It cannot, without reading outside the requesting user's scope. `UngroundedItemError` reports the
ids and the requesting user; attributing them is the alerting layer's job, which has
legitimate admin scope outside the request path. The rejection is identical either way —
an id we did not supply is refused whoever owns it.

## Outfits versus trend notes

An outfit slot naming an unowned id is a **hard rejection**: that garment would be put on
the user. A trend note referencing one is **dropped**: a note is context, not a slot, so it
cannot dress them in something they do not own — but it must not be shown implying they do
either (Case 16).
"""

from __future__ import annotations

from app.domain.compatibility import CORE_ROLES, conflicts
from app.domain.errors import IncompatibleOutfitError, UngroundedItemError
from app.domain.models import AdviceRequest, OutfitAdvice, WardrobeItem


def grounded_ids(request: AdviceRequest) -> set[str]:
    """The only item ids an advisor is permitted to name."""
    return {candidate.item_id for candidate in request.candidates}


def items_by_id(request: AdviceRequest) -> dict[str, WardrobeItem]:
    return {candidate.item_id: candidate for candidate in request.candidates}


def validate_advice(advice: OutfitAdvice, *, request: AdviceRequest) -> OutfitAdvice:
    """Run business, ownership and compatibility validation over a schema-valid response.

    Returns a cleaned response, or raises. Raising rather than silently repairing is
    deliberate for the outfit: a response that named something it should not have is not
    trustworthy in its other claims either, so the caller degrades to the deterministic
    ranker instead of serving a patched version of it.
    """
    allowed = grounded_ids(request)
    owned = items_by_id(request)
    required = tuple(request.required_roles or CORE_ROLES)

    if advice.outfit is not None:
        ungrounded = [item_id for item_id in advice.outfit.item_ids if item_id not in allowed]
        if ungrounded:
            raise UngroundedItemError(ungrounded, user_id=request.user_id)

        duplicates = len(advice.outfit.item_ids) != len(set(advice.outfit.item_ids))
        if duplicates:
            raise IncompatibleOutfitError(["the same garment appears twice in one look"])

        items = [owned[item_id] for item_id in advice.outfit.item_ids]
        reasons = conflicts(items, required)
        if reasons:
            raise IncompatibleOutfitError(reasons)

    # Trend notes are filtered, not fatal. See the module docstring.
    kept_notes = [
        note
        for note in advice.trend_notes
        if all(item_id in allowed for item_id in note.applies_to_items)
    ]

    # A gap the user has actually filled is stale advice, not a hard failure.
    filled = {item.extraction.category for item in request.candidates}
    kept_gaps = [gap for gap in advice.wardrobe_gaps if gap.category not in filled]

    return advice.model_copy(update={"trend_notes": kept_notes, "wardrobe_gaps": kept_gaps})


def validate_trend_notes(advice: OutfitAdvice, *, request: AdviceRequest) -> OutfitAdvice:
    """Drop notes referencing items outside the candidate set, without touching the outfit.

    Used on the swap path, which re-runs Architect and Editor only and so never rebuilds the
    outfit it is validating (docs/AGENT-SYSTEM.md cost controls).
    """
    allowed = grounded_ids(request)
    kept = [
        note
        for note in advice.trend_notes
        if all(item_id in allowed for item_id in note.applies_to_items)
    ]
    return advice.model_copy(update={"trend_notes": kept})


__all__ = ["grounded_ids", "items_by_id", "validate_advice", "validate_trend_notes"]
