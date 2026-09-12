# PHASE 3 — Wardrobe Onboarding + Composer

This is the cold-start path. There is no demo wardrobe, so a first-time user — including
a recruiter — meets the product here. It carries the whole first impression; build it
accordingly.

Build:
- multi-image picker: many photos in one gesture, drag-drop and camera roll
- per-image client validation with immediate, actionable feedback
- optional category hint per image at upload time
- progressive analysis view — cards resolve independently
- extraction review: per-field values, confidence hedging, inline correction
- wardrobe grid: browse, edit, archive, delete
- occasion / vibe / fit / colour preferences — **all skippable with working defaults**
- composer workspace
- mobile bottom sheets
- deterministic local state

Runs fully in demo mode with no credentials, via the deterministic analyzer.

UX requirements:
- progressive disclosure; never a wall of form
- the wardrobe is usable at three items — do not gate composition behind a minimum a
  first-time user will not reach
- a user who taps straight through the preferences still reaches an outfit
- low confidence reads as a hedge, not an error
- correction is one tap from the card, not buried in a settings screen
- a rejected image never disturbs the others
- "Compose outfit" is the primary action and is reachable early

Acceptance:
- upload → analysis → review → compose completes entirely in demo mode
- a failing image costs one card, not the run
- correcting a field persists and is reflected in the next composition
- selection and wardrobe state persist across navigation
- no console errors
