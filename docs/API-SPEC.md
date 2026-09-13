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
  "fit_preference": "regular",
  "color_preferences": [],
  "required_roles": ["top", "bottom", "footwear"]
}
```

No item IDs are accepted from the client — candidates are retrieved server-side from the
caller's wardrobe. Accepting client-supplied IDs would move the ownership boundary into
the request body. Every field is optional; the occasion defaults and the roles fall back to
the three that make an outfit, so a user who skipped the preferences step still composes.

`202` and a job. Composition calls a provider — one text call today, the crew in S8b — and a
route that blocked would have to change when that happens.

```json
{ "job_id": "job_9", "type": "compose_outfit", "status": "queued",
  "stage": null, "progress": null, "result_id": null }
```

Stages come from the composition vocabulary — `reading your wardrobe`, `matching silhouettes`,
`balancing palette`, `building look`, `ready` — and are reported through `GET /jobs/{job_id}`
like any other job. **Only the stages that correspond to work actually being done are
emitted.** At the single-call rung that is three of the five; the middle two happen inside
the advisor call, and firing them anyway would be a spinner with a caption (docs/DECISIONS.md).

When the job completes, `result_id` is the outfit to fetch:

```json
{ "job_id": "job_9", "type": "compose_outfit", "status": "completed",
  "stage": "ready", "progress": 1.0, "result_id": "outfit_7" }
```

Insufficient wardrobe is a **completed** job with no outfit and the gap named inline. Not a
failed one: a failure offers a retry, and retrying cannot conjure a pair of trousers.

```json
{ "job_id": "job_9", "type": "compose_outfit", "status": "completed",
  "stage": "ready", "progress": 1.0, "result_id": null,
  "result": {
    "missing_roles": ["footwear"],
    "wardrobe_gaps": [{ "category": "footwear",
                        "generic_description": "a clean low-profile shoe in a neutral colour",
                        "unlocks_outfits": 0 }],
    "rationale": ["Your wardrobe needs footwear before this look can be built."],
    "degradation_level": 5
  } }
```

## GET /outfits/{outfit_id}

The result screen's read, and the read behind every reload and every swap.

```json
{
  "outfit_id": "outfit_7",
  "name": "Quiet Weekday",
  "occasion": "college",
  "match_score": 87,
  "status": "ready",
  "degradation_level": 1,
  "rationale": ["Neutral palette holds together", "Relaxed top against a slim leg"],
  "saved": false,
  "missing_roles": [],
  "slots": [
    { "role": "top", "item_id": "item_1", "item": { "...": "a wardrobe item payload" } },
    { "role": "bottom", "item_id": "item_4", "item": { "...": "..." } },
    { "role": "footwear", "item_id": "item_9", "item": { "...": "..." } }
  ],
  "confidence": 0.87,
  "pro_tips": [{ "tip": "Half-tuck the shirt to break the vertical line",
                 "type": "proportion" }],
  "budget_tricks": ["Layer the grey tee under the open shirt for a third look"],
  "wardrobe_gaps": [{ "category": "footwear",
                      "generic_description": "a white leather sneaker",
                      "unlocks_outfits": 5 }],
  "trend_notes": []
}
```

Contract rules enforced server-side before this is returned:
- every item in every slot belongs to the caller
- every `trend_notes` entry has `source` and `published_at`, or it is absent
- `wardrobe_gaps[].generic_description` carries no brand, price, merchant or link
- `degradation_level` (1-5, `docs/AGENT-SYSTEM.md`) is reported honestly; the UI says when
  advice is shallower than usual rather than pretending otherwise
- there is **no price and no total anywhere in this payload**, and no field a client could
  sum. The product sells nothing.

`match_score` is Style Match: a UX heuristic, recomputed from the items by
`app.domain.scoring` rather than taken from whatever number the advisor asserted. Two
identical wardrobes must not show different figures because a model felt differently.

A slot whose garment was deleted keeps its place with `"item": null`, `status` becomes
`incomplete` and `missing_roles` names the role. The look is never silently shortened —
the screen has to be able to say *which* piece went missing and offer a swap for it
(AI-EVAL-CASES Case 14).

`critique` and `combinations` are absent. They belong to the agent crew and arrive with it in
S8b; a field in the contract that nothing produces is a contract nobody honours.

## GET /outfits/{outfit_id}/alternatives?role=bottom

Compatible alternatives from the caller's wardrobe, best first.

```json
{
  "role": "bottom",
  "current_item_id": "item_4",
  "alternatives": [
    { "item": { "...": "a wardrobe item payload" }, "match_score": 88, "delta": 4 }
  ],
  "gap": null
}
```

`match_score` is what the **look** would score with that garment in it, not what the garment
scores alone, and `delta` is the difference from the look as it stands. Candidates are scored
against the other pieces currently on screen: a shortlist ordered by solo score would
recommend the best shoe in the wardrobe rather than the best shoe with this shirt.

A negative delta is returned as readily as a positive one. The score is a heuristic and the
swap is the user's to make.

Empty is a valid answer and a 200:

```json
{ "role": "footwear", "current_item_id": "item_9", "alternatives": [],
  "gap": { "category": "footwear",
           "generic_description": "a clean low-profile shoe in a neutral colour" } }
```

The UI must handle that as a gap with an invitation to add a garment, never as an error. A
role the look does not contain is `422 ROLE_NOT_IN_OUTFIT`.

## POST /outfits/{outfit_id}/swap

```json
{ "role": "bottom", "replacement_item_id": "item_9" }
```

Recomposes that role only and returns **the whole updated outfit**, in the same shape as
`GET /outfits/{outfit_id}`. The full look rather than a patch, so the client renders from one
payload it did not assemble itself — a client merging a partial response into its own copy is
a client that can show a combination the wardrobe does not agree with.

Synchronous, and it calls no model. A scoped read, a recompute over six dimensions and one
row rewritten; the other slots keep their garments and their order.

The narration is rewritten too. `rationale` is recomputed from the new score and the pro
tips, budget tricks and trend notes are dropped, because they were written about a
combination that no longer exists (docs/DECISIONS.md). Wardrobe gaps survive: they describe
the wardrobe, not the look.

Refusals, all `422` except where noted, and none of them echo an id back as prose:

| code | when |
|---|---|
| `ROLE_NOT_IN_OUTFIT` | the look has no slot for that role |
| `ROLE_MISMATCH` | the replacement is a top and the slot is a bottom |
| `ITEM_NOT_READY` | the replacement is still being analysed and has nothing to score |
| `UNKNOWN_ROLE` | the role is not a garment category |
| *(404)* | the outfit or the replacement is not the caller's, or was deleted |

Swapping in the garment already in the slot is a **no-op 200**, not an error: the second tap
on the item you just chose should do nothing.

## POST /outfits/{outfit_id}/save

Idempotent — enforced by a unique constraint on `(user_id, outfit_id)` rather than by this
handler remembering to check.

```json
{ "outfit_id": "outfit_7", "saved": true }
```

There is no unsave in this phase. Nothing in the product removes a look yet, and an endpoint
with no caller is an endpoint nobody tested.

## DELETE /wardrobe/items

Remove the whole wardrobe in one action. docs/SECURITY-PRIVACY.md requires it; S11 built it.

```json
{ "deleted": true, "items": 6, "assets": 6, "affected_outfits": 2,
  "images_erased_after_days": 30 }
```

Counts, not ids: the caller is a user deleting everything, and a list of the hundred things
they just destroyed answers nothing they asked.

Soft, like the single delete, and on the same clock — which is why the response says so.
`{"deleted": true}` alone would invite the reading that the photographs are already gone.

Takes no confirmation token and no `?confirm=true`. A confirmation belongs in the interface,
where the person is; a flag here would be satisfied by any client that set it and would give
the endpoint the *appearance* of a safeguard.

Affected outfits become `incomplete` rather than being deleted, the same as a single
deletion. An outfit row is the record that the user composed something — not a garment.

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
`AGENT_BUDGET_EXCEEDED` · `TREND_SOURCE_UNAVAILABLE` · `RATE_LIMITED` · `AI_UNAVAILABLE`

`RATE_LIMITED` (429, S11) carries a `Retry-After` header and is the only fault that sets
one — a provider outage has no honest number to put there, and inventing one tells a client
to come back at a moment nobody has any reason to expect. One message for all three quotas:
which one was hit describes the shape of our provider spend, and a user only needs to know
to wait.

`request_id` is now always present (S11). Every response carries the same value in
`X-Request-ID`, and a caller-supplied `X-Request-ID` is kept when it is safe to echo, so a
trace started at the web tier survives the hop.

`AI_UNAVAILABLE` is a real outage, not a downgrade path. There is no demo mode to fall
back to, so say so plainly rather than serving a fabricated result.

Never expose stack traces.
