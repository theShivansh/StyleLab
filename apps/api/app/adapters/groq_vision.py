"""`GroqWardrobeAnalyzer` — the product's front door.

A user's closet becomes structured data only because a model read their photographs, so
extraction quality and extraction *honesty* are the central concerns here, not throughput.

## The fallback is for availability, never for quality

This is the rule most likely to be broken by someone trying to be helpful, so it is worth
stating plainly: the fallback model is tried when the primary model **could not answer** —
provider error, rate limit, timeout, or an id that no longer resolves. It is never tried
because the answer that came back was uncertain.

A low-confidence extraction is not a failure. It is the most useful thing the model
produces: it drives the hedge in the UI and the offer to correct. Retrying a cheaper model
to obtain a more confident answer replaces an honest "we are not sure" with a confident
guess, which is precisely the gimmick this project exists to avoid (AI-EVAL-CASES Case 24).

`analyze()` therefore never inspects `field_confidence`. There is no code path from a
confidence score to a model choice, which is a stronger guarantee than a rule about one.

## Schema failure does get one retry

Distinct from the above. If the model returns something that is not valid against the
schema, that is the model failing to follow instructions and a single re-ask often fixes
it. Bounded at one, on the same model, and then it fails — Case 06 puts the deterministic
ranker below this, not another attempt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.adapters.prompts import VISION_SYSTEM, vision_user_message
from app.adapters.provider_errors import ProviderError
from app.adapters.transport import (
    ChatMessage,
    ChatResult,
    ChatTransport,
    SchemaSpec,
    SignedUrlSource,
)
from app.domain.errors import SchemaInvalidError
from app.domain.models import GarmentExtraction, GarmentImage
from app.domain.schemas import EXTRACTION_JSON_SCHEMA, parse_extraction

logger = logging.getLogger("stylelab.vision")

#: How long a signed image URL needs to live: long enough for the provider to fetch it,
#: short enough that a leaked log line is worthless within minutes.
IMAGE_URL_TTL_S = 300

#: One re-ask when the model ignores the output schema. Not two: Case 06 puts the
#: deterministic path below this, and a model that failed the schema twice will fail it again.
SCHEMA_RETRIES = 1

VISION_SCHEMA = SchemaSpec(
    name="garment_extraction",
    schema=EXTRACTION_JSON_SCHEMA,
    description="Structured description of one garment in a photograph.",
)


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    """What one call to a model produced, for the `item_extractions` audit trail.

    Written whether or not it was accepted (docs/DATA-MODEL.md): an audit trail that keeps
    only the successes cannot show that anything was ever caught.
    """

    model: str
    raw_output: str
    schema_valid: bool
    latency_ms: int
    rejected_reason: str | None = None
    request_id: str | None = None
    used_fallback: bool = False


@dataclass
class AnalysisOutcome:
    """The extraction plus every attempt it took to get there."""

    extraction: GarmentExtraction
    attempts: list[AnalysisAttempt]

    @property
    def model(self) -> str:
        return self.attempts[-1].model

    @property
    def used_fallback(self) -> bool:
        return self.attempts[-1].used_fallback


class GroqWardrobeAnalyzer:
    """`WardrobeAnalyzer` over a `ChatTransport`.

    Holds no vendor type: the transport is injected, which is what lets `MockGroqProvider`
    drive this exact class — the real prompt, the real parser, the real fallback logic — with
    no key and no network.
    """

    def __init__(
        self,
        transport: ChatTransport,
        *,
        model: str,
        fallback_model: str | None = None,
        urls: SignedUrlSource | None = None,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._transport = transport
        self._model = model
        self._fallback_model = fallback_model
        self._urls = urls
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens

    async def analyze(self, image: GarmentImage) -> GarmentExtraction:
        """The `WardrobeAnalyzer` Protocol method."""
        return (await self.analyze_with_audit(image)).extraction

    async def analyze_with_audit(self, image: GarmentImage) -> AnalysisOutcome:
        """Same work, plus the attempt records the audit table wants.

        A separate method rather than a wider Protocol: the domain has no use for provider
        telemetry, and putting `model` on the interface would leak a vendor concept into it.
        """
        messages = await self._messages(image)
        attempts: list[AnalysisAttempt] = []

        # The chain is availability only. Nothing about the *content* of a response can put
        # us on the next model.
        chain = [(self._model, False)]
        if self._fallback_model and self._fallback_model != self._model:
            chain.append((self._fallback_model, True))

        last_provider_error: ProviderError | None = None

        for model, is_fallback in chain:
            try:
                extraction, model_attempts = await self._ask(model, messages, is_fallback)
            except ProviderError as error:
                attempts.append(
                    AnalysisAttempt(
                        model=model,
                        raw_output="",
                        schema_valid=False,
                        latency_ms=0,
                        rejected_reason=error.code,
                        used_fallback=is_fallback,
                    )
                )
                last_provider_error = error
                if error.use_fallback_model and not is_fallback:
                    logger.warning(
                        "vision model unavailable; trying the availability fallback",
                        extra={"code": error.code},
                    )
                    continue
                raise
            except SchemaInvalidError as error:
                # The model answered but would not follow the schema. That is not an
                # availability problem, so the fallback is not the answer — the caller
                # degrades instead.
                attempts.append(
                    AnalysisAttempt(
                        model=model,
                        raw_output="",
                        schema_valid=False,
                        latency_ms=0,
                        rejected_reason="schema_invalid",
                        used_fallback=is_fallback,
                    )
                )
                logger.warning("vision output failed the schema", extra={"reason": error.reason})
                raise

            attempts.extend(model_attempts)
            return AnalysisOutcome(extraction=extraction, attempts=attempts)

        raise last_provider_error or ProviderError("no vision model was reachable")

    # --- internals ---------------------------------------------------------------------

    async def _ask(
        self, model: str, messages: list[ChatMessage], is_fallback: bool
    ) -> tuple[GarmentExtraction, list[AnalysisAttempt]]:
        """One model, with a bounded re-ask when it ignores the schema."""
        attempts: list[AnalysisAttempt] = []

        for attempt in range(SCHEMA_RETRIES + 1):
            result = await self._transport.complete(
                model=model,
                messages=messages,
                schema=VISION_SCHEMA,
                timeout_s=self._timeout_s,
                max_tokens=self._max_tokens,
            )
            try:
                extraction = parse_extraction(result.content)
            except SchemaInvalidError as error:
                attempts.append(self._attempt(result, model, is_fallback, error.reason))
                if attempt == SCHEMA_RETRIES:
                    raise
                logger.info("re-asking the vision model for schema-valid output")
                continue

            attempts.append(self._attempt(result, model, is_fallback, None))
            # Deliberately no inspection of extraction.field_confidence here. See the module
            # docstring: there is no path from a confidence score to a model choice.
            return extraction, attempts

        raise SchemaInvalidError("extraction: no schema-valid response")

    @staticmethod
    def _attempt(
        result: ChatResult, model: str, is_fallback: bool, rejected_reason: str | None
    ) -> AnalysisAttempt:
        return AnalysisAttempt(
            model=result.model or model,
            raw_output=result.content,
            schema_valid=rejected_reason is None,
            latency_ms=result.latency_ms,
            rejected_reason=rejected_reason,
            request_id=result.request_id,
            used_fallback=is_fallback,
        )

    async def _messages(self, image: GarmentImage) -> list[ChatMessage]:
        """System prompt, then the instruction and the image reference.

        The URL is short-lived and signed; raw bytes never reach here (ARCHITECTURE §4).
        Neither the URL nor the storage key is logged.
        """
        url = await self._image_url(image)
        return [
            ChatMessage.text("system", VISION_SYSTEM),
            ChatMessage(
                role="user",
                content=[
                    {
                        "type": "text",
                        "text": vision_user_message(category_hint=image.category_hint),
                    },
                    {"type": "image_url", "url": url},
                ],
            ),
        ]

    async def _image_url(self, image: GarmentImage) -> str:
        if self._urls is None:
            raise ProviderError(
                "no signed-url source is configured, so no image can be sent for analysis"
            )
        return await self._urls.signed_url(image.storage_key, ttl_s=IMAGE_URL_TTL_S)


__all__ = [
    "IMAGE_URL_TTL_S",
    "SCHEMA_RETRIES",
    "VISION_SCHEMA",
    "AnalysisAttempt",
    "AnalysisOutcome",
    "GroqWardrobeAnalyzer",
]
