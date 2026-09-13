# STYLELAB ✦ — AI Wardrobe Stylist
## Claude Code / Codex-ready Production Build Kit

STYLELAB reads photographs of clothes you already own, turns them into a structured
wardrobe, and styles outfits from it. It sells nothing and links to no merchant.

> **STYLELAB understands YOUR closet.**

> **Requires a Groq API key.** There is no demo mode and no offline path — the app
> performs real inference and fails loudly at boot without a key. Copy `.env.example`
> to `.env` and set `GROQ_API_KEY` before running anything.

## Running it

```bash
pnpm install
cp .env.example .env          # then set GROQ_API_KEY
pnpm dev                      # web on :3000
```

The API runs from its own virtualenv:

```bash
python -m venv .venv
./.venv/Scripts/python -m pip install -e "apps/api[dev]"     # POSIX: .venv/bin/python
./.venv/Scripts/python -m uvicorn app.main:app --reload --app-dir apps/api
```

Checks — the same set CI runs:

```bash
pnpm format:check             # scoped to code; the prose specs are hand-wrapped
pnpm check                    # lint + typecheck + unit + build
pnpm --filter web test:e2e    # needs: pnpm exec playwright install chromium
./.venv/Scripts/python -m ruff check apps/api tests
./.venv/Scripts/python -m pytest apps/api/tests -q
GROQ_API_KEY= ./.venv/Scripts/python -m pytest tests/ai -q   # grounding, with no key
```

Python is pinned to **3.11** in both CI and local (`docs/DECISIONS.md`).

### The wardrobe lives in a database, and the database has migrations

```bash
cd apps/api && alembic upgrade head
```

Locally you can skip it: `APP_ENV` defaults to `local`, where `create_all` builds the schema
on boot. You cannot skip it in a deployment, and boot will tell you so — S11 added a check
that refuses to serve against a database that does not match the models, because
`create_all` adds missing *tables* and never missing *columns*, so a database that is merely
behind stays silently wrong until a query touches it.

If you have a database from before S11, it is not described by any revision. Delete
`stylelab.db` and start again, or add the missing column by hand and `alembic stamp head`.

### Deploying

Read `docs/DEPLOYMENT.md` first. The short version: set `APP_ENV=production` and the
application will tell you, in one message, every setting still holding a local default that
would be wrong in a container.

Two targets are prepared:

| Part | Where | How |
|---|---|---|
| Web | Vercel | build `apps/web`; set `NEXT_PUBLIC_API_URL` at **build** time |
| API | Hugging Face Space (Docker) | `python deploy/hf-space/prepare.py --space <owner>/<name>` |

The Space script assembles only `apps/api` plus a Dockerfile — never `.env`, never a
database file — and uploads with whatever login `hf auth login` has. It handles no secret:
the keys go in the Space's own settings page, by a human.

`GET /internal/db-activity` and `.github/workflows/db-activity.yml` keep a free Postgres from
pausing, and are a real `SELECT 1` connectivity check rather than a ping — a sleeping or
unreachable database turns the daily job red.

### Core loop

Upload → Extract → Review/correct → Compose → Swap → Save

### Signature features

1. Multi-image wardrobe capture in one gesture
2. Groq multimodal garment extraction into structured metadata
3. Per-field confidence, with correction as a first-class interaction
4. Ownership-scoped outfit composition — only items you own
5. Multi-agent advisory crew: critique, pro tips, alternatives, combinations, budget tricks
6. What-If swap, one slot at a time
7. Personalised style profile
8. Wardrobe gap detection, named generically — no brand, price or merchant
9. Extraction audit trail — what the model claimed, what was rejected
   plus sourced, dated trend context that can only re-rank what you own
10. 7-Day outfit planner *(P1, cuttable)*
11. AI evaluation harness, including cross-user isolation and agent ablation
12. Automated unit / integration / E2E / accessibility testing

### Product positioning

> A personal wardrobe intelligence layer: it makes the clothes you own legible to
> software, then styles them.

An independent portfolio concept. It has no retailer affiliation and makes no commerce
claims of any kind.

---

## Production-minded AI design

**Groq is the default AI provider.**

- `GROQ_TEXT_MODEL` — `openai/gpt-oss-120b`, powering the agent crew
- `GROQ_VISION_MODEL` — `qwen/qwen3.8-27b` for garment extraction
- `GROQ_VISION_FALLBACK_MODEL` — `qwen/qwen3.6-27b`, **availability only, never quality**
- Groq Structured Outputs with JSON Schema where supported
- Model IDs live in `.env.example` and the adapter config. Nowhere else.

Groq's throughput is what makes a seven-agent crew viable inside a 15s p95 budget. On a
slower provider this design would not ship — see `docs/AGENT-SYSTEM.md`.

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
extraction honesty · **sourced and dated trend claims** · **agent ablation — every role
must change the output or be deleted** · fallback ladder · latency/cost logging

### UX integrity
loading / error / empty states · responsive layout · keyboard navigation · reduced
motion · privacy controls · graceful extraction failures · correction affordances

### Demo integrity
rehearsed against the live path · no fabricated results anywhere · honest reporting when
the crew ran degraded · clearly labelled simulated metrics · no commerce or retailer claims

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
8b. Multi-agent advisory crew + trend grounding
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
