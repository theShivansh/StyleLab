import os

import pytest

# The app refuses to boot without a key, by design. Tests supply a fake one: this is a test
# double for an external dependency, not a demo mode. No real call is made from this suite.
os.environ.setdefault("GROQ_API_KEY", "test-key-not-a-real-credential")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
