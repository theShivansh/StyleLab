"""One real extraction and one real composition.

Everything here is `smoke`-marked and billed. The question these answer is the one no mock
can: *does the live model actually satisfy the schema we send it?* Structured Outputs is a
provider feature with provider-specific quirks, and a schema that validates perfectly
against a fixture can still be refused or quietly ignored by a real model.

Kept to two calls. `tests/ai/` proves the logic for free on every push; this proves the
contract holds against the thing itself, on main, once.

The extraction test needs a real image. `data/` holds a few sample garment photographs for
exactly this purpose (`CLAUDE.md` — test fixtures only, no seed catalogue); when none is
present the test skips rather than inventing one, because a synthetic 1x1 pixel would prove
that the model can describe a grey square.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from app.adapters.groq_text import GroqOutfitAdvisor
from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.domain.models import (
    AdviceRequest,
    GarmentExtraction,
    GarmentImage,
    ItemStatus,
    WardrobeItem,
)
from app.domain.models import GarmentCategory as C
from capacity import skip_if_the_fallback_covered_capacity, tolerating_capacity

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "data" / "samples"
SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


class DataUrls:
    """Serves a local file as a data URL.

    The live suite has no object storage and no signing service, so the real
    `ImageReferenceSource` cannot be used here. A data URL keeps the image reference out of any
    log while still exercising the real analyzer against the real model — which is what this
    suite is for. Production passes a short-lived signed URL instead; that path is covered
    by `apps/api/tests/test_groq_adapter.py`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    async def provider_url(self, storage_key: str, *, ttl_s: int = 300) -> str:
        encoded = base64.b64encode(self.path.read_bytes()).decode("ascii")
        suffix = "jpeg" if self.path.suffix in {".jpg", ".jpeg"} else self.path.suffix.lstrip(".")
        return f"data:image/{suffix};base64,{encoded}"


def _sample() -> Path:
    if not SAMPLES.is_dir():
        pytest.skip(f"no sample garment photographs in {SAMPLES.relative_to(REPO_ROOT)}")
    for path in sorted(SAMPLES.iterdir()):
        if path.suffix.lower() in SUFFIXES:
            return path
    pytest.skip(f"no usable image in {SAMPLES.relative_to(REPO_ROOT)}")


@pytest.mark.smoke
async def test_a_real_extraction_satisfies_the_schema(transport, settings, paced):
    """The claim the whole product rests on: a real photo becomes structured data."""
    sample = _sample()
    analyzer = GroqWardrobeAnalyzer(
        transport,
        model=settings.groq_vision_model,
        fallback_model=settings.groq_vision_fallback_model,
        urls=DataUrls(sample),
    )

    with tolerating_capacity():
        outcome = await analyzer.analyze_with_audit(
            GarmentImage(asset_id="live", storage_key=sample.name)
        )

    assert outcome.extraction.category is not None
    # Per-field confidence is the honesty signal. A model returning none of it would pass
    # the schema and defeat the point of the extraction path.
    assert outcome.extraction.field_confidence, "no per-field confidence came back"
    assert all(0.0 <= score <= 1.0 for score in outcome.extraction.field_confidence.values())
    # And it should not have needed the availability fallback on a healthy day.
    skip_if_the_fallback_covered_capacity(outcome)
    assert outcome.used_fallback is False


@pytest.mark.smoke
async def test_the_closed_vocabularies_survive_a_real_photograph(transport, settings, paced):
    """S8 closed four list fields to an `enum` in the strict schema. Two questions only a
    real call answers, and they pull in opposite directions.

    First, does the provider *accept* it — a strict schema with an enum on array items is
    exactly the kind of thing that validates locally and comes back 400. Second, and less
    obvious: is the vocabulary wide enough that a real garment still gets described? A
    vocabulary the model cannot fit a real photograph into would pass every mock-backed test
    in `tests/ai/` and quietly return empty tags for every user, which is a worse outcome
    than the leak it was closing.

    So this asserts the model produced *something* in at least one list, and that everything
    it produced is in the vocabulary. Not a specific tag: which adjectives a photograph
    earns is the model's judgement, and pinning it would make this a flake.
    """
    from app.domain.vocabulary import OCCASION_TAGS, SEASON_TAGS, STYLE_TAGS

    sample = _sample()
    analyzer = GroqWardrobeAnalyzer(
        transport,
        model=settings.groq_vision_model,
        fallback_model=settings.groq_vision_fallback_model,
        urls=DataUrls(sample),
    )

    with tolerating_capacity():
        extraction = await analyzer.analyze(
            GarmentImage(asset_id="live", storage_key=sample.name)
        )

    produced = {
        "style_tags": (extraction.style_tags, STYLE_TAGS),
        "season_tags": (extraction.season_tags, SEASON_TAGS),
        "occasion_tags": (extraction.occasion_tags, OCCASION_TAGS),
    }
    for field, (values, vocabulary) in produced.items():
        assert set(values) <= vocabulary, f"{field} came back with {set(values) - vocabulary}"

    assert any(values for values, _ in produced.values()), (
        "every closed list came back empty — the vocabulary is too narrow for a real garment"
    )


@pytest.mark.smoke
async def test_a_real_composition_stays_inside_the_candidate_set(transport, settings):
    """Grounding, against the live model rather than a fixture.

    The candidates are constructed here rather than read from a database: this suite has no
    database, and the assertion is about what the *model* does with a candidate list.
    Ownership enforcement itself is proven in `tests/ai/test_grounding.py`.
    """
    candidates = [
        _item("live-top", C.TOP, "navy", "oxford shirt"),
        _item("live-bottom", C.BOTTOM, "stone", "chinos"),
        _item("live-shoe", C.FOOTWEAR, "white", "leather sneaker"),
        _item("live-jacket", C.OUTERWEAR, "olive", "chore jacket"),
    ]
    request = AdviceRequest(
        user_id="live",
        candidates=candidates,
        occasion="everyday",
        vibe="minimal",
        required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR],
    )

    advice = await GroqOutfitAdvisor(transport, model=settings.groq_text_model).advise(request)

    allowed = {item.item_id for item in candidates}
    assert advice.outfit is not None, "the live model returned no outfit for a full wardrobe"
    assert set(advice.outfit.item_ids) <= allowed, (
        f"live model named an id outside the candidate set: "
        f"{set(advice.outfit.item_ids) - allowed}"
    )
    assert advice.rationale, "an outfit with no reasoning is not the product"


def _item(item_id: str, category: C, colour: str, subcategory: str) -> WardrobeItem:
    return WardrobeItem(
        item_id=item_id,
        user_id="live",
        status=ItemStatus.READY,
        extraction=GarmentExtraction(
            category=category,
            subcategory=subcategory,
            color_primary=colour,
            pattern="solid",
            fit="regular",
            style_tags=["minimal"],
            field_confidence={"category": 0.95},
        ),
    )
