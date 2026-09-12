"""Job status — the endpoint that makes async work observable.

docs/API-SPEC.md gives it a `stage` and a `progress`, and prompt 05 makes "job status is
observable" an acceptance criterion. The interesting part of that criterion is not that the
endpoint exists; it is that the stage names real work (`app/services/jobs.py`).

Scoped like everything else. A job id is a random 16-byte hex string and still not a
capability: `JobStore.get` takes `user_id` and returns `None` for another user's job, so
polling someone else's extraction answers 404 the same way a wardrobe item does.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.deps import CurrentUser, FaultError, Jobs
from app.routers.serialization import job_payload
from app.services.faults import Fault

router = APIRouter(tags=["jobs"])

JOB_NOT_FOUND = Fault(
    "ITEM_NOT_FOUND", "We couldn't find that job.", retryable=False, status=404
)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user_id: CurrentUser, jobs: Jobs) -> dict[str, Any]:
    """One job's status.

    404 rather than 410 for a job the process no longer holds. In-memory job records do not
    survive a restart (blocker B14), and a poller that meets a restart should give up on the
    job and re-read the item rather than treat the gap as a distinct state to handle.
    """
    job = await jobs.get(user_id, job_id)
    if job is None:
        raise FaultError(JOB_NOT_FOUND)
    return job_payload(job)


__all__ = ["router"]
