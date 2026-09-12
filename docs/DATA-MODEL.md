# Data Model — STYLELAB

## users

- id
- email
- created_at

## style_profiles

- id
- user_id
- occasion
- vibe
- fit_preference
- color_preferences
- style_vector
- updated_at

## garments

- id
- brand
- title
- category
- subcategory
- color
- fit
- material
- price
- image_url
- commerce_url
- style_tags
- occasion_tags
- active

## outfits

- id
- user_id
- name
- occasion
- match_score
- status
- created_at

## outfit_items

- outfit_id
- garment_id
- role
- rank

## tryon_sessions

- id
- user_id
- outfit_id
- input_asset_id
- output_asset_id
- status
- provider
- duration_ms
- error_code
- created_at

## saved_outfits

- id
- user_id
- outfit_id
- created_at

## events

- id
- user_id
- session_id
- event_name
- schema_version
- properties
- created_at

## jobs

- id
- type
- status
- payload_reference
- result_reference
- attempt
- created_at
- updated_at

## Constraints

- foreign keys where appropriate
- unique event IDs when ingestion is retried
- user-owned records protected by row-level security
- soft deletion only where product semantics require it
