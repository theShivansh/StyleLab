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

Return: a job. Composition runs the agent crew, so it is always async — see
`docs/AGENT-SYSTEM.md` for the stages surfaced through `GET /jobs/{job_id}`.

Completed result:
```json
{
  "outfit": { "item_ids": ["item_1","item_4","item_9"], "name": "Quiet Weekday",
              "occasion": "college", "match_score": 87 },
  "rationale": ["Neutral palette holds together", "Relaxed top against a slim leg"],
  "confidence": 0.87,
  "critique": { "considered": ["the olive jacket, too heavy for the occasion"],
                "tradeoffs": ["proportion is deliberate, not accidental"] },
  "pro_tips": [{ "tip": "Half-tuck the shirt to break the vertical line",
                 "type": "proportion" }],
  "alternatives": [{ "swap_role": "footwear", "item_id": "item_12",
                     "why": "same palette, lifts the formality" }],
  "combinations": [{ "item_ids": ["item_1","item_7"], "occasion": "evening",
                     "name": "Same shirt, later" }],
  "budget_tricks": [{ "trick": "Layer the grey tee under the open shirt for a third look",
                      "unlocks_outfits": 3 }],
  "wardrobe_gaps": [{ "category": "footwear",
                      "generic_description": "a white leather sneaker",
                      "unlocks_outfits": 5 }],
  "trend_notes": [{ "trend": "Relaxed tailoring holding through AW26",
                    "source": "...", "published_at": "2026-07-14",
                    "applies_to_items": ["item_4"] }],
  "degradation_level": 1
}
```

Contract rules enforced server-side before this is returned:
- every `item_id` in every field belongs to the caller
- every `trend_notes` entry has `source` and `published_at`, or it is absent
- `wardrobe_gaps[].generic_description` carries no brand, price, merchant or link
- `degradation_level` (1-5, `docs/AGENT-SYSTEM.md`) is reported honestly; the UI says when
  advice is shallower than usual rather than pretending otherwise

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
`EXTRACTION_FAILED` · `PROVIDER_TIMEOUT` · `INSUFFICIENT_WARDROBE` · `ITEM_NOT_FOUND` ·
`AGENT_BUDGET_EXCEEDED` · `TREND_SOURCE_UNAVAILABLE` · `AI_UNAVAILABLE`

`AI_UNAVAILABLE` is a real outage, not a downgrade path. There is no demo mode to fall
back to, so say so plainly rather than serving a fabricated result.

Never expose stack traces.
