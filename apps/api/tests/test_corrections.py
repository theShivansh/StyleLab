"""AI-EVAL-CASES Case 13 — a user correction is never recomputed.

The same rule is already enforced on the client (apps/web/src/lib/wardrobe-store.ts). It is
enforced again here because the client is not a security boundary and a re-analysis job runs
server-side, where no store exists to defend the field.
"""

from __future__ import annotations

import pytest

from app.domain.corrections import CORRECTABLE_FIELDS, apply_correction, merge_extraction
from app.domain.errors import SchemaInvalidError
from app.domain.models import Formality, GarmentCategory, GarmentExtraction
from app.repositories.wardrobe import WardrobeRepository


@pytest.fixture
def g(stubs):
    return stubs.garment


def test_a_correction_applies_the_value_and_records_the_field(g):
    item = g("i", color_primary="black", field_confidence={"color_primary": 0.52})
    corrected = apply_correction(item, "color_primary", "navy")

    assert corrected.extraction.color_primary == "navy"
    assert corrected.corrected_fields == ["color_primary"]


def test_a_correction_drops_the_fields_confidence_score(g):
    """Confidence describes a model guess. A corrected field is no longer one, so leaving a
    score on it would make the UI hedge the user's own answer back at them."""
    item = g("i", field_confidence={"category": 0.97, "color_primary": 0.52})
    corrected = apply_correction(item, "color_primary", "navy")

    assert "color_primary" not in corrected.extraction.field_confidence
    assert corrected.extraction.field_confidence["category"] == 0.97


def test_correcting_the_same_field_twice_does_not_duplicate_it(g):
    item = apply_correction(g("i"), "color_primary", "navy")
    item = apply_correction(item, "color_primary", "indigo")

    assert item.extraction.color_primary == "indigo"
    assert item.corrected_fields == ["color_primary"]


def test_re_analysis_does_not_overwrite_a_corrected_field(g):
    """Case 13. The fresh extraction is better in every respect except this one field, and it
    still loses on that field."""
    item = apply_correction(
        g("i", color_primary="black", fit="regular"), "color_primary", "navy"
    )

    fresh = GarmentExtraction(
        category=GarmentCategory.TOP,
        subcategory="oxford shirt",
        color_primary="black",  # the model has made the same mistake again
        pattern="solid",
        material_guess="cotton poplin",
        fit="slim",
        formality=Formality.SMART_CASUAL,
        field_confidence={"color_primary": 0.93, "fit": 0.88},
    )
    merged = merge_extraction(item, fresh)

    assert merged.extraction.color_primary == "navy"
    assert "color_primary" not in merged.extraction.field_confidence
    # Everything the user did not touch does take the new reading.
    assert merged.extraction.fit == "slim"
    assert merged.extraction.subcategory == "oxford shirt"
    assert merged.corrected_fields == ["color_primary"]


def test_a_second_correction_survives_a_third_analysis(g):
    item = apply_correction(g("i"), "color_primary", "navy")
    item = apply_correction(item, "fit", "relaxed")

    fresh = GarmentExtraction(color_primary="black", fit="slim", category=GarmentCategory.TOP)
    merged = merge_extraction(merge_extraction(item, fresh), fresh)

    assert merged.extraction.color_primary == "navy"
    assert merged.extraction.fit == "relaxed"
    assert sorted(merged.corrected_fields) == ["color_primary", "fit"]


def test_an_uncorrectable_field_is_refused(g):
    """`field_confidence` and `quality_warnings` are model telemetry, not user-editable
    content. Letting a correction write them would corrupt the honesty signal itself."""
    for field in ("field_confidence", "quality_warnings"):
        assert field not in CORRECTABLE_FIELDS
        with pytest.raises(SchemaInvalidError):
            apply_correction(g("i"), field, "anything")


def test_an_unknown_field_is_refused(g):
    with pytest.raises(SchemaInvalidError):
        apply_correction(g("i"), "brand", "Acme")


def test_a_correction_to_an_enum_field_is_validated(g):
    with pytest.raises(SchemaInvalidError):
        apply_correction(g("i"), "category", "trousers-ish")

    corrected = apply_correction(g("i"), "category", "bottom")
    assert corrected.extraction.category == GarmentCategory.BOTTOM


def test_a_correction_persists_and_survives_a_stored_re_analysis(session, g):
    """The round trip, because the merge rule is worthless if the repository writes the
    fresh extraction over the top of it."""
    repo = WardrobeRepository(session)
    repo.add_user("u1", "one@example.test")
    repo.add_item(g("i", color_primary="black", field_confidence={"color_primary": 0.5}))
    session.commit()

    repo.save_correction("u1", "i", "color_primary", "navy")
    session.commit()

    repo.save_extraction(
        "u1",
        "i",
        GarmentExtraction(category=GarmentCategory.TOP, color_primary="black", fit="slim"),
    )
    session.commit()

    stored = repo.get("u1", "i")
    assert stored is not None
    assert stored.extraction.color_primary == "navy"
    assert stored.extraction.fit == "slim"
    assert stored.corrected_fields == ["color_primary"]


def test_a_correction_cannot_reach_another_users_item(session, g):
    repo = WardrobeRepository(session)
    repo.add_user("u1", "one@example.test")
    repo.add_user("u2", "two@example.test")
    repo.add_item(g("u2-item", "u2", color_primary="black"))
    session.commit()

    assert repo.save_correction("u1", "u2-item", "color_primary", "navy") is False

    stored = repo.get("u2", "u2-item")
    assert stored is not None
    assert stored.extraction.color_primary == "black"
