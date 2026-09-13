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
import time
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
    """The real key, resolved the way the application resolves it.

    Read through `Settings` rather than from `os.environ`, because `Settings` also loads
    `.env` — which is where the documented setup instructions put the key. The first version
    of this fixture checked the environment only, so a correctly configured repository
    skipped the entire live suite and said "GROQ_API_KEY is not set" while it was sitting in
    `.env`. A suite that silently does nothing is worse than one that fails.

    Still skips rather than fails when there is genuinely no key. This is the one place in
    the repository where that is right: a test that cannot run has not found a bug, and it
    is a *test* skipping rather than the application degrading. The app refuses to boot
    without a key (AI-EVAL-CASES Case 25), asserted in `apps/api/tests/test_config.py`.
    """
    key = os.environ.get("GROQ_API_KEY", "")

    if not key:
        try:
            from app.config import Settings

            key = Settings().groq_api_key  # type: ignore[call-arg]
        except Exception:  # noqa: BLE001 - an absent or invalid key is the skip condition
            key = ""

    if not key or key.startswith("test-key"):
        pytest.skip("no real GROQ_API_KEY in the environment or .env; live suite skipped")
    return key


#: Seconds to wait before a module that spends its budget on vision calls.
#:
#: Measured on this account (headers from a live call, S7): 1000 requests/minute and 8000
#: **input** tokens/minute, alongside a separate **output** tokens-per-minute ceiling of
#: 1000 per model that the headers do not report. Our vision ceiling is 2048, so a single
#: extraction can ask for more output than the whole minute allows, and the provider then
#: refuses it up front on *expected* output: "Limit 1000, Requested 1579", before the model
#: runs at all.
#:
#: Every module passes on its own; the suite failed as a set, with the red landing on
#: whichever test was running when the budget ran out. Pacing is not papering over a race —
#: the wait *is* the rate limit, and a minute is the provider's window.
VISION_PACING_S = float(os.environ.get("STYLELAB_LIVE_PACING_S", "60"))


@pytest.fixture(scope="module")
def paced(api_key):
    """Wait out the provider's per-minute output budget before a vision-heavy module.

    Set `STYLELAB_LIVE_PACING_S=0` on a paid tier, where the limit this exists for does not
    bind. Left at its default everywhere else, because a suite that fails on the account it
    is actually run against is a suite people stop running.
    """
    if VISION_PACING_S > 0:
        time.sleep(VISION_PACING_S)


@pytest.fixture
def settings(api_key):
    from app.config import Settings

    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def transport(api_key):
    """The real transport. No mock anywhere in this directory — that is the whole point."""
    from app.adapters.groq_transport import GroqChatTransport

    return GroqChatTransport(api_key=api_key)
