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
- trend_note_shown            *(source, corpus age)*
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
- trend corpus age at use
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
