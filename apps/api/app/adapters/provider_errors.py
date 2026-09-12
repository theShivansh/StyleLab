"""Provider error taxonomy.

Every failure an external model service can hand us, reduced to the handful of distinctions
that change what we do next. The important axis is `retryable`, and the second is
`use_fallback_model` — those two flags drive the whole reliability story, so they are data
on the exception rather than a chain of `isinstance` checks at the call site.

## Messages are sanitised at the boundary

`ProviderError.message` is ours, not the provider's. A raw provider message can contain the
prompt, and the prompt contains text recovered from a user's photograph — a slogan, a care
label, a tag reading "ignore previous instructions" (AI-EVAL-CASES Case 07). Echoing that
into a log or an error envelope is how injected text reaches a human later.
`docs/SECURITY-PRIVACY.md` forbids surfacing a raw provider message; the original is kept on
`__cause__` for a debugger and never formatted into `str(error)`.

## What is deliberately absent

There is no `ProviderQualityError`. A low-confidence extraction is not a failure — it is a
signal to surface to the user for correction, and retrying a cheaper model to get a more
confident wrong answer is the opposite of what this system is for (Case 24).
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for anything the provider did wrong.

    `code` is a stable string for logs and the error envelope in `docs/API-SPEC.md`.
    """

    code = "AI_UNAVAILABLE"
    #: Whether trying the same call again could plausibly succeed.
    retryable = False
    #: Whether the availability fallback model should be tried. Availability only.
    use_fallback_model = False

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(message)
        #: Our wording. Never the provider's.
        self.message = message
        self.model = model


class ProviderTimeoutError(ProviderError):
    """The call exceeded its deadline."""

    code = "AI_TIMEOUT"
    retryable = True
    use_fallback_model = True


class ProviderRateLimitedError(ProviderError):
    """Quota or rate limit. Retryable after a wait, and a good reason to try the fallback."""

    code = "AI_RATE_LIMITED"
    retryable = True
    use_fallback_model = True

    def __init__(
        self, message: str, *, model: str | None = None, retry_after_s: float | None = None
    ) -> None:
        super().__init__(message, model=model)
        self.retry_after_s = retry_after_s


class ProviderUnavailableError(ProviderError):
    """Connection failure or a 5xx. The provider is having a bad time, not us."""

    code = "AI_UNAVAILABLE"
    retryable = True
    use_fallback_model = True


class ProviderModelMissingError(ProviderError):
    """The configured model id no longer resolves.

    Groq deprecates models on weeks of notice, so this is a routine operational event rather
    than an exotic one. Retrying the same id cannot help; the fallback is exactly what it
    exists for.
    """

    code = "AI_MODEL_MISSING"
    retryable = False
    use_fallback_model = True


class ProviderRefusedError(ProviderError):
    """Authentication, permission, or a malformed request — our fault, not the provider's.

    Not retryable and no fallback: a bad key is a bad key on every model, and retrying a
    request the provider called invalid just spends the quota twice.
    """

    code = "AI_REFUSED"
    retryable = False
    use_fallback_model = False


class ProviderContractError(ProviderError):
    """A 200 whose body was not the shape the API documents.

    Distinct from `SchemaInvalidError`, which is the *model* failing to follow the output
    schema. This is the transport itself being wrong — no choices array, no message content —
    and it means something changed underneath us.
    """

    code = "AI_CONTRACT"
    retryable = True
    use_fallback_model = False


__all__ = [
    "ProviderContractError",
    "ProviderError",
    "ProviderModelMissingError",
    "ProviderRateLimitedError",
    "ProviderRefusedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
