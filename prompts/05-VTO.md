# PHASE 5 — Upload + Async Image Analysis Pipeline

This phase replaces the former virtual try-on pipeline. STYLELAB renders nothing: the
result is a composed look made of the user's own garment photos. The async machinery that
was going to serve try-on now serves extraction, which is the path that actually runs on
every session.

Implement:
- multi-image upload in one gesture
- per-image validation: MIME allow-list, byte ceiling, resolution bounds
- **EXIF stripping on ingest, GPS included**
- private object storage abstraction + short-lived signed URLs
- `analyze_item` async job, one per image, running in parallel
- job status endpoint with named stages
- analyzer adapter boundary (interface from Phase 4)
- checksum cache — re-uploading an unchanged image costs nothing
- error classification and bounded retry
- `item_extractions` persistence for successes and failures alike
- soft delete cascading asset → item → dependent outfits

Frontend:
- progressive cards — each image resolves independently as its job finishes
- named stages, never a bare spinner, and never one spinner over the whole batch
- low-confidence fields visibly hedged and inline-correctable
- a rejected image shows its own actionable error without disturbing the others
- retry per image

Do not couple the frontend to a provider. Do not send a user's face or body photo
anywhere — the product has no try-on path and no reason to hold one.

Acceptance:
- the full upload → wardrobe path completes against live Groq, with the vision fallback
  chain exercised (primary error → fallback model, per AI-EVAL-CASES Case 24)
- one failing image fails one card, never the batch
- no blocking synchronous HTTP request for analysis
- job status is observable
- deleting an asset cascades correctly and reports which outfits became incomplete
