# Data Model — STYLELAB

The wardrobe is user-owned. Every garment row traces to an image that user uploaded.
There is no shared catalogue, no price, and no merchant URL — see `docs/DECISIONS.md`
(2026-09-12, wardrobe pivot).

## users

- id
- email
- created_at

## assets

Private image storage records. One row per uploaded file.

- id
- user_id
- storage_key
- mime_type
- byte_size
- width
- height
- checksum           *(sha256 of the **normalised** bytes — after EXIF stripping and
                     re-encoding, so the same photograph off two phones is one image.
                     The analysis cache keys on this, **scoped to one user**: a global
                     checksum index would deduplicate across wardrobes and hand one
                     user another's extraction.)*
- created_at
- deleted_at

## style_profiles

- id
- user_id
- occasion
- vibe
- fit_preference
- color_preferences
- style_vector
- updated_at

## wardrobe_items

Replaces the old `garments` table. A garment the user owns, not a product for sale.

- id
- user_id            *(NOT NULL — the ownership root; see Constraints)*
- asset_id
- status             `analyzing` · `ready` · `failed` · `archived`
- category           `top` · `bottom` · `footwear` · `outerwear` · `accessory`
- subcategory
- color_primary
- color_secondary
- pattern
- material_guess     *(a guess, and named as one — never displayed as fact)*
- fit
- formality          `casual` · `smart-casual` · `formal`
- season_tags
- occasion_tags
- style_tags
- extraction_confidence   *(overall, 0–1)*
- field_confidence        *(per-field map — drives which fields prompt for confirmation.
                          Keyed by the fields the user can correct, and no others: a hedge
                          on a field with no correction path is a dead end. The wire schema
                          enumerates those keys because a free-form map cannot be expressed
                          under strict Structured Outputs — see docs/DECISIONS.md, S6.)*
- corrected_fields        *(fields the user overrode; re-analysis must never overwrite these)*
- analyzed_by             *(model id; null before the first analysis. There is no
                          deterministic extraction path — see docs/DECISIONS.md)*
- analyzed_at
- created_at
- deleted_at

Removed from the old `garments` shape: `brand`, `price`, `commerce_url`, `active`.
Nothing in this table is a commerce fact, so nothing here can misstate one.

## item_extractions

Append-only audit of what the model claimed for an item, including rejected attempts.
This is the evidence trail behind every wardrobe field — keep it, it is what makes the
grounding story demonstrable rather than assertable.

- id
- wardrobe_item_id
- provider
- model
- raw_output          *(as returned, before validation)*
- schema_valid
- rejected_reason     *(null when accepted)*
- latency_ms
- created_at

## outfits

- id
- user_id
- name
- occasion
- match_score          *(Style Match, 0-100. Recomputed from the items by
                       `app.domain.scoring`, never taken from what the advisor asserted:
                       two identical wardrobes must not show different figures because a
                       model felt differently.)*
- rationale
- status               *(`ready` | `incomplete`. `incomplete` when a referenced garment was
                       deleted — Case 14, never a silent gap.)*
- degradation_level    *(which rung of the ladder produced it. Disclosed on screen.)*
- advisory             *(pro tips, budget tricks, gaps, trend notes, the advisor's own
                       confidence. One JSON column because none of it is ever queried — it
                       is read whole, with the look. What is queried has its own column.)*
- vibe                 *(added S7)*
- fit_preference       *(added S7)*
- color_preferences    *(added S7)*
- created_at

The three preference columns are what the look was composed **against**, stored with the
look rather than joined from `style_profiles`. A swap rescores, and `preference_match` is one
of the six dimensions: without them a slot change would silently neutralise a fifth of the
score and the number on screen would move for a reason nobody could explain. A user who
changes their preferences later has not changed what this outfit was for.

## outfit_items

- outfit_id
- wardrobe_item_id
- role               `top` · `bottom` · `footwear` · `outerwear` · `accessory`
- rank

## saved_outfits

- id
- user_id
- outfit_id
- created_at

A join table rather than a `saved` flag on `outfits`, and the reason is that every
composition writes an `outfits` row — it has to, because a swap needs something to swap
against. A flag would mean the table held mostly unsaved rows with "saved" as the exception
the schema was not shaped for. It also puts idempotency in the schema: the unique constraint
on `(user_id, outfit_id)` is what makes the second press of Save a no-op, rather than a
handler remembering to check.

Composite foreign key to `(outfits.id, outfits.user_id)`, same as `outfit_items`: a save may
only ever point at the saver's own look.

## events

- id
- user_id
- session_id
- event_name
- schema_version
- properties
- created_at

## jobs

Async work. With VTO removed, the analysis job is the async path.

- id
- user_id
- type              `analyze_item` · `compose_outfit`
- status
- payload_reference
- result_reference
- attempt
- created_at
- updated_at

## Constraints

- `wardrobe_items.user_id` is NOT NULL and every retrieval query filters on it.
  Ownership is enforced in SQL **before** the model is called, never by prompt instruction.
- `outfit_items` may only reference `wardrobe_items` belonging to the same user as the
  parent outfit. Enforce this in the schema — a composite foreign key on
  `(outfit_id, user_id)` / `(wardrobe_item_id, user_id)` makes cross-user leakage
  unrepresentable rather than merely untested.
- Row-level security on every user-owned table.
- Soft deletion (`deleted_at`) on `assets` and `wardrobe_items`: the privacy flow needs
  deletion to be observable and reversible-by-support, not silent.
- Deleting an asset must cascade to the wardrobe item that depends on it, and any outfit
  referencing that item becomes `status = incomplete` rather than silently rendering a gap.
- Soft deletion must be invisible to the product. Every scoped read filters `deleted_at`, so
  a deleted item answers 404, leaves the wardrobe, and stops serving its image — "reversible
  by support" is not "still there". The stored bytes are a separate question and are not yet
  unlinked (blocker B16).
- Unique event IDs when ingestion is retried.
