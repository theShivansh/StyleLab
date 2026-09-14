"""The transport seam — where the mock provider plugs in.

`ChatTransport` is deliberately narrow and provider-agnostic: a chat completion with a JSON
schema, and a list of model ids. No vendor type appears in this file, and none of its names
mention Groq.

## Why the seam is here and not one layer up

`MockGroqProvider` replaces the **transport**, so the analyzer and advisor above it run
their real prompt construction, real schema parsing, real retry and fallback logic, and
real error mapping against it. A mock that replaced `WardrobeAnalyzer` instead would
exercise none of that — it would assert that a stub returns what the stub was told to
return, which is the shape of a test suite that is green and worthless.

It is also what makes prompt 12's acceptance criterion checkable: *the domain layer cannot
tell whether it is using Groq or the mock adapter.* Both sit behind the same
`WardrobeAnalyzer` / `OutfitAdvisor` Protocols because the substitution happens underneath
them.

## Image references

`ImageReferenceSource` exists so the analyzer can turn a storage key into something the
provider can fetch, without knowing what the storage is. Raw bytes never pass through
domain code and images are never in a public bucket (docs/ARCHITECTURE.md section 4).

It was called `SignedUrlSource` when S5 wrote it, on the assumption that the answer was
always a signed URL. S6 found the assumption wrong in the case that matters most: a local
deployment's storage is a private directory, its own API is on `localhost`, and Groq's
servers cannot fetch either. The only reference that works there is an inlined `data:` URL.
Both are references with a deadline; only one is a signed URL, so the Protocol is named for
what it returns rather than for one implementation of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ChatResult:
    """One completion, plus the telemetry `docs/OBSERVABILITY.md` asks us to record.

    `content` is the raw text the model produced, unparsed — validation is the caller's job
    and the audit trail wants what actually arrived (docs/DATA-MODEL.md).
    """

    content: str
    #: Which model answered. Not necessarily the one requested: the fallback chain may have
    #: moved, and the audit row must record the model that actually ran.
    model: str
    latency_ms: int
    request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    #: True when the availability fallback produced this result. Surfaced so a degradation
    #: can be counted rather than inferred from a log.
    used_fallback: bool = False


@dataclass(frozen=True, slots=True)
class SchemaSpec:
    """A structured-output request.

    `strict` is advisory: providers that support strict adherence honour it, and the ones
    that do not still receive the schema. Either way `app.domain.schemas` validates the
    response, because a provider promising schema adherence is not the same as a response
    that adheres.
    """

    name: str
    schema: dict[str, Any]
    strict: bool = True
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A message in provider-neutral form.

    `content` is a list of parts so an image reference can sit beside text without this
    module knowing any provider's multimodal encoding. `{"type": "text", "text": ...}` and
    `{"type": "image_url", "url": ...}` are the two parts in use; the transport translates
    them.
    """

    role: str
    content: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def text(cls, role: str, body: str) -> ChatMessage:
        return cls(role=role, content=[{"type": "text", "text": body}])


@runtime_checkable
class ChatTransport(Protocol):
    """A chat completion endpoint. The one thing `MockGroqProvider` has to satisfy."""

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
        """Raises a `ProviderError` subclass, never a vendor exception.

        `reasoning_effort` is a hint for reasoning models (`low`, `medium`, `high`). `None`
        leaves the provider's default, which is what extraction wants.
        """
        ...

    async def available_models(self) -> set[str]:
        """Model ids the provider will currently serve.

        Used by the boot check. Groq deprecates models on weeks of notice, so a deployment
        that sat idle can wake up configured for a model that no longer exists.
        """
        ...


@runtime_checkable
class ImageReferenceSource(Protocol):
    """Turns a private storage key into something a provider can fetch.

    A signed HTTPS URL when the storage is reachable from the internet; an inlined `data:`
    URL when it is not. `ttl_s` bounds the first and is inert for the second — an inlined
    image has no lifetime beyond the request it was built for, which is the stricter of the
    two and needs no expiry to enforce.
    """

    async def provider_url(self, storage_key: str, *, ttl_s: int = 300) -> str: ...


__all__ = [
    "ChatMessage",
    "ChatResult",
    "ChatTransport",
    "ImageReferenceSource",
    "SchemaSpec",
]
