"""Stub adapters and domain fixtures for the proof layer.

These satisfy the adapter Protocols in `app.adapters` structurally, without importing them
and without importing any vendor SDK. They exist so the eval suite can run the whole
grounding path with no API key and no network.

**They are test doubles, not a demo mode.** Nothing under `apps/api/app/` may import this
module; `apps/api/tests/test_query_scoping.py` enforces that. A running STYLELAB always
performs real inference (docs/AI-EVAL-CASES.md Case 25).

The important one is `ScriptedAdvisor`. It returns whatever a test hands it — including a
well-formed, confident response naming an item belonging to somebody else. That is the only
way to prove Case 11's second half: that ownership re-validation, not the prompt, is what
stops a forged response.
"""

from __future__ import annotations

from datetime import date

from app.domain.models import (
    AdviceRequest,
    Formality,
    GarmentCategory,
    GarmentExtraction,
    GarmentImage,
    ItemStatus,
    Outfit,
    OutfitAdvice,
    TrendNote,
    TrendQuery,
    WardrobeItem,
)

# --- domain fixtures ---------------------------------------------------------------------


def garment(
    item_id: str,
    user_id: str = "u1",
    *,
    category: GarmentCategory = GarmentCategory.TOP,
    subcategory: str | None = None,
    color_primary: str = "navy",
    color_secondary: str | None = None,
    pattern: str = "solid",
    material_guess: str | None = "cotton",
    fit: str = "regular",
    formality: Formality = Formality.SMART_CASUAL,
    style_tags: list[str] | None = None,
    season_tags: list[str] | None = None,
    occasion_tags: list[str] | None = None,
    field_confidence: dict[str, float] | None = None,
    quality_warnings: list[str] | None = None,
    status: ItemStatus = ItemStatus.READY,
    corrected_fields: list[str] | None = None,
) -> WardrobeItem:
    """A ready wardrobe item owned by `user_id`. Every field has a workable default so a
    test names only the attribute it is actually about."""
    return WardrobeItem(
        item_id=item_id,
        user_id=user_id,
        status=status,
        corrected_fields=corrected_fields or [],
        extraction=GarmentExtraction(
            category=category,
            subcategory=subcategory or category.value,
            color_primary=color_primary,
            color_secondary=color_secondary,
            pattern=pattern,
            material_guess=material_guess,
            fit=fit,
            formality=formality,
            style_tags=style_tags or ["minimal"],
            season_tags=season_tags or [],
            occasion_tags=occasion_tags or [],
            field_confidence=field_confidence or {"category": 0.96},
            quality_warnings=quality_warnings or [],
        ),
    )


def trend_note(trend: str = "Relaxed tailoring holding through AW26", **over: object) -> TrendNote:
    payload: dict[str, object] = {
        "trend": trend,
        "source": "example-publication",
        "published_at": date(2026, 7, 14),
    }
    payload.update(over)
    return TrendNote(**payload)  # type: ignore[arg-type]


# --- stub adapters -----------------------------------------------------------------------


class ScriptedAdvisor:
    """Returns a pre-set response, whatever it contains.

    Deliberately does no validation of its own. An advisor that policed its own output would
    make the service's ownership check untestable, and in production the advisor is the
    component we least want to trust.
    """

    def __init__(self, response: OutfitAdvice) -> None:
        self.response = response
        self.calls: list[AdviceRequest] = []

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        self.calls.append(request)
        return self.response

    @classmethod
    def naming(cls, *item_ids: str, name: str = "Scripted Look", confidence: float = 0.91):
        """An advisor that confidently returns exactly these ids."""
        return cls(
            OutfitAdvice(
                outfit=Outfit(
                    item_ids=list(item_ids), name=name, occasion="everyday", match_score=88
                ),
                rationale=["Scripted for a test."],
                confidence=confidence,
            )
        )


class FailingAdvisor:
    """Raises on every call, to drive the degradation ladder down to the ranker."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("provider unavailable")
        self.calls = 0

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        self.calls += 1
        raise self.error


class ScriptedAnalyzer:
    """Returns queued extractions in order, then repeats the last one."""

    def __init__(self, *extractions: GarmentExtraction) -> None:
        self.queue = list(extractions)
        self.seen: list[GarmentImage] = []

    async def analyze(self, image: GarmentImage) -> GarmentExtraction:
        self.seen.append(image)
        if len(self.queue) > 1:
            return self.queue.pop(0)
        return self.queue[0]


class StaticTrendSource:
    def __init__(self, *notes: TrendNote) -> None:
        self.notes = list(notes)

    async def current(self, query: TrendQuery) -> list[TrendNote]:
        return list(self.notes)


class UnavailableTrendSource:
    async def current(self, query: TrendQuery) -> list[TrendNote]:
        raise RuntimeError("trend corpus unavailable")


__all__ = [
    "FailingAdvisor",
    "ScriptedAdvisor",
    "ScriptedAnalyzer",
    "StaticTrendSource",
    "UnavailableTrendSource",
    "garment",
    "trend_note",
]
