"""Advisory safety — AI-EVAL-CASES Case 22.

The piece of `docs/ARCHITECTURE.md` section 6 step 8 that was outstanding at the end of S4:
"drop unattributed trend notes and unsupportable tips". The trend half is in
`test_composition.py`; this is the tips half.

The distinction the tests care about most is between text **about a garment the user owns**,
where a material word launders `material_guess` into a fact, and a **wardrobe gap**, where a
material word is simply how the category is named. `docs/AI-EVAL-CASES.md` uses "a white
leather sneaker" as its own example of a good gap, so a filter that rejected it would be
wrong about the spec it came from.
"""

from __future__ import annotations

import pytest

from app.domain.advisory import (
    is_supportable,
    sanitize_advisory,
    unsupportable_reasons,
)
from app.domain.compatibility import GAP_DESCRIPTIONS
from app.domain.models import GarmentCategory as C
from app.domain.models import Outfit, OutfitAdvice, ProTip, WardrobeGap


def advice(**over) -> OutfitAdvice:
    payload = {
        "outfit": Outfit(item_ids=["a", "b", "c"], name="x", occasion="everyday", match_score=80),
        "rationale": ["The palette holds together."],
        "confidence": 0.8,
    }
    payload.update(over)
    return OutfitAdvice(**payload)


# --- what is refused --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This wool blend will last years if you air it.", "states fibre content as fact"),
        ("The cotton breathes well in summer.", "states fibre content as fact"),
        ("A hardwearing piece you will keep forever.", "claims durability"),
        ("At around £40 it was a bargain.", "makes a commerce claim"),
        ("Worth $80 of anyone's money.", "names a price"),
        ("See https://example.com/shop for more.", "contains a link"),
        ("This cut flatters your shape.", "comments on the user's body"),
        ("A slimming silhouette for your body type.", "comments on the user's body"),
    ],
)
def test_an_unsupportable_claim_is_named_and_refused(text, expected):
    assert not is_supportable(text)
    assert expected in unsupportable_reasons(text)


@pytest.mark.parametrize(
    "text",
    [
        "Half-tuck the shirt to shorten the torso line.",
        "Cuff the trouser once so the shoe reads as deliberate.",
        "Worn open over a plain tee this is a second outfit from one garment.",
        "Shop your own wardrobe before adding anything.",
        "Brand new pieces are not what this look needs.",
        "Air it between wears rather than washing every time.",
        "The volumes balance top to bottom.",
    ],
)
def test_genuine_styling_advice_survives(text):
    """The filter must not eat the product.

    "Shop your own wardrobe" and "brand new" are here on purpose: both contain a word that
    a naive commerce word list would flag, and both are advice worth keeping. That is why
    `shop` and `brand` are deliberately absent from `COMMERCE_WORDS`.
    """
    assert is_supportable(text), unsupportable_reasons(text)


def test_a_word_inside_another_word_is_not_a_match():
    """Word boundaries, so "buying" does not make "unbuying" of it — and, more usefully,
    a colour like "silky-looking" does not become a fibre claim."""
    assert is_supportable("A woolly idea is not the same as a wool claim.") is False
    assert is_supportable("Buttoned to the collar.") is True


# --- the gap exemption ------------------------------------------------------------------


def test_a_gap_may_name_a_material_because_that_is_the_category():
    """docs/AI-EVAL-CASES.md uses exactly this sentence as a well-formed gap."""
    text = "a white leather sneaker would unlock five more outfits"

    assert is_supportable(text, about_owned_garment=False) is True
    # And the same sentence about something owned would not be.
    assert is_supportable(text, about_owned_garment=True) is False


def test_every_built_in_gap_description_passes_its_own_filter():
    """`GAP_DESCRIPTIONS` includes "a simple leather belt". If the filter rejected the
    product's own copy, the filter would be wrong — this is the test that catches that."""
    for category, description in GAP_DESCRIPTIONS.items():
        assert is_supportable(description, about_owned_garment=False), (
            f"{category.value}: {unsupportable_reasons(description, about_owned_garment=False)}"
        )


def test_a_gap_still_cannot_name_a_price_or_a_shop():
    for text in ("a sneaker for about $60", "pick one up at example.com"):
        assert not is_supportable(text, about_owned_garment=False)


# --- sanitising a whole response --------------------------------------------------------


def test_an_unsupportable_tip_is_dropped_and_the_reason_reported():
    subject = advice(
        pro_tips=[
            ProTip(tip="Half-tuck the shirt.", type="proportion"),
            ProTip(tip="This wool blend will last years.", type="care"),
        ]
    )

    cleaned, dropped = sanitize_advisory(subject)

    assert [t.tip for t in cleaned.pro_tips] == ["Half-tuck the shirt."]
    assert len(dropped) == 1
    assert "pro_tip" in dropped[0]
    assert "fibre" in dropped[0]


def test_the_tip_is_dropped_whole_rather_than_edited():
    """Editing would leave a sentence the model never wrote, asserted with its authority,
    and nothing can check the edit preserved the meaning."""
    subject = advice(pro_tips=[ProTip(tip="This wool blend drapes nicely.", type="fit")])

    cleaned, _ = sanitize_advisory(subject)

    assert cleaned.pro_tips == []
    assert not any("drapes nicely" in t.tip for t in cleaned.pro_tips)


def test_budget_tricks_and_rationale_are_filtered_too():
    """Rationale is rendered to the user exactly as a tip is, so the same rule applies."""
    subject = advice(
        rationale=["Clean lines.", "The silk lining will outlast the jacket."],
        budget_tricks=["Re-wear it twice before washing.", "It was a bargain at £30."],
    )

    cleaned, dropped = sanitize_advisory(subject)

    assert cleaned.rationale == ["Clean lines."]
    assert cleaned.budget_tricks == ["Re-wear it twice before washing."]
    assert len(dropped) == 2


def test_a_clean_response_is_returned_unchanged_and_reports_nothing():
    """Identity, not a copy: a filter that rebuilds every response makes every response
    look touched in a diff, and hides the ones that actually were."""
    subject = advice(pro_tips=[ProTip(tip="Cuff the trouser once.", type="proportion")])

    cleaned, dropped = sanitize_advisory(subject)

    assert cleaned is subject
    assert dropped == []


def test_the_outfit_itself_is_never_altered_by_the_filter():
    """This is a content filter on presentational fields. It has no business touching which
    garments were chosen — that is ownership and compatibility validation, upstream."""
    subject = advice(pro_tips=[ProTip(tip="Worth $200.", type="value")])

    cleaned, _ = sanitize_advisory(subject)

    assert cleaned.outfit == subject.outfit
    assert cleaned.confidence == subject.confidence


def test_a_gap_description_survives_sanitising_while_a_tip_with_the_same_word_does_not():
    subject = advice(
        pro_tips=[ProTip(tip="The leather will soften over time.", type="care")],
        wardrobe_gaps=[
            WardrobeGap(
                category=C.FOOTWEAR,
                generic_description="a white leather sneaker",
                unlocks_outfits=5,
            )
        ],
    )

    cleaned, dropped = sanitize_advisory(subject)

    assert cleaned.pro_tips == []
    assert [g.generic_description for g in cleaned.wardrobe_gaps] == ["a white leather sneaker"]
    assert len(dropped) == 1


def test_a_rationale_reduced_to_nothing_is_not_an_error():
    """The outfit still stands on its score. Refusing to serve it because the copy was
    unusable would turn a cosmetic problem into a failed request."""
    subject = advice(rationale=["This cashmere will last a lifetime."])

    cleaned, dropped = sanitize_advisory(subject)

    assert cleaned.rationale == []
    assert cleaned.outfit is not None
    assert dropped
