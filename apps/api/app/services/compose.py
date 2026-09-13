"""Composition as async work, plus the swap that follows it.

`CompositionService` is the nine-step orchestration (docs/ARCHITECTURE.md section 6). This
module is what runs it for a real request: the job, the persistence, and the two operations
the result screen needs afterwards — alternatives for a slot, and a swap into it.

## Why composing is a job and swapping is not

Composing calls a provider. Whatever is behind `OutfitAdvisor` — one text call today, the
crew in S8b — the route must be able to return before it finishes, or the whole async model
is one endpoint away from being decorative. The stages come from CLAUDE.md's motion rules
and go out through the same `GET /jobs/{id}` the upload screen already polls.

Swapping calls nothing. It is a scoped read, a pure recompute over six dimensions, and one
row rewritten. Making it a job would mean the signature product moment — one slot changes,
the rest stay still — went through a queue and a poller to do arithmetic. It is synchronous
because it is fast, and it is fast because the model is not in the loop.

## Which stages are emitted, and why not all five

The vocabulary is the full five from CLAUDE.md. This rung emits three of them, because
three is how many pieces of separable work it actually does: read the wardrobe, ask the
advisor, done. "Matching silhouettes" and "balancing palette" are things that happen
*inside* the single advisor call at this rung, and a stage that fires immediately after its
predecessor is a spinner with a caption on it. When the crew lands in S8b those two become
real transitions, because a Silhouette agent finishing is an event.

## What a swap does to the words on the screen

It rewrites them. The rationale and the pro tips were written about a combination that no
longer exists, and a tip about the trouser the user just swapped out is the visual state
disagreeing with the wardrobe state, in prose. The recomputed rationale comes from
`app.domain.scoring.describe`, which describes the scoring — something the system knows
first-hand — and the note says plainly that this is what happened.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.adapters import OutfitAdvisor, TrendSource
from app.domain.compatibility import CORE_ROLES, GAP_DESCRIPTIONS
from app.domain.models import AdviceRequest, GarmentCategory, ItemStatus, WardrobeItem
from app.domain.ranker import DeterministicRanker
from app.domain.scoring import ScoreBreakdown, describe, score_outfit
from app.repositories.wardrobe import StoredItem, StoredOutfit, WardrobeRepository
from app.services.circuit import LatencyCircuit
from app.services.composition import CompositionService
from app.services.faults import classify
from app.services.jobs import (
    COMPOSE_STAGES,
    BackgroundJobs,
    InMemoryJobStore,
    Job,
    JobStatus,
    JobType,
    new_job_id,
)
from app.services.telemetry import GenerationLog

logger = logging.getLogger("stylelab.compose")

_T = TypeVar("_T")

#: How many alternatives one slot offers. Enough to be a real choice, few enough to read
#: without scrolling a sheet on a phone.
MAX_ALTERNATIVES = 8

#: Appended to a swapped look's rationale. The tips that came with the original are gone
#: and the user should be told why rather than watching them vanish.
RECOMPUTED_NOTE = (
    "Recomputed after your swap — the styling notes were written for the previous pieces."
)


class SwapNotPossibleError(Exception):
    """A swap the caller asked for that cannot be applied, with the reason.

    Separate from "not found": these are all cases where the outfit and the garment both
    exist and are the caller's, and the combination is still refused. The router turns it
    into a 422 naming the field, never echoing an id back as prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Alternative:
    """One garment that could fill a slot, and what the look would score with it in."""

    item: StoredItem
    match_score: int
    #: Against the look as it stands. Negative is shown as readily as positive — a swap the
    #: user wants for reasons the scorer cannot see is still theirs to make.
    delta: int


@dataclass(frozen=True, slots=True)
class AlternativesView:
    """Alternatives for one slot, plus the gap when there are none.

    An empty list is a valid answer (prompts/06). `gap` carries the generic description of
    what would unlock the slot, so the UI can offer to add one rather than reporting an
    error for a wardrobe that is simply small.
    """

    role: str
    current_item_id: str | None
    alternatives: list[Alternative]
    gap: dict[str, Any] | None


class OutfitComposer:
    """Compose, then swap. Holds a session factory for the same reason ingest does.

    The advisor call happens between two database operations and outside both of them: a
    session held across it is a connection checked out for the length of a provider request.
    """

    def __init__(
        self,
        *,
        sessions: sessionmaker[Session],
        advisor: OutfitAdvisor,
        jobs: InMemoryJobStore,
        background: BackgroundJobs,
        trend_source: TrendSource | None = None,
        ranker: DeterministicRanker | None = None,
        latency_budget_s: float | None = None,
        telemetry: GenerationLog | None = None,
        circuit: LatencyCircuit | None = None,
    ) -> None:
        self._sessions = sessions
        self._advisor = advisor
        self._jobs = jobs
        self._background = background
        self._trend_source = trend_source
        self._ranker = ranker or DeterministicRanker()
        self._latency_budget_s = latency_budget_s
        self._telemetry = telemetry
        #: Rung 3 of the ladder (docs/AGENT-SYSTEM.md). Lives here rather than on the service
        #: because consecutive breaches are a property of the process, and a service is built
        #: per request — it would never see a second one.
        self._circuit = (
            circuit
            if circuit is not None
            else (LatencyCircuit(latency_budget_s) if latency_budget_s else None)
        )

    # --- compose ------------------------------------------------------------------------

    async def start(
        self,
        user_id: str,
        *,
        occasion: str,
        vibe: str | None = None,
        fit_preference: str | None = None,
        color_preferences: Sequence[str] = (),
        required_roles: Sequence[GarmentCategory] = CORE_ROLES,
    ) -> Job:
        """Queue a composition and return its job. Nothing has been asked of a model yet."""
        job = await self._jobs.create(
            Job(
                job_id=new_job_id(),
                user_id=user_id,
                type=JobType.COMPOSE_OUTFIT,
                status=JobStatus.QUEUED,
            )
        )
        self._background.submit(
            lambda: self.run(
                user_id,
                job.job_id,
                occasion=occasion,
                vibe=vibe,
                fit_preference=fit_preference,
                color_preferences=tuple(color_preferences),
                required_roles=tuple(required_roles),
            ),
            name=f"compose:{job.job_id}",
        )
        return job

    async def run(
        self,
        user_id: str,
        job_id: str,
        *,
        occasion: str,
        vibe: str | None = None,
        fit_preference: str | None = None,
        color_preferences: Sequence[str] = (),
        required_roles: Sequence[GarmentCategory] = CORE_ROLES,
    ) -> None:
        """The `compose_outfit` job body.

        Public for the same two reasons `run_analysis` is: a test should be able to run it
        to completion rather than race a background task, and a durable queue in S11 calls
        exactly this.
        """
        try:
            await self._jobs.advance(job_id, COMPOSE_STAGES[0])  # reading your wardrobe
            candidates = await self._work(
                lambda session: WardrobeRepository(session).candidates(user_id)
            )

            service = CompositionService(
                repository=None,
                advisor=self._advisor_for_now(),
                ranker=self._ranker,
                trend_source=self._trend_source,
                latency_budget_s=self._latency_budget_s,
                telemetry=self._telemetry,
                job_id=job_id,
            )

            await self._jobs.advance(job_id, COMPOSE_STAGES[3])  # building look
            started = time.perf_counter()
            advice = await service.compose(
                user_id,
                occasion=occasion,
                vibe=vibe,
                fit_preference=fit_preference,
                color_preferences=color_preferences,
                required_roles=required_roles,
                candidates=candidates,
            )
            if self._circuit is not None:
                self._circuit.record(time.perf_counter() - started)

            if advice.outfit is None:
                # Not a failure. The wardrobe cannot fill a required role, and naming that
                # is the answer (rung 5) — a `failed` job would offer a retry for something
                # retrying cannot fix.
                await self._jobs.update(
                    job_id,
                    status=JobStatus.COMPLETED,
                    stage=COMPOSE_STAGES[-1],
                    result=advice.model_dump(mode="json", exclude={"outfit"}),
                )
                logger.info(
                    "composition named a gap",
                    extra={"job": job_id, "level": advice.degradation_level},
                )
                return

            composed = advice.outfit
            outfit_id = f"outfit_{uuid.uuid4().hex[:16]}"
            await self._work(
                lambda session: WardrobeRepository(session).save_outfit(
                    user_id,
                    outfit_id=outfit_id,
                    name=composed.name,
                    occasion=occasion,
                    item_ids=composed.item_ids,
                    match_score=composed.match_score,
                    rationale=advice.rationale,
                    degradation_level=advice.degradation_level,
                    advisory=advice.model_dump(
                        mode="json",
                        include={
                            "confidence",
                            "pro_tips",
                            "budget_tricks",
                            "wardrobe_gaps",
                            "trend_notes",
                        },
                    ),
                    vibe=vibe,
                    fit_preference=fit_preference,
                    color_preferences=color_preferences,
                )
            )

            await self._jobs.update(
                job_id,
                status=JobStatus.COMPLETED,
                stage=COMPOSE_STAGES[-1],
                result_id=outfit_id,
            )
            logger.info(
                "outfit composed",
                extra={"job": job_id, "level": advice.degradation_level},
            )

        except Exception as error:
            fault = classify(error)
            logger.warning(
                "composition failed", extra={"job": job_id, "code": fault.code}, exc_info=True
            )
            await self._jobs.update(
                job_id,
                status=JobStatus.FAILED,
                error_code=fault.code,
                error_message=fault.message,
                retryable=fault.retryable,
            )

    def _advisor_for_now(self) -> OutfitAdvisor:
        """The full crew, or a reduced one when the breaker is open.

        `getattr` rather than an `isinstance` check against `CrewAIOutfitAdvisor`: the
        composer must keep working with the single-call advisor and with any stub a test
        hands it, and importing the crew here would drag thirteen seconds of CrewAI into
        every module that touches composition. An advisor that cannot reduce simply does not.
        """
        if self._circuit is None or not self._circuit.tripped:
            return self._advisor

        reduce = getattr(self._advisor, "with_roles", None)
        if reduce is None:
            return self._advisor

        from app.adapters.crew import CrewRoles

        logger.warning("latency circuit open; composing with architect and editor only")
        return reduce(CrewRoles.architect_and_editor_only(), degradation_level=3)

    # --- read, swap, save ----------------------------------------------------------------

    async def result(self, user_id: str, outfit_id: str) -> StoredOutfit | None:
        return await self._work(
            lambda session: WardrobeRepository(session).get_outfit(user_id, outfit_id)
        )

    async def alternatives(
        self, user_id: str, outfit_id: str, *, role: str
    ) -> AlternativesView | None:
        return await self._work(
            lambda session: _alternatives_for(session, user_id, outfit_id, role=role)
        )

    async def swap(
        self, user_id: str, outfit_id: str, *, role: str, replacement_item_id: str
    ) -> StoredOutfit | None:
        return await self._work(
            lambda session: _apply_swap(
                session,
                user_id,
                outfit_id,
                role=role,
                replacement_item_id=replacement_item_id,
            )
        )

    async def save(self, user_id: str, outfit_id: str) -> bool:
        return await self._work(
            lambda session: WardrobeRepository(session).mark_saved(user_id, outfit_id)
        )

    # --- unit of work ---------------------------------------------------------------------

    async def _work(self, operation: Callable[[Session], _T]) -> _T:
        """One synchronous database operation, off the event loop. As `ingest._work`."""

        def run() -> _T:
            with self._sessions() as session:
                result = operation(session)
                session.commit()
                return result

        return await asyncio.to_thread(run)


# --- session-scoped operations -----------------------------------------------------------
#
# Free functions taking a `Session`, so what runs inside a transaction is visible at the
# call site. Same convention as `app/services/ingest.py`.


def _parse_role(role: str) -> GarmentCategory:
    try:
        return GarmentCategory(role)
    except ValueError as error:
        raise SwapNotPossibleError(
            "UNKNOWN_ROLE", "That is not a kind of garment this app knows about."
        ) from error


def _request_for(
    outfit: StoredOutfit, *, user_id: str, items: Sequence[WardrobeItem]
) -> AdviceRequest:
    """Rebuild the question the look was originally scored against.

    The preferences come off the outfit row rather than from the caller. A swap must not be
    able to change the score by changing the question — the user asked for `work` and
    `minimal` when they composed this, and that is what the new combination is judged on.
    """
    return AdviceRequest(
        user_id=user_id,
        candidates=list(items),
        occasion=outfit.occasion,
        vibe=outfit.vibe,
        fit_preference=outfit.fit_preference,
        color_preferences=list(outfit.color_preferences),
    )


def _score_with(
    outfit: StoredOutfit, *, user_id: str, items: Sequence[WardrobeItem]
) -> ScoreBreakdown:
    return score_outfit(list(items), _request_for(outfit, user_id=user_id, items=items))


def _other_items(outfit: StoredOutfit, *, role: str) -> list[WardrobeItem]:
    """Every garment in the look except the one filling `role`, skipping deleted slots."""
    return [
        slot.item.item for slot in outfit.slots if slot.filled and slot.role != role and slot.item
    ]


def _alternatives_for(
    session: Session, user_id: str, outfit_id: str, *, role: str
) -> AlternativesView | None:
    """Owned garments that could fill this slot, best first.

    "Compatible" is measured, not asserted: each candidate is scored *in the look*, against
    the other pieces actually on screen. A shortlist ordered by how good each garment is on
    its own would recommend the best shoe in the wardrobe rather than the best shoe with
    this shirt.
    """
    parsed = _parse_role(role)
    repository = WardrobeRepository(session)
    outfit = repository.get_outfit(user_id, outfit_id)
    if outfit is None:
        return None

    slot = next((s for s in outfit.slots if s.role == role), None)
    if slot is None:
        raise SwapNotPossibleError(
            "ROLE_NOT_IN_OUTFIT", f"This look has no {role} to change."
        )

    others = _other_items(outfit, role=role)
    current = [slot.item.item] if slot.item else []
    baseline = (
        _score_with(outfit, user_id=user_id, items=[*others, *current]).total
        if current
        else 0.0
    )

    scored: list[Alternative] = []
    for stored in repository.items(user_id, category=parsed, statuses=(ItemStatus.READY,)):
        if stored.item.item_id == slot.item_id:
            continue
        total = _score_with(outfit, user_id=user_id, items=[*others, stored.item]).total
        scored.append(
            Alternative(
                item=stored,
                match_score=round(total * 100),
                delta=round(total * 100) - round(baseline * 100),
            )
        )

    # Score descending, then id ascending. The id tie-break is what makes the sheet show
    # the same order every time it is opened, which is the difference between a list and a
    # shuffle (the ranker's stability rule, same reasoning).
    scored.sort(key=lambda a: (-a.match_score, a.item.item.item_id))

    return AlternativesView(
        role=role,
        current_item_id=slot.item_id if slot.filled else None,
        alternatives=scored[:MAX_ALTERNATIVES],
        gap=(
            None
            if scored
            else {
                "category": role,
                "generic_description": GAP_DESCRIPTIONS[parsed],
            }
        ),
    )


def _apply_swap(
    session: Session, user_id: str, outfit_id: str, *, role: str, replacement_item_id: str
) -> StoredOutfit | None:
    """Point one slot at a different garment the caller owns, and rescore the look.

    Every refusal below is checked against the caller's own scope. The replacement is read
    through `WardrobeRepository.get`, so an id belonging to somebody else is indistinguishable
    from one that does not exist — which is the answer docs/API-SPEC.md requires.
    """
    parsed = _parse_role(role)
    repository = WardrobeRepository(session)
    outfit = repository.get_outfit(user_id, outfit_id)
    if outfit is None:
        return None

    slot = next((s for s in outfit.slots if s.role == role), None)
    if slot is None:
        raise SwapNotPossibleError(
            "ROLE_NOT_IN_OUTFIT", f"This look has no {role} to change."
        )

    replacement = repository.get(user_id, replacement_item_id)
    if replacement is None:
        return None

    if replacement.status is not ItemStatus.READY:
        raise SwapNotPossibleError(
            "ITEM_NOT_READY", "That garment is still being read. Give it a moment."
        )

    if replacement.extraction.category is not parsed:
        found = replacement.extraction.category
        raise SwapNotPossibleError(
            "ROLE_MISMATCH",
            f"That is {found.value if found else 'not categorised'}, so it cannot fill "
            f"the {role} slot.",
        )

    if slot.item_id == replacement_item_id:
        # Already there. Idempotent rather than an error: the second tap on the item you
        # just chose should do nothing, not report a problem.
        return outfit

    items = [*_other_items(outfit, role=role), replacement]
    breakdown = _score_with(outfit, user_id=user_id, items=items)
    # Every slot filled after this write? The one being swapped now is, by construction.
    still_missing = [s for s in outfit.slots if not s.filled and s.role != role]

    repository.swap_slot(
        user_id,
        outfit_id,
        role=role,
        replacement_item_id=replacement_item_id,
        match_score=round(breakdown.total * 100),
        status="incomplete" if still_missing else "ready",
        rationale=[*describe(breakdown), RECOMPUTED_NOTE],
        # Gaps describe the wardrobe, so they survive a swap. Tips, tricks and trend notes
        # described the previous combination and do not.
        advisory={"wardrobe_gaps": outfit.advisory.get("wardrobe_gaps", [])},
    )
    return repository.get_outfit(user_id, outfit_id)


__all__ = [
    "MAX_ALTERNATIVES",
    "RECOMPUTED_NOTE",
    "Alternative",
    "AlternativesView",
    "OutfitComposer",
    "SwapNotPossibleError",
]
