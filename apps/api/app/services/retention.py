"""Retention — the sweep that makes deletion true on disk.

Blocker B16, open since S6. `DELETE /wardrobe/items/{id}` sets `deleted_at` on the item and
the asset, the file stops being served, and the bytes stay exactly where they were. That was
a deliberate trade — docs/DATA-MODEL.md wants deletion observable and reversible by support,
and a file unlinked the instant somebody taps a button makes the row a record of something
that cannot be undone.

The trade is only honest with the other half built. Without it, "delete my photographs" is
a statement about a database column, and the photographs are still on a disk, forever, with
nothing scheduled to change that. This module is the other half.

## The window

`RETENTION_WINDOW_S` is the gap between "the user asked" and "the bytes are gone". Long
enough that an accidental deletion is recoverable by a human; short enough that it is a
grace period rather than a filing cabinet. Thirty days, matching what the privacy copy
tells the user, because a retention period the product does not state is one the user has
not agreed to.

## Why it enumerates owners instead of asking one question

The natural query is "every asset anywhere whose window has closed". It is also precisely
the unscoped read path `tests/test_query_scoping.py` exists to prevent — a maintenance job
is exactly the "admin or debug" exception prompts/04 refuses to allow. So the sweep lists
owners and asks the ownership-scoped repository once per owner.

Reading the set of *owners* is not reading owned data, which is why that is allowed here and
`select(AssetRow)` is not allowed anywhere. It costs a query per user per sweep, and at this
project's scale that is not a price worth arguing about.

## Order of operations

Unlink the bytes, **then** record it. The other order leaves a row claiming a file is gone
while the file is still there, and somebody would eventually answer a subject access request
from that row. A store failure is logged and the asset is left for the next sweep, which is
the whole reason `purged_at` is a column rather than an inference.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import UserRow
from app.repositories.wardrobe import AssetRepository
from app.services.storage import ObjectStore, StorageError

logger = logging.getLogger("stylelab.retention")

#: How long a deleted photograph stays recoverable. Stated in the privacy copy, so changing
#: it here without changing that is changing the terms without telling anyone.
RETENTION_WINDOW_S = 30 * 24 * 60 * 60

#: Assets unlinked per user per sweep. Bounds one transaction, not the total work — the next
#: sweep picks up whatever is left, because `purged_at` makes the sweep resumable.
BATCH_PER_USER = 200


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """What a sweep did. Counts only — never a storage key, never an owner.

    This gets logged, and a log line naming the storage key of a photograph somebody asked
    us to delete would be a copy of the thing we just deleted, in a log aggregator, which is
    the sort of irony that ends up in an incident report.
    """

    scanned_users: int
    purged: int
    failed: int

    @property
    def did_anything(self) -> bool:
        return bool(self.purged or self.failed)


async def purge_expired(
    sessions: sessionmaker[Session],
    store: ObjectStore,
    *,
    window_s: float = RETENTION_WINDOW_S,
    now: datetime | None = None,
    batch_per_user: int = BATCH_PER_USER,
) -> PurgeReport:
    """Unlink the bytes of every asset whose retention window has closed.

    Idempotent: an asset already purged is not selected again, and a store that has already
    forgotten a key is not an error. Safe to run at boot, on a timer, and twice at once.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=window_s)
    purged = 0
    failed = 0

    user_ids = _owners(sessions)
    for user_id in user_ids:
        with sessions() as session:
            assets = AssetRepository(session).expired(
                user_id, cutoff=cutoff, limit=batch_per_user
            )

        for asset in assets:
            try:
                await store.delete(asset.storage_key)
            except StorageError:
                # Left for the next sweep rather than marked. The asset id is safe to log —
                # it is opaque and names no file — and the storage key is not.
                logger.warning(
                    "retention: could not unlink an expired asset; it will be retried",
                    extra={"asset_id": asset.asset_id},
                )
                failed += 1
                continue

            with sessions() as session:
                AssetRepository(session).mark_purged(user_id, asset.asset_id, at=cutoff)
                session.commit()
            purged += 1

    report = PurgeReport(scanned_users=len(user_ids), purged=purged, failed=failed)
    if report.did_anything:
        logger.info(
            "retention sweep: %d purged, %d deferred across %d users",
            report.purged,
            report.failed,
            report.scanned_users,
        )
    return report


def _owners(sessions: sessionmaker[Session]) -> list[str]:
    """Every user id, so the sweep can ask the scoped repository once per owner.

    The only read in the application that is not scoped to a user, and it reads the *users*
    table — the set of owners, not anything they own. Every asset, item and outfit this
    sweep touches is still fetched through `_scoped_select`.
    """
    with sessions() as session:
        return list(session.execute(select(UserRow.id)).scalars())


class RetentionSweeper:
    """Runs the sweep at boot and then on an interval.

    A timer rather than an opportunistic purge on each deletion. The opportunistic version
    is less code and answers the wrong question: a user who deletes their wardrobe and never
    returns is exactly the user whose photographs must go, and they are the one who never
    triggers it.

    In-process, so it belongs to one instance — the same seam and the same limitation as
    `BackgroundJobs` (blocker B14). Two replicas would both sweep, which is harmless because
    the sweep is idempotent, and zero replicas would not, which is why a deployment that
    scales to zero needs this run as a scheduled job instead. Said in docs/DEPLOYMENT.md
    rather than assumed.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        store: ObjectStore,
        *,
        window_s: float = RETENTION_WINDOW_S,
        interval_s: float = 60 * 60,
    ) -> None:
        self._sessions = sessions
        self._store = store
        self._window_s = window_s
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _loop(self) -> None:
        while True:
            try:
                await purge_expired(self._sessions, self._store, window_s=self._window_s)
            except Exception:
                # A sweep that raises must not take the loop with it. The next one is an
                # hour away and the data is still there to find; a dead sweeper is silent
                # and permanent.
                logger.exception("retention sweep failed; will retry on the next interval")
            await asyncio.sleep(self._interval_s)


__all__ = [
    "BATCH_PER_USER",
    "RETENTION_WINDOW_S",
    "PurgeReport",
    "RetentionSweeper",
    "purge_expired",
]
