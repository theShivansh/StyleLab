"""Provider adapter boundary.

Everything that talks to an outside system lives behind one of these Protocols. Domain code
depends on the Protocol, never on an implementation and never on a vendor SDK.

The check, from CLAUDE.md, is two greps that must both come back empty outside this package:

    git grep -i groq   -- ':!apps/api/app/adapters'
    git grep -i crewai -- ':!apps/api/app/adapters'

Implementations land in later phases:
  - GroqWardrobeAnalyzer     phase 12 (S5)
  - CrewAIOutfitAdvisor      phase 14 (S8b)
  - CorpusTrendSource        phase 14 (S8b)
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
