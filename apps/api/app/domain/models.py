"""Domain models.

Mirrors docs/DATA-MODEL.md. Note what is absent and must stay absent: brand, price,
commerce_url, active. The product sells nothing (docs/DECISIONS.md, 2026-09-12).

These are the types the adapter Protocols speak. They contain no vendor concepts — no model
id, no provider name, no framework object — so an adapter can be swapped without the domain
noticing.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GarmentCategory(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    FOOTWEAR = "footwear"
    OUTERWEAR = "outerwear"
    ACCESSORY = "accessory"


class Formality(StrEnum):
    CASUAL = "casual"
    SMART_CASUAL = "smart-casual"
    FORMAL = "formal"


class ItemStatus(StrEnum):
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GarmentImage(Strict):
    """A reference to a stored image. Never raw bytes through domain code."""

    asset_id: str
    storage_key: str
    #: The user's own selection at upload time. A prior for the live analyzer.
    category_hint: GarmentCategory | None = None


class GarmentExtraction(Strict):
    """What a vision model claims about one garment.

    `material_guess` is named a guess deliberately: it must read as one on screen, and a
    tip that asserts fibre content as fact is dropped (AI-EVAL-CASES Case 22).
    """

    category: GarmentCategory | None = None
    subcategory: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    pattern: str | None = None
    material_guess: str | None = None
    fit: str | None = None
    formality: Formality | None = None
    season_tags: list[str] = Field(default_factory=list)
    occasion_tags: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)


class WardrobeItem(Strict):
    item_id: str
    #: The ownership root. Every retrieval filters on this in SQL, before any prompt.
    user_id: str
    status: ItemStatus
    extraction: GarmentExtraction
    #: Fields the user corrected. Never recomputed by a later extraction.
    corrected_fields: list[str] = Field(default_factory=list)


class TrendQuery(Strict):
    categories: list[GarmentCategory] = Field(default_factory=list)
    region: str | None = None


class TrendNote(Strict):
    """A trend claim. Unattributed notes are dropped, not rendered."""

    trend: str
    source: str = Field(min_length=1)
    published_at: date
    applies_to_items: list[str] = Field(default_factory=list)


class AdviceRequest(Strict):
    user_id: str
    #: Already ownership-scoped. An advisor never widens this set.
    candidates: list[WardrobeItem]
    occasion: str
    vibe: str | None = None
    #: What the user asked for, not a measurement of them. Style Match is a UX heuristic.
    fit_preference: str | None = None
    color_preferences: list[str] = Field(default_factory=list)
    required_roles: list[GarmentCategory] = Field(default_factory=list)
    trend_notes: list[TrendNote] = Field(default_factory=list)


class Outfit(Strict):
    item_ids: list[str]
    name: str
    occasion: str
    match_score: int = Field(ge=0, le=100)


class ProTip(Strict):
    tip: str
    type: str


class WardrobeGap(Strict):
    """A named gap. Generic only — no brand, price, merchant or link."""

    category: GarmentCategory
    generic_description: str
    unlocks_outfits: int = Field(ge=0)


class OutfitAdvice(Strict):
    outfit: Outfit | None = None
    rationale: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    pro_tips: list[ProTip] = Field(default_factory=list)
    budget_tricks: list[str] = Field(default_factory=list)
    wardrobe_gaps: list[WardrobeGap] = Field(default_factory=list)
    trend_notes: list[TrendNote] = Field(default_factory=list)
    missing_roles: list[GarmentCategory] = Field(default_factory=list)
    #: 1 = full crew, 5 = honest gap statement. docs/AGENT-SYSTEM.md.
    degradation_level: int = Field(default=1, ge=1, le=5)
