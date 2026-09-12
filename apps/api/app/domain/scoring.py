"""Compatibility scoring across the six dimensions named in prompts/04.

    style compatibility · colour harmony · silhouette balance · occasion fit ·
    preference match · wardrobe variety

Every dimension returns 0..1 and every one is a pure function, so a look can be explained
by pointing at the breakdown rather than at a single opaque number.

## What this is not

It is not colour science and it is not a fit measurement. `docs/PRD.md` calls Style Match a
UX heuristic, and the rules below are heuristics of exactly that kind: a small neutral set,
a coarse warm/cool split, and a volume ordering over fit words. They are deliberately
legible — a user who disagrees with a score should be able to see why it came out that way.

Where a dimension has no evidence it returns `NEUTRAL` (0.5) rather than 0 or 1. An item
whose colour was never extracted is not a clash and is not a match; scoring it either way
would turn a missing reading into a confident claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.models import AdviceRequest, Formality, WardrobeItem

#: Returned by any dimension that has nothing to go on.
NEUTRAL = 0.5

#: Weights sum to 1.0, so `total` is directly a 0..1 figure.
WEIGHTS: dict[str, float] = {
    "style": 0.20,
    "color": 0.20,
    "silhouette": 0.15,
    "occasion": 0.20,
    "preference": 0.20,
    "variety": 0.05,
}

#: Colours that sit beside anything. Spelling variants included because extraction is free
#: text and "grey"/"gray" is not a styling distinction.
NEUTRALS: frozenset[str] = frozenset(
    {
        "black", "white", "grey", "gray", "charcoal", "navy", "beige", "cream", "ivory",
        "tan", "stone", "khaki", "off-white", "ecru", "camel", "denim", "indigo",
    }
)

#: A coarse warm/cool split. Two non-neutral families in one look is a deliberate choice;
#: three is usually an accident.
HUE_FAMILY: dict[str, str] = {
    "red": "warm", "burgundy": "warm", "maroon": "warm", "orange": "warm", "rust": "warm",
    "yellow": "warm", "mustard": "warm", "brown": "warm", "chocolate": "warm", "pink": "warm",
    "coral": "warm", "peach": "warm",
    "blue": "cool", "teal": "cool", "green": "cool", "olive": "cool", "sage": "cool",
    "mint": "cool", "purple": "cool", "lilac": "cool", "lavender": "cool", "aqua": "cool",
}

#: Volume ordering over the fit vocabulary. Distance between volumes is what reads as
#: balance, so the scale matters more than the labels.
FIT_VOLUME: dict[str, int] = {
    "skinny": 0, "slim": 0, "fitted": 0, "tailored": 1, "regular": 1, "straight": 1,
    "relaxed": 2, "loose": 2, "wide": 3, "oversized": 3, "baggy": 3,
}

FORMALITY_RANK: dict[Formality, int] = {
    Formality.CASUAL: 0,
    Formality.SMART_CASUAL: 1,
    Formality.FORMAL: 2,
}

#: What each occasion asks of formality. Unknown occasions fall back to smart-casual, which
#: is the least wrong answer when we genuinely do not know.
OCCASION_FORMALITY: dict[str, Formality] = {
    "everyday": Formality.CASUAL,
    "college": Formality.CASUAL,
    "campus": Formality.CASUAL,
    "weekend": Formality.CASUAL,
    "travel": Formality.CASUAL,
    "gym": Formality.CASUAL,
    "work": Formality.SMART_CASUAL,
    "office": Formality.SMART_CASUAL,
    "evening": Formality.SMART_CASUAL,
    "date": Formality.SMART_CASUAL,
    "dinner": Formality.SMART_CASUAL,
    "interview": Formality.FORMAL,
    "wedding": Formality.FORMAL,
    "formal": Formality.FORMAL,
}
DEFAULT_OCCASION_FORMALITY = Formality.SMART_CASUAL


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Per-dimension scores plus the weighted total. All values 0..1."""

    style: float
    color: float
    silhouette: float
    occasion: float
    preference: float
    variety: float
    total: float

    def as_dict(self) -> dict[str, float]:
        return {
            "style": self.style,
            "color": self.color,
            "silhouette": self.silhouette,
            "occasion": self.occasion,
            "preference": self.preference,
            "variety": self.variety,
            "total": self.total,
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _colour_words(item: WardrobeItem) -> list[str]:
    colours = (item.extraction.color_primary, item.extraction.color_secondary)
    return [c.strip().lower() for c in colours if c]


def _families(items: Sequence[WardrobeItem]) -> set[str]:
    found: set[str] = set()
    for item in items:
        for word in _colour_words(item):
            if word in NEUTRALS:
                continue
            family = HUE_FAMILY.get(word)
            found.add(family or f"unmapped:{word}")
    return found


def style_compatibility(items: Sequence[WardrobeItem]) -> float:
    """Do these garments belong to the same style world?

    Measured as the share of items carrying at least one tag the rest of the look also
    carries. A single shared thread is enough — a look does not need every item tagged
    identically, it needs them not to be strangers.
    """
    tagged = [set(i.extraction.style_tags) for i in items if i.extraction.style_tags]
    if len(tagged) < 2:
        return NEUTRAL

    connected = 0
    for index, tags in enumerate(tagged):
        others: set[str] = set().union(*(t for j, t in enumerate(tagged) if j != index))
        if tags & others:
            connected += 1
    return _clamp(connected / len(tagged))


def color_harmony(items: Sequence[WardrobeItem]) -> float:
    """Neutral-anchored looks score well; one accent family scores best; three clash.

    An all-neutral look is safe rather than interesting, so it scores high but not top —
    otherwise the ranker would always reach for black on black on black.
    """
    if not any(_colour_words(i) for i in items):
        return NEUTRAL

    families = _families(items)
    unmapped = {f for f in families if f.startswith("unmapped:")}
    known = families - unmapped

    # An unrecognised colour word is missing evidence, not a clash.
    if unmapped and not known:
        return NEUTRAL

    return {0: 0.85, 1: 1.0, 2: 0.55}.get(len(known), 0.25)


def silhouette_balance(items: Sequence[WardrobeItem]) -> float:
    """Some contrast in volume reads as intentional; none, or total contrast, does not.

    A relaxed top over a straight trouser is the classic balanced pair. Oversized head to
    toe loses shape; slim head to toe reads as a costume more often than a look.
    """
    volumes = [
        FIT_VOLUME[i.extraction.fit.strip().lower()]
        for i in items
        if i.extraction.fit and i.extraction.fit.strip().lower() in FIT_VOLUME
    ]
    if len(volumes) < 2:
        return NEUTRAL

    spread = max(volumes) - min(volumes)
    if spread in (1, 2):
        return 1.0
    if spread == 0:
        # Uniform: fine in the middle of the range, poor at either extreme.
        return 0.8 if volumes[0] == 1 else 0.4
    return 0.6  # spread of 3 — contrast so wide it stops being balance


def occasion_fit(items: Sequence[WardrobeItem], occasion: str) -> float:
    """Distance from the formality the occasion asks for.

    Scored per item and averaged, so one wrong register in an otherwise right look costs
    something without disqualifying it — that is a judgement call for the user, not for us.
    """
    target = OCCASION_FORMALITY.get((occasion or "").strip().lower(), DEFAULT_OCCASION_FORMALITY)
    ranks = [
        FORMALITY_RANK[i.extraction.formality] for i in items if i.extraction.formality is not None
    ]
    if not ranks:
        return NEUTRAL

    worst_case = max(FORMALITY_RANK.values())
    distances = [abs(rank - FORMALITY_RANK[target]) / worst_case for rank in ranks]
    return _clamp(1.0 - sum(distances) / len(distances))


def preference_match(items: Sequence[WardrobeItem], request: AdviceRequest) -> float:
    """How well the look answers what the user actually asked for.

    Distinct from `style_compatibility`: that asks whether the items agree with each other,
    this asks whether they agree with the user. A perfectly coherent look in the wrong vibe
    should score well on one and badly on the other.
    """
    signals: list[float] = []

    vibe = (request.vibe or "").strip().lower()
    if vibe:
        tagged = [i for i in items if i.extraction.style_tags]
        if tagged:
            hits = sum(1 for i in tagged if vibe in {t.lower() for t in i.extraction.style_tags})
            signals.append(hits / len(tagged))

    wanted_fit = (request.fit_preference or "").strip().lower()
    if wanted_fit in FIT_VOLUME:
        with_fit = [i for i in items if i.extraction.fit]
        if with_fit:
            target = FIT_VOLUME[wanted_fit]
            worst = max(FIT_VOLUME.values())
            near = [
                1.0 - abs(FIT_VOLUME.get(i.extraction.fit.strip().lower(), target) - target) / worst
                for i in with_fit
                if i.extraction.fit
            ]
            signals.append(sum(near) / len(near))

    wanted_colours = {c.strip().lower() for c in request.color_preferences if c.strip()}
    if wanted_colours:
        with_colour = [i for i in items if _colour_words(i)]
        if with_colour:
            hits = sum(1 for i in with_colour if wanted_colours & set(_colour_words(i)))
            signals.append(hits / len(with_colour))

    if not signals:
        return NEUTRAL
    return _clamp(sum(signals) / len(signals))


def wardrobe_variety(items: Sequence[WardrobeItem]) -> float:
    """Penalises a look that repeats itself.

    Two near-identical garments in one outfit is the deterministic ranker's characteristic
    failure — it finds a high-scoring item and reaches for its twin. Wear-recency is the
    other half of variety and needs a wear history, which arrives with the planner in S9;
    until then this measures variety *within* the look only, and is weighted lightly
    because that is all it can honestly claim.
    """
    if len(items) < 2:
        return NEUTRAL

    subcategories = [
        (i.extraction.subcategory or "").strip().lower() for i in items if i.extraction.subcategory
    ]
    distinct_shapes = (
        len(set(subcategories)) / len(subcategories) if subcategories else NEUTRAL
    )

    tags = [t.lower() for i in items for t in i.extraction.style_tags]
    tag_spread = len(set(tags)) / len(tags) if tags else NEUTRAL

    return _clamp(0.7 * distinct_shapes + 0.3 * tag_spread)


def score_outfit(items: Sequence[WardrobeItem], request: AdviceRequest) -> ScoreBreakdown:
    """The six dimensions and their weighted total."""
    style = style_compatibility(items)
    color = color_harmony(items)
    silhouette = silhouette_balance(items)
    occasion = occasion_fit(items, request.occasion)
    preference = preference_match(items, request)
    variety = wardrobe_variety(items)

    total = (
        WEIGHTS["style"] * style
        + WEIGHTS["color"] * color
        + WEIGHTS["silhouette"] * silhouette
        + WEIGHTS["occasion"] * occasion
        + WEIGHTS["preference"] * preference
        + WEIGHTS["variety"] * variety
    )
    return ScoreBreakdown(
        style=style,
        color=color,
        silhouette=silhouette,
        occasion=occasion,
        preference=preference,
        variety=variety,
        total=_clamp(total),
    )


def match_score(items: Sequence[WardrobeItem], request: AdviceRequest) -> int:
    """The 0..100 figure shown as Style Match. A UX heuristic, never a measurement."""
    return round(score_outfit(items, request).total * 100)


def solo_score(item: WardrobeItem, request: AdviceRequest) -> float:
    """How promising one garment is on its own, for shortlisting.

    Only the dimensions that make sense for a single item: colour, silhouette and variety
    all need a second garment to mean anything.
    """
    occasion = occasion_fit([item], request.occasion)
    preference = preference_match([item], request)
    return (occasion + preference) / 2


def describe(breakdown: ScoreBreakdown) -> list[str]:
    """Short, honest sentences for the strongest dimensions.

    No claim about material, durability, body or price (AI-EVAL-CASES Case 22). These lines
    describe the *scoring*, which is something the system actually knows.
    """
    phrases = {
        "style": "The pieces share a style language.",
        "color": "The palette holds together.",
        "silhouette": "The volumes balance top to bottom.",
        "occasion": "The register suits the occasion.",
        "preference": "It follows the preferences you set.",
        "variety": "Three distinct shapes rather than variations on one.",
    }
    ranked = sorted(
        ((name, value) for name, value in breakdown.as_dict().items() if name != "total"),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [phrases[name] for name, value in ranked[:3] if value > NEUTRAL]


__all__ = [
    "FIT_VOLUME",
    "FORMALITY_RANK",
    "HUE_FAMILY",
    "NEUTRAL",
    "NEUTRALS",
    "OCCASION_FORMALITY",
    "WEIGHTS",
    "ScoreBreakdown",
    "color_harmony",
    "describe",
    "match_score",
    "occasion_fit",
    "preference_match",
    "score_outfit",
    "silhouette_balance",
    "solo_score",
    "style_compatibility",
    "wardrobe_variety",
]
