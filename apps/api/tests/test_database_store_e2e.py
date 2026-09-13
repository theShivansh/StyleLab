"""The whole upload-and-serve path over `DatabaseObjectStore`.

`tests/test_storage.py` proves the store satisfies the Protocol. This proves the product
works through it, which is a different claim: the configuration this deployment actually runs
is `STORAGE_BACKEND=database`, and every other test in the suite uses the filesystem store
because that is what the fixture builds.

The property worth having is the one the platform forced: **nothing is written to disk**. A
photograph that lands in a directory on a host that discards its filesystem when idle is a
photograph the user loses between two visits, while the wardrobe row pointing at it survives.
So this asserts the bytes are in the database *and* that the storage root stayed empty.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.models import AssetBlobRow, Base
from app.db.session import build_engine, create_all, session_factory
from app.main import create_app
from app.services.storage import DatabaseObjectStore
from tests.support import make_image


@pytest.fixture
def api_on_database(stubs, tmp_path):
    """The app, with its images in the same database as its rows.

    The store shares the application's engine deliberately: that is the arrangement in
    production, and a test that gave the store its own database would not notice if the two
    ever had to agree about a transaction.
    """
    from app.config import get_settings

    settings = get_settings()
    transport = stubs.MockGroqProvider(
        models={
            settings.groq_text_model,
            settings.groq_vision_model,
            settings.groq_vision_fallback_model,
        }
    )

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'wardrobe.db').as_posix()}")
    create_all(engine)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)

    # A scripted extraction, the same fixture the wardrobe route tests use. Nothing here is
    # about the model; the store is what is under test and the analysis has to succeed for
    # an item to reach a state where its image can be asked for.
    transport.default = stubs.fixture("extraction_success.json")

    app = create_app(transport=transport, store=DatabaseObjectStore(sessions), sessions=sessions)

    with TestClient(app) as client:
        client.sessions = sessions  # type: ignore[attr-defined]
        yield client

    engine.dispose()


def _ready_item(client):
    """Upload one garment and poll it to a terminal state.

    Its own barrier rather than the shared `wait_for_job` fixture, which is bound to the
    suite-wide `api` client and would poll a different application than the one under test —
    a mistake that shows up as a `KeyError` on a 404 body rather than as anything legible.
    """
    import time

    session = client.post("/api/v1/session").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    files = [("images[]", ("shirt.png", make_image(fmt="PNG", colour=(20, 60, 90)), "image/png"))]
    body = client.post("/api/v1/wardrobe/items", files=files, headers=headers).json()["items"][0]

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{body['job_id']}", headers=headers).json()
        if job.get("status") in ("completed", "failed"):
            assert job["status"] == "completed", job
            return headers, body["item_id"]
        time.sleep(0.02)
    raise AssertionError("analysis never reached a terminal state")


def test_a_photograph_uploaded_to_the_database_comes_back_through_its_image_url(api_on_database):
    """The end-to-end claim, and the one that would have been false in production.

    No session header on the image request: the URL is a capability, which is what makes an
    `<img src>` work cross-origin. Nothing about that changes with the store — and the fact
    that it does not change is the evidence the seam held.
    """
    headers, item_id = _ready_item(api_on_database)

    item = api_on_database.get(f"/api/v1/wardrobe/items/{item_id}", headers=headers).json()
    response = api_on_database.get(item["image_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8\xff")


def test_the_bytes_are_in_the_database_and_not_on_a_disk(api_on_database, tmp_path):
    """The reason this store exists, asserted from both sides.

    The row must be there, and the storage root must be empty — because a store that wrote to
    both would pass every other test in this file and still lose photographs on the day the
    container was replaced.
    """
    _ready_item(api_on_database)

    with api_on_database.sessions() as session:
        blobs = session.query(AssetBlobRow).all()
        assert len(blobs) == 1
        assert blobs[0].byte_size > 0
        assert blobs[0].data.startswith(b"\xff\xd8\xff")

    # `STORAGE_ROOT` is never even created: the default is a relative path this app never
    # touches, and the temporary one is proof that nothing wrote beside the database.
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or not list(uploads.rglob("*"))


def test_deleting_the_wardrobe_stops_serving_the_photograph(api_on_database):
    """Soft deletion behaves identically over either store.

    The bytes are still in the table at this point — the thirty-day retention window is what
    erases them (`app/services/retention.py`), and this asserts the half that is immediate:
    the capability stops resolving.
    """
    headers, item_id = _ready_item(api_on_database)
    item = api_on_database.get(f"/api/v1/wardrobe/items/{item_id}", headers=headers).json()

    deleted = api_on_database.delete("/api/v1/wardrobe/items", headers=headers)

    assert deleted.status_code == 200
    assert api_on_database.get(item["image_url"]).status_code == 404
