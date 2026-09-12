# Analytics — STYLELAB

## Event naming

snake_case

All events include:
- schema_version
- session_id
- timestamp

## Core events

- landing_view
- composer_started
- photo_uploaded
- photo_rejected
- style_profile_completed
- garment_selected
- outfit_generate_clicked
- generation_started
- generation_completed
- generation_failed
- outfit_viewed
- item_swapped
- remix_clicked
- outfit_saved
- item_clicked
- add_to_bag_clicked
- outfit_shared
- session_completed

## Funnel

```text
Landing
→ Composer started
→ Photo uploaded
→ Style completed
→ Generate
→ Generation complete
→ Result viewed
→ Remix/product interaction
→ Save/shop
```

## Dashboard

KPIs:
- activation rate
- generation success
- median generation duration
- remix rate
- save rate
- product CTR
- add-to-bag intent
- session completion

## Root cause view

Break failures by:
- photo validation
- latency bucket
- provider failure
- catalogue mismatch
- user abandonment

## Analytics implementation rule

Create a typed `AnalyticsClient` abstraction.

Do not scatter vendor-specific event APIs across React components.

## Data hygiene

Never send:
- raw image URLs when not required
- secrets
- free-form sensitive user content
- inferred sensitive attributes

Use stable anonymous/user identifiers appropriate to the environment.
