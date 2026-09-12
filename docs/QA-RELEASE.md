# QA & Release Checklist

## Functional

- [ ] landing works
- [ ] app boots with a real key; **fails loudly without one, never into a stub**
- [ ] boot-time model availability check passes for both vision models
- [ ] agent crew p50 ≤ 8s, p95 ≤ 15s, measured
- [ ] ablation test green — every agent role changes the output
- [ ] trend notes all carry source + published_at
- [ ] no brand/price/merchant/link anywhere in advisory output
- [ ] multi-image upload works in one gesture
- [ ] invalid image gives actionable guidance and does not fail the batch
- [ ] cards appear progressively as each extraction finishes
- [ ] low-confidence fields are visibly hedged, not asserted
- [ ] field correction persists and survives re-analysis
- [ ] style profile saves, and is skippable with defaults
- [ ] composition renders with rationale
- [ ] swap changes one slot only, no page navigation
- [ ] regenerate works
- [ ] save works
- [ ] insufficient wardrobe names the gap instead of inventing an item
- [ ] deleting an item marks dependent outfits incomplete
- [ ] planner works where enabled
- [ ] failures can recover

## Responsive

- [ ] mobile 360px
- [ ] mobile 390px
- [ ] tablet
- [ ] desktop 1280px
- [ ] desktop 1440px+
- [ ] no horizontal overflow
- [ ] touch targets adequate

## Accessibility

- [ ] keyboard navigation
- [ ] focus states
- [ ] labels
- [ ] semantics
- [ ] contrast
- [ ] reduced motion

## Performance

- [ ] optimized images
- [ ] heavy components lazy-loaded
- [ ] no unnecessary rerender loops
- [ ] analysis does not block UI
- [ ] per-image analysis runs in parallel
- [ ] extraction cached by checksum; re-upload costs nothing

## Security

- [ ] no secrets committed
- [ ] upload validation (MIME, size, resolution)
- [ ] EXIF stripped on ingest, GPS included
- [ ] ownership enforced in the query, not the prompt
- [ ] cross-user isolation test green (AI-EVAL-CASES Case 11)
- [ ] 404 not 403 for items the caller does not own
- [ ] no raw image logging, no signed URLs in logs or analytics
- [ ] provider errors sanitized
- [ ] rate limiting on upload and extraction

## Build gates

- [ ] formatting
- [ ] lint
- [ ] typecheck
- [ ] unit tests
- [ ] integration tests
- [ ] production build

## Portfolio gate

- [ ] README has product story
- [ ] architecture diagram
- [ ] screenshots
- [ ] demo path
- [ ] measured demo metrics clearly labelled as demo/experimental
- [ ] no retailer affiliation, and no commerce claims at all — the product sells nothing
- [ ] no material/fibre claim presented as fact rather than estimate
- [ ] no inference about the person in any uploaded photo
- [ ] extraction audit trail reachable from the UI
