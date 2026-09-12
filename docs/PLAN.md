# Build Plan — STYLELAB

Produced in S0 (prompt `00-MASTER-BOOTSTRAP.md`). Recon + plan only; no application code
was written this session.

## 1. Reconnaissance

| Probe | Finding |
|-------|---------|
| Package manager | pnpm 10.33.0 available. **No `package.json`, no lockfile, no workspace.** |
| Framework | **None present.** Next.js and FastAPI are specified, not scaffolded. |
| Scripts | None. |
| Source tree | **Empty.** No `.ts`, `.tsx`, `.js`, `.py`, `.css` anywhere. |
| Directories | `.claude/`, `.github/`, `docs/`, `prompts/`, `tests/` (README only) |
| Env template | `.env.example` present — Groq required, no demo path |
| Tests | None. `tests/` holds a README and nothing else. |
| UI system | None. |
| Git | 4 commits, clean except one uncommitted `.env.example` change (see §5) |
| Node | v22.19.0 — ok |
| Python | **3.11.9 local vs `python-version: "3.12"` in CI** — drift |

The repository is a specification and harness, not a scaffold. Nothing is adapted; S1
builds from zero. Working rule 2 ("adapt rather than restart") does not apply — there is
nothing to adapt.

## 2. Gap analysis

**Have:** 24 coherent specs, a working execution harness (permissions, a Stop-hook gate,
the `PROGRESS` ledger, CI, a corrected prompt index), and six recorded architectural
decisions covering the wardrobe pivot, commerce removal, demo-mode removal, the agent
crew, the trend layer, and UI library verification.

**Need:** the entire application.

**Structural gaps that bite early, in the order they bite:**

1. **The repo layout in `CLAUDE.md` does not exist.** `apps/web`, `apps/api`, `packages/`,
   `data/`, `tests/ai/` are all specified and all absent. S1 creates them exactly as
   written — the audit's finding #6 was that an invented layout survives twelve sessions.
2. **The phase gate is currently inert.** `.claude/hooks/gate.sh` exits 0 while
   `apps/web/package.json` is missing. Until S1 creates it, nothing is gated and a session
   can end with a broken tree reporting success. S1 must create the web package *first*,
   not last.
3. **`tests/` sits at the repo root and must stay there.** `CLAUDE.md` names `tests/ai/`
   the cross-cutting proof layer. S1 will be tempted to fold it into an app. It must not.
4. **Python version drift.** CI pins 3.12; local is 3.11.9. Left alone this produces
   "works locally, fails in CI" at the worst moment. Resolve in S1 by pinning one version
   in both places — recommend matching CI at 3.12 and recording it.
5. **No `data/trends/` corpus** (B8). Without it the Trend Scout is skipped and the crew
   runs at degradation level 2. Not blocking until S8b.
6. **No Groq key** (B7). Blocking from S5 onward — S1 through S4 build interfaces and
   stubs and need nothing.

## 3. Conflicts between prompt 00 and decisions already taken

Prompt `00-MASTER-BOOTSTRAP.md` predates four decisions recorded on 2026-09-12. A future
session pasting it verbatim would be instructed to build things this project has removed.
Resolved in favour of `docs/DECISIONS.md`, and the prompt is patched in this commit.

| Prompt 00 said | Superseded by |
|----------------|---------------|
| Rule 9: "Make the demo path work even without external AI credentials" | Demo mode removed. The app requires a key and fails loudly without one. Test doubles are not a demo path. |
| "For Animaster, identify the exact intended repository/package" | B3: it does not exist. Do not look for it. |
| Hero moments: compose, **visualize**, remix | No rendering step. Hero moments are compose, **understand** (extraction + correction), swap. |
| "company-agnostic AI outfit composition product" | An AI wardrobe stylist over clothes the user owns. Sells nothing. |
| "Then implement the product phase-by-phase" | One phase per session. S0 stops at this plan. |

## 4. Implementation plan

Ordering follows `prompts/README.md`. Each session: `/resume`, paste the prompt,
`/plan-build`, `/implement-phase`, `/verify`, audit, update `PROGRESS`, commit, `/clear`.

| S | Prompt | Goal | Exit gate |
|---|--------|------|-----------|
| **S1** | `01` | pnpm workspace; `apps/web` (Next.js App Router, TS strict, Tailwind, shadcn); `apps/api` (FastAPI, Pydantic, SQLAlchemy); `packages/`; `tests/ai/`; `data/trends/`; scripts for lint, typecheck, test:unit, test:e2e, build | boots, build, typecheck, lint, test runner wired, **`apps/web/package.json` exists so the gate activates**, Python pinned to one version |
| **S2** | `02` | design tokens + landing | coherent at 390/768/1440, keyboard focus, reduced motion |
| S2b | `09` | reference to UI *(optional)* | only with reference images |
| **S3** | `03` | multi-image upload, progressive analysis cards, correction UI, composer | cold-start path completes, one bad image costs one card, no console errors |
| **S4** | `04` | wardrobe domain, ownership-scoped retrieval, `WardrobeAnalyzer` / `OutfitAdvisor` interfaces, `DeterministicRanker`, stubs | **cross-user rejection test red then green**, unowned-item rejection, deterministic ranker |
| **S5** | `12` | Groq adapters behind those interfaces, vision fallback chain | domain cannot tell Groq from stub, `git grep -i groq` outside `adapters/` empty, **needs B7** |
| **S6** | `05` | upload + async analysis pipeline, EXIF strip, checksum cache, soft-delete cascade | parallel per-image jobs, partial-batch success, job observable |
| **S7** | `06` | result + swap | one swap is not a full rebuild, no page nav, analytics fire |
| **S8** | `10` | AI eval harness | every case in `AI-EVAL-CASES.md` runs, **failure paths, not just happy path** |
| **S8b** | `14` | agent crew + trend grounding | **ablation green for every role**, p50 under 8s and p95 under 15s measured, `git grep -i crewai` outside `adapters/` empty, needs B8 |
| S9 | `07` | planner + analytics | P1 — cut first if time runs short |
| **S10** | `11` | recruiter demo | 90s path, timings recorded, rehearsed live |
| **S11** | `08` | harden + deploy | all QA-RELEASE gates green |
| S12 | `13` | final review | **review only** — do not run as a build |

**The ordering that matters most is S4 to S5.** S4 builds interfaces and stubs; S5 fills
them with Groq. Run together and Groq imports land inside domain code, breaking the rule
the architecture rests on. Verify between them with the grep.

**S8 before S8b is deliberate.** The crew is the component most likely to produce
confident nonsense, so the harness that catches it must exist first.

## 5. Assumptions recorded

1. Build from zero; nothing to adapt.
2. Repo layout exactly as `CLAUDE.md` specifies. No third app.
3. Python pinned to CI's 3.12, not local 3.11.9 — to be confirmed in S1.
4. `tests/ai/` stays at the repo root.
5. `DeterministicRanker` is a rung on the fallback ladder, never a product mode.
6. **Unresolved:** `.env.example` has an uncommitted change this session could not inspect
   — `.claude/settings.json` denies `Read(./.env.*)`, which matches `.env.example` as well
   as `.env`. The deny was not circumvented. `.env.example` is tracked and **not**
   gitignored, so if a real key was pasted there it would be committed by `git add -A`.
   Verify by hand before the next commit. If the rule proves too broad in practice,
   narrow it to `Read(./.env)` and `Read(./.env.local)` rather than disabling it.

## 6. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cold start (B6) — no demo wardrobe *and* no demo mode; a live upload and live Groq must both work in front of an interviewer | **High** | Stage presenter photos; rehearse the live path; hold the `DEMO-SCRIPT` budget |
| Extraction quality — if vision reads garments poorly, every outfit downstream is wrong | **High** | Confidence floor, correction UI as a first-class flow, extraction acceptance rate tracked from day one |
| Agent latency and cost — 4-6x a single ranking call | Medium | Parallel DAG, circuit breaker, degradation ladder, style-profile cache, ablation |
| Groq model deprecation on weeks of notice | Medium | Fallback chain plus boot-time availability check |
| Gate inert until S1 | Medium | Create `apps/web/package.json` first in S1 |
| Scope creep past the KEEP line | Medium | `EXECUTION-PLAN.md` triage: cut planner, share cards, preference learning first |

## 7. Not done this session

No application code, no dependencies installed, no scaffolding. S0 is recon and plan by
design — the execution plan warns that letting it implement burns the context window on a
half-built foundation. S1 starts the build.
