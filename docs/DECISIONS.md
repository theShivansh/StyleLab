# Architecture & Product Decisions

This file is append-only for meaningful decisions.

## Template

### YYYY-MM-DD — Decision title

Context:
Decision:
Alternatives:
Why:
Trade-offs:
Follow-up:

---

Claude Code should append decisions when a choice materially affects architecture, UX, provider strategy, privacy, or scope.

---

### 2026-09-12 — Groq vision model default (RESOLVED)

Context:
The harness patch added an "AI provider rules" section to `CLAUDE.md` that names
`qwen/qwen3.6-27b` as the vision default "for cost", and calls `qwen/qwen3.8-27b`
a one-line env change for quality comparison. The rest of the kit disagrees:
`.env.example`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `README.md` and
`prompts/13-FINAL-AUTONOMOUS-BUILD.md` all name `qwen/qwen3.8-27b`.

`CLAUDE.md` is the only file Claude Code auto-loads, so the 3.6 default will win in
practice while every other doc says 3.8 — the exact drift the audit's finding #13 warns about.

Decision:
**Primary `qwen/qwen3.8-27b`, fallback `qwen/qwen3.6-27b`.** Not an either/or — a chain.
3.8 is the stronger, ~33% pricier sibling and vision is now the product's front door, so
extraction quality is worth paying for. 3.6 catches deprecation, rate limits, and
provider errors without a code change.

`CLAUDE.md` and `.env.example` aligned to this; the five docs already saying 3.8 are now
correct. Model IDs remain confined to `.env.example` and the adapter config.

Alternatives:
(a) Align `.env.example` + `ARCHITECTURE.md` to `qwen/qwen3.6-27b` — follows CLAUDE.md's
    own rule that model IDs live in exactly two places, and takes the cheaper default.
(b) Align `CLAUDE.md` to `qwen/qwen3.8-27b` — matches the five existing kit docs.

Why:
Provider strategy is a real choice with a cost/quality trade-off, not a typo to sweep up.

Trade-offs:
Leaving it open risks S5 picking arbitrarily; that risk is why this entry exists.

Follow-up:
1. Verify both IDs against Groq's live model list at boot. Neither is independently
   confirmed here, and Groq has deprecated models on weeks of notice — the fallback
   reduces that risk but does not remove it. Fail loudly at startup, not at first request.
2. Fallback is for availability, not quality. If 3.8 returns a low-confidence extraction,
   that is a confidence problem surfaced to the user, not a reason to retry on 3.6.

---

### 2026-09-12 — UI library verification (blocker B3) — RESOLVED

Context:
`docs/UX-UI-SPEC.md` named three libraries — Skiper UI, Vengeance UI, "Animaster" —
none with a verified install source. Each was inspected against its live registry
before S2 so the build cannot fabricate an import.

Decision:
- **Vengeance UI — APPROVED.** Primary source for animated CTA / text / loader patterns.
- **Skiper UI — APPROVED WITH CONDITIONS.** Free components only, attribution required.
- **"Animaster" — REJECTED.** Removed from the spec. No package, no repo, no docs.

---

**Vengeance UI** — `https://vengenceui.com` (note the domain elides the second "a";
`vengeanceui.com` is not the site). Repo `github.com/Ashutoshx7/VengeanceUI`.

- MIT licensed. 1,135 stars, 103 forks, 27 contributors, last activity 2026-08-31.
- Backed by the Vercel OSS Program; tested with BrowserStack.
- Not an npm package. shadcn registry served **from the public repo**:
  `https://raw.githubusercontent.com/Ashutoshx7/VengeanceUI/main/public/r/{name}.json`
  Verified live — `animated-rays.json` returns valid `registry-item` JSON.
- `npx shadcn@latest add <raw-url>`, or alias `@vengeanceui/{name}` in `components.json`.
- Ships an official agent skill + MCP server (`npx vengeanceui init`, Cursor/Claude).

Why: registry is served from MIT-licensed public source, so it is auditable before
install, forkable, and pinnable. No licence key, no payment, no proprietary endpoint.

Trade-offs / conditions:
1. **The docs site displays a Solana memecoin contract address** ("Official CA /
   Community Token CA", pump.fun address, DEX Screener link) persistently across docs
   pages. The *code* is MIT and independently reviewable, so this does not contaminate
   the repo — but do not link Vengeance UI from STYLELAB's own README or demo script.
   A recruiter following that link lands on token promotion.
2. No releases/tags published. Pin by **commit SHA**, never `main` — `main` can change
   under you between installs.

---

**Skiper UI** — `https://skiper-ui.com`.

- Registry live at `https://skiper-ui.com/r/{name}.json`; verified — `skiper40` resolves
  to valid `registry-item` JSON (dependency: framer-motion).
- `npx shadcn add @skiper-ui/skiper40`. Drops source; no runtime package.
- Prereqs: framer-motion, tailwindcss, react, clsx, lucide-react, react-use-measure, gsap.

Conditions, all three load-bearing:
1. **No public source repository exists.** The site's only GitHub link is a personal
   profile (`Gurvinder-Singh02`); the `SkiperUI/skiper-ui` repo that third-party lists
   cite returns 404. Consequences: source cannot be audited before install, there is no
   issue tracker, and there is nothing to pin. **Vendor every component into the repo
   and treat it as our code from that moment.** Read each file before committing it.
2. **Free tier requires attribution to Skiper UI.** Add it to the app's colophon/footer.
   Do not buy Pro to remove it — a paid licence key validated on every install
   (`SKIPER_LICENSE_KEY`) is a network+payment dependency a portfolio project must not have.
3. The author states plainly: *"Most components here are recreations of the best out
   there. I don't claim to be the original creator."* Prefer Vengeance UI where both
   offer a usable pattern; reach for Skiper UI only where it is clearly better.

---

**"Animaster" — rejected.** No npm package, no GitHub repository, no documentation site.
It surfaces only as "Animaster Lib" / "AnimMaster" in Instagram, Facebook and YouTube
promo content. It cannot clear the verification gate in `docs/UX-UI-SPEC.md`.

Worth recording: **Skiper UI, Vengeance UI and Animaster Lib appear together as a trio
in those same social posts.** The spec's library list most likely came from a promo reel
rather than independent evaluation — which is why this gate existed. `animista.net` is a
real, free CSS-animation generator with a similar name, but it emits CSS keyframes, not
React components, so it is not a substitute. Do not adopt it as one.

Follow-up:
1. `docs/UX-UI-SPEC.md` updated in the same commit; "Animaster" removed.
2. **The mitigation that makes both acceptable:** these are source-drop registries, not
   runtime dependencies. After `shadcn add`, the component is a file in our repo with
   zero vendor coupling. Wrap each one behind `components/motion/*` per UX-UI-SPEC so
   the app stays replaceable, and record the upstream name + SHA in a header comment.
3. Re-check both before S11 (harden + deploy). Neither has a stability guarantee.

---

### 2026-09-12 — Wardrobe pivot: user-uploaded closet replaces the seeded catalogue

Context:
The build was blocked on two asset problems: B1 (~60 fictional garments with imagery and
commerce metadata) and B2 (~14 pre-generated try-on assets). Both were asset work Claude
Code could not do, and the demo was worthless without them.

Decision:
Replace the seeded commerce catalogue with a user-uploaded personal wardrobe.

```text
USER-UPLOADED WARDROBE → IMAGE ANALYSIS → STRUCTURED GARMENT METADATA
→ PERSONAL WARDROBE → AI OUTFIT RECOMMENDATION → SAVE / EDIT / SWAP / REGENERATE
```

The product should feel like: **STYLELAB understands YOUR closet.**

Three sub-decisions taken with it:

1. **No demo wardrobe.** Every user, recruiter included, uploads their own garments.
   B1 and B2 are closed outright; the project ships zero garment assets.
2. **Commerce removed entirely.** No prices, no merchant URLs, no add-to-bag. The
   `garments` table loses `brand`, `price`, `commerce_url`, `active`.
3. **No rendering.** The result is a composed look laid out from the user's own garment
   photographs. The VTO provider and its adapter are gone.

Alternatives considered and rejected:
- a pre-built demo closet (~15 items) preserving the 90-second credential-free path
- "shop the gap" commerce retained as P1
- mock VTO retained to preserve the provider-adapter story

Why:
It removes the only blockers Claude Code could not clear, it gives `GROQ_VISION_MODEL` a
genuine central role rather than a decorative one, and "styles what you already own" is a
sharper product than "helps you buy more clothes".

Trade-offs — all three are real and accepted:

- **Cold start is now the product's largest risk.** With no demo wardrobe, a first-time
  user sees nothing until they upload. The plan's hardest success criterion — "a stranger
  reaches a generated look in under 90 seconds with zero credentials" — now depends on a
  live upload succeeding in front of an interviewer. Mitigation: `docs/DEMO-SCRIPT.md`
  carries a per-beat timing budget and requires the presenter to stage their own garment
  photos in advance. The demo is the presenter's real closet.
- **The provider-adapter story moves rather than disappears.** It now lives on
  `WardrobeAnalyzer`, which is exercised on every single session instead of only in the
  try-on path. Arguably a stronger demonstration.
- **Grounding gets harder, and better.** "Never invent a SKU" becomes "never reference an
  item this user does not own" — which is also a security boundary. Cross-user isolation
  (`AI-EVAL-CASES.md` Case 11) replaces price integrity as the headline eval case.

Follow-up:
1. Demo mode must complete with `GROQ_API_KEY` unset and no seeded data. Resolved by
   `DeterministicWardrobeAnalyzer`, which measures colour and image quality from actual
   pixels and takes category from the user's upload hint, leaving everything else null at
   confidence 0. Nothing is fabricated, so the credential-free demo makes no claim the
   code cannot support. Specified in `docs/AI-SYSTEM.md`.
2. Ownership is enforced in SQL before the prompt and re-validated after, with a composite
   foreign key making cross-user references unrepresentable at the schema level.
3. Specs updated in the same commit: PRD, USER-FLOWS, DATA-MODEL, AI-SYSTEM,
   AI-EVAL-CASES, ARCHITECTURE, API-SPEC, ANALYTICS, SECURITY-PRIVACY, TESTING,
   QA-RELEASE, DEMO-SCRIPT, UX-UI-SPEC, DESIGN-PROMPT-SYSTEM, DEPLOYMENT, OBSERVABILITY,
   DEVELOPMENT-PLAN, README, AGENTS, CLAUDE.md, and prompts 03/04/05/06/07/08/10/11/12.
4. Privacy scope grew: closet photographs are taken indoors and carry incidental
   background. EXIF including GPS is stripped on ingest; see `docs/SECURITY-PRIVACY.md`.

---

### 2026-09-12 — Demo mode removed; the product always runs real AI

Context:
The kit treated demo mode as load-bearing: a credential-free path with seeded results, so
a recruiter could see the product with no key. The wardrobe pivot already removed seeded
data. The remaining question was whether a fake-inference path should exist at all.

Decision:
**No demo product mode.** `APP_MODE` is gone. The application requires `GROQ_API_KEY` and
always performs real inference. There is no deterministic analyzer serving users, no
seeded result, and no "demo data" label anywhere in the product.

**Test doubles are retained** — and are not demo mode. `tests/ai/` and CI run against
recorded fixtures and stub adapters, exactly as they would for any external dependency.

Why the distinction matters:
Making the eval suite require a live key would make the project's central proof — the
grounding and cross-user-isolation regression tests — slow, paid, non-deterministic, and
unrunnable on fork pull requests. A regression suite that costs money per run stops being
run. The doubles exist so the tests stay honest, not so the product can fake an answer.

CI shape:
- `ai-eval` and unit/integration jobs — stub adapters, no key, run on every PR
- `live-smoke` — real key from repository secrets, `main` only, a handful of calls that
  assert the live models still answer and still satisfy the schema

Trade-offs:
- No key, no product. A reviewer who clones the repo cannot run it without their own Groq
  key. Accepted: the demo is presenter-driven with a key in hand.
- Every demo now costs tokens and depends on Groq being up. Rehearse against the live
  path, not a mock, and have the model-availability boot check visible.
- `README` must state the key requirement prominently, or the repo looks broken to a
  reviewer who tries `pnpm dev` and sees a boot failure.

---

### 2026-09-12 — Multi-agent advisory layer (CrewAI behind an adapter)

Context:
The product should not just name an outfit; it should reason — trend awareness, pro tips,
alternatives, budget tricks, and a genuine second opinion.

Decision:
A crew of specialist agents on `openai/gpt-oss-120b` via Groq, orchestrated by **CrewAI**,
behind an `OutfitAdvisor` interface. See `docs/AGENT-SYSTEM.md` for roles and dataflow.

Why CrewAI over AutoGen:
The work is a fixed pipeline of distinct expert roles producing one merged artifact, which
is CrewAI's role/task model almost exactly. AutoGen's strength is open-ended conversational
delegation, which this does not need and which makes latency and cost unbounded.

Why behind an adapter:
`CLAUDE.md` forbids coupling domain code to vendor SDKs, and both frameworks churn fast.
The domain calls `OutfitAdvisor`; swapping CrewAI for AutoGen, or for plain orchestrated
calls, must be a one-file change. `git grep -i "crewai"` outside `adapters/` returns nothing.

Trade-offs — stated plainly:
- **Latency.** Naive sequential agents would take 30-60s. The DAG in `AGENT-SYSTEM.md`
  parallelises to ~4 sequential hops. Groq's speed is what makes this viable at all; on a
  slower provider this design would not ship. Budget is 8s p50, 15s p95, inside the
  existing async job with per-agent progress stages.
- **Cost.** Roughly 4-6x a single ranking call. Cap agent count, cap output tokens, and
  cache the style profile — it changes far more slowly than the outfit request.
- **Theatre risk.** An agent that only rephrases another agent's output is decoration.
  Each role must be independently ablatable, and `AGENT-SYSTEM.md` requires an ablation
  test proving each one changes the result.

Every agent's output is untrusted. Ownership validation runs on the final merged response
regardless of what any agent asserted, exactly as before.

---

### 2026-09-12 — Trend awareness must be sourced and dated, never recalled

Context:
"Current fashion sense" is a hallucination magnet. Asking an LLM what is trending returns
confident output drawn from a training cutoff, with no source and no date.

Decision:
Trend input comes from a `TrendSource` adapter, never from model recall.

- Default: a curated, dated, human-reviewed trend corpus committed to `data/trends/`,
  each entry carrying `source`, `published_at`, and `region`.
- Optional: a live web-search adapter for refresh.

Hard rules:
1. A trend may only **re-rank or contextualise items the user already owns.** It may never
   introduce a garment, and the ownership validator does not care where a suggestion came from.
2. Every trend claim surfaced to the user carries its source and date. If it cannot be
   attributed, it is not shown.
3. Trend text retrieved from the web is untrusted content — subject to the same injection
   rules as text found inside an uploaded image (`AI-EVAL-CASES.md` Case 07).
4. A stale corpus degrades gracefully: say "trend data from March 2026" rather than
   implying currency the data does not have.

Why:
An unsourced trend claim is exactly the gimmick the whole eval layer exists to prevent.
A dated, cited trend layer is a stronger interview artifact than a confident unsourced one.

---

### 2026-09-12 — Advisory output stays commerce-free

Context:
"Budget friendly tricks" could mean purchase advice, which would reintroduce the commerce
scope removed earlier the same day.

Decision:
Budget value comes from maximising what the user owns: layering, cuffing, tucking,
re-wear combinations, proportion tricks, care and longevity.

Wardrobe gaps may be named, but **generically only** — "a white leather sneaker would
unlock five more outfits". No brand, no price, no merchant, no link. This is the existing
`missing_roles` concept made useful, not commerce returning by the back door.

---

### 2026-09-12 — S0 assumptions (recon + plan)

Context:
Prompt 00 instructs the agent to make reasonable assumptions and record them rather than
ask. Recorded here; `docs/PLAN.md` has the full gap analysis.

Decision:
1. **Build from zero.** Recon found no source files at all, so working rule 2 ("adapt
   rather than restart") does not apply. Nothing is being migrated.
2. **Repo layout exactly as `CLAUDE.md` specifies** — `apps/web`, `apps/api`, `packages/`,
   `data/`, `tests/ai/`. No third app. `tests/ai/` stays at the repo root; it is the
   cross-cutting proof layer and must not be folded into either app.
3. **Python pinned to 3.12**, matching CI. Local is 3.11.9, which would otherwise produce
   "works locally, fails in CI". To be applied in S1.
4. **`apps/web/package.json` is created first in S1.** `.claude/hooks/gate.sh` exits 0
   while that file is absent, so the phase gate is currently inert — a session could end
   with a broken tree reporting success. Creating it early switches the gate on.
5. **Prompt 00 patched**, not merely overridden. It predated four decisions and would have
   instructed a future session to build a demo mode, hunt for a nonexistent library, and
   protect a "visualize" hero moment that no longer exists. Five contradictions listed in
   `docs/PLAN.md` §3.

Trade-offs:
Pinning Python to 3.12 means installing it locally before S1's API work. The alternative —
dropping CI to 3.11 — trades a one-time install for permanent drift against the deployment
target, which is the worse deal.

Follow-up:
`.env.example` carries an uncommitted change that S0 could not inspect: the permission
rule `Read(./.env.*)` in `.claude/settings.json` matches `.env.example` as well as `.env`.
The deny was respected rather than circumvented. Because `.env.example` is tracked and not
gitignored, a key pasted there would be committed. Verify by hand. If the rule proves too
broad in daily use, narrow it to `Read(./.env)` and `Read(./.env.local)` — do not remove it.
