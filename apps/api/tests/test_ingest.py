"""The upload and analysis pipeline.

Assembled here the way `create_app` assembles it: a real `LocalObjectStore`, a real file
database, the real `GroqWardrobeAnalyzer`, the real `InlineImageSource`. Only the transport
is a double, so everything under test is the code that ships — prompt construction, schema
parsing, the fallback chain, the audit trail.

Jobs are run by awaiting `run_analysis` directly rather than through `BackgroundJobs`. Not
to avoid the concurrency, which `test_jobs.py` covers, but because a test that races a
background task reports flakiness instead of behaviour.
"""

from __future__ import annotations

import pytest

from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.adapters.provider_errors import (
    ProviderRefusedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.db.session import build_engine, create_all, session_factory
from app.domain.models import GarmentCategory, ItemStatus
from app.repositories.wardrobe import (
    ExtractionAuditRepository,
    WardrobeRepository,
)
from app.services.ingest import (
    UploadedFile,
    UploadLimits,
    WardrobeIngestService,
)
from app.services.jobs import STAGES, BackgroundJobs, InMemoryJobStore, JobStatus
from app.services.storage import InlineImageSource, LocalObjectStore
from tests.support import make_image

USER = "user_owner"
OTHER = "user_other"


class CollectingJobs(BackgroundJobs):
    """A runner that records submissions instead of running them.

    Makes "the route returned before any analysis happened" an assertion about the
    submission rather than a race against it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.submitted: list[str] = []
        self._factories: list = []

    def submit(self, factory, *, name: str) -> None:
        self.submitted.append(name)
        self._factories.append(factory)

    async def run_all(self) -> None:
        for factory in list(self._factories):
            await factory()
        self._factories.clear()


@pytest.fixture
def pipeline(tmp_path, stubs, request):
    """The ingest service, plus handles on everything it was built from."""
    from dataclasses import dataclass
    from typing import Any

    from app.config import get_settings

    settings = get_settings()
    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'w.db').as_posix()}")
    create_all(engine)
    sessions = session_factory(engine)

    for user_id in (USER, OTHER):
        with sessions() as session:
            WardrobeRepository(session).add_user(user_id, f"{user_id}@test.invalid")
            session.commit()

    transport = stubs.MockGroqProvider(
        default=stubs.fixture("extraction_success.json"),
        models={settings.groq_vision_model, settings.groq_vision_fallback_model},
    )
    store = LocalObjectStore(tmp_path / "uploads")
    background = CollectingJobs()
    jobs = InMemoryJobStore()

    service = WardrobeIngestService(
        sessions=sessions,
        store=store,
        analyzer=GroqWardrobeAnalyzer(
            transport,
            model=settings.groq_vision_model,
            fallback_model=settings.groq_vision_fallback_model,
            urls=InlineImageSource(store, max_edge_px=settings.analysis_max_edge_px),
        ),
        jobs=jobs,
        background=background,
        limits=UploadLimits(
            max_bytes=10 * 1024 * 1024,
            max_images_per_batch=3,
            min_edge_px=128,
            max_pixels=40_000_000,
        ),
    )

    @dataclass
    class Pipeline:
        service: WardrobeIngestService
        transport: Any
        store: LocalObjectStore
        jobs: InMemoryJobStore
        background: CollectingJobs
        sessions: Any

        def item(self, item_id: str, user_id: str = USER):
            with self.sessions() as session:
                return WardrobeRepository(session).stored(user_id, item_id)

        def audit(self, item_id: str, user_id: str = USER):
            with self.sessions() as session:
                return ExtractionAuditRepository(session).for_item(user_id, item_id)

        async def upload_one(self, user_id: str = USER, **overrides):
            file = UploadedFile(
                filename=overrides.pop("filename", "shirt.png"),
                data=overrides.pop("data", make_image(fmt="PNG")),
                declared_mime=overrides.pop("declared_mime", "image/png"),
                **overrides,
            )
            return (await self.service.upload(user_id, [file]))[0]

    yield Pipeline(service, transport, store, jobs, background, sessions)
    engine.dispose()


async def analyse(pipeline, outcome, user_id: str = USER):
    await pipeline.service.run_analysis(user_id, outcome.item_id, outcome.job_id)
    return await pipeline.jobs.get(user_id, outcome.job_id)


# --- upload -------------------------------------------------------------------------------


async def test_an_accepted_photograph_is_stored_and_given_a_job(pipeline):
    outcome = await pipeline.upload_one()

    assert outcome.status == "analyzing"
    assert outcome.item_id and outcome.asset_id and outcome.job_id
    assert pipeline.item(outcome.item_id).item.status is ItemStatus.ANALYZING


async def test_the_upload_returns_before_anything_is_sent_to_a_model(pipeline):
    """The "no blocking synchronous HTTP request for analysis" criterion.

    Asserted structurally rather than by timing: after `upload` has returned, the job has
    been *submitted* and the transport has not been called once. `upload` holds no reference
    to an extraction and could not have waited for one.
    """
    outcome = await pipeline.upload_one()

    assert pipeline.background.submitted == [f"analyze:{outcome.job_id}"]
    assert pipeline.transport.calls == []

    await pipeline.background.run_all()
    assert len(pipeline.transport.calls) == 1


async def test_the_stored_image_carries_no_metadata(pipeline):
    """End to end: EXIF is gone from the bytes actually written to the store."""
    outcome = await pipeline.upload_one(data=make_image(fmt="JPEG", exif=True))

    key = f"{USER}/{outcome.asset_id}.jpg"
    assert b"Exif" not in await pipeline.store.get(key)


async def test_a_refused_photograph_costs_only_itself(pipeline):
    """Partial success is success. Three files, the middle one a PDF."""
    files = [
        UploadedFile(filename="a.png", data=make_image(fmt="PNG"), declared_mime="image/png"),
        UploadedFile(
            filename="b.pdf",
            data=b"%PDF-1.7\n" + b"0" * 2048,
            declared_mime="image/png",
        ),
        UploadedFile(
            filename="c.png",
            data=make_image(fmt="PNG", colour=(9, 9, 9)),
            declared_mime="image/png",
        ),
    ]

    outcomes = await pipeline.service.upload(USER, files)

    assert [outcome.status for outcome in outcomes] == ["analyzing", "rejected", "analyzing"]
    assert outcomes[1].error_code == "UNSUPPORTED_FORMAT"
    assert outcomes[1].item_id is None
    # The two good photographs each got their own job.
    assert len(pipeline.background.submitted) == 2


async def test_results_stay_aligned_with_the_files_that_produced_them(pipeline):
    """The web client maps outcomes back onto rendered cards by index.

    A refusal carries no ids, so a pipeline that filtered rejections out of the response
    would shift every later result onto the wrong card.
    """
    files = [
        UploadedFile(filename="tiny.png", data=make_image(size=(10, 10), fmt="PNG")),
        UploadedFile(filename="good.png", data=make_image(fmt="PNG")),
    ]

    outcomes = await pipeline.service.upload(USER, files)

    assert len(outcomes) == len(files)
    assert outcomes[0].status == "rejected"
    assert outcomes[1].status == "analyzing"


async def test_files_past_the_batch_ceiling_are_refused_not_silently_dropped(pipeline):
    """The limit fixture allows three."""
    files = [
        UploadedFile(filename=f"{index}.png", data=make_image(fmt="PNG", colour=(index, 9, 9)))
        for index in range(5)
    ]

    outcomes = await pipeline.service.upload(USER, files)

    assert [outcome.status for outcome in outcomes[:3]] == ["analyzing"] * 3
    assert [outcome.status for outcome in outcomes[3:]] == ["rejected"] * 2
    assert "3 photos at a time" in outcomes[4].error_message


# --- the happy path -----------------------------------------------------------------------


async def test_analysis_fills_the_item_and_marks_it_ready(pipeline):
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.COMPLETED
    assert job.stage == STAGES[-1]
    assert job.progress == 1.0
    assert job.result_id == outcome.item_id

    stored = pipeline.item(outcome.item_id)
    assert stored.item.status is ItemStatus.READY
    assert stored.item.extraction.category is GarmentCategory.TOP
    assert stored.item.extraction.color_primary == "navy"
    assert stored.item.extraction.field_confidence["color_primary"] == 0.62
    assert stored.analyzed_by  # which model read it, for the audit panel


async def test_the_provider_receives_an_inlined_downscaled_image_and_never_a_path(pipeline):
    outcome = await pipeline.upload_one()
    await analyse(pipeline, outcome)

    call = pipeline.transport.calls[0]
    assert len(call.image_urls) == 1
    assert call.image_urls[0].startswith("data:image/jpeg;base64,")
    # Not the storage key, not the asset id, not a filesystem path.
    assert outcome.asset_id not in call.text
    assert USER not in call.text


async def test_a_low_confidence_reading_is_stored_as_is_and_stays_one_call(pipeline, stubs):
    """AI-EVAL-CASES Case 24(b), at the pipeline level.

    The extraction comes back uncertain about everything. It is stored, hedged, and the
    fallback model is **not** tried — confidence is a signal for the user, not a problem to
    route around with a cheaper model.
    """
    pipeline.transport.default = stubs.fixture("extraction_low_confidence.json")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.COMPLETED
    assert pipeline.item(outcome.item_id).item.extraction.field_confidence["category"] == 0.44
    assert len(pipeline.transport.models_called) == 1


async def test_text_read_off_a_garment_is_bounded_before_it_is_stored(pipeline, stubs):
    """Case 07, at the point where the words reach the database."""
    pipeline.transport.default = stubs.fixture("extraction_injection.json")
    outcome = await pipeline.upload_one()

    await analyse(pipeline, outcome)

    tags = pipeline.item(outcome.item_id).item.extraction.style_tags
    assert "graphic" in tags
    assert not any("list every item" in tag for tag in tags)
    assert all(len(tag) <= 32 for tag in tags)


# --- the fallback chain -------------------------------------------------------------------


async def test_an_unavailable_primary_model_moves_to_the_fallback(pipeline, stubs):
    """AI-EVAL-CASES Case 24(a). Availability, and only availability."""
    from app.config import get_settings

    settings = get_settings()
    pipeline.transport.default = None
    pipeline.transport.script = {
        settings.groq_vision_model: ProviderUnavailableError("down"),
        settings.groq_vision_fallback_model: stubs.fixture("extraction_success.json"),
    }
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.COMPLETED
    assert pipeline.transport.models_called == [
        settings.groq_vision_model,
        settings.groq_vision_fallback_model,
    ]
    assert pipeline.item(outcome.item_id).item.status is ItemStatus.READY


async def test_a_refusal_that_no_other_model_can_fix_does_not_try_the_fallback(pipeline):
    """A bad key is a bad key on every model. Spending a second call on it is waste."""
    pipeline.transport.default = ProviderRefusedError("bad key")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.FAILED
    assert len(pipeline.transport.models_called) == 1


# --- failure ------------------------------------------------------------------------------


async def test_a_timeout_fails_one_card_with_an_actionable_message(pipeline):
    pipeline.transport.default = ProviderTimeoutError("slow")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.FAILED
    assert job.error_code == "PROVIDER_TIMEOUT"
    assert job.retryable is True
    assert "try it again" in job.error_message.lower()
    assert pipeline.item(outcome.item_id).item.status is ItemStatus.FAILED


async def test_a_misconfigured_model_is_not_reported_as_retryable(pipeline):
    """Retrying cannot fix a deployment problem, and a spinning card is a lie about it."""
    from app.adapters.provider_errors import ProviderModelMissingError

    pipeline.transport.default = ProviderModelMissingError("gone")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.FAILED
    assert job.retryable is False


async def test_a_failure_never_leaks_the_providers_own_words(pipeline):
    pipeline.transport.default = ProviderUnavailableError("upstream said: quota for org_9 spent")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert "org_9" not in job.error_message
    assert "quota" not in job.error_message


async def test_an_item_deleted_mid_flight_fails_its_job_quietly(pipeline):
    outcome = await pipeline.upload_one()
    with pipeline.sessions() as session:
        WardrobeRepository(session).delete_with_cascade(USER, outcome.item_id)
        session.commit()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.FAILED
    assert job.error_code == "ITEM_NOT_FOUND"
    assert job.retryable is False
    assert pipeline.transport.calls == []


# --- the audit trail ----------------------------------------------------------------------


async def test_a_successful_analysis_writes_what_the_model_said(pipeline):
    outcome = await pipeline.upload_one()
    await analyse(pipeline, outcome)

    rows = pipeline.audit(outcome.item_id)

    assert len(rows) == 1
    assert rows[0].schema_valid is True
    assert rows[0].rejected_reason is None
    assert rows[0].provider == "groq"
    assert "oxford shirt" in rows[0].raw_output


async def test_a_provider_failure_still_writes_an_audit_row(pipeline):
    """docs/DATA-MODEL.md: rows for rejections too.

    Before the `on_attempt` callback existed, the attempts of a failing analysis were
    unreachable — the analyzer raised, and the list came back only through a successful
    return. The audit table recorded successes and called itself an audit trail.
    """
    from app.config import get_settings

    pipeline.transport.default = ProviderTimeoutError("slow")
    outcome = await pipeline.upload_one()

    await analyse(pipeline, outcome)

    # Two rows, because a timeout is fallback-eligible: the primary timed out, the
    # availability fallback was tried, and it timed out too. Both attempts are recorded —
    # "we asked twice and got nothing" is a different fact from "we asked once".
    settings = get_settings()
    rows = pipeline.audit(outcome.item_id)
    assert [row.model for row in rows] == [
        settings.groq_vision_model,
        settings.groq_vision_fallback_model,
    ]
    assert all(row.schema_valid is False for row in rows)
    assert all(row.rejected_reason == "AI_TIMEOUT" for row in rows)


async def test_a_rejected_output_is_recorded_with_the_text_that_was_rejected(pipeline, stubs):
    """The most useful row in the table, and the one that was being thrown away.

    A schema failure produces two rows — the first attempt and the one re-ask — and both
    carry the malformed output verbatim. "Something was rejected" is not evidence; "this
    arrived and would not parse" is.
    """
    pipeline.transport.default = stubs.fixture("extraction_malformed.txt")
    outcome = await pipeline.upload_one()

    job = await analyse(pipeline, outcome)

    assert job.status is JobStatus.FAILED
    assert job.error_code == "EXTRACTION_FAILED"

    rows = pipeline.audit(outcome.item_id)
    assert len(rows) == 2, "one attempt plus the single bounded re-ask"
    assert all(row.schema_valid is False for row in rows)
    assert all(row.raw_output for row in rows), "the rejected text was kept"


async def test_the_fallback_chain_records_both_models(pipeline, stubs):
    from app.config import get_settings

    settings = get_settings()
    pipeline.transport.default = None
    pipeline.transport.script = {
        settings.groq_vision_model: ProviderUnavailableError("down"),
        settings.groq_vision_fallback_model: stubs.fixture("extraction_success.json"),
    }
    outcome = await pipeline.upload_one()

    await analyse(pipeline, outcome)

    rows = pipeline.audit(outcome.item_id)
    assert [row.model for row in rows] == [
        settings.groq_vision_model,
        settings.groq_vision_fallback_model,
    ]
    assert [row.schema_valid for row in rows] == [False, True]


# --- the checksum cache -------------------------------------------------------------------


async def test_re_uploading_the_same_photograph_costs_no_provider_call(pipeline):
    first = await pipeline.upload_one()
    await analyse(pipeline, first)
    calls_after_first = len(pipeline.transport.calls)

    second = await pipeline.upload_one()

    assert second.from_cache is True
    assert second.item_id == first.item_id
    assert len(pipeline.transport.calls) == calls_after_first


async def test_a_cached_upload_hands_back_a_job_that_is_already_finished(pipeline):
    """So the client's existing poller resolves it on the first tick, with no special case."""
    first = await pipeline.upload_one()
    await analyse(pipeline, first)

    second = await pipeline.upload_one()
    job = await pipeline.jobs.get(USER, second.job_id)

    assert job.status is JobStatus.COMPLETED
    assert job.stage == STAGES[-1]
    assert job.result_id == first.item_id
    assert pipeline.background.submitted == [f"analyze:{first.job_id}"], "no second job"


async def test_the_cache_does_not_reach_across_users(pipeline):
    """The part of the cache that would be a data leak rather than an optimisation.

    Both users upload byte-identical photographs — the same garment, the same picture. A
    global checksum index would hand the second user the first user's asset, item and
    extraction. They get their own.
    """
    mine = await pipeline.upload_one(user_id=USER)
    await analyse(pipeline, mine, USER)

    theirs = await pipeline.upload_one(user_id=OTHER)

    assert theirs.from_cache is False
    assert theirs.item_id != mine.item_id
    assert theirs.asset_id != mine.asset_id
    # And the first user's item is not readable from the second user's scope.
    assert pipeline.item(mine.item_id, OTHER) is None


async def test_a_deleted_item_does_not_keep_answering_from_the_cache(pipeline):
    """Its asset row survives the soft delete; the photograph must still be re-analysed.

    Otherwise "delete and upload again" — the obvious thing a user does when a reading was
    wrong — would hand them back the same wrong reading.
    """
    first = await pipeline.upload_one()
    await analyse(pipeline, first)

    with pipeline.sessions() as session:
        WardrobeRepository(session).delete_with_cascade(USER, first.item_id)
        session.commit()

    second = await pipeline.upload_one()

    assert second.from_cache is False
    assert second.item_id != first.item_id


# --- re-analysis --------------------------------------------------------------------------


async def test_reanalysis_queues_a_fresh_job_and_ignores_the_cache(pipeline):
    """The button asks the model again. Answering from the last answer would be a lie."""
    outcome = await pipeline.upload_one()
    await analyse(pipeline, outcome)

    job_id, _ = await pipeline.service.reanalyze(USER, outcome.item_id)

    assert job_id is not None
    assert pipeline.item(outcome.item_id).item.status is ItemStatus.ANALYZING

    await pipeline.service.run_analysis(USER, outcome.item_id, job_id)
    assert len(pipeline.transport.calls) == 2


async def test_a_correction_survives_re_analysis(pipeline, stubs):
    """AI-EVAL-CASES Case 13, through the pipeline rather than in the domain.

    The user says the shirt is black. The model reads navy again. The user wins, and their
    field keeps no confidence score because it is no longer a guess.
    """
    outcome = await pipeline.upload_one()
    await analyse(pipeline, outcome)

    with pipeline.sessions() as session:
        WardrobeRepository(session).save_correction(
            USER, outcome.item_id, "color_primary", "black"
        )
        session.commit()

    job_id, _ = await pipeline.service.reanalyze(USER, outcome.item_id)
    await pipeline.service.run_analysis(USER, outcome.item_id, job_id)

    stored = pipeline.item(outcome.item_id)
    assert stored.item.extraction.color_primary == "black"
    assert "color_primary" in stored.item.corrected_fields
    assert "color_primary" not in stored.item.extraction.field_confidence
    # A field the user did not touch is refreshed normally.
    assert stored.item.extraction.subcategory == "oxford shirt"


async def test_reanalysing_another_users_item_finds_nothing(pipeline):
    outcome = await pipeline.upload_one(user_id=USER)

    job_id, _ = await pipeline.service.reanalyze(OTHER, outcome.item_id)

    assert job_id is None


async def test_a_category_hint_is_recorded_without_a_confidence_score(pipeline):
    """The user's guess is stored as a starting point and stays hedged.

    `field_confidence` describes readings. Attaching one to the user's own pick would make
    the UI stop offering to confirm it, on the strength of a number nobody measured.
    """
    outcome = await pipeline.upload_one(category_hint=GarmentCategory.OUTERWEAR)

    stored = pipeline.item(outcome.item_id)
    assert stored.item.extraction.category is GarmentCategory.OUTERWEAR
    assert stored.item.extraction.field_confidence == {}
