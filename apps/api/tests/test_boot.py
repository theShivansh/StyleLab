"""Boot-time checks.

Two things must fail loudly at startup rather than at a user's first request: a missing key
(AI-EVAL-CASES Case 25) and a configured model id the provider will not serve. Groq
deprecates models on weeks of notice, so the second is routine rather than exotic — a
deployment that sat idle for a month can wake up pointing at a model that no longer exists.

The distinction these tests pin down is between *we are configured wrong*, which is fatal
and only a human can fix, and *the check could not run*, which is loud but survivable.
"""

from __future__ import annotations

import logging

import pytest

from app.adapters.boot import verify_models
from app.adapters.provider_errors import ProviderUnavailableError
from app.config import Settings
from app.domain.errors import ConfigurationError

TEXT = "test/text"
VISION = "test/vision"
FALLBACK = "test/vision-fallback"


def settings_for(**over: str) -> Settings:
    values = {
        "groq_api_key": "not-a-real-key",
        "groq_text_model": TEXT,
        "groq_vision_model": VISION,
        "groq_vision_fallback_model": FALLBACK,
    }
    values.update(over)
    return Settings(**values)  # type: ignore[arg-type]


async def test_all_three_models_present_passes(stubs):
    transport = stubs.MockGroqProvider(models={TEXT, VISION, FALLBACK, "other/model"})

    verified = await verify_models(transport, settings_for())

    assert verified == {TEXT, VISION, FALLBACK}


@pytest.mark.parametrize(
    "absent", ["groq_text_model", "groq_vision_model", "groq_vision_fallback_model"]
)
async def test_a_model_the_provider_will_not_serve_is_fatal(stubs, absent):
    """Including the fallback.

    An unverified fallback is worse than no fallback: it looks like a safety net and is
    discovered to be missing at exactly the moment the primary has already failed.
    """
    settings = settings_for(**{absent: "test/deprecated-last-year"})
    transport = stubs.MockGroqProvider(models={TEXT, VISION, FALLBACK})

    with pytest.raises(ConfigurationError) as caught:
        await verify_models(transport, settings)

    message = str(caught.value)
    assert "test/deprecated-last-year" in message
    # Names the env var, so the fix is obvious without reading the source.
    assert absent.upper() in message
    # And points at where model ids actually change.
    assert "console.groq.com" in message


async def test_the_error_names_every_missing_model_not_just_the_first(stubs):
    settings = settings_for(groq_text_model="gone/a", groq_vision_model="gone/b")
    transport = stubs.MockGroqProvider(models={FALLBACK})

    with pytest.raises(ConfigurationError) as caught:
        await verify_models(transport, settings)

    assert "gone/a" in str(caught.value)
    assert "gone/b" in str(caught.value)


async def test_an_unreachable_provider_is_loud_but_not_fatal(stubs, caplog):
    """The check is advisory, and its own dependency can fail.

    Refusing to start on a failed list call means a provider blip during a rollout takes the
    whole service down — including the parts that never touch the provider. Logged at ERROR
    so it is visible, and the app comes up unverified.
    """
    transport = stubs.MockGroqProvider(
        models=set(), list_error=ProviderUnavailableError("provider down")
    )

    with caplog.at_level(logging.ERROR):
        verified = await verify_models(transport, settings_for())

    assert verified == set()
    assert any("unverified" in record.message for record in caplog.records)


async def test_a_verified_boot_records_what_it_verified(stubs):
    """`app.state.verified_models` is read by the health surface in S11; an empty set there
    means the check did not run, which is worth being able to tell apart from a pass."""
    transport = stubs.MockGroqProvider(models={TEXT, VISION, FALLBACK})

    assert await verify_models(transport, settings_for()) != set()


# --- through the app -------------------------------------------------------------------


def test_the_app_boots_and_runs_the_check(client):
    """The `client` fixture builds the app with a mock transport, so the real
    `verify_models` runs at startup rather than being skipped in tests."""
    assert client.get("/health").json() == {"status": "ok"}
    assert client.app.state.verified_models


def test_a_misconfigured_app_refuses_to_start(stubs):
    """The whole point of a boot check: the failure happens here, once, not on every
    request afterwards with no obvious cause."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    transport = stubs.MockGroqProvider(models={"something/else"})

    with pytest.raises(ConfigurationError), TestClient(create_app(transport=transport)):
        pass


# The other boot failure — a missing or empty GROQ_API_KEY (Case 25) — is asserted in
# tests/test_config.py, where `Settings` itself is under test. It is a separate and earlier
# check than the model list, so there is no ordering in which a keyless app reaches the
# provider at all.
