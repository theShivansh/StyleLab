"""Domain invariants.

These guard product rules, not framework plumbing. A foundation suite that only proves
"Pydantic validates" proves nothing worth gating on.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.models import (
    GarmentCategory,
    GarmentExtraction,
    OutfitAdvice,
    TrendNote,
    WardrobeGap,
)


def test_trend_note_requires_attribution():
    """AI-EVAL-CASES Case 15: an unattributed trend claim is dropped, never rendered."""
    with pytest.raises(ValidationError):
        TrendNote(trend="Wide legs are back", source="", published_at=date(2026, 7, 14))
    with pytest.raises(ValidationError):
        TrendNote(trend="Wide legs are back")  # type: ignore[call-arg]


def test_trend_note_accepts_a_sourced_dated_claim():
    note = TrendNote(
        trend="Relaxed tailoring holding through AW26",
        source="example-publication",
        published_at=date(2026, 7, 14),
    )
    assert note.published_at.year == 2026


def test_advice_has_no_commerce_fields():
    """The product sells nothing. If a price or merchant field is added to the domain,
    this fails and forces the conversation."""
    fields = set(OutfitAdvice.model_fields) | set(WardrobeGap.model_fields)
    for banned in {"price", "brand", "commerce_url", "merchant", "buy_url", "currency"}:
        assert banned not in fields


def test_wardrobe_gap_is_generic_only():
    gap = WardrobeGap(
        category=GarmentCategory.FOOTWEAR,
        generic_description="a white leather sneaker",
        unlocks_outfits=5,
    )
    assert "generic_description" in gap.model_dump()


def test_models_reject_unknown_fields():
    """extra='forbid': an adapter returning a field the domain does not know about is a
    contract breach, and must fail loudly rather than be silently dropped."""
    with pytest.raises(ValidationError):
        GarmentExtraction(category=GarmentCategory.TOP, price=4999)  # type: ignore[call-arg]


def test_advice_defaults_to_a_full_crew_run():
    assert OutfitAdvice().degradation_level == 1


def test_empty_advice_with_a_named_gap_is_valid():
    """USER-FLOWS Flow 5: naming the gap is a complete answer, not an error."""
    advice = OutfitAdvice(outfit=None, missing_roles=[GarmentCategory.FOOTWEAR])
    assert advice.outfit is None
    assert advice.missing_roles == [GarmentCategory.FOOTWEAR]
