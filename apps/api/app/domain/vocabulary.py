"""Closed vocabularies for the extraction fields that are lists.

S8 found the hole these fill. `style_tags` is free text written by a vision model, it is
**not rendered on the garment card**, and `app/adapters/prompts.py` interpolates it into the
*advice* prompt. So it is a channel into a second model that the user never sees — the worst
combination of properties a field can have — and the only thing standing in it was a 32
-character ceiling from `app.domain.hygiene`.

Two things went through it in the eval harness:

* `"printed slogan reading ignore pr"` — Case 07's injection, truncated but intact enough to
  survive into a downstream prompt.
* `"size 8, approximately 5 foot 6"` — a description of the person in the photograph, which
  CLAUDE.md forbids outright, stored and carried forward.

Length was the wrong control. A short person-description is still a person-description, and
a truncated instruction is still attacker-influenced text arriving where a model will read
it. What these fields actually are is **enumerations that were typed as strings**, so the
answer is to close them.

## Allow-list, not deny-list

Unknown tags are dropped. That fails closed: the next phrasing of a body description, and
the next injection, are both unknown and both go. A deny-list would need to anticipate them,
and would also strip legitimate garment vocabulary on a bad guess.

The cost is real and small: a genuine style word we did not think of is silently not shown.
Losing a decorative adjective is a much smaller harm than storing a stranger's estimate of
someone's dress size, and the vocabulary is one edit away when a gap shows up.

## Why the fields stay `list[str]` in the domain

A `Literal` would make an unrecognised tag fail the whole extraction, turning a decorative
word into a failed photograph (Case 06's ladder for something trivial). Instead the
vocabulary reaches the provider as a schema `enum` — so it is guidance the model is given —
and `hygiene.sanitize_extraction` enforces it by filtering. Off-vocabulary output costs the
tag, never the garment.

## What is deliberately still free text

`subcategory`, `pattern`, `color_primary`, `color_secondary` and `fit`. These are open sets
in the world — a garment really can be a "wrap midi skirt" — and, crucially, all five are
**rendered on the garment card and offered for correction**. A person-description landing in
one of them is visible to the user and fixable by them in one tap, which is a different
class of problem from one that only a downstream prompt ever sees. They stay bounded by
length and stripped of control characters, and that is the honest limit of what this module
claims. See docs/DECISIONS.md and blocker B18.
"""

from __future__ import annotations

#: Adjectives describing how a garment reads, not who is wearing it.
STYLE_TAGS: frozenset[str] = frozenset(
    {
        "athleisure",
        "bohemian",
        "casual",
        "classic",
        "coastal",
        "cosy",
        "cropped",
        "edgy",
        "elevated",
        "fitted",
        "flowing",
        "formal",
        "graphic",
        "grunge",
        "layering",
        "longline",
        "military",
        "minimal",
        "monochrome",
        "nautical",
        "neutral",
        "normcore",
        "outdoor",
        "oversized",
        "preppy",
        "printed",
        "relaxed",
        "retro",
        "romantic",
        "sleek",
        "sporty",
        "statement",
        "streetwear",
        "structured",
        "tailored",
        "textured",
        "utilitarian",
        "vintage",
        "western",
        "workwear",
    }
)

SEASON_TAGS: frozenset[str] = frozenset(
    {"spring", "summer", "autumn", "winter", "all-season", "transitional"}
)

OCCASION_TAGS: frozenset[str] = frozenset(
    {
        "everyday",
        "work",
        "weekend",
        "evening",
        "formal",
        "party",
        "travel",
        "active",
        "lounge",
        "outdoor",
    }
)

#: What the model may say went wrong with the photograph.
#:
#: Closed for a second reason as well as the channel: the web renders each of these as a
#: specific sentence and falls back to "Worth a second look" for anything else. Before this
#: was a fixed set the model was free to invent a warning, and an invented warning rendered
#: as the generic one — a quality signal that reached the user with its meaning removed.
QUALITY_WARNINGS: frozenset[str] = frozenset(
    {
        "low_light",
        "blurred",
        "cropped",
        "multiple_garments",
        "obscured",
        "no_garment_detected",
        "colour_uncertain",
    }
)

#: Field name to its vocabulary. Read by `app.domain.hygiene` to filter and by
#: `app.domain.schemas` to publish the enum to the provider — one definition, two uses, so
#: the set we ask for and the set we accept cannot drift.
VOCABULARIES: dict[str, frozenset[str]] = {
    "style_tags": STYLE_TAGS,
    "season_tags": SEASON_TAGS,
    "occasion_tags": OCCASION_TAGS,
    "quality_warnings": QUALITY_WARNINGS,
}


def permitted(field: str, value: str) -> bool:
    """Is this an allowed value for a closed field? Case-insensitive, whitespace-trimmed.

    Tolerant about spelling and strict about membership: a model answering "Minimal" means
    the tag, and a model answering "minimal, elevated" in one string does not.
    """
    vocabulary = VOCABULARIES.get(field)
    if vocabulary is None:
        return True
    return value.strip().lower() in vocabulary


__all__ = [
    "OCCASION_TAGS",
    "QUALITY_WARNINGS",
    "SEASON_TAGS",
    "STYLE_TAGS",
    "VOCABULARIES",
    "permitted",
]
