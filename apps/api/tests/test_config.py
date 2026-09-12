"""Config boundary tests.

These assert the rules in CLAUDE.md that are easy to violate silently later.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_api_key_is_a_hard_failure(monkeypatch):
    """No demo mode: absent credentials must raise, never degrade to a stub.

    AI-EVAL-CASES Case 25.
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_empty_api_key_is_also_rejected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_vision_fallback_differs_from_primary(monkeypatch):
    """A fallback identical to the primary is not a fallback.

    Availability chain per docs/DECISIONS.md (B5): 3.8 primary, 3.6 fallback.
    """
    monkeypatch.setenv("GROQ_API_KEY", "k")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groq_vision_model != settings.groq_vision_fallback_model


def test_confidence_floor_is_a_probability(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert 0.0 < settings.confidence_floor <= 1.0
