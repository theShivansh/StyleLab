# Analytics — STYLELAB

## Event naming

snake_case. All events include `schema_version`, `session_id`, `timestamp`.

## Core events

Wardrobe capture:
- landing_view
- wardrobe_start_clicked
- images_selected            *(count)*
- image_uploaded
- image_rejected             *(reason)*
- extraction_started
- extraction_completed       *(confidence bucket, duration)*
- extraction_failed          *(error code)*
- extraction_field_corrected *(field name, from → to)*
- item_deleted

Composition:
- style_profile_completed
- compose_clicked
- composition_started
- composition_completed
- composition_failed
- insufficient_wardrobe      *(missing roles)*
- outfit_viewed
- agent_stage_completed       *(role, duration, tokens)*
- crew_degraded               *(level, reason)*
- trend_note_shown            *(source, days since publication)*
- pro_tip_viewed
- alternative_applied
- budget_trick_viewed
- wardrobe_gap_shown
- item_swapped
- outfit_regenerated
- outfit_saved
- outfit_shared
- session_completed

Removed with the commerce scope: `item_clicked`, `add_to_bag_clicked`,
`garment_selected`, `remix_clicked`, `generation_*`.

## Funnel

```text
Landing
→ Wardrobe started
→ Images uploaded
→ Extraction completed
→ Style completed
→ Compose
→ Outfit viewed
→ Swap / Save
```

The drop-off that matters most is Landing → Images uploaded. With no demo wardrobe, that
step is the entire cold-start risk (`docs/PRD.md` §11) — instrument it finely enough to
see *where* in the upload people quit.

## Dashboard

KPIs:
- upload completion rate
- median items per first session
- **extraction acceptance rate** — fields kept vs corrected
- extraction failure rate
- median analysis latency per image
- time to first outfit
- swap rate
- save rate
- insufficient-wardrobe rate
- composition p50 / p95 latency
- crew degradation level distribution
- tokens per composition
- age of the trend articles actually shown
- advisory engagement rate
- session completion

Extraction acceptance rate is the honest quality signal for the AI. A high correction
rate is information, not embarrassment — show it.

## Root cause view

Break failures by:
- image validation reason
- extraction confidence bucket
- provider failure vs schema failure vs ownership rejection
- latency bucket
- missing-role type
- user abandonment point

## Implementation rule

Create a typed `AnalyticsClient` abstraction. Do not scatter vendor event APIs across
React components.

Built in S7: `apps/web/src/lib/analytics.ts`. There is no vendor behind it yet — PostHog is
wired up with the rest of the funnel in S9 — so the default sink drops events and the seam is
one function to replace. What exists now is the type, and the type is the data-hygiene rule:
every event names the properties it may carry, and none of them is an image URL, a garment
name typed by a user, or anything derived from a photograph beyond the metadata the wardrobe
already shows on screen.

A signed image URL is a live capability. In an analytics payload it would hand a third party
a working link to someone's photograph, which is why the list below cannot express one.

Emitting as of S7 (composition): `compose_clicked`, `composition_started`,
`composition_completed`, `composition_failed`, `insufficient_wardrobe`, `outfit_viewed`,
`swap_opened`, `item_swapped`, `outfit_regenerated`, `outfit_saved`, `outfit_shared`,
`wardrobe_gap_shown`.

Added in S11 (capture): `images_selected`, `image_rejected`, `extraction_completed`,
`extraction_failed`, `extraction_field_corrected`, `item_deleted`, `wardrobe_cleared`.

S11 is late for these, and the release audit is what caught it. The funnel had been
instrumented from `compose_clicked` onwards — which is to say from *after* the step this
document calls the entire cold-start risk. Every KPI about upload completion was
unmeasurable, and nothing said so.

### `extraction_field_corrected` carries the field name and not the values

The list above asks for "field name, from → to". S11 shipped the first half and declined the
second.

`subcategory`, `pattern`, `color_primary` and `fit` are free text written by a vision model
looking at a photograph taken inside somebody's home, and **blocker B18 is open precisely
because those fields can carry a description of a person in the frame.** "Data hygiene"
below forbids inferences about the person in a photo; sending the raw corrected values would
take the one channel we already know is imperfect and pipe it to a third party.

The loss is smaller than it looks. The KPI this document actually names is *extraction
acceptance rate* — fields kept versus corrected — and that is a count per field, which is
exactly what the event carries. Reopen it if and when B18 closes.

Deliberately not the default sink: `console.log`. A product that prints a running commentary
of the user's session to their devtools looks like it is leaking, whatever it is doing.

## Data hygiene

Never send:
- image URLs, signed or otherwise
- image content or derived thumbnails
- secrets
- free-form sensitive user content
- inferences about the person in a photo

`extraction_field_corrected` carries field names and garment attribute values only
("black" → "navy"). That is wardrobe metadata, not personal data — keep it that way.

Use stable anonymous identifiers appropriate to the environment.
