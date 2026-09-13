"""Wire shapes, in one place.

docs/API-SPEC.md is the contract and `apps/web/src/lib/schemas/wardrobe.ts` parses against
it, so a field renamed here fails loudly in the browser rather than arriving as
`undefined` three components deep. Keeping the serialisers together makes the two files
diffable against each other.

Note what a wardrobe item payload does **not** carry: `user_id`. The client already knows
who it is, the value would be the same on every row, and a field that exists is a field
that gets sent somewhere. Ownership is a server-side property; putting it in the payload
invites a future reader to filter on it in the browser.

`material_guess` keeps its name all the way to the wire. It is a guess in the column, in
the domain, in the JSON and on screen — four places where the name is the safeguard.
"""

from __future__ import annotations

from typing import Any

from app.repositories.wardrobe import StoredExtraction, StoredItem, StoredOutfit
from app.security.tokens import TokenSigner
from app.services.compose import AlternativesView
from app.services.jobs import Job
from app.services.storage import browser_image_url


def item_payload(
    stored: StoredItem, *, base_url: str, signer: TokenSigner, image_ttl_s: int
) -> dict[str, Any]:
    """One wardrobe item, as docs/API-SPEC.md describes it.

    `image_url` is minted per read rather than stored, which is what lets the token be
    short-lived without the wardrobe screen going blank while a user is looking at it.
    Empty string when the asset is gone — the field is required by the client schema, and
    a card with no image is a truer rendering than a card with a link that 404s.
    """
    extraction = stored.item.extraction
    return {
        "item_id": stored.item.item_id,
        "status": stored.item.status.value,
        "category": extraction.category.value if extraction.category else None,
        "subcategory": extraction.subcategory,
        "color_primary": extraction.color_primary,
        "color_secondary": extraction.color_secondary,
        "pattern": extraction.pattern,
        "material_guess": extraction.material_guess,
        "fit": extraction.fit,
        "formality": extraction.formality.value if extraction.formality else None,
        "season_tags": list(extraction.season_tags),
        "occasion_tags": list(extraction.occasion_tags),
        "style_tags": list(extraction.style_tags),
        "field_confidence": dict(extraction.field_confidence),
        "corrected_fields": list(stored.item.corrected_fields),
        "quality_warnings": list(extraction.quality_warnings),
        "image_url": (
            browser_image_url(
                stored.asset_id,
                user_id=stored.item.user_id,
                base_url=base_url,
                signer=signer,
                ttl_s=image_ttl_s,
            )
            if stored.asset_id
            else ""
        ),
    }


def job_payload(job: Job) -> dict[str, Any]:
    """One job. `progress` is derived from the stage — see `app/services/jobs.py`.

    The error is included when there is one, because a poller that learns only "failed" has
    to invent its own copy for the card, and the honest message was already written by the
    classifier.

    `result_id` and `result` are how a finished job hands its answer over. A composition
    that produced a look gives the outfit id to fetch; one that could not gives the named
    gap inline, because there is no row to point at and "your wardrobe needs a bottom" is
    an answer rather than an error.
    """
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "type": job.type.value,
        "status": job.status.value,
        "stage": job.stage,
        "progress": job.progress,
        "result_id": job.result_id,
    }
    if job.result is not None:
        payload["result"] = job.result
    if job.error_code:
        payload["error"] = {
            "code": job.error_code,
            "message": job.error_message,
            "retryable": job.retryable,
        }
    return payload


def outfit_payload(
    outfit: StoredOutfit, *, base_url: str, signer: TokenSigner, image_ttl_s: int
) -> dict[str, Any]:
    """One composed look, with every slot resolved.

    A slot whose garment was deleted keeps its place with `item: null`. The result screen
    needs the role to offer a swap for it, and a look that quietly got shorter is the silent
    gap docs/AI-EVAL-CASES.md Case 14 forbids — the honest answer is to say which piece.

    The advisory keys are listed rather than spread, so the wire shape is the same whatever
    happens to be in the stored blob.
    """
    advisory = outfit.advisory or {}
    return {
        "outfit_id": outfit.outfit_id,
        "name": outfit.name,
        "occasion": outfit.occasion,
        # A UX heuristic, labelled as one on screen. Never a fit measurement.
        "match_score": outfit.match_score,
        "status": outfit.status,
        "degradation_level": outfit.degradation_level,
        "rationale": list(outfit.rationale),
        "saved": outfit.saved,
        "missing_roles": outfit.missing_roles,
        "slots": [
            {
                "role": slot.role,
                "item_id": slot.item_id,
                "item": (
                    item_payload(
                        slot.item, base_url=base_url, signer=signer, image_ttl_s=image_ttl_s
                    )
                    if slot.item
                    else None
                ),
            }
            for slot in outfit.slots
        ],
        "confidence": advisory.get("confidence"),
        "pro_tips": advisory.get("pro_tips", []),
        "budget_tricks": advisory.get("budget_tricks", []),
        "wardrobe_gaps": advisory.get("wardrobe_gaps", []),
        "trend_notes": advisory.get("trend_notes", []),
    }


def alternatives_payload(
    view: AlternativesView, *, base_url: str, signer: TokenSigner, image_ttl_s: int
) -> dict[str, Any]:
    """What else could fill one slot.

    `match_score` is what the *look* would score with that garment in, not what the garment
    scores alone, and `delta` is the difference from the look as it stands. Both are shown:
    a swap the user wants for reasons the scorer cannot see is still theirs to make, and
    hiding a negative delta would be deciding for them.
    """
    return {
        "role": view.role,
        "current_item_id": view.current_item_id,
        "alternatives": [
            {
                "item": item_payload(
                    alternative.item,
                    base_url=base_url,
                    signer=signer,
                    image_ttl_s=image_ttl_s,
                ),
                "match_score": alternative.match_score,
                "delta": alternative.delta,
            }
            for alternative in view.alternatives
        ],
        "gap": view.gap,
    }


def extraction_payload(extraction: StoredExtraction) -> dict[str, Any]:
    """One audit row — what a model returned and whether it was accepted.

    `raw_output` is included. This endpoint is the "show me the grounding" moment
    (docs/API-SPEC.md), and it is only evidence if it shows what actually arrived; a
    normalised copy proves nothing. It is the caller's own photograph and the caller's own
    extraction, so there is nobody else's data in it.
    """
    return {
        "provider": extraction.provider,
        "model": extraction.model,
        "raw_output": extraction.raw_output,
        "schema_valid": extraction.schema_valid,
        "rejected_reason": extraction.rejected_reason,
        "latency_ms": extraction.latency_ms,
    }


__all__ = [
    "alternatives_payload",
    "extraction_payload",
    "item_payload",
    "job_payload",
    "outfit_payload",
]
