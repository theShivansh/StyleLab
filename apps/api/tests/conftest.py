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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


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
