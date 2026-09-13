"""An upload on one instance, polled on another — the first bug the live deployment found.

The deployed site showed an upload card failing with "That item isn't in your wardrobe" for a
photograph that was, at that moment, being read. Nothing was wrong with the photograph, the
model or the database. The upload had reached one process and the poll after it another, and
job records lived in the memory of the first.

These tests build two complete applications over one database — which is what a gradual
rollout or a second replica is — and send the upload to one and every poll to the other. The
first test reproduces the failure with the in-memory store, so the diagnosis is a fact in the
suite rather than a story in a commit message. The second shows the database store closing it.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.db.session import build_engine, create_all, session_factory
from app.main import create_app
from app.services.storage import DatabaseObjectStore
from tests.support import make_image


@pytest.fixture
def instances(stubs, tmp_path, monkeypatch):
    """A factory for two applications sharing one database and one signing key.

    The shared `SESSION_SECRET` is not incidental. Without it the second instance would refuse
    the first one's token with a 401, which is a different production failure (preflight makes
    it fatal) and would mask the one under test.
    """
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "session_secret", "s" * 48)

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'shared.db').as_posix()}")
    create_all(engine)
    sessions = session_factory(engine)
    opened: list[TestClient] = []

    def build(job_backend: str) -> tuple[TestClient, TestClient]:
        monkeypatch.setattr(settings, "job_backend", job_backend)

        def one() -> TestClient:
            transport = stubs.MockGroqProvider(
                models={
                    settings.groq_text_model,
                    settings.groq_vision_model,
                    settings.groq_vision_fallback_model,
                }
            )
            transport.default = stubs.fixture("extraction_success.json")
            client = TestClient(
                create_app(
                    transport=transport, store=DatabaseObjectStore(sessions), sessions=sessions
                )
            )
            client.__enter__()
            opened.append(client)
            return client

        return one(), one()

    yield build

    for client in reversed(opened):
        client.__exit__(None, None, None)
    engine.dispose()


def _upload_on(instance: TestClient) -> tuple[dict[str, str], dict]:
    token = instance.post("/api/v1/session").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    files = [("images[]", ("shirt.png", make_image(fmt="PNG", colour=(40, 70, 90)), "image/png"))]
    response = instance.post("/api/v1/wardrobe/items", files=files, headers=headers)
    assert response.status_code == 201, response.text
    return headers, response.json()["items"][0]


def test_with_jobs_in_memory_the_other_instance_reports_a_running_job_as_missing(instances):
    """The defect, reproduced. This is the 404 behind the card on the deployed site."""
    uploader, poller = instances("memory")
    headers, item = _upload_on(uploader)

    elsewhere = poller.get(f"/api/v1/jobs/{item['job_id']}", headers=headers)
    here = uploader.get(f"/api/v1/jobs/{item['job_id']}", headers=headers)

    assert here.status_code == 200
    assert elsewhere.status_code == 404
    assert elsewhere.json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_with_jobs_in_the_database_the_other_instance_follows_the_job_to_the_end(instances):
    """The fix, from the user's side of the screen.

    Every poll goes to the instance that did not take the upload, and every one answers 200 —
    through the named stages, to `completed`, to a readable garment and a photograph that loads.
    """
    uploader, poller = instances("database")
    headers, item = _upload_on(uploader)

    statuses: list[int] = []
    job: dict = {}
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        response = poller.get(f"/api/v1/jobs/{item['job_id']}", headers=headers)
        statuses.append(response.status_code)
        job = response.json()
        if job.get("status") in ("completed", "failed"):
            break
        uploader.get("/health")  # give the uploading instance's loop a turn, as live traffic would
        time.sleep(0.02)

    assert set(statuses) == {200}, statuses
    assert job["status"] == "completed", job

    garment = poller.get(f"/api/v1/wardrobe/items/{item['item_id']}", headers=headers)
    assert garment.status_code == 200
    assert garment.json()["status"] == "ready"
    assert poller.get(garment.json()["image_url"]).status_code == 200
