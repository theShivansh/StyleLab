"""Live-suite configuration.

Every test here makes a real, billed Groq call. Two consequences shape this file:

* **It skips without a key**, rather than failing. A test that cannot run has not found a
  bug. This is the one place in the repository where a missing `GROQ_API_KEY` is not an
  error — and it is a *test* skipping, never the application degrading. The app itself
  refuses to boot without a key (AI-EVAL-CASES Case 25), which is asserted in
  `apps/api/tests/test_config.py`.
* **It is deliberately tiny.** A canary for model deprecation, not a second test suite.
  Everything that can be proven with `MockGroqProvider` is proven there, for free, on every
  push.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "apps" / "api"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.option.asyncio_mode = "auto"
    config.addinivalue_line("markers", "smoke: live-provider smoke tests, main branch only")


@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key or key.startswith("test-key"):
        pytest.skip("GROQ_API_KEY is not set; live suite skipped")
    return key


@pytest.fixture
def settings(api_key):
    from app.config import Settings

    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def transport(api_key):
    """The real transport. No mock anywhere in this directory — that is the whole point."""
    from app.adapters.groq_transport import GroqChatTransport

    return GroqChatTransport(api_key=api_key)
