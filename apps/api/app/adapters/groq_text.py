"""`GroqOutfitAdvisor` — a single-call advisor over the text model.

This is the `OutfitAdvisor` implementation that exists between S5 and S8b. The agent crew
(`docs/AGENT-SYSTEM.md`) replaces it behind the same Protocol; keeping a working single-call
version means the composition path is exercisable now, and it stays useful afterwards as
rung 3 of the ladder — "Architect + Editor only" is a single call in all but name.

## What this deliberately does not do

**It does not validate ownership.** Not because it is hard, but because putting the check
here would make it look done and leave the real seam untested. `CompositionService`
re-validates every id against the retrieved candidate set, in memory, after this returns —
and `tests/test_groq_adapter.py` asserts that this class hands back an unowned id rather
than quietly filtering it. An adapter that cleans up after the model is an adapter that
hides how often the model needs cleaning up after.

That is also the honest reading of `docs/ARCHITECTURE.md` section 6: steps 5 and 7 are
separate, and no amount of deliberation upstream substitutes for the ownership check.

It does parse and schema-validate, because that is the wire format and the wire format is
the adapter's business.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.adapters.prompts import ADVICE_SYSTEM, advice_user_message
from app.adapters.transport import ChatMessage, ChatTransport, SchemaSpec
from app.domain.models import AdviceRequest, OutfitAdvice
from app.domain.schemas import ADVICE_JSON_SCHEMA, parse_advice

logger = logging.getLogger("stylelab.advisor")

#: One re-ask on a schema failure, same reasoning as the vision path.
SCHEMA_RETRIES = 1

ADVICE_SCHEMA = SchemaSpec(
    name="outfit_advice",
    schema=ADVICE_JSON_SCHEMA,
    description="One outfit composed from the supplied candidates, or a named gap.",
)


@dataclass(frozen=True, slots=True)
class AdviceTelemetry:
    """Per-call figures `docs/OBSERVABILITY.md` asks us to record."""

    model: str
    latency_ms: int
    request_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None


class GroqOutfitAdvisor:
    """`OutfitAdvisor` over a `ChatTransport`."""

    def __init__(
        self,
        transport: ChatTransport,
        *,
        model: str,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._transport = transport
        self._model = model
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        #: Last call's telemetry. Read by the caller for logging; not part of the Protocol,
        #: because the domain has no business knowing which model answered.
        self.last_telemetry: AdviceTelemetry | None = None

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        messages = [
            ChatMessage.text("system", ADVICE_SYSTEM),
            ChatMessage.text("user", advice_user_message(request)),
        ]

        last_reason = ""
        for attempt in range(SCHEMA_RETRIES + 1):
            result = await self._transport.complete(
                model=self._model,
                messages=messages,
                schema=ADVICE_SCHEMA,
                timeout_s=self._timeout_s,
                max_tokens=self._max_tokens,
            )
            self.last_telemetry = AdviceTelemetry(
                model=result.model or self._model,
                latency_ms=result.latency_ms,
                request_id=result.request_id,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )

            try:
                # Shape only. Ownership is the service's, immediately after this returns.
                return parse_advice(result.content)
            except Exception as error:
                last_reason = getattr(error, "reason", "") or type(error).__name__
                if attempt == SCHEMA_RETRIES:
                    raise
                logger.info("re-asking the advisor for schema-valid output")

        raise RuntimeError(f"advice: no schema-valid response ({last_reason})")


__all__ = ["ADVICE_SCHEMA", "SCHEMA_RETRIES", "AdviceTelemetry", "GroqOutfitAdvisor"]
