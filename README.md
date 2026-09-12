# STYLELAB ✦ — AI Wardrobe Stylist
## Claude Code / Codex-ready Production Build Kit

STYLELAB reads photographs of clothes you already own, turns them into a structured
wardrobe, and styles outfits from it. It sells nothing and links to no merchant.

> **STYLELAB understands YOUR closet.**

### Core loop

Upload → Extract → Review/correct → Compose → Swap → Save

### Signature features

1. Multi-image wardrobe capture in one gesture
2. Groq multimodal garment extraction into structured metadata
3. Per-field confidence, with correction as a first-class interaction
4. Ownership-scoped outfit composition — only items you own
5. What-If swap, one slot at a time
6. Personalised style profile
7. Wardrobe gap detection ("you have no footwear yet")
8. Extraction audit trail — what the model claimed, what was rejected
9. 7-Day outfit planner *(P1, cuttable)*
10. Demo mode that runs with no credentials and fabricates nothing
11. AI evaluation harness, including cross-user isolation
12. Automated unit / integration / E2E / accessibility testing

### Product positioning

> A personal wardrobe intelligence layer: it makes the clothes you own legible to
> software, then styles them.

An independent portfolio concept. It has no retailer affiliation and makes no commerce
claims of any kind.

---

## Production-minded AI design

**Groq is the default AI provider.**

- `GROQ_TEXT_MODEL` — `openai/gpt-oss-120b` for structured reasoning and ranking
- `GROQ_VISION_MODEL` — garment extraction; **the default is an open decision, see
  `docs/DECISIONS.md`** before S5
- Groq Structured Outputs with JSON Schema where supported
- Model IDs live in `.env.example` and the adapter config. Nowhere else.

Verify configured model IDs against Groq's live model list at boot in production, and
fail loudly there rather than at a user's first request — Groq has deprecated models on
weeks of notice.

### The grounding rule

```text
LLM     → ranking, rationale, and attribute extraction only
Database → source of truth for what the user owns
```

The LLM may never reference:
- an item the user does not own
- **an item belonging to another user**
- fibre or material content stated as fact rather than estimate
- any attribute of the person in a photograph

Ownership is enforced in the SQL query **before** the model is called, and re-validated
after it returns. Prompt wording is never the only thing standing between two users'
wardrobes.

---

## "Not a gimmick" standards

A pretty UI does not make this complete.

### Product integrity
clear user problem · measurable hypothesis · analytics funnel · root-cause analysis ·
experimentation plan

### Engineering integrity
typed APIs · schema validation · provider adapters · async jobs · retries/timeouts ·
database constraints that make cross-user leakage unrepresentable · observability ·
automated tests

### AI integrity
deterministic candidate retrieval · structured model outputs · evaluation fixtures ·
hallucination checks · **unowned-item rejection** · **cross-user isolation** ·
extraction honesty · fallback behaviour · latency/cost logging

### UX integrity
loading / error / empty states · responsive layout · keyboard navigation · reduced
motion · privacy controls · graceful extraction failures · correction affordances

### Demo integrity
complete path without private credentials · a demo analyzer that measures rather than
fabricates · clearly labelled demo metrics · no commerce or retailer claims

---

## Design system

Visual target: editorial fashion × AI laboratory × personal archive.

Base:
- warm ivory `#FAF9F7`
- black `#111111`
- controlled pink `#FF3F7F`
- soft neutrals
- 20–28px rounded cards
- large typography
- the user's own garment photography as the imagery
- restrained glass effects

Libraries:
Next.js · TypeScript · Tailwind CSS · shadcn/ui · Vengeance UI · Skiper UI · Motion ·
Lucide · Zustand · TanStack Query

Both UI libraries are shadcn source-drop registries, verified 2026-09-12 — see
`docs/DECISIONS.md` for licence terms and conditions of use. Wrap vendor components with
local ones.

---

## Build order

0. Foundation
1. Design system + landing
2. Wardrobe onboarding + composer
3. Wardrobe domain + recommendation engine
4. Groq AI layer + garment extraction
5. Upload + async analysis pipeline
6. Result + Swap
7. Planner + analytics
8. AI evaluation
9. QA + security + accessibility + performance
10. Deployment + portfolio case study

See `prompts/README.md` for the authoritative session order and `docs/PROGRESS.md` for
current state.

---

## Definition of Done

- production build passes
- unit, API contract, and critical E2E tests pass
- accessibility checks pass
- no high-severity security issue open
- AI evaluation fixtures pass, **cross-user isolation included**
- the full path works with `GROQ_API_KEY` unset
- loading / error / empty states exist
- documentation is synchronised
