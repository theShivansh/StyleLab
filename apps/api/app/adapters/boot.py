"""Boot-time provider checks, and the default transport.

`docs/AI-SYSTEM.md`: "Both IDs are verified against Groq's model list at boot." Groq
deprecates models on weeks of notice, so a deployment that sat idle for a month can wake up
configured for a model that no longer exists — and without this check the first person to
find out is a user mid-upload.

## Two failures, deliberately treated differently

* **A configured model is absent from the list.** Fatal. Every request using that model
  will fail, so starting up is worse than not: it turns a deployment error into a stream of
  user-facing errors with no obvious cause.
* **The list could not be fetched at all.** Logged at ERROR, not fatal. That is a network
  or provider-availability problem, and refusing to start on it means a provider blip
  during a rollout takes the whole service down — including the parts that do not need the
  provider. The check is advisory precisely because its own dependency can fail.

The distinction is the point: `ConfigurationError` means *we are configured wrong*, which
only a human can fix. A failed list call may well fix itself.

A missing `GROQ_API_KEY` is caught earlier and separately, by `Settings` itself, and is
always fatal (AI-EVAL-CASES Case 25).
"""

from __future__ import annotations

import logging

from app.adapters.groq_transport import GroqChatTransport
from app.adapters.provider_errors import ProviderError
from app.adapters.transport import ChatTransport
from app.config import Settings
from app.domain.errors import ConfigurationError

logger = logging.getLogger("stylelab.boot")


def default_transport(settings: Settings) -> ChatTransport:
    """The production transport.

    The only place the concrete Groq transport is constructed outside its own module, so
    `app/main.py` never handles the key and never names the vendor.
    """
    return GroqChatTransport(api_key=settings.groq_api_key)


async def verify_models(transport: ChatTransport, settings: Settings) -> set[str]:
    """Check every configured model id resolves. Returns the ids that were verified.

    Raises `ConfigurationError` when the provider answers and a configured id is not in its
    list. Returns an empty set, having logged at ERROR, when the list itself could not be
    fetched.
    """
    configured = {
        "GROQ_TEXT_MODEL": settings.groq_text_model,
        "GROQ_VISION_MODEL": settings.groq_vision_model,
        "GROQ_VISION_FALLBACK_MODEL": settings.groq_vision_fallback_model,
    }

    try:
        available = await transport.available_models()
    except ProviderError as error:
        # Advisory check, failed dependency. Loud, but not a refusal to start.
        logger.error(
            "could not verify model ids at boot; continuing unverified",
            extra={"code": error.code},
        )
        return set()

    missing = {name: value for name, value in configured.items() if value not in available}
    if missing:
        listed = "; ".join(f"{name}={value}" for name, value in sorted(missing.items()))
        raise ConfigurationError(
            "configured model id(s) do not resolve with the provider: "
            f"{listed}. Groq deprecates models on weeks of notice — check "
            "https://console.groq.com/docs/models and update .env."
        )

    logger.info("model ids verified", extra={"count": len(configured)})
    return set(configured.values())


__all__ = ["default_transport", "verify_models"]
