import importlib.util
import os
import sys
from pathlib import Path

import pytest

# The app refuses to boot without a key, by design. Tests supply a fake one: this is a test
# double for an external dependency, not a demo mode. No real call is made from this suite.
os.environ.setdefault("GROQ_API_KEY", "test-key-not-a-real-credential")

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_stubs():
    """Load the canonical stub adapters from `tests/ai/stubs.py` at the repository root.

    They live there because prompts/04 puts stub implementations in `tests/ai/` only, and
    `tests/README.md` forbids moving that directory into either app. Loaded by explicit file
    path rather than by adding the repo root to `sys.path`, because that root also contains a
    `tests` package and the two would collide under one import name.
    """
    path = REPO_ROOT / "tests" / "ai" / "stubs.py"
    spec = importlib.util.spec_from_file_location("stylelab_ai_stubs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def stubs():
    return _load_stubs()


def _mock_transport(stubs):
    from app.config import get_settings

    settings = get_settings()
    return stubs.MockGroqProvider(
        models={
            settings.groq_text_model,
            settings.groq_vision_model,
            settings.groq_vision_fallback_model,
        }
    )


@pytest.fixture
def client(stubs, tmp_path):
    """A TestClient over an app wired to the mock provider.

    Importantly this still runs the real boot checks — `create_app` takes the transport, so
    `verify_models` executes against a scripted model list rather than being skipped. The
    first version of this fixture used the module-level `app`, whose lifespan built the real
    Groq transport and made a live `models.list()` call with the fake key: the suite passed
    (the failure is tolerated by design) but every run took ten seconds and needed a network.
    A unit suite that silently depends on the internet is a unit suite that fails on a train.

    The store and the database are temporary for the same class of reason: left to its
    defaults the lifespan creates `apps/api/stylelab.db` and `apps/api/var/uploads/` in the
    working tree, so running the suite would leave a database behind and a second run would
    inherit the first one's wardrobe.
    """
    from fastapi.testclient import TestClient

    from app.db.session import build_engine, create_all, session_factory
    from app.main import create_app
    from app.services.storage import LocalObjectStore

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'client.db').as_posix()}")
    create_all(engine)

    app = create_app(
        transport=_mock_transport(stubs),
        store=LocalObjectStore(tmp_path / "uploads"),
        sessions=session_factory(engine),
    )
    with TestClient(app) as test_client:
        yield test_client

    engine.dispose()


# --- the HTTP surface, with real storage and a real database -----------------------------


@pytest.fixture
def api(stubs, tmp_path):
    """The whole API over a temporary store and a temporary database.

    The database is a **file**, not `:memory:`. Analysis runs in background tasks and each
    one opens its own session on a worker thread; a SQLite memory database is per-connection,
    so the job would look into an empty schema and the whole pipeline would fail in a way
    that told you nothing about the pipeline.

    Returns the client and a `user` helper carrying the `Authorization` header, because
    every wardrobe route is scoped and a test that forgets the header is testing the 401.
    """
    from dataclasses import dataclass

    from fastapi.testclient import TestClient

    from app.db.session import build_engine, create_all, session_factory
    from app.main import create_app
    from app.services.storage import LocalObjectStore

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'wardrobe.db').as_posix()}")
    create_all(engine)

    app = create_app(
        transport=_mock_transport(stubs),
        store=LocalObjectStore(tmp_path / "uploads"),
        sessions=session_factory(engine),
    )

    @dataclass
    class Caller:
        user_id: str
        headers: dict[str, str]

    with TestClient(app) as test_client:

        def start_session() -> Caller:
            body = test_client.post("/api/v1/session").json()
            return Caller(
                user_id=body["user_id"], headers={"Authorization": f"Bearer {body['token']}"}
            )

        test_client.start_session = start_session  # type: ignore[attr-defined]
        test_client.transport_double = app.state.transport  # type: ignore[attr-defined]
        yield test_client

    engine.dispose()


# --- persistence -------------------------------------------------------------------------


@pytest.fixture
def engine():
    """In-memory SQLite, schema created per test.

    The URL is passed in explicitly: `build_engine` has no default and `get_engine()` raises
    when DATABASE_URL is unset, so nothing can silently run against a throwaway database.
    """
    from app.db.models import Base
    from app.db.session import build_engine

    eng = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    from app.db.session import session_factory

    with session_factory(engine)() as s:
        yield s


@pytest.fixture
def executed(engine):
    """Every statement the engine runs, with its parameters.

    Used by the cross-user isolation test to assert a stronger property than "the wrong item
    was not returned": that it was never asked for. See tests/test_ownership.py.
    """
    from sqlalchemy import event

    log: list[tuple[str, object]] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        log.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    yield log
    event.remove(engine, "before_cursor_execute", record)


@pytest.fixture
def wait_for_job(api):
    """Poll a job to a terminal state, the way the browser does.

    A barrier rather than a sleep. Background analysis runs on the app's event loop in the
    TestClient's portal thread, so it progresses between requests — polling the documented
    endpoint is both the barrier and a test of the endpoint.
    """
    import time

    def wait(headers: dict[str, str], job_id: str, timeout_s: float = 15.0) -> dict:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            body = api.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
            if body["status"] in ("completed", "failed"):
                return body
            time.sleep(0.02)
        raise AssertionError(f"job {job_id} never reached a terminal state")

    return wait


# --- image fixtures ----------------------------------------------------------------------


@pytest.fixture
def image_bytes():
    from tests.support import make_image

    return make_image


@pytest.fixture
def limits():
    from app.services.ingest import UploadLimits

    return UploadLimits(
        max_bytes=10 * 1024 * 1024,
        max_images_per_batch=12,
        min_edge_px=128,
        max_pixels=40_000_000,
    )
