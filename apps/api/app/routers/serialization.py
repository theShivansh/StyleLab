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

from app.repositories.wardrobe import StoredExtraction, StoredItem
from app.security.tokens import TokenSigner
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
    """
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "type": job.type.value,
        "status": job.status.value,
        "stage": job.stage,
        "progress": job.progress,
    }
    if job.error_code:
        payload["error"] = {
            "code": job.error_code,
            "message": job.error_message,
            "retryable": job.retryable,
        }
    return payload


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


__all__ = ["extraction_payload", "item_payload", "job_payload"]
