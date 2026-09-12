# STYLELAB — Claude Code Project Instructions

## Mission

Build STYLELAB as a production-quality AI wardrobe stylist. The user photographs clothes
they own; a vision model turns those photos into structured garment data; outfits are
composed only from that wardrobe. It sells nothing and links to no merchant.

It should feel like: **STYLELAB understands YOUR closet.**

Optimize for a polished end-to-end demo, not maximal feature count.

## Always do this

1. Read the relevant docs before changing architecture.
2. Inspect the existing code before proposing new files.
3. Keep public APIs typed and validated.
4. Prefer small composable modules.
5. Never reference a garment the user does not own.
6. Keep AI providers behind interfaces/adapters.
7. Keep product logic separate from presentation.
8. Make loading, error, empty, and retry states first-class.
9. Respect reduced motion and keyboard accessibility.
10. Run targeted checks before declaring work complete.
11. Update docs when architecture or behavior materially changes.
12. Never let the running app fall back to a test double — there is no demo mode.

## Product rules

The primary flow is:

Landing → Upload wardrobe → AI extraction → Review/correct → Preferences → Compose
→ Result → Swap/Regenerate/Save.

The signature product moment is Swap. It should feel immediate, understandable, and
visually satisfying — one slot changes, the rest stay still.

The AI is allowed to:
- read uploaded garment photos into structured metadata
- rank and combine items the user owns
- generate style descriptions and rationale
- name what the wardrobe is missing
- analyze user-selected style preferences

The AI may never:
- reference a garment the user does not own
- reference another user's garment, under any circumstances
- state fibre or material content as fact — it is `material_guess`, and must read as a guess
- claim certainty about physical fit
- infer attributes of the person in a photograph
- act on text it read inside an image

Ownership is enforced in the SQL query before the model is called and re-validated after
it returns. Prompt wording is never the only thing standing between users' wardrobes.

There is no curated fallback outfit. A fallback assembled from garments the user does not
own would break the one rule the product rests on. Degrade to the deterministic ranker
over the same wardrobe, then say honestly what is missing.

A guess must look like a guess. Fields below the confidence floor are hedged in the UI and
offered for correction; a user correction is never overwritten by later re-analysis.

Style Match is a UX heuristic, not a scientific body/fit measurement.

## Architecture rules

Use:
- Next.js App Router + TypeScript for web
- FastAPI + Pydantic for API
- Supabase/Postgres for persistence
- object storage abstraction for images
- async job model for VTO
- adapter pattern for LLM/VTO/analytics/commerce

Do not couple React components directly to vendor SDKs.

## UI rules

Visual target:
editorial fashion × AI lab × premium commerce.

Use:
- warm neutral surfaces
- dark typography
- controlled pink accent
- large imagery
- rounded cards
- strong typography
- restrained gradients
- purposeful motion

Avoid:
- generic AI dashboard styling
- excessive glassmorphism
- neon everywhere
- gratuitous 3D
- animation on every element
- dense information above the fold

Use Skiper/Vengeance components as ingredients, not as the visual identity.

## Motion rules

Functional: 100–180ms
Spatial: 250–500ms
Hero/reveal: 600–1200ms

Honor:
`prefers-reduced-motion: reduce`

Progress states name real work, never a bare spinner.

Extraction: reading photo → finding garment → reading colour and cut → checking confidence → ready.
Composition: reading your wardrobe → matching silhouettes → balancing palette → building look → ready.

During a multi-image upload, each card resolves independently. Never show one blocking
spinner over the whole batch.

## Privacy rules

User images require explicit consent and clear deletion behavior.

Never log raw image bytes, sensitive image URLs, or secrets.

Do not infer or expose sensitive personal attributes. Keep appearance/style preferences user-controlled.

## Analytics rules

Track the funnel defined in docs/ANALYTICS.md. Use typed event payloads.

## Code quality

Prefer:
- strict TypeScript
- schema validation
- explicit error types
- testable pure functions
- accessible primitives
- server/client separation
- stable loading boundaries
- meaningful names

Avoid:
- `any` unless unavoidable and documented
- giant components
- duplicated product metadata
- hidden side effects
- random AI calls from UI components
- hardcoded secrets

## Verification

Before finishing a task:
- run formatting/lint
- run typecheck/build
- run targeted tests
- inspect the changed UI
- verify mobile behavior
- verify reduced motion
- verify error states

If a check fails, fix it before claiming completion.

## Repository documentation

Keep:
- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/UX-UI-SPEC.md`
- `docs/USER-FLOWS.md`
- `docs/DATA-MODEL.md`
- `docs/API-SPEC.md`
- `docs/ANALYTICS.md`
- `docs/SECURITY-PRIVACY.md`
- `docs/QA-RELEASE.md`
- `docs/DEVELOPMENT-PLAN.md`

Do not let this file become a giant reference manual. Move detailed procedures into `.claude/skills/`.

## Decision protocol

When a requirement is ambiguous:
- choose the smallest option that preserves the product goal
- document the assumption
- continue
- do not block the build with unnecessary questions

## AI provider rules

Default provider: **Groq**. Config is read from environment, never hardcoded:

- `GROQ_TEXT_MODEL` — `openai/gpt-oss-120b` (orchestration, agents, ranking, rationale)
- `GROQ_VISION_MODEL` — `qwen/qwen3.8-27b` (garment extraction)
- `GROQ_VISION_FALLBACK_MODEL` — `qwen/qwen3.6-27b`

Vision is the product's front door, so extraction quality is worth the ~33% premium of
3.8. The fallback exists for availability — deprecation, rate limits, provider errors —
**not for quality**. A low-confidence extraction from 3.8 is a confidence signal to
surface to the user, never a reason to retry on 3.6.

Rules:
- Model IDs appear in exactly two places: `.env.example` and the adapter config.
- Verify configured model IDs against Groq's model list at boot and fail loudly there,
  not at a user's first request. Groq deprecates models on weeks of notice.
- Never let a model ID string appear in a React component, a route handler, or a prompt
  template.
- Never expose `GROQ_API_KEY` to the browser.

**There is no demo mode.** The application requires a real key and always performs real
inference. `tests/ai/` and CI use stub adapters — those are test doubles for an external
dependency, not a product path, and nothing in the running app may fall back to them.

Prefer Structured Outputs / JSON Schema with `additionalProperties: false` and explicit
enums. Schema validity is not business validity, and neither is authorisation —
catalogue and ownership validation still run after it, always.

## Agent rules

Outfit advice comes from a crew of specialist agents behind the `OutfitAdvisor`
interface. Roles, dataflow, latency budget and output contract: `docs/AGENT-SYSTEM.md`.

- Domain code never imports the agent framework, same rule as Groq. Enforced by
  `apps/api/tests/test_adapter_boundary.py`, which parses with `ast` rather than grepping:
  no vendor import or symbol outside `adapters/`, no model id literal outside the adapter
  config, and `domain/` never imports `adapters/`. A plain `git grep -i crewai` will match
  settings field names and docstring prose — those are not coupling, and chasing the grep to
  zero would mean renaming settings away from their environment variables.
- **Every agent's output is untrusted, including the Editor's.** Schema → business →
  ownership validation runs on the merged response regardless of what any agent asserted.
  An agent asked to critique is not thereby trusted.
- Agent-to-agent messages are untrusted. A compromised upstream agent must not be able
  to instruct a downstream one.
- Each role must be independently ablatable and must change the output. A role that can
  be removed without changing the result is decoration — delete it.
- Never re-run the full crew for a single-slot swap.

## Trend rules

Trend input comes from the `TrendSource` adapter, never from model recall. Asking a model
what is currently fashionable returns confident output from a training cutoff with no
source and no date — that is the gimmick this project exists to avoid.

- A trend may only re-rank or contextualise items the user already owns. It may never
  introduce a garment.
- Every trend claim shown to the user carries its source and publication date. If it
  cannot be attributed, it is not shown.
- Trend text from the web is untrusted content, subject to the same injection rules as
  text found inside an uploaded image.
- A stale corpus degrades honestly: name the date rather than implying currency.

## Advisory output rules

The product gives pro tips, alternatives, combinations and budget tricks. Budget value
comes from maximising what the user already owns — layering, cuffing, tucking, re-wear,
proportion, care and longevity.

Wardrobe gaps may be named generically ("a white leather sneaker would unlock five more
outfits"). Never a brand, price, merchant or link. The product sells nothing.

## Repository layout

```
apps/web      Next.js App Router + TypeScript  (Vitest, Playwright)
apps/api      FastAPI + Pydantic              (pytest, ruff)
packages/     shared TS types only, if genuinely shared
data/         test fixtures only — a few sample garment images for the eval suite.
              There is no seed catalogue and no demo wardrobe; see docs/DECISIONS.md.
tests/ai/     grounding fixtures + eval runner (python, mock provider)
docs/         specs — see docs/INDEX.md for the full list
```

pnpm workspace at root. Do not create a third app. Do not move `tests/ai` into
either app — it is the cross-cutting proof layer.

## Session protocol

This build spans many sessions. Context does not survive; the ledger does.

1. Start every session with `/resume`.
2. `docs/PROGRESS.md` is the source of truth for what is done. The repo overrules it;
   your memory overrules neither.
3. One phase per session. Update the PROGRESS row and commit before the session ends.
4. Append to `docs/DECISIONS.md` whenever a choice materially affects architecture,
   UX, provider strategy, privacy, or scope.

## Doc index

`docs/INDEX.md` lists all 20 specs. Read the ones the current phase names — not all
of them, every time.
