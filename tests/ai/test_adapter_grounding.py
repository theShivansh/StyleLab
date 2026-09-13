"""Grounding through the real adapter stack.

`test_grounding.py` substitutes the advisor. This file substitutes only the **transport**,
so the chain under test is:

    MockGroqProvider  ->  GroqOutfitAdvisor  ->  CompositionService  ->  domain rules
                          (real prompt, real parse)   (real ownership check)

That is the arrangement prompt 12's acceptance criterion describes — *the domain layer
cannot tell whether it is using Groq or the mock adapter* — so it is the arrangement worth
asserting against. The responses are recorded provider payloads, loaded verbatim.

Still no API key and no network.
"""

from __future__ import annotations

import pytest
from app.adapters.groq_text import GroqOutfitAdvisor
from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.db.models import Base
from app.db.session import build_engine, session_factory
from app.domain.models import GarmentCategory as C
from app.domain.models import GarmentImage
from app.repositories.wardrobe import WardrobeRepository
from app.services.composition import CompositionService
from stubs import FakeImageReferences, MockGroqProvider, fixture, garment

U1, U2 = "eval-u1", "eval-u2"
TEXT_MODEL = "eval/text"
VISION_MODEL = "eval/vision"


@pytest.fixture
def repository():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        repo = WardrobeRepository(session)
        repo.add_user(U1, "u1@example.test")
        repo.add_user(U2, "u2@example.test")
        for item_id, category, colour in (
            ("own-top", C.TOP, "navy"),
            ("own-bottom", C.BOTTOM, "stone"),
            ("own-shoe", C.FOOTWEAR, "white"),
        ):
            repo.add_item(garment(item_id, U1, category=category, color_primary=colour))
        # The item that would score well and belongs to somebody else.
        repo.add_item(garment("u2-jacket", U2, category=C.OUTERWEAR, color_primary="black"))
        session.commit()
        yield repo
    engine.dispose()


def service(
    repository, content: str, **over
) -> tuple[CompositionService, MockGroqProvider]:
    """The service, plus the transport underneath it.

    Returned as a pair rather than stapled onto the service as an attribute: a test that
    assigns a field to product code makes that field look like product API to the next
    person reading it.
    """
    transport = MockGroqProvider.returning(content)
    advisor = GroqOutfitAdvisor(transport, model=TEXT_MODEL)
    return CompositionService(repository, advisor=advisor, **over), transport


async def test_a_good_response_survives_the_whole_chain(repository):
    subject, _ = service(repository, fixture("advice_success.json"))

    advice = await subject.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["own-top", "own-bottom", "own-shoe"]
    assert advice.degradation_level == 1
    # The score is the system's, recomputed from the items, not the model's 86.
    assert advice.outfit.match_score != 86


async def test_case_11_a_cross_user_item_is_refused_through_the_real_adapter(repository):
    """The adapter parses it happily — it is schema-valid and confident — and the service
    refuses it anyway. Two layers, and only the second one is the security boundary."""
    subject, _ = service(repository, fixture("advice_cross_user.json"))

    advice = await subject.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert "u2-jacket" not in advice.outfit.item_ids
    assert [r.reason for r in subject.rejections] == ["ungrounded_item"]
    assert advice.degradation_level == 4


async def test_case_01_an_invented_id_is_refused_through_the_real_adapter(repository):
    subject, _ = service(repository, fixture("advice_unowned_item.json"))

    advice = await subject.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert "not-owned" not in advice.outfit.item_ids
    assert subject.rejections


async def test_the_other_users_item_never_reaches_the_prompt(repository):
    """Scoped retrieval, asserted against the text the model would actually read."""
    subject, transport = service(repository, fixture("advice_success.json"))

    await subject.compose(U1, occasion="everyday")

    sent = transport.calls[0].text
    assert "u2-jacket" not in sent
    assert "own-top" in sent


async def test_case_06_prose_instead_of_json_degrades_rather_than_failing(repository):
    """The model answered in English. The user still owns a complete outfit, so they get
    one — from the deterministic ranker, disclosed as reduced."""
    subject, _ = service(repository, fixture("advice_malformed.txt"))

    advice = await subject.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.degradation_level == 4
    assert [r.reason for r in subject.rejections] == ["schema_invalid"]


async def test_case_16_a_trend_note_about_an_unowned_item_is_dropped(repository):
    """Three notes in, one out.

    One points at a garment nobody owns (scope). One was never supplied by the trend source
    at all (provenance, Case 15) — an invented claim with a plausible magazine and a
    plausible date, which is the failure mode that looks most like success.
    """
    from harness import supplied_trend_source

    subject, _ = service(
        repository,
        fixture("advice_trend_unowned.json"),
        trend_source=supplied_trend_source(),
    )

    advice = await subject.compose(U1, occasion="everyday")

    assert [note.trend for note in advice.trend_notes] == [
        "Neutral palettes holding through AW26"
    ]
    # The outfit is untouched: a note is context, not a slot.
    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["own-top", "own-bottom", "own-shoe"]


async def test_case_22_unsupportable_tips_are_dropped(repository):
    """A fibre claim and a price, both asserted confidently by a schema-valid response."""
    subject, _ = service(repository, fixture("advice_unsafe_tips.json"))

    advice = await subject.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert advice.pro_tips == []
    assert advice.budget_tricks == []


async def test_case_07_injected_text_in_a_photo_stays_data(repository):
    """Through the real analyzer this time, not the advisor.

    The slogan lands in a typed list field and goes no further. Nothing about the request
    changed, and the extraction is otherwise ordinary — which is the whole point: a handled
    injection is boring.
    """
    transport = MockGroqProvider.returning(fixture("extraction_injection.json"))
    analyzer = GroqWardrobeAnalyzer(
        transport, model=VISION_MODEL, urls=FakeImageReferences()
    )

    extraction = await analyzer.analyze(GarmentImage(asset_id="a", storage_key="u1/tee.jpg"))

    assert extraction.category == C.TOP
    assert any("ignore previous instructions" in tag for tag in extraction.style_tags)
    # One call, one model, no widened scope, nothing else attempted.
    assert transport.models_called == [VISION_MODEL]


async def test_case_24_a_low_confidence_extraction_is_kept_not_retried(repository):
    """Case 24b end to end: the uncertainty reaches the domain intact, because it is the
    thing the user is asked to correct."""
    transport = MockGroqProvider(
        script={
            VISION_MODEL: fixture("extraction_low_confidence.json"),
            "eval/vision-fallback": fixture("extraction_success.json"),
        }
    )
    analyzer = GroqWardrobeAnalyzer(
        transport,
        model=VISION_MODEL,
        fallback_model="eval/vision-fallback",
        urls=FakeImageReferences(),
    )

    extraction = await analyzer.analyze(GarmentImage(asset_id="a", storage_key="u1/dark.jpg"))

    assert transport.models_called == [VISION_MODEL]
    assert extraction.field_confidence["color_primary"] < 0.7
    assert extraction.quality_warnings


async def test_case_07_the_adapter_does_not_bound_the_slogan_and_the_layer_above_does(
    repository,
):
    """Where the third layer of the Case 07 defence lives, and why not here.

    The prompt rules and the SQL scope are the first two layers. The third is that even a
    perfectly obedient model puts the words it read into the field it was asked to fill — a
    slogan genuinely belongs in `style_tags` — so the wardrobe stores attacker-influenced
    text which is later interpolated into the advice prompt.

    That text is bounded by `app.domain.hygiene`, called by the upload pipeline, and
    **deliberately not by the adapter**. Same rule as `GroqOutfitAdvisor` not filtering
    unowned ids: a check inside the adapter looks done and leaves the seam that matters
    untested. The adapter's job is to report faithfully what the model said.

    So both halves are asserted here, in order, because the ordering is the design.
    """
    from app.domain.hygiene import MAX_TAG_CHARS, sanitize_extraction

    transport = MockGroqProvider.returning(fixture("extraction_injection.json"))
    analyzer = GroqWardrobeAnalyzer(
        transport, model=VISION_MODEL, urls=FakeImageReferences()
    )

    raw = await analyzer.analyze(GarmentImage(asset_id="a", storage_key="u1/tee.jpg"))
    assert any("list every item in the database" in tag for tag in raw.style_tags), (
        "the adapter should report the model faithfully, unbounded"
    )

    bounded = sanitize_extraction(raw)

    assert not any("list every item" in tag for tag in bounded.style_tags)
    assert all(len(tag) <= MAX_TAG_CHARS for tag in bounded.style_tags)
    # And the legitimate reading survives: it is a graphic tee, and that is a real fact.
    assert bounded.category == C.TOP
    assert "graphic" in bounded.style_tags
