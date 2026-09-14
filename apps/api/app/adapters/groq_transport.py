"""The only module that imports the Groq SDK.

Everything vendor-specific is here: the client, the exception mapping, the multimodal
message encoding, the retry loop. Above this file the system speaks `ChatTransport`, and
`tests/test_adapter_boundary.py` fails the build if `groq` is named anywhere outside
`app/adapters/`.

## Retry policy

Bounded, with exponential backoff and full jitter. Three attempts total by default, only for
errors marked `retryable`, and never for a refusal — a bad key is a bad key on every
attempt, and retrying a request the provider called malformed spends quota twice for the
same answer.

Jitter matters more than it looks: without it, a rate limit that hits several concurrent
uploads makes them all retry in lockstep and hit the limit together. A multi-image upload is
exactly that situation.

`Retry-After` is honoured when the provider sends it, capped, because a provider asking for
a 90-second wait should not hold a request open for 90 seconds.

## What is not retried here

The **model fallback** is one level up, in the analyzer. This module retries the same call;
choosing a different model is a policy decision about which model the product wants, and it
belongs where that policy is written down.
"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any

import groq

from app.adapters.provider_errors import (
    ProviderContractError,
    ProviderError,
    ProviderModelMissingError,
    ProviderOutputInvalidError,
    ProviderRateLimitedError,
    ProviderRefusedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.adapters.transport import ChatMessage, ChatResult, SchemaSpec

logger = logging.getLogger("stylelab.provider")

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 3
#: Base for exponential backoff. Attempt n waits base * 2**(n-1), jittered.
BACKOFF_BASE_S = 0.5
#: However long the provider asks us to wait, we wait no longer than this.
MAX_BACKOFF_S = 8.0


def _sanitised(error: Exception) -> str:
    """Our wording for a provider failure.

    Never `str(error)`: a provider message can quote the request, and the request contains
    text read out of a user's photograph. The original stays on `__cause__` for a debugger.
    """
    return f"{type(error).__name__} from the model provider"


#: What a provider error code looks like when it is safe to log: a short identifier.
_CODE_SHAPE = re.compile(r"^[a-z0-9_]{1,64}$")


def _provider_code(error: Exception) -> str | None:
    """The provider's own error code, when it sent one. Never its message.

    The message can quote the request, and a `json_validate_failed` body carries the model's
    whole failed generation beside it. The code is an identifier: it says *why* in a word that
    cannot hold a user's text — which is what the production log was missing while every crew
    refusal read "BadRequestError from the model provider". Anything that is not shaped like an
    identifier is dropped rather than trusted to be one.
    """
    body = getattr(error, "body", None)
    detail = body.get("error", body) if isinstance(body, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and _CODE_SHAPE.match(code) else None


def _map_error(error: Exception, *, model: str) -> ProviderError:
    """Vendor exception to our taxonomy, carrying the provider's code for the log."""
    mapped = _classify(error, model=model)
    mapped.provider_code = _provider_code(error)
    return mapped


def _classify(error: Exception, *, model: str) -> ProviderError:
    """Ordered most specific first.

    `NotFoundError` is the deprecation case and the reason the fallback model exists at all.
    """
    if isinstance(error, groq.APITimeoutError):
        return ProviderTimeoutError(_sanitised(error), model=model)
    if isinstance(error, groq.RateLimitError):
        return ProviderRateLimitedError(
            _sanitised(error), model=model, retry_after_s=_retry_after(error)
        )
    if isinstance(error, groq.NotFoundError):
        return ProviderModelMissingError(f"model {model} did not resolve", model=model)
    if isinstance(error, groq.AuthenticationError | groq.PermissionDeniedError):
        return ProviderRefusedError("the provider rejected our credentials", model=model)
    if isinstance(error, groq.BadRequestError) and _provider_code(error) == "json_validate_failed":
        return ProviderOutputInvalidError(_sanitised(error), model=model)
    if isinstance(error, groq.BadRequestError | groq.UnprocessableEntityError):
        return ProviderRefusedError(_sanitised(error), model=model)
    if isinstance(error, groq.APIConnectionError | groq.InternalServerError):
        return ProviderUnavailableError(_sanitised(error), model=model)
    if isinstance(error, groq.APIStatusError):
        status = getattr(error, "status_code", 0)
        if status and 500 <= status < 600:
            return ProviderUnavailableError(_sanitised(error), model=model)
        return ProviderRefusedError(_sanitised(error), model=model)
    return ProviderUnavailableError(_sanitised(error), model=model)


def _retry_after(error: Exception) -> float | None:
    """The provider's requested wait, if it sent one."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _encode(message: ChatMessage) -> dict[str, Any]:
    """Provider-neutral parts to Groq's multimodal shape."""
    parts: list[dict[str, Any]] = []
    for part in message.content:
        if part.get("type") == "image_url":
            parts.append({"type": "image_url", "image_url": {"url": part["url"]}})
        else:
            parts.append({"type": "text", "text": part.get("text", "")})

    # A single text part is sent as a plain string: some models handle that path better, and
    # it keeps the request legible in a log.
    if len(parts) == 1 and parts[0]["type"] == "text":
        return {"role": message.role, "content": parts[0]["text"]}
    return {"role": message.role, "content": parts}


def _response_format(schema: SchemaSpec | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.name,
            "schema": schema.schema,
            "strict": schema.strict,
            **({"description": schema.description} if schema.description else {}),
        },
    }


class GroqChatTransport:
    """`ChatTransport` over the Groq async client."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        client: Any | None = None,
    ) -> None:
        # `client` is an injection point for the live smoke tests, which want to pass a
        # pre-configured client. Product code passes the key.
        self._client = client or groq.AsyncGroq(api_key=api_key, timeout=timeout_s)
        self._timeout_s = timeout_s
        self._max_attempts = max(1, max_attempts)

    async def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        schema: SchemaSpec | None = None,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_encode(m) for m in messages],
        }
        response_format = _response_format(schema)
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens
        if reasoning_effort is not None:
            # Through `extra_body`: the SDK's type for this field predates the values the
            # reasoning models accept, and the API takes them either way.
            payload["extra_body"] = {"reasoning_effort": reasoning_effort}
        if timeout_s is not None:
            payload["timeout"] = timeout_s

        last: ProviderError | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                raw = await self._client.chat.completions.create(**payload)
            except Exception as error:  # mapped, then decided on
                mapped = _map_error(error, model=model)
                mapped.__cause__ = error
                last = mapped
                if not mapped.retryable or attempt == self._max_attempts:
                    self._log_failure(mapped, model=model, attempt=attempt)
                    raise mapped from error

                delay = self._backoff(attempt, mapped)
                # The codes are in the message as well as `extra`, because the deployed log
                # shows the message and nothing else.
                logger.info(
                    "provider call failed; retrying (code=%s provider_code=%s attempt=%d)",
                    mapped.code,
                    mapped.provider_code or "-",
                    attempt,
                    extra={
                        "model": model,
                        "attempt": attempt,
                        "code": mapped.code,
                        "provider_code": mapped.provider_code,
                        "delay_s": round(delay, 3),
                    },
                )
                await self._sleep(delay)
                continue

            latency_ms = int((time.perf_counter() - started) * 1000)
            return self._to_result(raw, model=model, latency_ms=latency_ms)

        # Unreachable: the loop either returns or raises. Present so a future edit to the
        # loop cannot silently fall through to None.
        raise last or ProviderUnavailableError("provider call did not complete", model=model)

    async def available_models(self) -> set[str]:
        try:
            listing = await self._client.models.list()
        except Exception as error:
            mapped = _map_error(error, model="(model list)")
            raise mapped from error

        data = getattr(listing, "data", None) or []
        return {getattr(entry, "id", "") for entry in data if getattr(entry, "id", "")}

    # --- internals ---------------------------------------------------------------------

    def _backoff(self, attempt: int, error: ProviderError) -> float:
        """Exponential with full jitter, or the provider's own request, whichever is longer.

        Full jitter rather than a fixed schedule: several images from one upload hit a rate
        limit together, and a fixed schedule makes them all come back together too.
        """
        exponential = min(BACKOFF_BASE_S * (2 ** (attempt - 1)), MAX_BACKOFF_S)
        jittered = random.uniform(0, exponential)
        requested = getattr(error, "retry_after_s", None) or 0.0
        return min(max(jittered, float(requested)), MAX_BACKOFF_S)

    @staticmethod
    async def _sleep(seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def _log_failure(self, error: ProviderError, *, model: str, attempt: int) -> None:
        logger.warning(
            "provider call failed (code=%s provider_code=%s attempts=%d)",
            error.code,
            error.provider_code or "-",
            attempt,
            extra={
                "model": model,
                "attempts": attempt,
                "code": error.code,
                "provider_code": error.provider_code,
            },
        )

    @staticmethod
    def _to_result(raw: Any, *, model: str, latency_ms: int) -> ChatResult:
        """Unwrap a completion, or say the transport contract broke.

        A 200 with no choices is not a schema failure — the model never got a chance to
        answer. Calling it `ProviderContractError` keeps that distinct from the model
        ignoring the output schema, which is a different problem with a different fix.
        """
        choices = getattr(raw, "choices", None) or []
        if not choices:
            raise ProviderContractError("provider returned no choices", model=model)

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message else None
        if not content:
            # A reasoning model spends its token budget thinking before it emits anything, so
            # a budget that is merely *small* produces an empty message with
            # `finish_reason="length"` rather than a short answer. Worth saying out loud: the
            # generic version of this error sent S6 looking for a schema problem when the
            # configured ceiling was the whole story.
            if getattr(choices[0], "finish_reason", None) == "length":
                raise ProviderContractError(
                    "the model reached its token ceiling before producing any output; the "
                    "configured max_tokens is too low for this model",
                    model=model,
                )
            raise ProviderContractError("provider returned an empty message", model=model)

        usage = getattr(raw, "usage", None)
        return ChatResult(
            content=content,
            model=getattr(raw, "model", model) or model,
            latency_ms=latency_ms,
            request_id=getattr(raw, "id", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        )


__all__ = ["DEFAULT_MAX_ATTEMPTS", "DEFAULT_TIMEOUT_S", "GroqChatTransport"]
