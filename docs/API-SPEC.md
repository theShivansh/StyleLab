# API Specification — STYLELAB

Base: `/api/v1`

Every wardrobe route is ownership-scoped. A request for an item the caller does not own
returns 404, never 403 — do not confirm the existence of another user's item.

## Identity

Every wardrobe route requires `Authorization: Bearer <token>`, where the token was minted
and signed by this API. Missing, malformed, expired and forged tokens all answer **401** with
the same message; the caller's response to each is the same, and distinguishing them tells
an attacker which of their guesses was structurally right.

**The caller never names the user.** `user_id` is read out of our own signature, never from
a header or a request body. A client-supplied id would make every scoped query below
decorative — see `apps/api/app/security/identity.py`.

### POST /session

Creates an anonymous user and returns a token for it. Takes no body: a `POST /session` that
accepted a `user_id` would be a login with no credential.

```json
{ "user_id": "user_a1b2c3", "token": "<opaque>", "expires_in": 2592000 }
```

Not authentication — an identity *seam* of the right shape. Real accounts arrive in S11 with
Supabase auth; the header and every scoped query stay as they are.

## POST /wardrobe/items

Multi-image upload. Each file is validated independently.

Input: `multipart/form-data` — `images[]`, plus an optional `category_hint` per file
(used directly by the demo analyzer, treated as a prior by the live one).

`201`, with one result per file **in the order the files were sent**. The client maps
results back onto cards it has already rendered by index, so a refusal keeps its slot even
though it carries no ids.

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
the others, and the batch is never failed as a whole.

`status` is `analyzing` or `rejected` and nothing else. A re-upload of a photograph already
in the caller's wardrobe is also `analyzing`, with a `job_id` that is already `completed` —
the checksum cache answers it and no model is called. A third status meaning "already done"
would have added a branch to every card in the UI to save one round trip.

Validation before storage, in this order: byte ceiling, then **the real format sniffed from
magic bytes** (never the declared `Content-Type`), then a pixel ceiling read from the header,
then decode, then a resolution floor. EXIF is stripped on ingest — GPS included — with
orientation *applied* first, or every portrait photograph would be stored on its side.

## GET /jobs/{job_id}

Ownership-scoped like everything else: another user's job answers 404. A job id is random
and unguessable, and "unguessable" is not an authorisation model.

```json
{
  "job_id": "job_1",
  "type": "analyze_item",
  "status": "processing",
  "stage": "reading colour and cut",
  "progress": 0.6
}
```

`stage` is one of the named extraction stages, in order — `reading photo`, `finding
garment`, `reading colour and cut`, `checking confidence`, `ready`. Each corresponds to work
that actually happens before the next one; a stage that fires immediately after its
predecessor is a spinner with a caption. `progress` is derived from `stage`, so the two
cannot disagree.

On failure the job carries the reason, written server-side against the actual failure:

```json
{
  "job_id": "job_1", "type": "analyze_item", "status": "failed",
  "stage": null, "progress": null,
  "error": { "code": "PROVIDER_TIMEOUT",
             "message": "Reading that photo took too long. Try it again.",
             "retryable": true }
}
```

`retryable` answers "would doing this again plausibly work?" — true for a timeout, false for
a model id that no longer resolves. A card offering a retry that cannot help wastes the
user's time instead of ours.

One job per image, never one per batch. A batch-level job has one status, and one status
means one spinner over eight photographs.

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

Returns the full updated item. A field outside the correctable set, or an invalid value for
one inside it, answers `422` naming the field and never echoing the value. An unknown field
is refused rather than ignored: silently dropping it leaves the user looking at a screen
that says the correction saved when nothing did.

## POST /wardrobe/items/{item_id}/reanalyze

Re-runs extraction. Fields in `corrected_fields` are preserved, not recomputed. `202` and a
job, not a result — this is the per-image retry, and a retry that blocked would be a worse
version of what the async pipeline exists to avoid.

```json
{ "item_id": "item_1", "job_id": "job_9", "status": "analyzing" }
```

The checksum cache is deliberately not consulted: the button asks the model again, and
answering from the last answer would make it a lie.

## DELETE /wardrobe/items/{item_id}

Soft-deletes the item and its asset. Returns the outfits made incomplete by the deletion
so the UI can say what else changed.

```json
{ "deleted": true, "affected_outfits": ["outfit_7"] }
```

Soft on both rows, because docs/DATA-MODEL.md wants deletion observable and reversible by
support. "Reversible by support" is not "still in the product": a deleted item answers 404
on every read, disappears from the wardrobe, and its `image_url` stops serving even though
the token has not expired. Affected outfits become `incomplete` rather than being discarded —
the user composed that look, and the honest answer to one missing piece is to say which
piece (AI-EVAL-CASES Case 14).

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

```json
{ "item_id": "item_1",
  "extractions": [
    { "provider": "groq", "model": "...", "raw_output": "...",
      "schema_valid": true, "rejected_reason": null, "latency_ms": 1841 }
  ] }
```

Rows exist for rejected attempts too, including the raw text that failed to parse. An audit
trail reachable only through a successful analysis is an audit trail of successes.

## GET /assets/{asset_id}/{token}

The stored photograph. The only way an uploaded image leaves the server, and the value of
`image_url` on a wardrobe item.

The token is a signed, expiring capability naming **one owner and one asset**, minted fresh
each time an item is read. It sits in the path, not the query string, because
docs/SECURITY-PRIVACY.md says signed URLs are never placed in one — and a path segment
satisfies that literally while behaving identically in an `<img src>` cross-origin with no
cookie.

Everything that does not verify answers 404: expired, forged, wrong purpose, pointed at a
different asset, or belonging to a deleted item. The owner comes out of the signature, so the
handler still reads through the same ownership-scoped query as every other route.

Access logs must not record the token. Enforced at the logging layer
(`apps/api/app/logging_setup.py`), not by asking callers to remember.

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
