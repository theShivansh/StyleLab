"""Wardrobe routes — docs/API-SPEC.md.

Every handler takes `user_id` from `CurrentUser` and passes it as the first argument to
everything it calls. No handler accepts a user id from the request, and no handler reads a
row without one.

## 404, never 403

An item the caller does not own is indistinguishable from an item that does not exist. That
is docs/SECURITY-PRIVACY.md, and the reason is that 403 confirms existence: a 403 on
`item_a1b2` tells an attacker that `item_a1b2` is real and belongs to somebody. Here it
falls out of the design rather than being remembered — the repository's scoped read returns
`None` for both cases, so there is no branch in which a handler *could* answer 403.

## Correction lands before re-analysis, always

`PATCH` records the field in `corrected_fields`, which is what protects it from a later
extraction (AI-EVAL-CASES Case 13). The merge rule is in `app.domain.corrections`, applied
by the repository — this route only names the field and the value.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Form, Request, UploadFile

from app.config import get_settings
from app.deps import NOT_FOUND, CurrentUser, FaultError, Ingest, Sessions, Signer
from app.domain.corrections import CORRECTABLE_FIELDS
from app.domain.errors import SchemaInvalidError
from app.domain.models import GarmentCategory, ItemStatus
from app.repositories.wardrobe import ExtractionAuditRepository, WardrobeRepository
from app.routers.serialization import extraction_payload, item_payload
from app.services.faults import Fault
from app.services.ingest import UploadedFile

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])


def _api_base(request: Request) -> str:
    """The absolute prefix an image URL is built from.

    Taken from the request rather than configured: behind a reverse proxy the configured
    value and the one the browser used are routinely different, and the browser's is the one
    that has to work.
    """
    return f"{str(request.base_url).rstrip('/')}/api/v1"


def _category_hint(raw: str | None) -> GarmentCategory | None:
    """Parse one optional hint. An unrecognised value is ignored, not refused.

    The hint is a prior the user offered, and the photograph is the payload. Rejecting a
    whole upload because a hint did not parse would spend the user's goodwill on a field
    that was optional.
    """
    if not raw:
        return None
    try:
        return GarmentCategory(raw)
    except ValueError:
        return None


@router.post("/items", status_code=201)
async def upload_items(
    request: Request,
    user_id: CurrentUser,
    service: Ingest,
    images: Annotated[list[UploadFile], File(alias="images[]")],
    category_hints: Annotated[list[str] | None, Form(alias="category_hints[]")] = None,
) -> dict[str, Any]:
    """Multi-image upload. Each file is validated independently.

    201 with a body describing every file, including the refused ones. Partial success is a
    success: a batch where the third photograph was a PDF is still a batch that accepted
    seven photographs, and a 4xx for the whole request would throw them away.

    Hints arrive as a parallel list because multipart has no way to attach a field to a
    file. An empty string means "let it decide", which is why the list is not filtered.
    """
    hints = category_hints or []
    files = [
        UploadedFile(
            filename=image.filename or "photo",
            data=await image.read(),
            declared_mime=image.content_type,
            category_hint=_category_hint(hints[index] if index < len(hints) else None),
        )
        for index, image in enumerate(images)
    ]

    outcomes = await service.upload(user_id, files)

    return {
        "items": [
            {
                "item_id": outcome.item_id,
                "asset_id": outcome.asset_id,
                "job_id": outcome.job_id,
                "status": outcome.status,
                **(
                    {"error": {"code": outcome.error_code, "message": outcome.error_message}}
                    if outcome.error_code
                    else {}
                ),
            }
            for outcome in outcomes
        ]
    }


@router.get("/items")
async def list_items(
    request: Request,
    user_id: CurrentUser,
    sessions: Sessions,
    signer: Signer,
    category: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """The caller's wardrobe. Includes items still analysing and items that failed.

    A photograph that could not be read has to keep a card, or the user's file appears to
    have vanished. `candidates()` — the narrower `ready`-only set — is what the advisor
    sees, and this is not that.
    """
    settings = get_settings()
    parsed_category = _category_hint(category)
    statuses = [ItemStatus(status)] if status in set(ItemStatus) else None

    with sessions() as session:
        stored = WardrobeRepository(session).items(
            user_id, category=parsed_category, statuses=statuses
        )

    return {
        "items": [
            item_payload(
                item,
                base_url=_api_base(request),
                signer=signer,
                image_ttl_s=settings.image_url_ttl_s,
            )
            for item in stored
        ]
    }


@router.get("/items/{item_id}")
async def get_item(
    request: Request,
    item_id: str,
    user_id: CurrentUser,
    sessions: Sessions,
    signer: Signer,
) -> dict[str, Any]:
    with sessions() as session:
        stored = WardrobeRepository(session).stored(user_id, item_id)
    if stored is None:
        raise FaultError(NOT_FOUND)

    return item_payload(
        stored,
        base_url=_api_base(request),
        signer=signer,
        image_ttl_s=get_settings().image_url_ttl_s,
    )


@router.patch("/items/{item_id}")
async def correct_item(
    request: Request,
    item_id: str,
    user_id: CurrentUser,
    sessions: Sessions,
    signer: Signer,
    patch: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    """Apply user corrections. Every field named becomes protected from re-analysis.

    An unknown field is refused rather than ignored. Silently dropping it would leave the
    user looking at a screen that says their correction was saved when nothing was.
    """
    unknown = sorted(set(patch) - CORRECTABLE_FIELDS)
    if unknown:
        raise FaultError(
            Fault(
                "EXTRACTION_FAILED",
                f"{', '.join(unknown)} cannot be corrected directly.",
                retryable=False,
                status=422,
            )
        )
    if not patch:
        raise FaultError(
            Fault("EXTRACTION_FAILED", "Nothing to change.", retryable=False, status=422)
        )

    with sessions() as session:
        repository = WardrobeRepository(session)
        for field, value in patch.items():
            try:
                if not repository.save_correction(user_id, item_id, field, value):
                    raise FaultError(NOT_FOUND)
            except SchemaInvalidError as error:
                # A correctable field with an invalid value — "formality": "elegant".
                # `_describe` in the domain names the field and never echoes the value.
                raise FaultError(
                    Fault(
                        "EXTRACTION_FAILED",
                        f"That isn't a value we can store for {field}.",
                        retryable=False,
                        status=422,
                    )
                ) from error
        session.commit()
        stored = repository.stored(user_id, item_id)

    if stored is None:  # pragma: no cover - written above, in this session
        raise FaultError(NOT_FOUND)

    return item_payload(
        stored,
        base_url=_api_base(request),
        signer=signer,
        image_ttl_s=get_settings().image_url_ttl_s,
    )


@router.post("/items/{item_id}/reanalyze", status_code=202)
async def reanalyze_item(
    item_id: str, user_id: CurrentUser, service: Ingest
) -> dict[str, Any]:
    """Re-run extraction. Corrected fields are preserved, not recomputed.

    202 and a job: this is the per-image retry the upload queue offers, and it must not
    block any more than the first analysis did.
    """
    job_id, _ = await service.reanalyze(user_id, item_id)
    if job_id is None:
        raise FaultError(NOT_FOUND)
    return {"item_id": item_id, "job_id": job_id, "status": "analyzing"}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: str, user_id: CurrentUser, sessions: Sessions
) -> dict[str, Any]:
    """Soft-delete the item and its asset, and report what else changed.

    `affected_outfits` is the reason this returns a body rather than a 204. A garment can be
    in a saved look, and deleting it without saying so leaves the user to discover the hole
    themselves (AI-EVAL-CASES Case 14).

    The stored image is not unlinked here. Deletion is soft on both rows because
    docs/DATA-MODEL.md wants it observable and reversible by support, and a file deleted
    immediately makes the row's `deleted_at` a record of something that cannot be undone.
    Hard deletion on a retention timer lands with the privacy flow in S11.
    """
    with sessions() as session:
        result = WardrobeRepository(session).delete_with_cascade(user_id, item_id)
        session.commit()

    if not result.deleted:
        raise FaultError(NOT_FOUND)
    return {"deleted": True, "affected_outfits": result.affected_outfits}


@router.get("/items/{item_id}/extractions")
async def item_extractions(
    item_id: str, user_id: CurrentUser, sessions: Sessions
) -> dict[str, Any]:
    """The audit trail — what each model returned, what was rejected and why.

    Empty for an item the caller does not own, which is the same answer as for an item with
    no attempts yet. Consistent with 404-not-403: this endpoint does not become the one that
    confirms somebody else's item exists.
    """
    with sessions() as session:
        if WardrobeRepository(session).stored(user_id, item_id) is None:
            raise FaultError(NOT_FOUND)
        rows = ExtractionAuditRepository(session).for_item(user_id, item_id)

    return {"item_id": item_id, "extractions": [extraction_payload(row) for row in rows]}


__all__ = ["router"]
