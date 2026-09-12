"""Advisory safety — AI-EVAL-CASES Case 22.

`docs/ARCHITECTURE.md` section 6, step 8: "drop unattributed trend notes and unsupportable
tips". The trend half lives in `validation.py`, where ownership is already being checked.
This is the tips half, and it was the piece left outstanding at the end of S4.

## What makes a claim unsupportable

Not tone, and not usefulness — only whether the system is in a position to know it.

* **Fibre content as fact.** The column is `material_guess` and the UI hedges it. A tip
  reading "this wool blend will last years" launders a guess into an assertion and adds a
  durability claim on top.
* **Durability.** The system has never seen the garment wear.
* **Price, merchant, link.** Nothing in the data model is a commerce fact, so any number
  here was invented.
* **The person's body.** No inference about the user from a photograph, ever (`CLAUDE.md`).

## Two rule sets, because a gap is not an owned garment

The fibre and durability rules apply to text **about a garment the user owns**. They do not
apply to `wardrobe_gaps`, which name a kind of garment that is absent — and there the
material word is how people describe the category. `docs/AI-EVAL-CASES.md` uses "a white
leather sneaker" as its own example of a well-formed gap, and `GAP_DESCRIPTIONS` in
`compatibility.py` offers "a simple leather belt". Neither launders a guess, because there
is no garment to have guessed about.

Gaps are still checked for price, merchant, link and body claims. Those are wrong wherever
they appear.

## Dropped, not rewritten

A claim that breaks a rule is removed whole. Editing it — stripping the word "wool", say —
would leave a sentence the model never wrote, asserted with its authority, and nothing can
check that the edit preserved the meaning. Dropping loses a tip; rewriting invents one.

## Why a word list is honest here, and where it would not be

Matching a fibre vocabulary catches the failure this case describes and will miss a
paraphrase. That is acceptable because the cost of a miss is a hedged claim shown unhedged
in cosmetic copy — not a wrong garment, and not another user's data. The rules that carry
real weight (ownership, scope) are enforced structurally, in SQL and in memory, and never by
matching words.

Recorded so nobody later mistakes this for a security boundary: it is a content filter on a
presentational field.
"""

from __future__ import annotations

import re

from app.domain.models import OutfitAdvice, ProTip

#: Fibres and finishes. Naming one as fact asserts what only `material_guess` guessed.
FIBRE_WORDS: frozenset[str] = frozenset(
    {
        "acrylic", "alpaca", "bamboo", "cashmere", "cotton", "elastane", "flannel",
        "fleece", "leather", "linen", "lycra", "merino", "modal", "nylon", "polyester",
        "rayon", "satin", "silk", "spandex", "suede", "tweed", "twill", "velvet", "viscose",
        "wool",
    }
)

#: Durability and longevity.
DURABILITY_PHRASES: frozenset[str] = frozenset(
    {"durable", "hardwearing", "indestructible", "last years", "lasts forever", "outlast",
     "will last", "built to last"}
)

#: Commerce. Deliberately narrow: "shop" and "brand" are excluded because "shop your own
#: wardrobe" is a legitimate budget trick and "brand new" is ordinary English — and the
#: literal word "brand" was never how a brand claim would arrive anyway.
COMMERCE_WORDS: frozenset[str] = frozenset(
    {"bargain", "buy", "cheap", "discount", "merchant", "priced", "retail", "resale"}
)

#: Claims about the wearer.
BODY_PHRASES: frozenset[str] = frozenset(
    {
        "your body", "your figure", "your shape", "your build", "your skin",
        "your complexion", "flatters your", "slimming", "hides your", "body type",
    }
)

#: A currency symbol or an amount. Cheaper than a price grammar, and catches what a model
#: actually writes.
MONEY = re.compile(r"[$£€¥]\s?\d|\b\d+\s?(?:usd|eur|gbp|dollars|pounds|euros|rupees|inr)\b")

#: A link *or* a bare domain. The bare-domain half was added after a test caught that
#: "pick one up at example.com" passed a scheme-only check — which is exactly how a merchant
#: reference would actually be written. Short, ambiguous TLDs (`.co`, `.in`) are left out:
#: they would fire on ordinary prose the moment a space after a full stop went missing, and
#: the cost of a false positive here is a dropped styling tip.
URL = re.compile(
    r"https?://|www\.|\b[a-z0-9][a-z0-9-]*\.(?:com|net|org|io|shop|store|uk|de|fr)\b"
)


def _has_word(lowered: str, words: frozenset[str]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)


def _universal_violations(lowered: str) -> list[str]:
    """Rules that hold for every field, gap descriptions included."""
    broken: list[str] = []
    if _has_word(lowered, COMMERCE_WORDS):
        broken.append("makes a commerce claim")
    if any(phrase in lowered for phrase in BODY_PHRASES):
        broken.append("comments on the user's body")
    if MONEY.search(lowered):
        broken.append("names a price")
    if URL.search(lowered):
        broken.append("contains a link")
    return broken


def _violations(text: str, *, about_owned_garment: bool = True) -> list[str]:
    """Every rule this sentence breaks, named. Empty means it is servable."""
    lowered = text.lower()
    broken = _universal_violations(lowered)

    if about_owned_garment:
        if _has_word(lowered, FIBRE_WORDS):
            broken.append("states fibre content as fact")
        if any(phrase in lowered for phrase in DURABILITY_PHRASES):
            broken.append("claims durability")

    return broken


def is_supportable(text: str, *, about_owned_garment: bool = True) -> bool:
    return not _violations(text, about_owned_garment=about_owned_garment)


def unsupportable_reasons(text: str, *, about_owned_garment: bool = True) -> list[str]:
    """Exposed for logging: a dropped claim should say what it was dropped for."""
    return _violations(text, about_owned_garment=about_owned_garment)


def sanitize_advisory(advice: OutfitAdvice) -> tuple[OutfitAdvice, list[str]]:
    """Drop unsupportable tips, tricks, rationale lines and gap descriptions.

    Returns the cleaned advice and a reason per removal, so the caller can log what was
    dropped rather than the removal being invisible.

    `rationale` is included because it is rendered to the user exactly as a tip is, so the
    same rule applies. A rationale reduced to nothing is not an error — the outfit still
    stands on its score.
    """
    dropped: list[str] = []

    def keep(text: str, label: str, *, about_owned_garment: bool = True) -> bool:
        reasons = _violations(text, about_owned_garment=about_owned_garment)
        if reasons:
            dropped.append(f"{label}: {', '.join(reasons)}")
            return False
        return True

    tips: list[ProTip] = [t for t in advice.pro_tips if keep(t.tip, "pro_tip")]
    tricks = [t for t in advice.budget_tricks if keep(t, "budget_trick")]
    rationale = [r for r in advice.rationale if keep(r, "rationale")]
    gaps = [
        g
        for g in advice.wardrobe_gaps
        if keep(g.generic_description, "wardrobe_gap", about_owned_garment=False)
    ]

    if not dropped:
        return advice, []

    return (
        advice.model_copy(
            update={
                "pro_tips": tips,
                "budget_tricks": tricks,
                "rationale": rationale,
                "wardrobe_gaps": gaps,
            }
        ),
        dropped,
    )


__all__ = [
    "BODY_PHRASES",
    "COMMERCE_WORDS",
    "DURABILITY_PHRASES",
    "FIBRE_WORDS",
    "is_supportable",
    "sanitize_advisory",
    "unsupportable_reasons",
]
