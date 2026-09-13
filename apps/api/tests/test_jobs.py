"""The async job model."""

from __future__ import annotations

import asyncio

import pytest

from app.services.jobs import (
    STAGES,
    BackgroundJobs,
    DatabaseJobStore,
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


# --- the store, for both implementations -------------------------------------------------------


@pytest.fixture(params=["memory", "database"])
def store(request, tmp_path):
    """Both implementations, through one set of tests.

    The move `tests/test_storage.py` makes for images, for the same reason: a Protocol is only
    worth having if its implementations are interchangeable, and running identical assertions
    against each is how that stops being a belief.
    """
    if request.param == "memory":
        yield InMemoryJobStore()
        return

    from app.db.models import Base
    from app.db.session import build_engine, session_factory

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    Base.metadata.create_all(engine)
    yield DatabaseJobStore(session_factory(engine))
    engine.dispose()


async def test_a_job_is_readable_by_its_owner(store):
    job = await store.create(make_job())

    assert (await store.get("user_1", job.job_id)) == job


async def test_another_users_job_is_not_readable_even_with_its_id(store):
    """A job id is unguessable and still not a capability.

    Same rule as every repository read: the scope is a parameter, not an assumption about
    how hard the identifier is to find.
    """
    job = await store.create(make_job(user_id="user_owner"))

    assert await store.get("user_other", job.job_id) is None


async def test_a_missing_job_reads_as_none(store):
    assert await store.get("user_1", "job_nope") is None


async def test_updating_replaces_fields_and_moves_the_timestamp(store):
    job = await store.create(make_job())

    updated = await store.update(job.job_id, status=JobStatus.COMPLETED, result_id="item_1")

    assert updated is not None
    assert updated.status is JobStatus.COMPLETED
    assert updated.result_id == "item_1"
    assert updated.updated_at >= job.updated_at
    assert updated.created_at == job.created_at


async def test_advancing_a_queued_job_marks_it_processing(store):
    job = await store.create(make_job())

    advanced = await store.advance(job.job_id, STAGES[1])

    assert advanced is not None
    assert advanced.status is JobStatus.PROCESSING
    assert advanced.stage == STAGES[1]


async def test_updating_a_job_that_does_not_exist_is_not_an_error(store):
    assert await store.update("job_nope", status=JobStatus.FAILED) is None


async def test_a_job_record_is_immutable_so_a_poller_never_sees_a_half_update(store):
    """Frozen and replaced rather than mutated.

    A poller reading a record while a background task set `status=completed` but had not yet
    set `result_id` would see a finished job with nothing to fetch.
    """
    job = await store.create(make_job())
    held = await store.get("user_1", job.job_id)

    await store.update(job.job_id, status=JobStatus.COMPLETED)

    assert held is not None
    assert held.status is JobStatus.QUEUED  # the reference the poller holds did not change


async def test_a_named_gap_survives_the_round_trip(store):
    """A composition that cannot fill a role answers inline, in `result`, with no row to fetch.

    The database store has to carry that payload intact or the product silently loses its
    honest answer — "your wardrobe needs footwear" — and the client shows a generic failure.
    """
    job = await store.create(make_job(type=JobType.COMPOSE_OUTFIT))
    gap = {"missing_roles": ["footwear"], "wardrobe_gaps": [{"item": "white leather sneaker"}]}

    await store.update(job.job_id, status=JobStatus.COMPLETED, result=gap)
    read = await store.get("user_1", job.job_id)

    assert read is not None
    assert read.type is JobType.COMPOSE_OUTFIT
    assert read.result == gap


async def test_a_failure_keeps_its_code_message_and_whether_to_retry(store):
    """The card shows the classifier's message and offers a retry only when it said to."""
    job = await store.create(make_job())

    await store.update(
        job.job_id,
        status=JobStatus.FAILED,
        error_code="EXTRACTION_FAILED",
        error_message="We couldn't read that garment clearly.",
        retryable=True,
        attempt=2,
    )
    read = await store.get("user_1", job.job_id)

    assert read is not None
    assert (read.error_code, read.retryable, read.attempt) == ("EXTRACTION_FAILED", True, 2)
    assert read.error_message == "We couldn't read that garment clearly."


async def test_a_job_written_by_one_process_is_read_and_finished_by_another(tmp_path):
    """The property the database store exists for, without HTTP in the way.

    Two stores, each with its own engine, over one database — which is what two replicas are.
    One creates and advances; the other reads the progress and records the result; the first
    sees it. `InMemoryJobStore` cannot pass this, and that is not a limitation to work around:
    it is the 404 a user saw on the deployed site.
    """
    from app.db.models import Base
    from app.db.session import build_engine, session_factory

    url = f"sqlite+pysqlite:///{(tmp_path / 'shared.db').as_posix()}"
    first_engine, second_engine = build_engine(url), build_engine(url)
    Base.metadata.create_all(first_engine)
    first = DatabaseJobStore(session_factory(first_engine))
    second = DatabaseJobStore(session_factory(second_engine))

    try:
        job = await first.create(make_job())
        await first.advance(job.job_id, STAGES[2])

        seen = await second.get("user_1", job.job_id)
        assert seen is not None
        assert seen.stage == STAGES[2]

        await second.update(job.job_id, status=JobStatus.COMPLETED, result_id="item_9")
        finished = await first.get("user_1", job.job_id)
        assert finished is not None
        assert (finished.status, finished.result_id) == (JobStatus.COMPLETED, "item_9")
    finally:
        first_engine.dispose()
        second_engine.dispose()


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
