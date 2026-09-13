"""Wardrobe to outfit — the orchestration in docs/ARCHITECTURE.md section 6.

This module is the only place the three layers meet: it holds a repository (SQL), an
advisor (an adapter Protocol) and the domain rules. It lives in `services/` rather than
`domain/` for that reason — `tests/test_adapter_boundary.py` forbids domain code from
importing `app.adapters`, and the dependency direction is worth keeping legible.

The order of operations is the product:

    1  retrieve candidates, scoped to user_id in SQL
    2  no complete outfit possible?  → name the gap and stop (rung 5)
    3  fetch dated trend notes, or drop to rung 2 without them
    4  run the advisor over the retrieved set
    5  validate the shape           (app.domain.schemas, at the adapter edge)
    6  re-validate every item id    (app.domain.validation, in memory, no query)
    7  drop unsupportable tips      (app.domain.advisory)
    8  recompute the score          (deterministic, from the items)
    9  anything failed?             → deterministic ranker over the same set (rung 4)

Steps 4 and 6 are separated deliberately. No amount of agent deliberation substitutes for
the ownership check, and a Critic agent that approved a response is not evidence.

There is no rung below 5. A curated fallback outfit would be made of garments the user does
not own, which is precisely what the grounding rule forbids — so the ladder ends at an
honest statement of what is missing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.adapters import OutfitAdvisor, TrendSource
from app.domain.advisory import sanitize_advisory
from app.domain.compatibility import CORE_ROLES, missing_roles
from app.domain.errors import IncompatibleOutfitError, SchemaInvalidError, UngroundedItemError
from app.domain.models import (
    AdviceRequest,
    GarmentCategory,
    Outfit,
    OutfitAdvice,
    TrendNote,
    TrendQuery,
    WardrobeItem,
)
from app.domain.ranker import DeterministicRanker
from app.domain.scoring import match_score
from app.domain.validation import validate_advice
from app.repositories.wardrobe import WardrobeRepository

logger = logging.getLogger("stylelab.composition")


@dataclass(frozen=True, slots=True)
class Rejection:
    """One discarded advisor response, kept for the evidence trail.

    Held on the service rather than written to `item_extractions`, which is keyed to a
    wardrobe item and audits *extraction*. Composition rejections get their own persistence
    when the compose endpoint lands in S7; recording them in memory now means the S4 tests
    assert on the same object that endpoint will serialise.
    """

    user_id: str
    reason: str
    detail: str


@dataclass
class CompositionService:
    """Composes one outfit for one user.

    Construct per request: it holds a session-bound repository, and `rejections` is
    request-scoped evidence rather than shared state.
    """

    #: `None` when the caller retrieves the candidates itself and passes them to `compose`.
    #: The async job runner does exactly that: this method awaits a provider call, and a
    #: repository held across that await is a database connection checked out for the
    #: length of an HTTP request to Groq (`app/services/compose.py`, and the same rule
    #: `app/services/ingest.py` follows for extraction).
    repository: WardrobeRepository | None
    advisor: OutfitAdvisor
    ranker: DeterministicRanker = field(default_factory=DeterministicRanker)
    trend_source: TrendSource | None = None
    rejections: list[Rejection] = field(default_factory=list)

    async def compose(
        self,
        user_id: str,
        *,
        occasion: str,
        vibe: str | None = None,
        fit_preference: str | None = None,
        color_preferences: Sequence[str] = (),
        required_roles: Sequence[GarmentCategory] = CORE_ROLES,
        candidates: Sequence[WardrobeItem] | None = None,
    ) -> OutfitAdvice:
        required = tuple(required_roles)

        # 1 — scoped retrieval. The grounding guarantee starts here, in SQL — including
        #     when the caller did the retrieving: `candidates` may only ever arrive from
        #     `WardrobeRepository.candidates`, which is the one query that names the owner.
        candidates = (
            list(candidates) if candidates is not None else self._retrieve(user_id)
        )

        # 2 — no complete outfit is possible, so there is nothing to deliberate about.
        #     The advisor is not called at all: paying for a crew run to be told what a
        #     count already told us is waste, and asking a model to style around a missing
        #     role invites it to fill one.
        if missing_roles(candidates, required):
            return DeterministicRanker.gap_advice(candidates, required)

        # 3 — trend input, if the corpus is reachable.
        trend_notes, degradation = await self._trend_notes(required)

        request = AdviceRequest(
            user_id=user_id,
            candidates=candidates,
            occasion=occasion,
            vibe=vibe,
            fit_preference=fit_preference,
            color_preferences=list(color_preferences),
            required_roles=list(required),
            trend_notes=trend_notes,
        )

        # 4..6 — advise, then validate what came back.
        try:
            advice = await self.advisor.advise(request)
            validated = validate_advice(advice, request=request)
        except UngroundedItemError as error:
            # An advisor naming an id we did not supply is a serious event whoever owns it.
            # CRITICAL, and never retried into: docs/AI-SYSTEM.md.
            logger.critical(
                "ungrounded item id in advisor response; rejected without fetching",
                extra={"user_id": user_id, "item_ids": error.item_ids},
            )
            self.rejections.append(
                Rejection(user_id=user_id, reason="ungrounded_item", detail=error.detail)
            )
            return self._degrade(request)
        except IncompatibleOutfitError as error:
            logger.warning(
                "advisor response was not a valid outfit", extra={"reasons": error.reasons}
            )
            self.rejections.append(
                Rejection(
                    user_id=user_id, reason="incompatible_outfit", detail="; ".join(error.reasons)
                )
            )
            return self._degrade(request)
        except SchemaInvalidError as error:
            logger.warning("advisor response failed the schema", extra={"reason": error.reason})
            self.rejections.append(
                Rejection(user_id=user_id, reason="schema_invalid", detail=error.reason)
            )
            return self._degrade(request)
        except Exception:  # provider outage, timeout, framework error
            logger.warning("advisor unavailable; falling back to the ranker", exc_info=True)
            self.rejections.append(
                Rejection(user_id=user_id, reason="advisor_unavailable", detail="")
            )
            return self._degrade(request)

        # 7 — drop unsupportable tips (ARCHITECTURE section 6). Removals are logged rather
        #     than silent: a filter nobody can see is a filter nobody notices breaking.
        cleaned, dropped = sanitize_advisory(validated)
        if dropped:
            logger.info("dropped unsupportable advisory content", extra={"dropped": dropped})

        return self._rescore(cleaned, request, degradation)

    # --- internals ---------------------------------------------------------------------

    def _retrieve(self, user_id: str) -> list[WardrobeItem]:
        if self.repository is None:
            raise ValueError("compose() needs either a repository or a candidate set")
        return self.repository.candidates(user_id)

    async def _trend_notes(
        self, required: Sequence[GarmentCategory]
    ) -> tuple[list[TrendNote], int]:
        """Rung 2: an unreachable trend source costs the Trend Scout, not the request."""
        if self.trend_source is None:
            return [], 1
        try:
            notes = await self.trend_source.current(TrendQuery(categories=list(required)))
        except Exception:
            logger.info("trend source unavailable; composing without trend input")
            return [], 2
        return list(notes), 1

    def _rescore(
        self, advice: OutfitAdvice, request: AdviceRequest, degradation: int
    ) -> OutfitAdvice:
        """Step 9 — the score the user sees is computed from the items, not asserted.

        The advisor writes the name and the rationale; those are judgements and it is better
        at them. It does not get to set the number, because two identical wardrobes must not
        show different Style Match figures depending on how confident a model felt.
        """
        if advice.outfit is None:
            return advice.model_copy(update={"degradation_level": degradation})

        owned = {item.item_id: item for item in request.candidates}
        items = [owned[item_id] for item_id in advice.outfit.item_ids]
        rescored = Outfit(
            item_ids=advice.outfit.item_ids,
            name=advice.outfit.name,
            occasion=advice.outfit.occasion,
            match_score=match_score(items, request),
        )
        return advice.model_copy(update={"outfit": rescored, "degradation_level": degradation})

    def _degrade(self, request: AdviceRequest) -> OutfitAdvice:
        """Rung 4 — rank the same candidate set without a model.

        The candidate set is reused unchanged. Re-retrieving would be a second chance to get
        the scope wrong, and the set in hand is already the authoritative one.
        """
        return self.ranker.compose(request)


__all__ = ["CompositionService", "Rejection"]
