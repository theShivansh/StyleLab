"""Text recovered from a photograph is data, and data has a size.

AI-EVAL-CASES Case 07 is usually read as a prompt-engineering problem: a slogan tee or a
care label says "ignore previous instructions", and the defence is the FORBIDDEN
ASSUMPTIONS section of the vision prompt plus the fact that retrieval scope is fixed in SQL
before the model is called. Both of those are in place (`app/adapters/prompts.py`,
`app/repositories/wardrobe.py`).

This module handles the part that survives all of that. Even a perfectly obedient model
puts the words it read into the fields it was asked to fill — a slogan legitimately belongs
in `pattern` or `style_tags`. So the wardrobe ends up storing attacker-influenced strings,
and those strings are later rendered in the UI and interpolated into the **advice** prompt,
where a downstream model with no memory of where they came from reads them.

The answer is not to detect intent. It is to make the channel too small to carry a payload
and too plain to carry markup:

* **bounded length** — a garment's colour is a word; a paragraph in `color_primary` is not
  a colour. A 30-character ceiling ends an injection attempt without needing to recognise
  one.
* **bounded list length** — `style_tags` is a handful of words, not a corpus.
* **no control characters** — newlines and escapes are what let injected text impersonate a
  prompt's own section headings once interpolated.
* **a closed vocabulary on the list fields** — added in S8, when the eval harness showed
  that length was the wrong control for them. `app.domain.vocabulary` says why: those
  fields go into the *advice* prompt and are never rendered to the user, so a truncated
  instruction and a stranger's estimate of somebody's dress size both survived a ceiling
  and neither was ever seen by the person who could have objected.

Free-text fields are truncated rather than dropped. A truncated colour is still the user's
garment and still correctable; discarding the field would lose a real reading over a length.
List fields are the opposite — an unrecognised tag is dropped, because there is no user
looking at it to notice that it should not be there.

Nothing here is a substitute for the prompt rules or the SQL scope. It is the third layer,
and it is the one that holds when the model is compliant and the content is still hostile.
"""

from __future__ import annotations

import re

from app.domain.models import GarmentExtraction
from app.domain.vocabulary import VOCABULARIES, permitted

#: Per-field ceilings. Generous for what a garment actually is, far too small for a payload.
FIELD_LIMITS: dict[str, int] = {
    "subcategory": 48,
    "color_primary": 30,
    "color_secondary": 30,
    "pattern": 48,
    "material_guess": 48,
    "fit": 30,
}

#: Tag lists: how many, and how long each.
MAX_TAGS = 8
MAX_TAG_CHARS = 32
#: Quality warnings come from our own schema enum in practice, but they are still model
#: output and still rendered.
MAX_WARNINGS = 6

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")

_TAG_FIELDS = ("season_tags", "occasion_tags", "style_tags")


def clean_text(value: str | None, *, limit: int) -> str | None:
    """One field: strip control characters, collapse whitespace, truncate.

    Returns None for a value that is empty once cleaned, so a model answering with a space
    is treated as not answering — which is what the confidence hedge and the correction
    prompt are for.
    """
    if value is None:
        return None
    collapsed = _WHITESPACE.sub(" ", _CONTROL.sub(" ", value)).strip()
    if not collapsed:
        return None
    return collapsed[:limit]


def clean_tags(
    values: list[str], *, max_items: int = MAX_TAGS, field: str | None = None
) -> list[str]:
    """De-duplicated, bounded, order-preserving, and — for a closed field — filtered.

    `field` names the vocabulary to enforce. Passing nothing filters nothing, which is the
    right default for a caller cleaning an open list; every caller inside this module names
    its field, so the closed ones cannot be cleaned by accident without their vocabulary.

    Values are normalised to their canonical spelling rather than kept as the model wrote
    them. "Minimal" and "minimal" are the same tag, and storing both spellings would make
    the set useless for anything but display.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        tag = clean_text(value, limit=MAX_TAG_CHARS)
        if tag is None:
            continue
        key = tag.lower()
        if key in seen:
            continue
        if field is not None and not permitted(field, key):
            continue
        seen.add(key)
        cleaned.append(key if field in VOCABULARIES else tag)
        if len(cleaned) == max_items:
            break
    return cleaned


def sanitize_extraction(extraction: GarmentExtraction) -> GarmentExtraction:
    """Bound every free-text field a model filled in.

    `category` and `formality` are absent from this function on purpose: they are enums,
    already constrained by the schema to a closed set, and a closed set needs no hygiene.
    `field_confidence` is numeric and validated by range. What is left is exactly the text
    a photograph can influence.

    The four list fields are closed too, but by vocabulary rather than by type
    (`app.domain.vocabulary` explains why they are not `Literal`), so unlike the enums they
    are enforced here — the schema asks the provider for the vocabulary and this is what
    holds it to it.
    """
    updates: dict[str, object] = {
        name: clean_text(getattr(extraction, name), limit=limit)
        for name, limit in FIELD_LIMITS.items()
    }
    for name in _TAG_FIELDS:
        updates[name] = clean_tags(getattr(extraction, name), field=name)
    updates["quality_warnings"] = clean_tags(
        extraction.quality_warnings, max_items=MAX_WARNINGS, field="quality_warnings"
    )
    return extraction.model_copy(update=updates)


__all__ = [
    "FIELD_LIMITS",
    "MAX_TAGS",
    "MAX_TAG_CHARS",
    "MAX_WARNINGS",
    "clean_tags",
    "clean_text",
    "sanitize_extraction",
]
