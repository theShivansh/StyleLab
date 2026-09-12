"""The async job model."""

from __future__ import annotations

import asyncio

import pytest

from app.services.jobs import (
    STAGES,
    BackgroundJobs,
    InMemoryJobStore,
    Job,
    JobStatus,
    JobType,
    new_job_id,
    stage_progress,
)


def make_job(**overrides) -> Job:
    defaults = {
        "job_id": new_job_id(),
        "user_id": "user_1",
        "type": JobType.ANALYZE_ITEM,
    }
    return Job(**{**defaults, **overrides})


# --- stages -------------------------------------------------------------------------------


def test_the_stages_are_the_ones_the_motion_rules_name():
    """CLAUDE.md gives this sequence verbatim for extraction. It is a product decision.

    Pinned here because the copy on screen comes straight from this tuple: rewording a
    stage is a UX change, and it should have to be made deliberately rather than while
    tidying a constant.
    """
    assert STAGES == (
        "reading photo",
        "finding garment",
        "reading colour and cut",
        "checking confidence",
        "ready",
    )


def test_progress_is_derived_from_the_stage_and_ends_at_one():
    """One source of truth for "how far along", and it is the one the user reads."""
    assert stage_progress(STAGES[0]) == 0.2
    assert stage_progress(STAGES[-1]) == 1.0
    assert [stage_progress(s) for s in STAGES] == sorted(stage_progress(s) for s in STAGES)


def test_an_unknown_or_absent_stage_has_no_progress():
    """`null`, not 0. A queued job has not made no progress; it has not started."""
    assert stage_progress(None) is None
    assert stage_progress("inventing things") is None


def test_a_job_reports_its_own_progress():
    assert make_job(stage=STAGES[1]).progress == 0.4
    assert make_job().progress is None


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (JobStatus.QUEUED, False),
        (JobStatus.PROCESSING, False),
        (JobStatus.COMPLETED, True),
        (JobStatus.FAILED, True),
    ],
)
def test_terminal_states_are_the_two_the_poller_stops_on(status, terminal):
    assert make_job(status=status).terminal is terminal


# --- the store ----------------------------------------------------------------------------


async def test_a_job_is_readable_by_its_owner():
    store = InMemoryJobStore()
    job = await store.create(make_job())

    assert (await store.get("user_1", job.job_id)) == job


async def test_another_users_job_is_not_readable_even_with_its_id():
    """A job id is unguessable and still not a capability.

    Same rule as every repository read: the scope is a parameter, not an assumption about
    how hard the identifier is to find.
    """
    store = InMemoryJobStore()
    job = await store.create(make_job(user_id="user_owner"))

    assert await store.get("user_other", job.job_id) is None


async def test_a_missing_job_reads_as_none():
    assert await InMemoryJobStore().get("user_1", "job_nope") is None


async def test_updating_replaces_fields_and_moves_the_timestamp():
    store = InMemoryJobStore()
    job = await store.create(make_job())

    updated = await store.update(job.job_id, status=JobStatus.COMPLETED, result_id="item_1")

    assert updated is not None
    assert updated.status is JobStatus.COMPLETED
    assert updated.result_id == "item_1"
    assert updated.updated_at >= job.updated_at
    assert updated.created_at == job.created_at


async def test_advancing_a_queued_job_marks_it_processing():
    store = InMemoryJobStore()
    job = await store.create(make_job())

    advanced = await store.advance(job.job_id, STAGES[1])

    assert advanced is not None
    assert advanced.status is JobStatus.PROCESSING
    assert advanced.stage == STAGES[1]


async def test_updating_a_job_that_does_not_exist_is_not_an_error():
    assert await InMemoryJobStore().update("job_nope", status=JobStatus.FAILED) is None


async def test_a_job_record_is_immutable_so_a_poller_never_sees_a_half_update():
    """Frozen and replaced rather than mutated.

    A poller reading a record while a background task set `status=completed` but had not yet
    set `result_id` would see a finished job with nothing to fetch.
    """
    store = InMemoryJobStore()
    job = await store.create(make_job())
    held = await store.get("user_1", job.job_id)

    await store.update(job.job_id, status=JobStatus.COMPLETED)

    assert held is not None
    assert held.status is JobStatus.QUEUED  # the reference the poller holds did not change


# --- the runner ---------------------------------------------------------------------------


async def test_submitted_work_runs_and_is_not_collected_before_it_does():
    """Why the task set exists.

    `asyncio.create_task` returns a task the loop only weakly references. Drop it and the
    job can be garbage-collected mid-flight — an extraction that simply never finishes and
    never fails.
    """
    background = BackgroundJobs()
    done = asyncio.Event()

    background.submit(_setter(done), name="test")
    assert background.in_flight == 1

    await background.drain(timeout_s=5)
    assert done.is_set()
    assert background.in_flight == 0


async def test_a_crashing_job_does_not_escape_into_the_event_loop():
    """The last resort. A job body records its own failure; this catches the case where
    recording it is what failed."""
    background = BackgroundJobs()

    async def explode() -> None:
        raise RuntimeError("recording the failure failed")

    background.submit(explode, name="test")
    await background.drain(timeout_s=5)  # no exception escapes


async def test_draining_with_nothing_outstanding_returns_immediately():
    await BackgroundJobs().drain(timeout_s=5)


async def test_many_jobs_run_concurrently_rather_than_in_sequence():
    """The batch guarantee at its smallest: eight photographs are eight jobs at once.

    Sequential execution would make an eight-photo upload take eight extraction latencies,
    which is the experience a single batch spinner is there to hide.
    """
    background = BackgroundJobs()
    running = 0
    peak = 0

    async def slow() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    for index in range(8):
        background.submit(slow, name=f"test-{index}")
    await background.drain(timeout_s=5)

    assert peak == 8


def _setter(event: asyncio.Event):
    async def run() -> None:
        event.set()

    return run
