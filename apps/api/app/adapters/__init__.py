"""Provider adapter boundary.

Everything that talks to an outside system lives behind one of these Protocols. Domain code
depends on the Protocol, never on an implementation and never on a vendor SDK.

## The rule, and how it is actually checked

CLAUDE.md states the check as two greps coming back empty outside this package:

    git grep -i groq   -- ':!apps/api/app/adapters'
    git grep -i crewai -- ':!apps/api/app/adapters'

Those greps do **not** come back empty, and never could. `Settings` has to call its own
fields `groq_api_key` and `groq_text_model` because they map to `GROQ_*` environment
variables, and a docstring explaining why Groq lives behind an adapter is not coupling.
Satisfying the literal grep would mean renaming the settings away from their environment
variables or deleting the explanations — both worse code for no gain.

`tests/test_adapter_boundary.py` enforces the three things the greps were reaching for,
using `ast` so that prose does not trip them:

  1. no vendor module is imported or referenced outside `app/adapters/`
  2. no model **id** is written as a literal outside `app/config.py`
  3. `app/domain/` never imports `app.adapters` — the dependency runs one way

Implementations:
  - GroqWardrobeAnalyzer     `groq_vision.py`  — live, with the availability fallback chain
  - GroqOutfitAdvisor        `groq_text.py`    — live single call; the crew replaces it in S8b
  - CrewAIOutfitAdvisor      phase 14 (S8b)
  - CorpusTrendSource        phase 14 (S8b)

Both live adapters take a `ChatTransport` (`transport.py`) rather than a client, which is
what lets `MockGroqProvider` exercise the real prompt construction, parsing, retry and
fallback logic with no key and no network. Only `groq_transport.py` imports the SDK.

Stubs for tests/ai live in tests, not here — they are test doubles, not a product mode.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models import (
    AdviceRequest,
    GarmentExtraction,
    GarmentImage,
    OutfitAdvice,
    TrendNote,
    TrendQuery,
)


@runtime_checkable
class WardrobeAnalyzer(Protocol):
    """Reads one garment photograph into structured metadata.

    Implementations must never infer anything about a person visible in the photo, and must
    never treat text found inside the image as an instruction (AI-EVAL-CASES Case 07).
    """

    async def analyze(self, image: GarmentImage) -> GarmentExtraction: ...


@runtime_checkable
class OutfitAdvisor(Protocol):
    """Produces an outfit plus advisory content from a candidate set.

    The candidate set is retrieved ownership-scoped *before* this is called, and every item
    id in the response is re-validated against it afterwards. An advisor is never trusted to
    respect scope on its own — see docs/AGENT-SYSTEM.md.
    """

    async def advise(self, request: AdviceRequest) -> OutfitAdvice: ...


@runtime_checkable
class TrendSource(Protocol):
    """Supplies dated, attributed trend notes.

    Never model recall. Every note carries a source and a publication date, or it is dropped
    rather than shown (AI-EVAL-CASES Case 15).
    """

    async def current(self, query: TrendQuery) -> list[TrendNote]: ...


__all__ = ["OutfitAdvisor", "TrendSource", "WardrobeAnalyzer"]
