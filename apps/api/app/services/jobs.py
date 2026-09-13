"""Async jobs, and the named stages a user actually sees.

docs/ARCHITECTURE.md section 5: upload enqueues one `analyze_item` job per image and the
client receives cards progressively. Two consequences shape this module.

**One job per image, never one per batch.** A batch-level job would have one status, and one
status means one spinner over eight photographs — the exact thing CLAUDE.md's motion rules
forbid. Eight jobs is what lets the fourth photo fail while the other seven resolve.

**Stages are named work, not a percentage.** `STAGES` below is the sequence from CLAUDE.md,
word for word. `progress` is derived from the stage rather than tracked separately, because
two sources of truth for "how far along" drift and the named one is the one on screen.

## The runner is in-process, and that is a known ceiling

`BackgroundJobs` spawns asyncio tasks in the API process. It survives a single-instance
deployment and nothing more: a restart loses queued work, and a second instance knows
nothing of the first's jobs. A durable queue lands in S11 (blocker B14).

The seam is deliberate — `submit` takes a factory and returns nothing, so a real queue
replaces this class without touching the pipeline above it. What is *not* deferred is the
part that would be expensive to retrofit: the route returns before any analysis begins, so
nothing above this module assumes a synchronous result.

`InMemoryJobStore` is guarded by a lock because job records are written from request
handlers and from background tasks, and read by pollers, on one event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger("stylelab.jobs")


class JobType(StrEnum):
    ANALYZE_ITEM = "analyze_item"
    COMPOSE_OUTFIT = "compose_outfit"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


#: Extraction stages, verbatim from CLAUDE.md's motion rules. The last is terminal.
STAGES: tuple[str, ...] = (
    "reading photo",
    "finding garment",
    "reading colour and cut",
    "checking confidence",
    "ready",
)

#: Composition stages, also verbatim from CLAUDE.md. A separate sequence because they
#: describe different work: an extraction reads one photograph, a composition reads a
#: wardrobe. Sharing one list would mean showing "finding garment" while ranking outfits.
COMPOSE_STAGES: tuple[str, ...] = (
    "reading your wardrobe",
    "matching silhouettes",
    "balancing palette",
    "building look",
    "ready",
)

#: Both sequences, searched in order. They share "ready" and nothing else; since it is last
#: in each and both are the same length, the progress it maps to is the same either way.
_SEQUENCES: tuple[tuple[str, ...], ...] = (STAGES, COMPOSE_STAGES)


def stage_progress(stage: str | None) -> float | None:
    """Fraction complete, derived from the named stage.

    Derived rather than stored: a separate `progress` field and a stage name are two claims
    about the same thing, and the one the user reads is the name.

    Looked up across both sequences rather than passed the job type, because the stage name
    is already unambiguous and threading the type through would let a caller ask for the
    progress of a stage against the wrong sequence.
    """
    if stage is None:
        return None
    for sequence in _SEQUENCES:
        if stage in sequence:
            return round((sequence.index(stage) + 1) / len(sequence), 2)
    return None


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True, slots=True)
class Job:
    """One unit of async work.

    Frozen, and updated by replacement in the store. A job record read by a poller while a
    background task is halfway through mutating it would otherwise be a job with a
    completed status and no result.
    """

    job_id: str
    #: The owner. `GET /jobs/{id}` is scoped on this — a job id is not a capability.
    user_id: str
    type: JobType
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    #: What the job produced, for the client to fetch. An item id for `analyze_item`, an
    #: outfit id for `compose_outfit`.
    result_id: str | None = None
    #: A small terminal payload for a job whose answer is not a row. `compose_outfit` uses
    #: it for the insufficient-wardrobe case: there is no outfit to fetch, and naming the
    #: gap is the answer rather than an error. Left `None` by `analyze_item`, which always
    #: has an item id to point at.
    result: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    attempt: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def progress(self) -> float | None:
        return stage_progress(self.stage)

    @property
    def terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)


class JobStore(Protocol):
    """Where job records live. In-memory now, Redis or Postgres in S11."""

    async def create(self, job: Job) -> Job: ...

    async def get(self, user_id: str, job_id: str) -> Job | None: ...

    async def update(self, job_id: str, **changes: object) -> Job | None: ...


class InMemoryJobStore:
    """Per-process job records.

    `get` takes `user_id` and filters on it, the same rule as every repository method. A job
    id is random and unguessable, but "unguessable" is not an authorisation model and a
    scoped read costs one comparison.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: Job) -> Job:
        async with self._lock:
            self._jobs[job.job_id] = job
        return job

    async def get(self, user_id: str, job_id: str) -> Job | None:
        async with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job

    async def update(self, job_id: str, **changes: object) -> Job | None:
        """Replace a job's fields. Unscoped on purpose — the only callers are the background
        tasks that own the job, and they were handed the id rather than asking for it."""
        async with self._lock:
            existing = self._jobs.get(job_id)
            if existing is None:
                return None
            updated = replace(existing, updated_at=datetime.now(UTC), **changes)  # type: ignore[arg-type]
            self._jobs[job_id] = updated
            return updated

    async def advance(self, job_id: str, stage: str) -> Job | None:
        """Move to a named stage, marking the job processing if it was queued."""
        return await self.update(job_id, stage=stage, status=JobStatus.PROCESSING)


class BackgroundJobs:
    """Fire-and-forget task spawning, with a reference held so nothing is collected.

    `asyncio.create_task` returns a task the event loop only weakly references; drop it and
    a job can be garbage-collected mid-flight. The task set is the fix, and the callback is
    what keeps it from growing without bound.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, factory: Callable[[], Awaitable[None]], *, name: str) -> None:
        task = asyncio.create_task(_guarded(factory, name), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @property
    def in_flight(self) -> int:
        return len([task for task in self._tasks if not task.done()])

    async def drain(self, timeout_s: float = 30.0) -> None:
        """Wait for outstanding work. Used at shutdown and by tests that need a barrier."""
        if not self._tasks:
            return
        await asyncio.wait(set(self._tasks), timeout=timeout_s)


async def _guarded(factory: Callable[[], Awaitable[None]], name: str) -> None:
    """Run a job body so that no exception escapes into the event loop's unhandled set.

    A job that raises has already recorded its own failure on the job record — this is the
    last resort for the case where recording the failure is itself what failed.
    """
    try:
        await factory()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("background job crashed", extra={"job": name})


__all__ = [
    "COMPOSE_STAGES",
    "STAGES",
    "BackgroundJobs",
    "InMemoryJobStore",
    "Job",
    "JobStatus",
    "JobStore",
    "JobType",
    "new_job_id",
    "stage_progress",
]
