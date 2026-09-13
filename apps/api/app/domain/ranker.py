"""The deterministic ranker — rung 4 of the fallback ladder.

It builds outfits from items the user owns, with no LLM involved, and it exists for one
reason: when the agent crew is unavailable the user still owns a wardrobe, and a provider
outage is not their problem.

## What it is not

It is not a demo mode and it is not a product path. `docs/AI-SYSTEM.md` puts it below the
crew, and the application must never route here while the provider is healthy. Two design
choices keep that honest:

* It has no `advise()` method, so it does **not** satisfy the `OutfitAdvisor` Protocol and
  cannot be injected as the advisor. A fallback that is structurally substitutable for the
  real thing is one config change away from becoming the product.
* Its output always carries `degradation_level` 4 or 5, and its rationale says so in words.
  A degraded answer that looks identical to a full one is the gimmick this project exists
  to avoid.

There is no curated fallback outfit. When a required role has nothing to fill it, this
returns no outfit and names the gap — a look assembled from garments the user does not own
would break the one rule the product rests on.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import product
from typing import NamedTuple

from app.domain.compatibility import (
    ADDITIVE_ROLES,
    CORE_ROLES,
    group_by_role,
    is_valid_combination,
    missing_roles,
    name_gaps,
)
from app.domain.models import (
    AdviceRequest,
    GarmentCategory,
    Outfit,
    OutfitAdvice,
    WardrobeItem,
)
from app.domain.scoring import ScoreBreakdown, describe, score_outfit, solo_score

#: Enumeration is a product of per-role counts, so it has to be bounded: a 200-garment
#: wardrobe would otherwise be a timeout. Eight per role caps the search at 8^3 = 512
#: combinations for the three core roles, which is milliseconds and still wide enough that
#: the shortlist is a real choice rather than a formality.
MAX_CANDIDATES_PER_ROLE = 8

#: How many distinct looks to keep. Case 10 asks for diversity, so the caller gets
#: alternatives rather than one answer to take or leave.
DEFAULT_LIMIT = 3

#: Kept, unused by `advise`, and deliberately so — see the note below on why the ranker no
#: longer writes its own disclosure into the rationale. Exported because a non-browser client
#: reading `degradation_level` off the API has to render *something*, and one wording beats
#: each caller inventing its own.
DEGRADED_NOTE = (
    "Styled without the full advisory crew, so this is a shorter read than usual — "
    "the pieces are all yours and the reasoning is reduced, not the wardrobe."
)


class RankedLook(NamedTuple):
    items: list[WardrobeItem]
    breakdown: ScoreBreakdown


class DeterministicRanker:
    """Ranks owned items into valid outfits without a model.

    Stateless; safe to share. Every method is pure with respect to its arguments.
    """

    def shortlist(
        self, request: AdviceRequest
    ) -> dict[GarmentCategory, list[WardrobeItem]]:
        """The best `MAX_CANDIDATES_PER_ROLE` items per role, ordered deterministically.

        Sorted by solo score descending, then by `item_id` ascending. The id tie-break is
        what makes the whole ranker stable: without it two equally-scoring garments would
        order by however the database happened to return them, and the same wardrobe would
        produce different outfits on different days.
        """
        grouped = group_by_role(request.candidates)
        roles = tuple(request.required_roles or CORE_ROLES) + ADDITIVE_ROLES

        shortlist: dict[GarmentCategory, list[WardrobeItem]] = {}
        for role in roles:
            bucket = grouped.get(role, [])
            if not bucket:
                continue
            ordered = sorted(bucket, key=lambda i: (-solo_score(i, request), i.item_id))
            shortlist[role] = ordered[:MAX_CANDIDATES_PER_ROLE]
        return shortlist

    def rank(self, request: AdviceRequest, *, limit: int = DEFAULT_LIMIT) -> list[RankedLook]:
        """Valid outfits, best first. Empty when a required role cannot be filled."""
        required = tuple(request.required_roles or CORE_ROLES)
        if missing_roles(request.candidates, required):
            return []

        shortlist = self.shortlist(request)
        buckets = [shortlist.get(role, []) for role in required]
        if not all(buckets):
            return []

        looks: list[RankedLook] = []
        for combination in product(*buckets):
            items = list(combination)
            if not is_valid_combination(items, required):
                continue
            looks.append(RankedLook(items, score_outfit(items, request)))

        # Total descending, then ids ascending. Both keys matter: the first is the ranking,
        # the second is the reason the ranking is reproducible.
        looks.sort(key=lambda look: (-look.breakdown.total, tuple(i.item_id for i in look.items)))
        return looks[:limit]

    def compose(self, request: AdviceRequest) -> OutfitAdvice:
        """One outfit, or an honest statement of what is missing.

        Rung 4 when it can build something; rung 5 when it cannot. Those are the last two
        rungs of the ladder in docs/AI-SYSTEM.md and there is nothing below them.
        """
        required = tuple(request.required_roles or CORE_ROLES)
        ranked = self.rank(request, limit=1)

        if not ranked:
            return self.gap_advice(request.candidates, required)

        look = ranked[0]
        return OutfitAdvice(
            outfit=Outfit(
                item_ids=[item.item_id for item in look.items],
                name=self._name(look.items),
                occasion=request.occasion,
                match_score=round(look.breakdown.total * 100),
            ),
            # The disclosure is **not** a rationale line. S11 found the result screen saying
            # it twice, in two wordings, stacked: once from here and once from the client's
            # own `degradation_level` footer. They read as a stutter, and only one of them
            # was right about where it belongs — a rationale line explains the *outfit*
            # (palette, volumes, shapes), and how deeply the pipeline reasoned is a fact
            # about the pipeline. `degradation_level` already carries it, for every rung
            # rather than only this one.
            rationale=list(describe(look.breakdown)),
            confidence=round(look.breakdown.total, 2),
            degradation_level=4,
        )

    @staticmethod
    def gap_advice(
        candidates: Sequence[WardrobeItem], required: Sequence[GarmentCategory] = CORE_ROLES
    ) -> OutfitAdvice:
        """Rung 5. Name what is missing and stop.

        Static because the composition service needs this answer before it has decided
        whether to call an advisor at all — there is nothing to deliberate about when a role
        is empty.
        """
        gaps = name_gaps(candidates, required)
        absent = missing_roles(candidates, required)
        listed = " and ".join(role.value for role in absent)
        return OutfitAdvice(
            outfit=None,
            missing_roles=absent,
            wardrobe_gaps=gaps,
            rationale=[
                f"Your wardrobe needs {listed} before this look can be built.",
                "Nothing gets invented on your behalf — add a photo and it will compose.",
            ],
            degradation_level=5,
        )

    @staticmethod
    def _name(items: Sequence[WardrobeItem]) -> str:
        """A short descriptive name from what was actually extracted.

        Colour and cut only. No claim about material, durability, cost or the person
        wearing it (AI-EVAL-CASES Case 22) — this names the look, it does not review it.
        """
        grouped = group_by_role(items)
        top = grouped.get(GarmentCategory.TOP, [])
        fits = {i.extraction.fit for i in items if i.extraction.fit}
        colour = top[0].extraction.color_primary if top else None

        if colour and "relaxed" in fits:
            return f"Relaxed {colour.title()}"
        if colour:
            return f"{colour.title()} Everyday"
        return "Everyday Look"


__all__ = [
    "DEFAULT_LIMIT",
    "DEGRADED_NOTE",
    "MAX_CANDIDATES_PER_ROLE",
    "DeterministicRanker",
    "RankedLook",
]
