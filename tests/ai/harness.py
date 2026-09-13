"""One wardrobe, one stack, one way to feed a hostile response through it.

Everything in this directory needs the same setup: two users, one of whom owns a complete
outfit and one of whom owns the garment that must never appear, and the real adapter stack
above a scripted transport. Defining that twice is how the ids in a reviewer's report come
to disagree with the ids in the test output.

The stack assembled here is deliberately the **real** one from the transport up:

    MockGroqProvider -> GroqOutfitAdvisor -> CompositionService -> domain rules
    (scripted bytes)    (real prompt/parse)  (real ownership check)

Only the bytes on the wire are ours. Nothing else is stubbed, which is what makes a refusal
observed here evidence about the product rather than evidence about a mock.

`refuse()` returns what happened rather than asserting it, so the same function can back a
pytest assertion and a printed report. A harness that can only be consumed by `assert` is a
harness a reviewer cannot watch.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.adapters.groq_text import GroqOutfitAdvisor
from app.adapters.groq_vision import GroqWardrobeAnalyzer
from app.db.models import Base
from app.db.session import build_engine, session_factory
from app.domain.models import GarmentCategory as C
from app.repositories.wardrobe import WardrobeRepository
from app.services.composition import CompositionService
from stubs import (
    CollectingGenerationLog,
    FakeImageReferences,
    MockGroqProvider,
    StaticTrendSource,
    garment,
    trend_note,
)

#: The requesting user, and the one whose wardrobe must never be reachable from it.
U1, U2 = "eval-u1", "eval-u2"

#: Deliberately opaque. A model id in this file would be a model id outside the adapter
#: config, which CLAUDE.md forbids and `test_adapter_boundary.py` enforces.
TEXT_MODEL = "eval/text"
VISION_MODEL = "eval/vision"
VISION_FALLBACK = "eval/vision-fallback"

#: What U1 owns: one complete outfit, plus a second top so a two-tops response has something
#: real to name (Case 02).
OWNED: tuple[tuple[str, C, str], ...] = (
    ("own-top", C.TOP, "navy"),
    ("own-second-top", C.TOP, "white"),
    ("own-bottom", C.BOTTOM, "stone"),
    ("own-shoe", C.FOOTWEAR, "white"),
)

#: What U2 owns. It would score well, and that is the point.
FOREIGN_ITEM = "u2-jacket"

#: The two notes a trend source supplies in the scenarios that use one. Notes are matched
#: back to these by URL (`app.domain.validation`), so a scenario that wants a note to survive
#: has to supply it here — which is the rule under test, not a fixture inconvenience.
SUPPLIED_TRENDS: tuple[tuple[str, str, str], ...] = (
    (
        "Wide-leg trousers still reading current",
        "example-publication",
        "https://example-publication.test/wide-leg",
    ),
    (
        "Neutral palettes holding through AW26",
        "example-publication",
        "https://example-publication.test/neutral-palettes",
    ),
)


def supplied_trend_source() -> StaticTrendSource:
    """A `TrendSource` returning exactly the notes the fixtures cite."""
    from datetime import date

    return StaticTrendSource(
        *(
            trend_note(trend, source=source, url=url, published_at=date(2026, 8, 2))
            for trend, source, url in SUPPLIED_TRENDS
        )
    )


@dataclass
class Stack:
    """The assembled system, plus the seams a scenario needs to look through."""

    service: CompositionService
    transport: MockGroqProvider
    telemetry: CollectingGenerationLog
    logs: list[logging.LogRecord] = field(default_factory=list)

    @property
    def prompt(self) -> str:
        """Every word the model was actually sent. Empty before the first call."""
        return self.transport.calls[0].text if self.transport.calls else ""

    def logged(self, level: int) -> list[str]:
        return [record.getMessage() for record in self.logs if record.levelno >= level]


@contextmanager
def wardrobe() -> Iterator[WardrobeRepository]:
    """Two users and their garments, in a database that lives for one scenario."""
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        repo = WardrobeRepository(session)
        repo.add_user(U1, "u1@example.test")
        repo.add_user(U2, "u2@example.test")
        for item_id, category, colour in OWNED:
            repo.add_item(garment(item_id, U1, category=category, color_primary=colour))
        repo.add_item(garment(FOREIGN_ITEM, U2, category=C.OUTERWEAR, color_primary="black"))
        session.commit()
        yield repo
    engine.dispose()


class _Capture(logging.Handler):
    """Collects records so a scenario can show the refusal being logged, not just returned."""

    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__(level=logging.DEBUG)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)


@contextmanager
def stack(
    repository: WardrobeRepository,
    content: str,
    *,
    advisor: Any | None = None,
    **over: Any,
) -> Iterator[Stack]:
    """The real advisor over a transport that returns exactly `content`.

    `advisor` overrides it, for the scenarios that are about the *call* rather than about
    what came back — a timeout has no response to script.
    """
    transport = MockGroqProvider.returning(content)
    telemetry = CollectingGenerationLog()
    records: list[logging.LogRecord] = []
    handler = _Capture(records)
    logger = logging.getLogger("stylelab")
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield Stack(
            service=CompositionService(
                repository,
                advisor=advisor or GroqOutfitAdvisor(transport, model=TEXT_MODEL),
                telemetry=telemetry,
                **over,
            ),
            transport=transport,
            telemetry=telemetry,
            logs=records,
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def analyzer(
    content: str, *, fallback: str | None = None, fallback_content: str | None = None
) -> tuple[GroqWardrobeAnalyzer, MockGroqProvider]:
    """The real vision adapter over a scripted transport.

    Returned as a pair so a scenario can assert on which models were called — the difference
    between "the fallback was used for availability" and "the fallback was used to get a
    more confident answer" is visible only in that list (Case 24).
    """
    script: dict[str, Any] = {VISION_MODEL: content}
    if fallback is not None:
        script[fallback] = fallback_content
    transport = MockGroqProvider(script=script)
    return (
        GroqWardrobeAnalyzer(
            transport,
            model=VISION_MODEL,
            fallback_model=fallback,
            urls=FakeImageReferences(),
        ),
        transport,
    )


__all__ = [
    "FOREIGN_ITEM",
    "OWNED",
    "SUPPLIED_TRENDS",
    "TEXT_MODEL",
    "U1",
    "U2",
    "VISION_FALLBACK",
    "VISION_MODEL",
    "Stack",
    "analyzer",
    "stack",
    "supplied_trend_source",
    "wardrobe",
]
