# Product Requirements Document — STYLELAB

## 1. Product summary

STYLELAB is an AI-assisted outfit composition layer for fashion-commerce experiences.

It helps shoppers:
- understand how products work together
- visualize outfits on themselves
- explore alternatives without restarting
- save complete looks
- convert product browsing into outfit-level decisions

## 2. Problem

Online fashion discovery is item-centric while purchase decisions are outfit-centric.

Users can find a shirt they like but still need to decide:
- what bottom matches it
- what shoes work
- whether the overall look suits the intended occasion
- whether they can imagine themselves wearing it

The product hypothesis is that reducing this composition/visualization burden can increase meaningful product interaction and purchase confidence.

Do not claim unvalidated abandonment or conversion statistics as facts.

## 3. Target users

### A — “What goes with this?” shopper
Wants quick combinations.

### B — Fast shopper
Wants a complete look with minimal browsing.

### C — Experimenter
Wants remixing, trend exploration, and alternatives.

## 4. Jobs to be done

“When I like a fashion item but do not know what to pair with it, help me quickly create a complete look that feels like me.”

“When I am uncertain about a look, let me visualize it before I buy.”

“When I like an outfit but want one change, let me swap an item without rebuilding everything.”

## 5. Product goals

Primary:
- increase outfit-level engagement
- reduce time to first complete look
- improve recommendation interaction
- increase multi-item shopping intent
- learn user style preferences

Secondary:
- make trend discovery actionable
- turn generated outfits into shareable content
- create a reusable commerce intelligence layer

## 6. Non-goals

MVP does not aim to:
- perfectly simulate fabric physics
- provide medically or scientifically precise body analysis
- build live AR video try-on
- replace merchant checkout
- scrape private retailer systems
- train a foundation model

## 7. MVP feature set

### P0
- landing
- demo mode
- photo upload
- style preferences
- product catalogue
- outfit composer
- AI ranking
- async VTO
- result screen
- remix
- save
- mock commerce CTA
- analytics

### P1
- 7-day planner
- shareable look cards
- preference learning
- trend insights

### P2
- live camera/AR
- real merchant integrations
- size intelligence
- advanced fit simulation
- creator tooling

## 8. Core user flow

Landing
→ Create/Demo
→ Photo
→ Style profile
→ Product selection
→ Compose
→ AI generation
→ Result
→ Remix/Save/Shop

## 9. Success metrics

North Star:
Successful Outfit Session Rate

A successful session:
- generates an outfit
- interacts with the result
- saves or expresses shopping intent

Supporting metrics:
- activation rate
- generation success rate
- time to first outfit
- remix rate
- save rate
- product CTR
- add-to-bag intent
- session completion
- generation failure rate
- average generation latency

## 10. Experiment backlog

A/B:
- 3 vs 5 suggested looks
- “Try On” vs “See Yourself In It”
- instant demo vs forced upload
- save-first vs shop-first result layout

## 11. Risks

AI quality, latency, privacy, inaccurate recommendations, scope creep, and unclear commerce integration.

## 12. Product principles

1. Show, don't describe.
2. One great remix is better than ten weak recommendations.
3. Ground every recommendation in real catalogue objects.
4. Make latency feel intentional.
5. Preserve user control.
6. Design mobile interactions first.
