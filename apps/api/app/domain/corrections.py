"""User corrections — AI-EVAL-CASES Case 13.

A guess must look like a guess, and once the user has settled a field it stops being a
guess. Two rules follow, and they are the whole module:

1. Correcting a field **drops its confidence score**. Confidence describes a model guess; a
   corrected field is no longer one, and leaving a score attached would make the UI hedge
   the user's own answer back at them.
2. Re-analysis **never overwrites a corrected field**. The fresh extraction may be better
   in every other respect and still lose on that one field.

The same rules are enforced on the client in `apps/web/src/lib/wardrobe-store.ts`. They are
enforced again here because the client is not a security boundary and re-analysis runs
server-side, where no store exists to defend the field.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.domain.errors import SchemaInvalidError
from app.domain.models import GarmentExtraction, WardrobeItem

#: Fields a user may set by hand.
#:
#: Deliberately excludes `field_confidence` and `quality_warnings`: those are model
#: telemetry, not content. A correction that could write them would corrupt the honesty
#: signal itself — a user could be shown "high confidence" on a value no model ever read.
CORRECTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "category",
        "subcategory",
        "color_primary",
        "color_secondary",
        "pattern",
        "material_guess",
        "fit",
        "formality",
        "season_tags",
        "occasion_tags",
        "style_tags",
    }
)

#: Fields that read as a guess whatever the confidence score says.
#:
#: The floor decides the hedge for everything else: a model that is sure about a colour has
#: usually seen the colour. Fibre content is different in kind — a photograph does not show
#: what a garment is made of, so a high score there is confidence about an inference, not
#: about an observation, and rendering it as settled fact is exactly what CLAUDE.md forbids
#: ("never state fibre or material content as fact") and what AI-EVAL-CASES Case 08 lists
#: under Fail.
#:
#: S8 found the product doing it: an extraction asserting "100% merino wool" at 0.99 cleared
#: the floor and rendered with no hedge at all.
#:
#: A user correction still settles it — they can read their own care label, which is the one
#: source that actually knows.
#:
#: Mirrored in `apps/web/src/lib/schemas/wardrobe.ts`, which is where the rule is *applied*,
#: since the API renders nothing. That mirroring is the same arrangement as the upload
#: limits and carries the same caveat: if a second renderer ever appears, this moves into
#: the item payload rather than being copied a third time.
ALWAYS_A_GUESS: frozenset[str] = frozenset({"material_guess"})


def apply_correction(item: WardrobeItem, field: str, value: object) -> WardrobeItem:
    """Set one field by hand, record it, and drop its confidence score.

    Validates through the extraction model, so a correction cannot put a value in the
    wardrobe that the extractor itself would have been refused for — an enum is still an
    enum when a human types it.
    """
    if field not in CORRECTABLE_FIELDS:
        raise SchemaInvalidError(f"correction: {field} is not a user-correctable field")

    extraction = item.extraction.model_dump()
    extraction[field] = value
    extraction["field_confidence"] = {
        name: score for name, score in item.extraction.field_confidence.items() if name != field
    }

    try:
        corrected = GarmentExtraction.model_validate(extraction)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(p) for p in d['loc'])}: {d['type']}" for d in error.errors()
        )
        raise SchemaInvalidError(f"correction: {details}") from error

    recorded = item.corrected_fields if field in item.corrected_fields else [
        *item.corrected_fields,
        field,
    ]
    return item.model_copy(update={"extraction": corrected, "corrected_fields": recorded})


def merge_extraction(item: WardrobeItem, fresh: GarmentExtraction) -> WardrobeItem:
    """Apply a new extraction over an item, leaving corrected fields alone.

    Everything the user has not touched takes the new reading, including a field that was
    previously absent. Corrected fields keep their value *and* keep their confidence score
    dropped — re-analysis must not be able to restore a score to a field the user settled.
    """
    if not item.corrected_fields:
        return item.model_copy(update={"extraction": fresh})

    merged = fresh.model_dump()
    previous = item.extraction.model_dump()

    for field in item.corrected_fields:
        if field in merged:
            merged[field] = previous[field]

    merged["field_confidence"] = {
        name: score
        for name, score in fresh.field_confidence.items()
        if name not in item.corrected_fields
    }

    return item.model_copy(update={"extraction": GarmentExtraction.model_validate(merged)})


__all__ = ["ALWAYS_A_GUESS", "CORRECTABLE_FIELDS", "apply_correction", "merge_extraction"]
