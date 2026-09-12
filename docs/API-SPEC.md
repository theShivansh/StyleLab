# API Specification — STYLELAB

Base: `/api/v1`

Every wardrobe route is ownership-scoped. A request for an item the caller does not own
returns 404, never 403 — do not confirm the existence of another user's item.

## POST /wardrobe/items

Multi-image upload. Each file is validated independently.

Input: `multipart/form-data` — `images[]`, plus an optional `category_hint` per file
(used directly by the demo analyzer, treated as a prior by the live one).

Return:
```json
{
  "items": [
    { "item_id": "item_1", "asset_id": "asset_1", "job_id": "job_1", "status": "analyzing" },
    { "item_id": null, "asset_id": null, "job_id": null, "status": "rejected",
      "error": { "code": "IMAGE_TOO_LARGE", "message": "That photo is over 10 MB." } }
  ]
}
```

Partial success is a success. A rejected image returns its own error and does not affect
the others.

## GET /jobs/{job_id}

```json
{
  "job_id": "job_1",
  "type": "analyze_item",
  "status": "processing",
  "stage": "reading garment",
  "progress": 0.6
}
```

## GET /wardrobe/items

Query: `category`, `status`, `cursor`.

Returns the caller's wardrobe only.

## GET /wardrobe/items/{item_id}

```json
{
  "item_id": "item_1",
  "status": "ready",
  "category": "top",
  "subcategory": "oxford shirt",
  "color_primary": "navy",
  "material_guess": "cotton",
  "field_confidence": { "category": 0.97, "color_primary": 0.62, "material_guess": 0.41 },
  "corrected_fields": [],
  "quality_warnings": ["low_light"],
  "image_url": "https://signed..."
}
```

## PATCH /wardrobe/items/{item_id}

User correction. Every field named here is added to `corrected_fields` and is protected
from subsequent re-analysis.

```json
{ "color_primary": "navy" }
```

## POST /wardrobe/items/{item_id}/reanalyze

Re-runs extraction. Fields in `corrected_fields` are preserved, not recomputed.

## DELETE /wardrobe/items/{item_id}

Soft-deletes the item and its asset. Returns the outfits made incomplete by the deletion
so the UI can say what else changed.

```json
{ "deleted": true, "affected_outfits": ["outfit_7"] }
```

## POST /outfits/compose

```json
{
  "occasion": "college",
  "vibe": "minimal-street",
  "required_roles": ["top", "bottom", "footwear"]
}
```

No item IDs are accepted from the client — candidates are retrieved server-side from the
caller's wardrobe. Accepting client-supplied IDs would move the ownership boundary into
the request body.

Return: a job, or a composed outfit.

Insufficient wardrobe is a 200 with a named gap, not an error:
```json
{
  "outfit": null,
  "missing_roles": ["footwear"],
  "message": "You have no footwear yet — add a pair and I'll finish this look."
}
```

## POST /outfits/{outfit_id}/swap

```json
{ "role": "bottom", "replacement_item_id": "item_9" }
```

Recomposes that role only. Returns the updated outfit with the other roles unchanged.
`replacement_item_id` is ownership-checked before use.

## GET /outfits/{outfit_id}/alternatives?role=bottom

Compatible alternatives from the caller's wardrobe. Empty array is a valid answer and the
UI must handle it as a gap, not an error.

## POST /outfits/{outfit_id}/save

Idempotent.

## GET /wardrobe/items/{item_id}/extractions

The audit trail — what each model returned, what was rejected and why. Powers the
"show me the grounding" moment in the demo.

## Error contract

```json
{
  "error": {
    "code": "EXTRACTION_FAILED",
    "message": "We couldn't read that photo clearly.",
    "retryable": true,
    "request_id": "req_123"
  }
}
```

Codes: `IMAGE_TOO_LARGE` · `UNSUPPORTED_FORMAT` · `IMAGE_UNREADABLE` ·
`EXTRACTION_FAILED` · `PROVIDER_TIMEOUT` · `INSUFFICIENT_WARDROBE` · `ITEM_NOT_FOUND`

Never expose stack traces.
