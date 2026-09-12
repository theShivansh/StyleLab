# STYLELAB ✦ — AI Outfit Composer
## Claude Code / Codex-ready Production Build Kit

STYLELAB is a company-agnostic AI fashion-commerce experience that turns product discovery into visual outfit composition.

### Core loop

Discover → Compose → Visualize → Remix → Save/Shop

### Signature features

1. AI Outfit Composer
2. Groq-powered style/product intelligence
3. Groq multimodal image understanding
4. AI-generated Virtual Try-On through a provider adapter
5. What-If Remix
6. Personalized Style Profile
7. 7-Day Outfit Planner
8. Catalogue-grounded recommendations
9. Product intelligence analytics
10. Demo Mode with deterministic seeded results
11. AI evaluation harness
12. Automated unit/integration/E2E/accessibility testing

### Product positioning

> A reusable AI commerce layer that sits on top of a fashion catalogue and helps shoppers visualize, remix, and shop complete outfits.

This is an independent portfolio/startup concept. Do not represent it as an official retailer product or integration.

---

## Production-minded AI design

**Groq is the default AI provider.**

Recommended current Groq configuration:
- `qwen/qwen3.8-27b` for multimodal style/image understanding where preview-model use is acceptable.
- `openai/gpt-oss-120b` for strong structured text reasoning / outfit orchestration.
- use Groq Structured Outputs with JSON Schema where supported.
- keep model IDs in environment/config rather than hardcoding across the codebase.

Groq's current documentation lists Qwen 3.8 27B as multimodal with vision, tool use, JSON Schema mode and reasoning; Groq also documents strict Structured Outputs for selected models including GPT-OSS 120B and Qwen 3.8 27B.

The system must still validate every model result against the application schema and against the real product catalogue.

### AI grounding rule

LLM → candidate ranking/attributes only
Database → source of truth for product IDs, prices, URLs, active state

The LLM may never invent:
- SKU
- price
- stock
- URL
- merchant
- product claims

---

## “Not a gimmick” standards

The project is not considered complete because it has a pretty UI.

It must demonstrate:

### Product integrity
- clear user problem
- measurable hypothesis
- analytics funnel
- root-cause analysis
- experimentation plan

### Engineering integrity
- typed APIs
- schema validation
- provider adapters
- async jobs
- retries/timeouts
- database constraints
- observability
- automated tests

### AI integrity
- deterministic candidate retrieval
- structured model outputs
- model/evaluation fixtures
- hallucination checks
- invalid-SKU rejection
- fallback behavior
- latency/cost logging

### UX integrity
- loading/error/empty states
- responsive layout
- keyboard navigation
- reduced motion
- privacy controls
- graceful generation failures

### Demo integrity
- complete demo path without private credentials
- pre-generated VTO fallback
- clearly labeled demo metrics
- no fake retailer affiliation

---

## Design system

Visual target:
editorial fashion × AI laboratory × premium commerce.

Base:
- warm ivory `#FAF9F7`
- black `#111111`
- controlled pink `#FF3F7F`
- soft neutrals
- 20–28px rounded cards
- large typography
- editorial imagery
- restrained glass effects

Libraries:
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Skiper UI
- Vengeance UI
- Motion
- Lucide
- Zustand
- TanStack Query

Use vendor UI selectively and wrap it with local components.

---

## Build order

0. Foundation
1. Design system + landing
2. Onboarding + composer
3. Catalogue + recommendation engine
4. Groq AI layer + vision analysis
5. VTO async pipeline
6. Result + Remix
7. Planner + analytics
8. AI evaluation
9. QA + security + accessibility + performance
10. Deployment + portfolio case study

---

## Definition of Done

A release is done only when:
- production build passes
- unit tests pass
- API contract tests pass
- E2E critical flow passes
- accessibility checks pass
- no high-severity security issue is open
- AI evaluation fixtures pass
- demo flow works without paid/private integrations
- loading/error/empty states exist
- documentation is synchronized
