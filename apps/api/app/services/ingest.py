"""Upload and analysis — docs/ARCHITECTURE.md section 5.

    POST /wardrobe/items (n images)
    → validate each independently
    → store assets
    → enqueue analyze_item job per image
    → worker: vision adapter → schema → business validation
    → wardrobe_item (status ready, field_confidence set)
    → item_extractions row written either way, including rejections
    → client receives cards progressively

## One image is never allowed to cost another image anything

`upload` loops per file and catches per file. A refused photograph produces a `rejected`
outcome in its own slot and the loop continues; a photograph that fails *analysis* fails
its own job, minutes later, on its own card. Partial success is success (docs/API-SPEC.md),
and the only way to hold that line is to have no shared failure path — no batch
transaction, no batch job, no first-error-aborts.

The loop is also why `upload` returns a list positionally aligned with its input. The web
client maps results back onto the cards it already rendered by index, so a result for the
fourth file must be the fourth element even when it is a refusal carrying no ids.

## The upload response promises nothing about analysis

By the time `POST` returns, every accepted photograph has been validated, stripped, stored
and given a job — and not one has been sent to a model. That is the "no blocking
synchronous HTTP request for analysis" criterion, and it is structural: `upload` has no
reference to an extraction and cannot wait for one.

## The checksum cache

A re-uploaded photograph should cost nothing, so `upload` looks for a live asset with the
same checksum **belonging to the same user** and, finding one, hands back the existing item
with a job that is already `completed`. The poller resolves on its first tick and no model
is called.

The per-user scope is the part that matters. A global checksum index would be a
deduplication table across wardrobes: upload a photograph someone else had uploaded and you
would be handed their asset and their extraction. The cache is an optimisation; ownership
is not negotiable to get one.

## Where the retries are, and why there are not more

docs/05 asks for "error classification and bounded retry". Both exist, and neither is here:

  * **transient provider failures** — retried in the transport, three attempts with jittered
    backoff (`groq_transport.py`)
  * **schema failures** — re-asked once by the analyzer, same model (`groq_vision.py`)

This layer adds **no third retry**. Stacking one would multiply: three transport attempts
inside two analyzer attempts inside two job attempts is twelve calls for one photograph of
a shirt, most of them into a rate limit that is already refusing us. What this layer does
instead is classify the failure honestly and stop, leaving the retry to the person looking
at the card — `POST /wardrobe/items/{id}/reanalyze`, which they can press when they have
reason to think it will work.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.analysis import AnalysisAttempt, AuditingWardrobeAnalyzer
from app.domain.hygiene import sanitize_extraction
from app.domain.models import GarmentCategory, GarmentImage, ItemStatus
from app.repositories.wardrobe import (
    AssetRepository,
    ExtractionAuditRepository,
    StoredAsset,
    WardrobeRepository,
)
from app.services import images as image_service
from app.services.faults import Fault, classify
from app.services.jobs import (
    STAGES,
    BackgroundJobs,
    Job,
    JobStatus,
    JobStore,
    JobType,
    new_job_id,
)
from app.services.storage import ObjectStore, extension_for, storage_key
from app.services.telemetry import GenerationEvent, GenerationLog, Outcome

logger = logging.getLogger("stylelab.ingest")

#: The provider recorded against every audit row. One value because there is one provider;
#: it is a column rather than a constant in the row-writing code so that adding a second
#: provider does not require a migration to tell them apart.
PROVIDER = "groq"

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """One file as it arrived, before anything has been decided about it."""

    filename: str
    data: bytes
    declared_mime: str | None = None
    #: The user's own selection at pick time. A prior for the model, not a decision.
    category_hint: GarmentCategory | None = None


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    """What happened to one file. Aligned positionally with the request's files."""

    status: str
    item_id: str | None = None
    asset_id: str | None = None
    job_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    #: True when the checksum cache answered, so no provider call will happen. Not part of
    #: the wire contract — the client cannot act on it, and telemetry can.
    from_cache: bool = False

    @classmethod
    def rejected(cls, fault: Fault) -> UploadOutcome:
        return cls(
            status="rejected", error_code=fault.code, error_message=fault.message
        )


@dataclass
class UploadLimits:
    """Ingest bounds, read from settings once and passed down.

    A dataclass rather than a `Settings` reference so the pipeline can be exercised at a
    boundary without a global: a test that wants a 1 KB ceiling says so.
    """

    max_bytes: int
    max_images_per_batch: int
    min_edge_px: int
    max_pixels: int


class WardrobeIngestService:
    """Upload, analyse, correct, re-analyse, delete.

    Holds a session *factory*, not a session. Analysis runs in a background task long after
    the request that started it has closed its own session, so a job that shared one would
    be writing through a closed connection — or, worse, holding one open for the length of a
    provider call.
    """

    def __init__(
        self,
        *,
        sessions: sessionmaker[Session],
        store: ObjectStore,
        analyzer: AuditingWardrobeAnalyzer,
        jobs: JobStore,
        background: BackgroundJobs,
        limits: UploadLimits,
        telemetry: GenerationLog | None = None,
    ) -> None:
        self._sessions = sessions
        self._store = store
        self._analyzer = analyzer
        self._jobs = jobs
        self._background = background
        self._limits = limits
        self._telemetry = telemetry

    # --- upload ---------------------------------------------------------------------

    async def upload(
        self, user_id: str, files: Sequence[UploadedFile]
    ) -> list[UploadOutcome]:
        """Accept a batch. Returns one outcome per file, in order.

        Over-count is refused per file rather than by truncating the batch: silently
        dropping a user's photograph is worse than telling them which ones did not fit.
        """
        outcomes: list[UploadOutcome] = []

        for index, upload in enumerate(files):
            if index >= self._limits.max_images_per_batch:
                outcomes.append(
                    UploadOutcome(
                        status="rejected",
                        error_code="IMAGE_TOO_LARGE",
                        error_message=(
                            f"Only {self._limits.max_images_per_batch} photos at a time. "
                            "Add the rest in a second batch."
                        ),
                    )
                )
                continue

            try:
                outcomes.append(await self._accept(user_id, upload))
            except Exception as error:
                # Deliberately broad. This loop is the partial-success guarantee, and an
                # unexpected failure on the third photograph must not take the other seven
                # with it. Logged with the type so it is not swallowed silently.
                logger.exception("upload failed for one file")
                outcomes.append(UploadOutcome.rejected(classify(error)))

        return outcomes

    async def _accept(self, user_id: str, upload: UploadedFile) -> UploadOutcome:
        """Validate, store and enqueue one file."""
        try:
            prepared = image_service.prepare_image(
                upload.data,
                declared_mime=upload.declared_mime,
                max_bytes=self._limits.max_bytes,
                min_edge_px=self._limits.min_edge_px,
                max_pixels=self._limits.max_pixels,
            )
        except image_service.ImageRejectedError as rejection:
            return UploadOutcome.rejected(classify(rejection))

        cached = await self._cache_hit(user_id, prepared.checksum)
        if cached is not None:
            return cached

        asset_id = f"asset_{uuid.uuid4().hex[:16]}"
        item_id = f"item_{uuid.uuid4().hex[:16]}"
        key = storage_key(user_id, asset_id, extension=extension_for(prepared.mime_type))

        # Bytes first, rows second. A row pointing at a file that was never written is a
        # broken card with no way back; a file with no row is unreferenced and cleaned up.
        await self._store.put(key, prepared.data, content_type=prepared.mime_type)
        try:
            await self._work(
                lambda session: _insert_asset_and_item(
                    session,
                    user_id=user_id,
                    asset_id=asset_id,
                    item_id=item_id,
                    key=key,
                    prepared=prepared,
                    category_hint=upload.category_hint,
                )
            )
        except Exception:
            await self._store.delete(key)
            raise

        job = await self._jobs.create(
            Job(
                job_id=new_job_id(),
                user_id=user_id,
                type=JobType.ANALYZE_ITEM,
                status=JobStatus.QUEUED,
                result_id=item_id,
            )
        )
        self._submit_analysis(user_id, item_id, job.job_id, upload.category_hint)

        return UploadOutcome(
            status="analyzing", item_id=item_id, asset_id=asset_id, job_id=job.job_id
        )

    async def _cache_hit(self, user_id: str, checksum: str) -> UploadOutcome | None:
        """The same photograph, already read, for this user.

        Returns an outcome carrying a job that is already `completed`, so the client's
        existing poller resolves it on the first tick with no special case. The alternative —
        a third upload status meaning "already done" — would have added a branch to every
        card in the UI to save one HTTP round trip.
        """
        found = await self._work(lambda session: _find_cached(session, user_id, checksum))
        if found is None:
            return None

        asset, item_id = found
        job = await self._jobs.create(
            Job(
                job_id=new_job_id(),
                user_id=user_id,
                type=JobType.ANALYZE_ITEM,
                status=JobStatus.COMPLETED,
                stage=STAGES[-1],
                result_id=item_id,
            )
        )
        logger.info("checksum cache hit; no provider call", extra={"job": job.job_id})
        return UploadOutcome(
            status="analyzing",
            item_id=item_id,
            asset_id=asset.asset_id,
            job_id=job.job_id,
            from_cache=True,
        )

    # --- analysis -------------------------------------------------------------------

    def _submit_analysis(
        self, user_id: str, item_id: str, job_id: str, category_hint: GarmentCategory | None
    ) -> None:
        self._background.submit(
            lambda: self.run_analysis(user_id, item_id, job_id, category_hint),
            name=f"analyze:{job_id}",
        )

    async def reanalyze(
        self, user_id: str, item_id: str
    ) -> tuple[str | None, GarmentCategory | None]:
        """Queue a fresh extraction for an item the caller owns.

        Corrected fields survive it — `save_extraction` merges through
        `app.domain.corrections`, so a re-read cannot overwrite the user's own answer
        (AI-EVAL-CASES Case 13). That rule lives in the domain rather than here precisely so
        that this method cannot forget it.

        The checksum cache is deliberately not consulted. Re-analysis is a request to ask
        the model again; answering it from the last answer would make the button a lie.
        """
        stored = await self._work(lambda session: _stored_item(session, user_id, item_id))
        if stored is None:
            return None, None

        hint = stored.item.extraction.category
        await self._work(
            lambda session: WardrobeRepository(session).set_status(
                user_id, item_id, ItemStatus.ANALYZING
            )
        )
        job = await self._jobs.create(
            Job(
                job_id=new_job_id(),
                user_id=user_id,
                type=JobType.ANALYZE_ITEM,
                status=JobStatus.QUEUED,
                result_id=item_id,
            )
        )
        self._submit_analysis(user_id, item_id, job.job_id, hint)
        return job.job_id, hint

    async def run_analysis(
        self,
        user_id: str,
        item_id: str,
        job_id: str,
        category_hint: GarmentCategory | None = None,
    ) -> None:
        """The `analyze_item` job body.

        Public because a test should be able to run it to completion deterministically
        rather than racing a background task, and because a real queue in S11 calls exactly
        this with exactly these arguments.

        Every stage transition below corresponds to work that actually happens between it
        and the next one. Naming a stage that fires immediately after the previous one is
        the same thing as a spinner with extra words.
        """
        attempts: list[AnalysisAttempt] = []
        try:
            await self._jobs.advance(job_id, STAGES[0])  # reading photo
            asset = await self._work(lambda session: _asset_for_item(session, user_id, item_id))
            if asset is None:
                # The item or its asset went away between upload and analysis — a delete
                # that landed first. Not an error worth alarming about.
                await self._jobs.update(
                    job_id,
                    status=JobStatus.FAILED,
                    error_code="ITEM_NOT_FOUND",
                    error_message="That photo is no longer in your wardrobe.",
                    retryable=False,
                )
                return

            image = GarmentImage(
                asset_id=asset.asset_id,
                storage_key=asset.storage_key,
                category_hint=category_hint,
            )

            await self._jobs.advance(job_id, STAGES[1])  # finding garment
            outcome = await self._analyzer.analyze_with_audit(
                image, on_attempt=attempts.append
            )

            await self._jobs.advance(job_id, STAGES[2])  # reading colour and cut
            extraction = sanitize_extraction(outcome.extraction)

            await self._jobs.advance(job_id, STAGES[3])  # checking confidence
            await self._work(
                lambda session: _persist_extraction(
                    session,
                    user_id=user_id,
                    item_id=item_id,
                    extraction=extraction,
                    analyzed_by=outcome.model,
                )
            )

            await self._jobs.update(
                job_id,
                status=JobStatus.COMPLETED,
                stage=STAGES[4],
                result_id=item_id,
                attempt=len(attempts),
            )
            logger.info(
                "extraction stored",
                extra={
                    "job": job_id,
                    "attempts": len(attempts),
                    "used_fallback": outcome.used_fallback,
                },
            )

        except Exception as error:
            fault = classify(error)
            logger.warning(
                "analysis failed", extra={"job": job_id, "code": fault.code}, exc_info=True
            )
            await self._work(
                lambda session: WardrobeRepository(session).set_status(
                    user_id, item_id, ItemStatus.FAILED
                )
            )
            await self._jobs.update(
                job_id,
                status=JobStatus.FAILED,
                error_code=fault.code,
                error_message=fault.message,
                retryable=fault.retryable,
                attempt=len(attempts),
            )

        finally:
            # In a `finally` because the failure path is the one the audit trail exists for.
            # Rejected attempts carry the raw output that was refused; losing them on the
            # only runs that produce them would make `item_extractions` a log of successes.
            if attempts:
                await self._record_attempts(user_id, item_id, attempts)
            self._emit(attempts, user_id=user_id, job_id=job_id)

    def _emit(
        self, attempts: Sequence[AnalysisAttempt], *, user_id: str, job_id: str
    ) -> None:
        """One generation event per attempt, in the order they happened.

        Per attempt rather than per photograph, because that is what makes `retry_rate` and
        `fallback_calls` mean anything: a re-ask that succeeded is one failure and one
        success, not one success. The attempts carry `raw_output` and the events do not —
        the raw text belongs in our own audit table, never in telemetry
        (`app/services/telemetry.py`).
        """
        if self._telemetry is None:
            return
        for index, attempt in enumerate(attempts, start=1):
            self._telemetry.record(
                GenerationEvent(
                    operation="extraction",
                    model=attempt.model,
                    outcome=_extraction_outcome(attempt),
                    latency_ms=attempt.latency_ms,
                    attempt=index,
                    used_fallback=attempt.used_fallback,
                    request_id=attempt.request_id,
                    job_id=job_id,
                    user_id=user_id,
                )
            )

    async def _record_attempts(
        self, user_id: str, item_id: str, attempts: Sequence[AnalysisAttempt]
    ) -> None:
        try:
            await self._work(
                lambda session: _write_audit(session, user_id, item_id, attempts)
            )
        except Exception:
            # The audit write failing must not turn a completed analysis into a failed one.
            # Loud, because an audit trail that quietly stops being written is worse than
            # one that was never claimed.
            logger.exception("could not write the extraction audit trail")

    # --- unit of work ---------------------------------------------------------------

    async def _work(self, operation: Callable[[Session], _T]) -> _T:
        """Run one synchronous database operation off the event loop.

        SQLAlchemy's `Session` is synchronous, and this pipeline is not: a commit inside a
        coroutine blocks every other photograph in the batch for its duration. A thread per
        operation, each with its own session, keeps the batch genuinely concurrent without
        introducing a second ORM.
        """

        def run() -> _T:
            with self._sessions() as session:
                result = operation(session)
                session.commit()
                return result

        return await asyncio.to_thread(run)


# --- session-scoped operations -------------------------------------------------------
#
# Free functions taking a `Session` rather than methods, so that what runs inside a
# transaction is visible at the call site and nothing accidentally holds a session open
# across an `await`.


def _extraction_outcome(attempt: AnalysisAttempt) -> Outcome:
    """One attempt's fate, in the telemetry vocabulary.

    The three cases are distinguishable without reading the reason string, which is the
    point of recording an empty `raw_output` for a refusal: no response arrived, so there is
    nothing to have failed a schema. `AI_TIMEOUT` is split out because a slow provider and a
    broken one need different responses (docs/OBSERVABILITY.md).
    """
    if attempt.schema_valid:
        return "ok"
    if attempt.raw_output:
        return "schema_invalid"
    return "timeout" if attempt.rejected_reason == "AI_TIMEOUT" else "provider_error"


def _insert_asset_and_item(
    session: Session,
    *,
    user_id: str,
    asset_id: str,
    item_id: str,
    key: str,
    prepared: image_service.PreparedImage,
    category_hint: GarmentCategory | None,
) -> None:
    from app.domain.models import GarmentExtraction, WardrobeItem

    AssetRepository(session).add(
        user_id,
        asset_id=asset_id,
        storage_key=key,
        mime_type=prepared.mime_type,
        byte_size=prepared.byte_size,
        width=prepared.width,
        height=prepared.height,
        checksum=prepared.checksum,
    )
    WardrobeRepository(session).add_item(
        WardrobeItem(
            item_id=item_id,
            user_id=user_id,
            status=ItemStatus.ANALYZING,
            # The hint is recorded as the starting category with no confidence attached. It
            # is the user's guess, not a reading, and `field_confidence` describes readings —
            # so the field stays hedged until a model or the user settles it.
            extraction=GarmentExtraction(category=category_hint),
        ),
        asset_id=asset_id,
    )


def _find_cached(
    session: Session, user_id: str, checksum: str
) -> tuple[StoredAsset, str] | None:
    assets = AssetRepository(session)
    asset = assets.by_checksum(user_id, checksum)
    if asset is None:
        return None
    item_id = assets.item_for_asset(user_id, asset.asset_id)
    if item_id is None:
        # The asset survived but its item was deleted. Nothing to hand back, so this is a
        # miss and the photograph is analysed again.
        return None
    return asset, item_id


def _asset_for_item(session: Session, user_id: str, item_id: str) -> StoredAsset | None:
    stored = WardrobeRepository(session).stored(user_id, item_id)
    if stored is None or stored.asset_id is None:
        return None
    return AssetRepository(session).get(user_id, stored.asset_id)


def _stored_item(session: Session, user_id: str, item_id: str) -> Any:
    return WardrobeRepository(session).stored(user_id, item_id)


def _persist_extraction(
    session: Session,
    *,
    user_id: str,
    item_id: str,
    extraction: Any,
    analyzed_by: str,
) -> None:
    repository = WardrobeRepository(session)
    repository.save_extraction(user_id, item_id, extraction, analyzed_by=analyzed_by)
    repository.set_status(user_id, item_id, ItemStatus.READY)


def _write_audit(
    session: Session, user_id: str, item_id: str, attempts: Sequence[AnalysisAttempt]
) -> None:
    audit = ExtractionAuditRepository(session)
    for attempt in attempts:
        audit.record(
            user_id,
            item_id,
            provider=PROVIDER,
            model=attempt.model,
            raw_output=attempt.raw_output,
            schema_valid=attempt.schema_valid,
            latency_ms=attempt.latency_ms,
            rejected_reason=attempt.rejected_reason,
        )


__all__ = [
    "PROVIDER",
    "UploadLimits",
    "UploadOutcome",
    "UploadedFile",
    "WardrobeIngestService",
]
