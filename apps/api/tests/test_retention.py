"""Deletion, and the part of it that was not true until S11.

Blocker B16, open since S6: `deleted_at` stopped a photograph being served and left the
bytes on disk with nothing scheduled to remove them. "Delete my photographs" was a statement
about a database column.

Two halves are tested here. The **bulk delete** is the right docs/SECURITY-PRIVACY.md has
asked for since S0 — *"a user must be able to remove their entire wardrobe in one action"* —
and the **sweep** is what eventually makes any deletion true at the filesystem level.

The clock is passed in rather than waited out. A thirty-day window tested by sleeping is a
test nobody runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import AssetRow
from app.repositories.wardrobe import AssetRepository, WardrobeRepository
from app.services.retention import RETENTION_WINDOW_S, purge_expired
from app.services.storage import LocalObjectStore, StorageError
from tests.support import make_image

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def caller(api, stubs):
    api.transport_double.default = stubs.fixture("extraction_success.json")
    return api.start_session()


def upload(api, caller, count: int = 1):
    files = [
        (
            "images[]",
            (f"shirt{index}.png", make_image(fmt="PNG", colour=(index, 60, 90)), "image/png"),
        )
        for index in range(count)
    ]
    return api.post("/api/v1/wardrobe/items", files=files, headers=caller.headers)


# --- the whole wardrobe, in one action -------------------------------------------------------


def test_a_user_can_remove_their_entire_wardrobe_in_one_request(api, caller, wait_for_job):
    """The sentence docs/SECURITY-PRIVACY.md has carried since S0.

    Before S11 the only deletion was per item, so exercising this right meant one request per
    photograph and trusting that none was missed.
    """
    body = upload(api, caller, count=3).json()
    for item in body["items"]:
        wait_for_job(caller.headers, item["job_id"])

    response = api.delete("/api/v1/wardrobe/items", headers=caller.headers)

    assert response.status_code == 200
    assert response.json()["items"] == 3
    assert response.json()["assets"] == 3
    assert api.get("/api/v1/wardrobe/items", headers=caller.headers).json()["items"] == []


def test_the_response_states_the_retention_window_rather_than_implying_the_bytes_are_gone(
    api, caller, wait_for_job
):
    """Soft deletion is the honest default and it has to be said out loud.

    A response of `{"deleted": true}` invites the reading that the photographs are gone.
    They are not — they are recoverable for thirty days, which is a feature and only a
    feature if the user is told.
    """
    upload(api, caller)

    body = api.delete("/api/v1/wardrobe/items", headers=caller.headers).json()

    assert body["images_erased_after_days"] == RETENTION_WINDOW_S // 86400 == 30


def test_clearing_a_wardrobe_cannot_reach_another_users(api, stubs, wait_for_job):
    """The one property that would make this endpoint catastrophic rather than convenient."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    mine = api.start_session()
    theirs = api.start_session()
    upload(api, mine)
    body = upload(api, theirs).json()["items"][0]
    wait_for_job(theirs.headers, body["job_id"])

    api.delete("/api/v1/wardrobe/items", headers=mine.headers)

    assert len(api.get("/api/v1/wardrobe/items", headers=theirs.headers).json()["items"]) == 1


def test_clearing_an_empty_wardrobe_is_a_success_with_nothing_in_it(api, caller):
    """Not a 404. The user asked for their wardrobe to be empty and it is."""
    response = api.delete("/api/v1/wardrobe/items", headers=caller.headers)

    assert response.status_code == 200
    assert response.json() == {
        "deleted": True,
        "items": 0,
        "assets": 0,
        "affected_outfits": 0,
        "images_erased_after_days": 30,
    }


def test_clearing_a_wardrobe_needs_a_session(api):
    assert api.delete("/api/v1/wardrobe/items").status_code == 401


# --- the sweep --------------------------------------------------------------------------------


def stored_asset(session, store_root, *, user_id: str, asset_id: str, deleted_ago_days: float):
    """One asset with real bytes on disk and a chosen deletion date."""
    key = f"{user_id}/{asset_id}.png"
    path = store_root / user_id
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{asset_id}.png").write_bytes(b"pretend-jpeg-bytes")

    session.add(
        AssetRow(
            id=asset_id,
            user_id=user_id,
            storage_key=key,
            mime_type="image/png",
            byte_size=18,
            deleted_at=NOW - timedelta(days=deleted_ago_days),
        )
    )
    session.flush()
    return key


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(tmp_path / "uploads")


@pytest.fixture
def sessions(engine):
    from app.db.session import session_factory

    return session_factory(engine)


def add_user(sessions, user_id: str) -> None:
    with sessions() as session:
        WardrobeRepository(session).add_user(user_id, f"{user_id}@anonymous.invalid")
        session.commit()


async def test_bytes_outlive_the_request_and_not_the_window(sessions, store):
    """The whole point. A photograph deleted long enough ago stops existing."""
    add_user(sessions, "u1")
    with sessions() as session:
        key = stored_asset(session, store.root, user_id="u1", asset_id="a1", deleted_ago_days=31)
        session.commit()
    assert await store.exists(key)

    report = await purge_expired(sessions, store, now=NOW)

    assert report.purged == 1
    assert not await store.exists(key)


async def test_a_photograph_inside_the_window_is_left_alone(sessions, store):
    """The grace period is the reason deletion is soft at all.

    Unlinking on the tap would make `deleted_at` a record of something irreversible, which
    docs/DATA-MODEL.md specifically does not want.
    """
    add_user(sessions, "u1")
    with sessions() as session:
        key = stored_asset(session, store.root, user_id="u1", asset_id="a1", deleted_ago_days=29)
        session.commit()

    report = await purge_expired(sessions, store, now=NOW)

    assert report.purged == 0
    assert await store.exists(key)


async def test_a_live_photograph_is_never_touched(sessions, store):
    add_user(sessions, "u1")
    with sessions() as session:
        key = "u1/a1.png"
        (store.root / "u1").mkdir(parents=True, exist_ok=True)
        (store.root / "u1" / "a1.png").write_bytes(b"bytes")
        session.add(
            AssetRow(id="a1", user_id="u1", storage_key=key, mime_type="image/png", byte_size=5)
        )
        session.commit()

    await purge_expired(sessions, store, now=NOW)

    assert await store.exists(key)


async def test_the_sweep_is_idempotent(sessions, store):
    """Safe to run at boot, on a timer, and twice at once.

    The second run must not re-attempt work it already did — that is what `purged_at` is
    for, and without it every sweep would grow to re-delete every file ever deleted.
    """
    add_user(sessions, "u1")
    with sessions() as session:
        stored_asset(session, store.root, user_id="u1", asset_id="a1", deleted_ago_days=31)
        session.commit()

    assert (await purge_expired(sessions, store, now=NOW)).purged == 1
    assert (await purge_expired(sessions, store, now=NOW)).purged == 0


async def test_it_sweeps_every_user_not_only_the_one_who_asked(sessions, store):
    """The reason it is a timer and not an opportunistic purge on deletion.

    A user who deletes their wardrobe and never comes back is exactly the user whose
    photographs must go, and they are the one who never triggers an opportunistic sweep.
    """
    for user_id in ("u1", "u2", "u3"):
        add_user(sessions, user_id)
        with sessions() as session:
            stored_asset(
                session, store.root, user_id=user_id, asset_id=f"{user_id}-a", deleted_ago_days=31
            )
            session.commit()

    report = await purge_expired(sessions, store, now=NOW)

    assert report.scanned_users == 3
    assert report.purged == 3


async def test_a_store_failure_defers_the_asset_rather_than_marking_it_gone(sessions, store):
    """Unlink, then record — never the other way round.

    A row claiming a file is gone while the file is still there is worse than no row at all,
    because somebody would answer a subject access request from it.
    """

    class RefusingStore:
        root = store.root

        async def delete(self, key: str) -> None:
            raise StorageError("the object store said no")

    add_user(sessions, "u1")
    with sessions() as session:
        stored_asset(session, store.root, user_id="u1", asset_id="a1", deleted_ago_days=31)
        session.commit()

    report = await purge_expired(sessions, RefusingStore(), now=NOW)  # type: ignore[arg-type]

    assert report.failed == 1 and report.purged == 0
    with sessions() as session:
        assert AssetRepository(session).expired(
            "u1", cutoff=NOW - timedelta(seconds=RETENTION_WINDOW_S), limit=10
        ), "a failed purge must remain selectable by the next sweep"


async def test_the_report_names_no_storage_key_and_no_owner(sessions, store):
    """It gets logged.

    A log line naming the storage key of a photograph somebody asked us to delete is a copy
    of the thing we just deleted, in a log aggregator.
    """
    add_user(sessions, "u1")
    with sessions() as session:
        stored_asset(session, store.root, user_id="u1", asset_id="a1", deleted_ago_days=31)
        session.commit()

    report = await purge_expired(sessions, store, now=NOW)

    rendered = repr(report)
    assert "u1" not in rendered and "a1" not in rendered and ".png" not in rendered


async def test_a_batch_is_bounded_so_one_transaction_cannot_run_away(sessions, store):
    add_user(sessions, "u1")
    with sessions() as session:
        for index in range(5):
            stored_asset(
                session, store.root, user_id="u1", asset_id=f"a{index}", deleted_ago_days=31
            )
        session.commit()

    report = await purge_expired(sessions, store, now=NOW, batch_per_user=2)

    assert report.purged == 2
    # Resumable: the rest is picked up next time rather than lost.
    assert (await purge_expired(sessions, store, now=NOW, batch_per_user=2)).purged == 2
