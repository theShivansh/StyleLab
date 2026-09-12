"""Does every configured model still exist?

The canary. Groq deprecates models on weeks of notice, so this is the test that turns "the
app broke for everyone overnight" into "a CI job went red on main". It is the cheapest test
in the repository — one `models.list()` call, no completion, no tokens spent on inference —
and it is the one most likely to catch a real outage before a user does.

It runs the same `verify_models` the application runs at boot, rather than a parallel
re-implementation. A canary that checks something slightly different from what production
checks is a canary that can sing while production suffocates.
"""

from __future__ import annotations

import pytest
from app.adapters.boot import verify_models

#: Enough headroom for a reasoning model to think and then answer. The models configured
#: here (`openai/gpt-oss-*`) emit nothing at all below roughly a few hundred tokens, so a
#: ceiling is a correctness setting and not only a cost one.
VISION_AND_TEXT_HEADROOM = 1024


async def test_every_configured_model_resolves(transport, settings):
    """Fails loudly and names the offender.

    `verify_models` raises `ConfigurationError` listing every missing id, with a pointer to
    Groq's model page — so a CI failure here is actionable without opening the source.
    """
    verified = await verify_models(transport, settings)

    assert verified == {
        settings.groq_text_model,
        settings.groq_vision_model,
        settings.groq_vision_fallback_model,
    }


async def test_the_fallback_model_is_verified_too(transport, settings):
    """Stated separately because it is the one people forget.

    An unverified fallback is worse than no fallback: it looks like a safety net and is
    discovered to be missing at precisely the moment the primary has already failed.
    """
    available = await transport.available_models()

    assert settings.groq_vision_fallback_model in available
    assert settings.groq_vision_model in available
    assert settings.groq_vision_model != settings.groq_vision_fallback_model


@pytest.mark.smoke
async def test_the_provider_answers_at_all(transport, settings):
    """A connectivity check, separate from the model list.

    Marked `smoke` because it spends a handful of tokens. If this passes and the test above
    fails, the problem is our configuration; if both fail, the problem is the provider.
    Telling those two apart at 3am is worth one API call.
    """
    from app.adapters.transport import ChatMessage

    result = await transport.complete(
        model=settings.groq_text_model,
        messages=[ChatMessage.text("user", 'Reply with exactly: {"ok": true}')],
        # Not 32, which is what this test asked for until S6 ran it against the real
        # provider. `openai/gpt-oss-120b` is a reasoning model: it spends its budget
        # thinking before it emits a token of output, so a small ceiling does not produce a
        # short answer — it produces an empty message with `finish_reason="length"`. The
        # canary was failing for a reason that had nothing to do with connectivity.
        max_tokens=VISION_AND_TEXT_HEADROOM,
    )

    assert result.content
    assert result.latency_ms >= 0


@pytest.mark.smoke
async def test_a_token_ceiling_that_is_too_low_says_so(transport, settings):
    """The other half of the lesson above, kept as a test because the symptom is misleading.

    An empty response reads like a model fault or a schema problem; it is a configuration
    problem, and the error has to name it. Costs a handful of tokens and buys back the hour
    this took to diagnose the first time.
    """
    from app.adapters.provider_errors import ProviderContractError
    from app.adapters.transport import ChatMessage

    with pytest.raises(ProviderContractError) as raised:
        await transport.complete(
            model=settings.groq_text_model,
            messages=[ChatMessage.text("user", "Explain the Gauss-Bonnet theorem.")],
            max_tokens=16,
        )

    assert "max_tokens" in str(raised.value.message)
