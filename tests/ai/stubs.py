"""Stub adapters and domain fixtures for the proof layer.

These satisfy the adapter Protocols in `app.adapters` structurally, without importing them
and without importing any vendor SDK. They exist so the eval suite can run the whole
grounding path with no API key and no network.

**They are test doubles, not a demo mode.** Nothing under `apps/api/app/` may import this
module; `apps/api/tests/test_query_scoping.py` enforces that. A running STYLELAB always
performs real inference (docs/AI-EVAL-CASES.md Case 25).

Two levels of double live here, and the difference matters:

* **`MockGroqProvider`** replaces the *transport*. The real `GroqWardrobeAnalyzer` and
  `GroqOutfitAdvisor` sit on top of it and run their real prompt construction, real schema
  parsing, real retry and real fallback logic. This is the one that tests the adapter.
* **`ScriptedAdvisor` / `ScriptedAnalyzer`** replace the *adapter*. They test everything
  above the adapter — the composition service and the domain rules — without caring how a
  response was produced.

`ScriptedAdvisor` returns whatever a test hands it, including a well-formed, confident
response naming an item belonging to somebody else. That is the only way to prove Case 11's
second half: that ownership re-validation, not the prompt, is what stops a forged response.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.models import (
    AdviceRequest,
    Formality,
    GarmentCategory,
    GarmentExtraction,
    GarmentImage,
    ItemStatus,
    Outfit,
    OutfitAdvice,
    TrendNote,
    TrendQuery,
    WardrobeItem,
)

# --- domain fixtures ---------------------------------------------------------------------


def garment(
    item_id: str,
    user_id: str = "u1",
    *,
    category: GarmentCategory = GarmentCategory.TOP,
    subcategory: str | None = None,
    color_primary: str = "navy",
    color_secondary: str | None = None,
    pattern: str = "solid",
    material_guess: str | None = "cotton",
    fit: str = "regular",
    formality: Formality = Formality.SMART_CASUAL,
    style_tags: list[str] | None = None,
    season_tags: list[str] | None = None,
    occasion_tags: list[str] | None = None,
    field_confidence: dict[str, float] | None = None,
    quality_warnings: list[str] | None = None,
    status: ItemStatus = ItemStatus.READY,
    corrected_fields: list[str] | None = None,
) -> WardrobeItem:
    """A ready wardrobe item owned by `user_id`. Every field has a workable default so a
    test names only the attribute it is actually about."""
    return WardrobeItem(
        item_id=item_id,
        user_id=user_id,
        status=status,
        corrected_fields=corrected_fields or [],
        extraction=GarmentExtraction(
            category=category,
            subcategory=subcategory or category.value,
            color_primary=color_primary,
            color_secondary=color_secondary,
            pattern=pattern,
            material_guess=material_guess,
            fit=fit,
            formality=formality,
            style_tags=style_tags or ["minimal"],
            season_tags=season_tags or [],
            occasion_tags=occasion_tags or [],
            field_confidence=field_confidence or {"category": 0.96},
            quality_warnings=quality_warnings or [],
        ),
    )


def trend_note(trend: str = "Relaxed tailoring holding through AW26", **over: object) -> TrendNote:
    payload: dict[str, object] = {
        "trend": trend,
        "source": "example-publication",
        "published_at": date(2026, 7, 14),
    }
    payload.update(over)
    return TrendNote(**payload)  # type: ignore[arg-type]


# --- stub adapters -----------------------------------------------------------------------


class ScriptedAdvisor:
    """Returns a pre-set response, whatever it contains.

    Deliberately does no validation of its own. An advisor that policed its own output would
    make the service's ownership check untestable, and in production the advisor is the
    component we least want to trust.
    """

    def __init__(self, response: OutfitAdvice) -> None:
        self.response = response
        self.calls: list[AdviceRequest] = []

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        self.calls.append(request)
        return self.response

    @classmethod
    def naming(cls, *item_ids: str, name: str = "Scripted Look", confidence: float = 0.91):
        """An advisor that confidently returns exactly these ids."""
        return cls(
            OutfitAdvice(
                outfit=Outfit(
                    item_ids=list(item_ids), name=name, occasion="everyday", match_score=88
                ),
                rationale=["Scripted for a test."],
                confidence=confidence,
            )
        )


class FailingAdvisor:
    """Raises on every call, to drive the degradation ladder down to the ranker."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("provider unavailable")
        self.calls = 0

    async def advise(self, request: AdviceRequest) -> OutfitAdvice:
        self.calls += 1
        raise self.error


class ScriptedAnalyzer:
    """Returns queued extractions in order, then repeats the last one."""

    def __init__(self, *extractions: GarmentExtraction) -> None:
        self.queue = list(extractions)
        self.seen: list[GarmentImage] = []

    async def analyze(self, image: GarmentImage) -> GarmentExtraction:
        self.seen.append(image)
        if len(self.queue) > 1:
            return self.queue.pop(0)
        return self.queue[0]


class StaticTrendSource:
    def __init__(self, *notes: TrendNote) -> None:
        self.notes = list(notes)

    async def current(self, query: TrendQuery) -> list[TrendNote]:
        return list(self.notes)


class UnavailableTrendSource:
    async def current(self, query: TrendQuery) -> list[TrendNote]:
        raise RuntimeError("trend corpus unavailable")


# --- provider fixtures -------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "groq"


def fixture(name: str) -> str:
    """One recorded provider response, exactly as it would arrive.

    Returns the raw completion text, not a parsed object: `.json` fixtures are re-serialised
    so the adapter does its own `json.loads`, and `.txt` fixtures are returned untouched so a
    truncated or prose response stays truncated. Validation is what is under test; handing
    the test a parsed dict would skip it.
    """
    path = FIXTURES / name
    if not path.exists():
        available = ", ".join(sorted(p.name for p in FIXTURES.iterdir()))
        raise FileNotFoundError(f"no fixture {name}; have: {available}")

    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.dumps(json.loads(text))
    return text


# --- transport double --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One call the adapter made, for asserting on what it actually sent."""

    model: str
    messages: list[Any]
    schema_name: str | None
    timeout_s: float | None
    max_tokens: int | None

    @property
    def text(self) -> str:
        """Every text part of every message, joined. What the model would read."""
        parts: list[str] = []
        for message in self.messages:
            for part in message.content:
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
        return "\n".join(parts)

    @property
    def image_urls(self) -> list[str]:
        return [
            part["url"]
            for message in self.messages
            for part in message.content
            if part.get("type") == "image_url"
        ]


@dataclass
class MockGroqProvider:
    """A `ChatTransport` that returns scripted content, or raises.

    Scripting is per model so the availability fallback chain can be exercised properly:
    give the primary model an exception and the fallback a payload, and the adapter's own
    logic decides whether to move on. A mock that ignored the model argument could not tell
    a correct fallback from a wrong one.

    `script` entries may be:
      * a `str` — returned as the completion content
      * an `Exception` — raised
      * a `list` of either — consumed in order, the last entry repeating

    `calls` records every request, which is how the prompt-contract tests assert that no
    model id, and no user id, ever reached a prompt.
    """

    script: dict[str, Any] = field(default_factory=dict)
    default: Any = None
    models: set[str] = field(default_factory=set)
    latency_ms: int = 11
    #: Raised by `available_models()`. Used for the boot check's degraded path.
    list_error: Exception | None = None
    calls: list[RecordedCall] = field(default_factory=list)

    @classmethod
    def returning(cls, content: str, *, models: set[str] | None = None) -> MockGroqProvider:
        """Answers every model with the same content."""
        return cls(default=content, models=models or set())

    async def complete(
        self,
        *,
        model: str,
        messages: list[Any],
        schema: Any | None = None,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        from app.adapters.transport import ChatResult

        self.calls.append(
            RecordedCall(
                model=model,
                messages=list(messages),
                schema_name=getattr(schema, "name", None),
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )
        )

        entry = self.script.get(model, self.default)
        if isinstance(entry, list):
            if not entry:
                raise AssertionError(f"mock script for {model} is exhausted")
            value = entry.pop(0) if len(entry) > 1 else entry[0]
        else:
            value = entry

        if isinstance(value, Exception):
            raise value
        if value is None:
            raise AssertionError(f"mock has no scripted response for model {model}")

        return ChatResult(
            content=value,
            model=model,
            latency_ms=self.latency_ms,
            request_id=f"req_mock_{len(self.calls)}",
            prompt_tokens=120,
            completion_tokens=180,
        )

    async def available_models(self) -> set[str]:
        if self.list_error is not None:
            raise self.list_error
        return set(self.models)

    # --- assertions helpers ------------------------------------------------------------

    @property
    def models_called(self) -> list[str]:
        return [call.model for call in self.calls]


class FakeSignedUrls:
    """A `SignedUrlSource` that hands back an opaque, obviously-fake URL.

    Records what it was asked for so a test can assert the analyzer passed a storage key
    and never raw bytes.
    """

    def __init__(self, base: str = "https://storage.example.test/signed") -> None:
        self.base = base
        self.requested: list[tuple[str, int]] = []

    async def signed_url(self, storage_key: str, *, ttl_s: int = 300) -> str:
        self.requested.append((storage_key, ttl_s))
        return f"{self.base}/{storage_key}?exp={ttl_s}"


__all__ = [
    "FIXTURES",
    "FailingAdvisor",
    "FakeSignedUrls",
    "MockGroqProvider",
    "RecordedCall",
    "ScriptedAdvisor",
    "ScriptedAnalyzer",
    "StaticTrendSource",
    "UnavailableTrendSource",
    "fixture",
    "garment",
    "trend_note",
]
