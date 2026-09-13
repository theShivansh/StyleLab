"""Outfit routes — docs/API-SPEC.md.

The same two rules as the wardrobe routes, for the same reasons: `user_id` comes from the
signed token and is the first argument to everything, and an outfit the caller does not own
answers 404 rather than 403.

## No item ids in a compose request

`POST /outfits/compose` takes an occasion and some preferences. It does not take candidates.
Accepting them would move the ownership boundary into the request body — the server would
be styling with whatever ids it was handed, and the SQL scope that makes the grounding
guarantee true would be scoping a set the caller had already chosen.

## Compose is a job, swap is not

Compose calls a provider and returns 202 with a job to poll. Swap is a scoped read, a pure
recompute and one row rewritten, so it answers with the updated look directly. That is the
signature product moment (CLAUDE.md), and it should cost one request and no navigation.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Request

from app.config import get_settings
from app.deps import (
    OUTFIT_NOT_FOUND,
    Composer,
    CurrentUser,
    FaultError,
    Rates,
    Signer,
    enforce,
)
from app.domain.compatibility import CORE_ROLES
from app.domain.models import GarmentCategory
from app.routers.serialization import alternatives_payload, job_payload, outfit_payload
from app.services.compose import SwapNotPossibleError
from app.services.faults import Fault

router = APIRouter(prefix="/outfits", tags=["outfits"])


def _api_base(request: Request) -> str:
    """The absolute prefix an image URL is built from. As `routers/wardrobe.py`."""
    return f"{str(request.base_url).rstrip('/')}/api/v1"


def _roles(raw: object) -> list[GarmentCategory]:
    """Parse `required_roles`, falling back to the three roles that make an outfit.

    An unrecognised role is dropped rather than refused, and an empty result falls back to
    the core three: the field is a refinement, and failing a composition because a client
    sent a role this build does not know would cost the user their outfit over a hint.
    """
    if not isinstance(raw, list):
        return list(CORE_ROLES)
    parsed: list[GarmentCategory] = []
    for value in raw:
        try:
            parsed.append(GarmentCategory(str(value)))
        except ValueError:
            continue
    return parsed or list(CORE_ROLES)


def _text(raw: object, *, limit: int = 64) -> str | None:
    """One short free-text preference, bounded.

    Bounded here because these strings reach a prompt. The length cap is not a safety
    boundary — ownership and validation are — but an unbounded field that ends up in a
    model request is a cost problem and an obvious place to paste something long.
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned[:limit] or None


def _swap_fault(error: SwapNotPossibleError) -> FaultError:
    """A refused swap, as the documented envelope. 422: the request was understood."""
    return FaultError(Fault(error.code, error.message, retryable=False, status=422))


@router.post("/compose", status_code=202)
async def compose(
    user_id: CurrentUser,
    composer: Composer,
    rates: Rates,
    body: Annotated[dict[str, Any] | None, Body()] = None,
) -> dict[str, Any]:
    """Start a composition. 202 and a job — nothing has reached a model yet.

    Async even though today's advisor is a single call. The crew lands behind the same
    Protocol in S8b and takes longer; a route that blocked now would have to change then,
    and every client written against it with it.
    """
    # The most expensive thing the product does: six agents, ~7,600 input tokens, against
    # an account measured at 8,000 per minute (blocker B17). Limited before the job is
    # created, so a refusal costs a 429 rather than a queued crew run.
    enforce(rates.compositions, user_id)

    payload = body or {}
    occasion = _text(payload.get("occasion"), limit=32) or "everyday"
    colors = payload.get("color_preferences")
    job = await composer.start(
        user_id,
        occasion=occasion,
        vibe=_text(payload.get("vibe"), limit=32),
        fit_preference=_text(payload.get("fit_preference"), limit=32),
        color_preferences=[
            text
            for value in (colors if isinstance(colors, list) else [])
            if (text := _text(value, limit=24))
        ][:6],
        required_roles=_roles(payload.get("required_roles")),
    )
    return job_payload(job)


@router.get("/{outfit_id}")
async def get_outfit(
    request: Request,
    user_id: CurrentUser,
    composer: Composer,
    signer: Signer,
    outfit_id: str,
) -> dict[str, Any]:
    """One look. The read behind the result screen, and behind every reload of it."""
    outfit = await composer.result(user_id, outfit_id)
    if outfit is None:
        raise FaultError(OUTFIT_NOT_FOUND)

    settings = get_settings()
    return outfit_payload(
        outfit,
        base_url=_api_base(request),
        signer=signer,
        image_ttl_s=settings.image_url_ttl_s,
    )


@router.get("/{outfit_id}/alternatives")
async def alternatives(
    request: Request,
    user_id: CurrentUser,
    composer: Composer,
    signer: Signer,
    outfit_id: str,
    role: str,
) -> dict[str, Any]:
    """What else the caller owns that could fill one slot.

    An empty list is a valid answer and answers 200 with a named gap, not an error. A user
    who owns one pair of shoes has a small wardrobe, not a broken request.
    """
    try:
        view = await composer.alternatives(user_id, outfit_id, role=role)
    except SwapNotPossibleError as error:
        raise _swap_fault(error) from error

    if view is None:
        raise FaultError(OUTFIT_NOT_FOUND)

    settings = get_settings()
    return alternatives_payload(
        view,
        base_url=_api_base(request),
        signer=signer,
        image_ttl_s=settings.image_url_ttl_s,
    )


@router.post("/{outfit_id}/swap")
async def swap(
    request: Request,
    user_id: CurrentUser,
    composer: Composer,
    signer: Signer,
    outfit_id: str,
    body: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Change one slot. Returns the whole look so the client never has to guess the rest.

    Synchronous, and the full updated outfit rather than a patch: the client renders from
    one payload it did not assemble itself, which is what keeps "visual state never
    disagrees with wardrobe state" true after a swap as well as before one.
    """
    role = _text(body.get("role"), limit=16)
    replacement = _text(body.get("replacement_item_id"), limit=64)
    if not role or not replacement:
        raise FaultError(
            Fault(
                "ITEM_NOT_FOUND",
                "A swap needs a role and the garment to put in it.",
                retryable=False,
                status=422,
            )
        )

    try:
        outfit = await composer.swap(
            user_id, outfit_id, role=role, replacement_item_id=replacement
        )
    except SwapNotPossibleError as error:
        raise _swap_fault(error) from error

    if outfit is None:
        raise FaultError(OUTFIT_NOT_FOUND)

    settings = get_settings()
    return outfit_payload(
        outfit,
        base_url=_api_base(request),
        signer=signer,
        image_ttl_s=settings.image_url_ttl_s,
    )


@router.post("/{outfit_id}/save")
async def save(user_id: CurrentUser, composer: Composer, outfit_id: str) -> dict[str, Any]:
    """Keep a look. Idempotent, in the schema rather than in this handler."""
    if not await composer.save(user_id, outfit_id):
        raise FaultError(OUTFIT_NOT_FOUND)
    return {"outfit_id": outfit_id, "saved": True}


__all__ = ["router"]
