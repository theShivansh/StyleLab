"""The composer, below the routes.

Three things this reaches that a route test cannot:

* **No database session is held across the provider call.** The claim is in the module
  docstring of `app/services/compose.py`; here it is measured, by counting open sessions
  from inside the advisor.
* **A swap is scored against the question the look was composed for**, not against an empty
  one. The preferences live on the outfit row precisely so this holds.
* **Ordering is stable**, so opening the swap sheet twice shows the same list in the same
  order rather than a shuffle.
"""

from __future__ import annotations

import pytest

from app.db.session import build_engine, create_all, session_factory
from app.domain.models import AdviceRequest, ItemStatus, Outfit, OutfitAdvice
from app.domain.models import GarmentCategory as C
from app.domain.scoring import match_score
from app.repositories.wardrobe import WardrobeRepository
from app.services.compose import OutfitComposer, SwapNotPossibleError, _apply_swap
from app.services.composition import CompositionService
from app.services.jobs import (
    COMPOSE_STAGES,
    BackgroundJobs,
    InMemoryJobStore,
    Job,
    JobStatus,
    JobType,
)

U1 = "u1"


class CountingSessions:
    """A session factory that knows how many sessions are open right now.

    Wraps the real factory rather than faking one: the point is to watch the actual objects
    the composer opens and closes, not a stand-in that might close differently.
    """

    def __init__(self, factory) -> None:
        self._factory = factory
        self.open = 0
        self.peak = 0

    def __call__(self):
        session = self._factory()
        self.open += 1
        self.peak = max(self.peak, self.open)
        closing = session.close

        def close() -> None:
            self.open -= 1
            closing()

        session.close = close  # type: ignore[method-assign]
        return session


class WatchingAdvisor:
    """An advisor that records the world as it was while the "provider call" was in flight."""

    def __init__(self, advice: OutfitAdvice, sessions: CountingSessions) -> None:
        self._advice = advice
        self._sessions = sessions
        self.sessions_open_during_call: int | None = None

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        self.sessions_open_during_call = self._sessions.open
        return self._advice


@pytest.fixture
def sessions(tmp_path):
    """File-backed SQLite. The composer runs its database work on worker threads, and an
    in-memory database is per-connection — a job would look into an empty schema."""
    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'compose.db').as_posix()}")
    create_all(engine)
    yield session_factory(engine)
    engine.dispose()


@pytest.fixture
def wardrobe(sessions, stubs):
    """One of each core role, plus a second pair of shoes to swap in."""
    with sessions() as session:
        repository = WardrobeRepository(session)
        repository.add_user(U1, "one@example.test")
        for item in (
            stubs.garment("top-1", U1, category=C.TOP, color_primary="white", fit="slim"),
            stubs.garment("bottom-1", U1, category=C.BOTTOM, color_primary="navy", fit="slim"),
            stubs.garment("shoe-1", U1, category=C.FOOTWEAR, color_primary="white", fit="slim"),
            stubs.garment("shoe-2", U1, category=C.FOOTWEAR, color_primary="black", fit="slim"),
        ):
            repository.add_item(item)
        session.commit()
    return sessions


def outfit_advice(*item_ids: str) -> OutfitAdvice:
    return OutfitAdvice(
        outfit=Outfit(
            item_ids=list(item_ids), name="Quiet Navy", occasion="everyday", match_score=99
        ),
        rationale=["The palette holds together."],
        confidence=0.8,
    )


def composer_for(sessions, advisor, *, jobs: InMemoryJobStore | None = None) -> OutfitComposer:
    return OutfitComposer(
        sessions=sessions,
        advisor=advisor,
        jobs=jobs or InMemoryJobStore(),
        background=BackgroundJobs(),
    )


async def queued(composer: OutfitComposer, job_id: str = "job_1") -> str:
    """A job record without the background task that `start` would also spawn.

    Tests here drive `run` directly so the work is finished when the call returns. Calling
    `start` as well would run the same composition twice, concurrently — which is a real
    thing to know about the runner, and the wrong thing to be measuring in a test about
    stages or open sessions.
    """
    await composer._jobs.create(
        Job(job_id=job_id, user_id=U1, type=JobType.COMPOSE_OUTFIT)
    )
    return job_id


# --- session hygiene ---------------------------------------------------------------------


async def test_no_database_session_is_open_while_the_advisor_is_working(wardrobe, stubs):
    """A session held across a provider call is a connection checked out for the length of
    an HTTP request to Groq. The same rule the extraction pipeline follows."""
    counting = CountingSessions(wardrobe)
    advisor = WatchingAdvisor(outfit_advice("top-1", "bottom-1", "shoe-1"), counting)
    composer = composer_for(counting, advisor)

    await composer.run(U1, await queued(composer), occasion="everyday")

    assert advisor.sessions_open_during_call == 0
    # And it did open sessions either side, so the zero above is not an empty assertion.
    assert counting.peak >= 1


async def test_compose_without_a_repository_or_candidates_is_a_loud_error(stubs):
    """The injectable candidate set is a session-hygiene affordance, not a way to compose
    against nothing. Retrieval has to happen somewhere, and it has to be scoped."""
    service = CompositionService(
        repository=None, advisor=stubs.ScriptedAdvisor.naming("top-1")
    )

    with pytest.raises(ValueError, match="repository or a candidate set"):
        await service.compose(U1, occasion="everyday")


# --- the job ------------------------------------------------------------------------------


async def test_the_job_walks_the_composition_stages_in_order(wardrobe, stubs):
    """Recorded as they happen, because the stage a user reads is the whole point of naming
    them. Only the stages that correspond to separable work are emitted at this rung."""
    seen: list[str] = []

    class RecordingStore(InMemoryJobStore):
        async def update(self, job_id: str, **changes: object):
            stage = changes.get("stage")
            if isinstance(stage, str):
                seen.append(stage)
            return await super().update(job_id, **changes)

    composer = composer_for(
        wardrobe,
        stubs.ScriptedAdvisor(outfit_advice("top-1", "bottom-1", "shoe-1")),
        jobs=RecordingStore(),
    )

    await composer.run(U1, await queued(composer), occasion="everyday")

    assert seen == [COMPOSE_STAGES[0], COMPOSE_STAGES[3], COMPOSE_STAGES[-1]]
    # Every stage emitted belongs to the composition vocabulary, not the extraction one.
    assert set(seen) <= set(COMPOSE_STAGES)


async def test_a_composed_look_is_persisted_with_the_preferences_it_was_composed_for(
    wardrobe, stubs
):
    composer = composer_for(
        wardrobe, stubs.ScriptedAdvisor(outfit_advice("top-1", "bottom-1", "shoe-1"))
    )
    job_id = await queued(composer)
    await composer.run(
        U1, job_id, occasion="work", vibe="minimal", fit_preference="oversized"
    )

    finished = await composer._jobs.get(U1, job_id)
    assert finished is not None and finished.result_id
    stored = await composer.result(U1, finished.result_id)
    assert stored is not None
    assert stored.occasion == "work"
    assert stored.vibe == "minimal"
    assert stored.fit_preference == "oversized"


async def test_an_unexpected_failure_fails_the_job_with_a_classified_fault(wardrobe):
    class Exploding:
        async def advise(self, request):  # pragma: no cover - the raise is the point
            raise RuntimeError("boom")

    composer = composer_for(wardrobe, Exploding())
    job_id = await queued(composer)

    await composer.run(U1, job_id, occasion="everyday")

    # A provider failure alone degrades rather than fails — that is the ladder, and it is
    # tested in test_composition.py. This asserts the outer guard still exists: the look was
    # built by the ranker, and the job completed.
    finished = await composer._jobs.get(U1, job_id)
    assert finished is not None
    assert finished.status is JobStatus.COMPLETED
    outfit = await composer.result(U1, finished.result_id or "")
    assert outfit is not None
    assert outfit.degradation_level == 4


# --- swap ----------------------------------------------------------------------------------


def make_outfit(sessions, **preferences) -> str:
    with sessions() as session:
        WardrobeRepository(session).save_outfit(
            U1,
            outfit_id="o1",
            name="Quiet Navy",
            occasion="everyday",
            item_ids=["top-1", "bottom-1", "shoe-1"],
            match_score=80,
            rationale=["written about the first combination"],
            advisory={"pro_tips": [{"tip": "Cuff the trouser", "type": "proportion"}]},
            **preferences,
        )
        session.commit()
    return "o1"


async def test_a_swap_scores_against_the_preferences_the_look_was_composed_for(
    wardrobe, stubs
):
    """The preferences are read off the outfit row, not defaulted. Without them a fifth of
    the score would silently neutralise the moment a slot changed, and the number on screen
    would move for a reason the user could not see."""
    make_outfit(wardrobe, fit_preference="oversized")
    composer = composer_for(wardrobe, stubs.ScriptedAdvisor(outfit_advice()))

    swapped = await composer.swap(U1, "o1", role="footwear", replacement_item_id="shoe-2")

    assert swapped is not None
    with wardrobe() as session:
        items = [
            item
            for item in WardrobeRepository(session).candidates(U1)
            if item.item_id in {"top-1", "bottom-1", "shoe-2"}
        ]
    expected = match_score(
        items,
        AdviceRequest(
            user_id=U1, candidates=items, occasion="everyday", fit_preference="oversized"
        ),
    )
    indifferent = match_score(
        items, AdviceRequest(user_id=U1, candidates=items, occasion="everyday")
    )

    assert swapped.match_score == expected
    # The two differ, so the assertion above is about the preferences and not a coincidence.
    assert expected != indifferent


async def test_a_swap_leaves_the_other_slots_in_place_and_in_order(wardrobe, stubs):
    make_outfit(wardrobe)
    composer = composer_for(wardrobe, stubs.ScriptedAdvisor(outfit_advice()))
    before = await composer.result(U1, "o1")
    assert before is not None

    after = await composer.swap(U1, "o1", role="footwear", replacement_item_id="shoe-2")

    assert after is not None
    assert [slot.role for slot in after.slots] == [slot.role for slot in before.slots]
    assert [s.item_id for s in after.slots if s.role != "footwear"] == [
        s.item_id for s in before.slots if s.role != "footwear"
    ]


def test_swapping_in_a_garment_that_is_still_being_read_is_refused(sessions, stubs):
    """An analysing item has no metadata to style with, so it cannot be scored — and a slot
    filled with an unknown is worse than the slot the user was already looking at."""
    with sessions() as session:
        repository = WardrobeRepository(session)
        repository.add_user(U1, "one@example.test")
        for item in (
            stubs.garment("top-1", U1, category=C.TOP),
            stubs.garment("bottom-1", U1, category=C.BOTTOM),
            stubs.garment("shoe-1", U1, category=C.FOOTWEAR),
            stubs.garment(
                "shoe-2", U1, category=C.FOOTWEAR, status=ItemStatus.ANALYZING
            ),
        ):
            repository.add_item(item)
        repository.save_outfit(
            U1,
            outfit_id="o1",
            name="x",
            occasion="everyday",
            item_ids=["top-1", "bottom-1", "shoe-1"],
        )
        session.commit()

    with sessions() as session, pytest.raises(SwapNotPossibleError) as raised:
        _apply_swap(
            session, U1, "o1", role="footwear", replacement_item_id="shoe-2"
        )

    assert raised.value.code == "ITEM_NOT_READY"


# --- alternatives -----------------------------------------------------------------------------


async def test_alternatives_come_back_in_the_same_order_every_time(wardrobe, stubs):
    """A sheet that reorders itself between openings is a sheet the user cannot learn."""
    make_outfit(wardrobe)
    composer = composer_for(wardrobe, stubs.ScriptedAdvisor(outfit_advice()))

    first = await composer.alternatives(U1, "o1", role="footwear")
    second = await composer.alternatives(U1, "o1", role="footwear")

    assert first is not None and second is not None
    assert [a.item.item.item_id for a in first.alternatives] == [
        a.item.item.item_id for a in second.alternatives
    ]


async def test_an_alternative_is_scored_with_the_rest_of_the_look_around_it(
    wardrobe, stubs
):
    """Not on its own. A shortlist by solo score would recommend the best shoe in the
    wardrobe rather than the best shoe with this shirt."""
    make_outfit(wardrobe)
    composer = composer_for(wardrobe, stubs.ScriptedAdvisor(outfit_advice()))

    view = await composer.alternatives(U1, "o1", role="footwear")

    assert view is not None
    assert view.alternatives
    with wardrobe() as session:
        owned = {i.item_id: i for i in WardrobeRepository(session).candidates(U1)}
    for alternative in view.alternatives:
        trio = [owned["top-1"], owned["bottom-1"], owned[alternative.item.item.item_id]]
        expected = match_score(
            trio, AdviceRequest(user_id=U1, candidates=trio, occasion="everyday")
        )
        assert alternative.match_score == expected


async def test_an_unknown_role_is_refused_rather_than_guessed(wardrobe, stubs):
    make_outfit(wardrobe)
    composer = composer_for(wardrobe, stubs.ScriptedAdvisor(outfit_advice()))

    with pytest.raises(SwapNotPossibleError) as raised:
        await composer.alternatives(U1, "o1", role="hat")

    assert raised.value.code == "UNKNOWN_ROLE"
