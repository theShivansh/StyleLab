"""Local pytest configuration for the proof layer.

Two things this file bootstraps, both because `tests/ai/` sits outside either app on
purpose (`tests/README.md`) and therefore inherits neither app's configuration:

* **`apps/api` on `sys.path`.** CI installs the API (`pip install -e apps/api[dev]`) so
  `app` resolves there; a developer running `pytest tests/ai` from the repository root has
  no such install. Adding the path makes the command work in both, which matters for a
  suite whose entire value is that it is cheap enough to run constantly.
* **`asyncio_mode = auto`.** Set in `apps/api/pyproject.toml`, which does not reach here.

Deliberately does **not** set `GROQ_API_KEY`. Nothing in this directory needs one, and a
placeholder would quietly weaken the claim this layer exists to make: the whole grounding
suite runs with no key, no network and no cost.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "apps" / "api"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    config.option.asyncio_mode = "auto"
