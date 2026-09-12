# Product Requirements Document — STYLELAB

## 1. Product summary

STYLELAB turns a photo of your clothes into a wardrobe that understands itself, then
styles outfits from what you already own.

Upload a few garments. A vision model reads each one into structured metadata. That
becomes your personal wardrobe, and every outfit STYLELAB proposes is assembled only
from items in it.

The product should feel like: **STYLELAB understands YOUR closet.**

## 2. Problem

Most style tools recommend things to buy. The harder, more common problem is standing in
front of clothes you already own and not seeing the outfit in them.

Existing wardrobe apps fail on the entry cost: cataloguing a closet by hand is tedious
enough that nobody finishes. Automatic extraction from photographs is what makes a
personal wardrobe viable at all — it is the feature, not a convenience on top of one.

Do not claim unvalidated statistics about wardrobe utilisation or decision fatigue.

## 3. Target users

### A — Owns plenty, wears a fraction
Wants to rediscover combinations already in the closet.

### B — Decision-fatigued
Wants a defensible answer to "what do I wear today" in seconds.

### C — Experimenter
Wants to remix, swap, and explore alternatives within what they own.

## 4. Jobs to be done

"When I look at my own clothes and see nothing to wear, show me a combination I own but
had not considered."

"When I like an outfit but want one change, let me swap a single item without rebuilding it."

"When I photograph my clothes, do the cataloguing for me — and let me fix what you get wrong."

## 5. Product goals

Primary:
- make wardrobe capture fast enough to actually complete
- produce outfits that are unambiguously grounded in owned items
- make correcting the AI feel like part of the product, not an apology for it
- reduce time to first complete outfit
- learn style preferences from swaps and saves

Secondary:
- surface genuine wardrobe gaps
- make outfits shareable
- make the extraction audit trail inspectable

## 6. Non-goals

MVP does not aim to:
- sell anything, or link to any merchant
- simulate fabric physics
- provide body analysis or size intelligence
- build live AR or video try-on
- render photorealistic try-on images
- train a foundation model

Commerce was deliberately removed — see `docs/DECISIONS.md` (2026-09-12).

## 7. MVP feature set

### P0
- landing
- multi-image wardrobe upload
- image validation
- AI garment extraction with per-field confidence
- extraction review and correction
- wardrobe browse / edit / archive
- style preferences
- outfit composition grounded in the wardrobe
- outfit result with rationale
- multi-agent advisory output: critique, pro tips, alternatives, combinations,
  budget tricks, generically-named wardrobe gaps
- sourced and dated trend context
- swap one slot
- regenerate
- save
- insufficient-wardrobe handling
- analytics

### P1
- 7-day planner
- shareable look cards
- preference learning from swaps
- wardrobe gap insights

### P2
- live camera capture
- generative try-on rendering
- size intelligence
- outfit sharing between users
- creator tooling

## 8. Core user flow

Landing → Upload → Analysis → Review → Preferences → Compose → Result → Swap / Save

## 9. Success metrics

North Star:
**Wardrobe-to-Outfit Completion Rate** — sessions that upload at least three items and
reach a saved or swapped outfit.

Supporting:
- upload completion rate
- median items per first session
- extraction acceptance rate *(fields kept vs corrected)*
- time to first outfit
- swap rate
- save rate
- regeneration rate
- insufficient-wardrobe rate
- extraction failure rate
- median analysis latency per image
- median and p95 composition latency
- crew degradation level distribution
- tokens per composition
- advisory engagement: tips read, alternatives applied

Extraction acceptance rate is the honest quality signal. Track it from day one; a high
correction rate is information, not embarrassment.

## 10. Experiment backlog

A/B:
- 3 vs 6 items requested at onboarding
- review-before-compose vs compose-then-correct
- confidence shown numerically vs as a hedge in wording
- swap-first vs save-first result layout

## 11. Risks

**Extraction quality is the product risk.** If the vision model reads garments poorly,
every downstream outfit is wrong and the correction UI carries the whole experience.

**Cold start is the adoption risk.** With no demo wardrobe *and* no demo mode, a
first-time user must upload photos and reach live Groq before seeing any value. Deliberate
(`docs/DECISIONS.md`); it makes the first 60 seconds the highest-stakes part of the product.

**Agent latency and cost are the operational risks.** The crew costs roughly 4-6x a single
ranking call and adds hops to the critical path. Budgets, the degradation ladder and the
anti-theatre ablation requirement are in `docs/AGENT-SYSTEM.md`.

**Unsourced trend claims are the credibility risk.** Mitigated by requiring source and
date on every trend note, and dropping those that lack it.

Also: privacy of closet imagery, and scope creep.

## 12. Product principles

1. Show, don't describe.
2. One great swap beats ten weak recommendations.
3. Ground every outfit in items the user owns. No exceptions, no curated fallback.
4. A guess must look like a guess.
5. Correcting the AI is a first-class interaction.
6. Make latency feel intentional.
7. Design mobile-first — the photos are on the phone.
