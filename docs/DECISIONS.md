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

---

### 2026-09-12 — Python pinned to 3.11, reversing the S0 assumption

Context:
S0 assumed the fix for the local-vs-CI drift was to install Python 3.12 locally and match
CI. S1 checked what is actually installed: only Python 3.11 (Microsoft Store build).
3.12 is absent.

Decision:
**Pin Python 3.11 everywhere.** CI dropped from 3.12 to 3.11 to match the development
machine.

Why the reversal:
Installing 3.12 is a system-level change to the user's machine, not a repo change, and it
is not mine to make unilaterally. More to the point, nothing in this project needs 3.12 —
FastAPI, Pydantic v2 and SQLAlchemy 2.x all fully support 3.11, which has security support
into late 2027. The drift was the problem, not the version number; matching the real
environment removes it at zero cost.

Trade-offs:
The deployment target must also run 3.11. Record it in the container/runtime config when
S11 sets deployment up, or the drift returns at the last possible moment.

Supersedes: assumption 3 in the S0 entry above, and `docs/PLAN.md` §5.3.

---

### 2026-09-12 — S2 landing: two spec substitutions and a motion rewrite

Context:
`docs/UX-UI-SPEC.md` section 1 predates the wardrobe pivot and the demo-mode removal, so two
of its landing elements could not be built as written.

Decisions:

1. **Secondary CTA "Explore demo" → "See how it works".** There is no demo mode and no demo
   wardrobe, so there is nothing to explore without uploading. An "Explore demo" button would
   be a promise the product cannot keep. The secondary action scrolls to the explanation.

2. **"Sample looks" section → "Anatomy of a read" (`ExtractionAnatomy`).** Sample looks need
   garment photography and the project ships zero garment assets by decision (B1/B2 closed).
   Fabricating a closet on the landing page would contradict the grounding rule the product
   rests on. The replacement shows the actual differentiator — a low-confidence field beside
   the same field after user correction — built from the real Zod schema so it cannot drift
   from the live contract, and labelled as an interface illustration.

3. **No vendor UI component vendored yet.** UX-UI-SPEC says to use Vengeance UI and Skiper UI
   "selectively"; selectively includes "not yet". The landing needs one reveal primitive and
   a dialog, both of which are better served by ~60 lines of local code than by vendoring a
   file from a registry that has to be read line-by-line first. Revisit at S7, where a
   carousel or complex image interaction might genuinely earn it. No Skiper UI attribution is
   required in the colophon until one is actually used.

4. **Reveal motion rewritten from keyframes to transitions, with layered fallbacks.**
   This was a bug, not a preference. The first implementation hid content with `opacity: 0`
   and revealed it via a keyframe animation with `fill-mode: both`, gated on
   IntersectionObserver. Three separate failure modes were found, each leaving the page blank:
   - an animation with `both` fill holds its `from` state whenever it does not actually run
     (paused, throttled, screenshot capture, print stylesheet);
   - an instant scroll or anchor jump moves past elements without them ever intersecting;
   - **IntersectionObserver is throttled to the point of never firing at all in an occluded
     window** — verified directly: a freshly-created observer's callback never ran.

   The rule adopted: **every failure mode must land on "visible".** Visibility now lives in
   CSS keyed off `data-revealed`, driven by a transition (which degrades to the final state
   rather than the initial one), with three independent triggers — IntersectionObserver, a
   scroll/resize position check, and a 2.5s safety timer — plus two static escapes needing no
   JS at all: reduced-motion renders visible immediately, and a `<noscript>` rule forces every
   reveal visible. `AI-EVAL-CASES`-style regression: an e2e test deletes
   `window.IntersectionObserver` outright and asserts the page still renders.

5. **`tailwind-merge` added.** `cn()` was a 6-line joiner with a comment saying conflict
   resolution could wait until genuinely needed. It was needed: `Button`'s base sets
   `inline-flex`, the navbar passed `hidden sm:inline-flex`, and the winner is decided by
   Tailwind's stylesheet order rather than attribute order — so the desktop CTA rendered at
   375px and caused horizontal overflow. Found by the overflow test, not by review.

6. **Fluid display type via `clamp()`.** `4.25rem` made "Recomposed." 500px wide, overflowing
   a 375px viewport. `clamp(2.5rem, 10.5vw, 5.5rem)` scales instead of clipping and removed
   the breakpoint step entirely.

7. **Font variables moved from `<body>` to `<html>`.** Tailwind 4 hoists `@theme` tokens to
   `:root`, so `--font-sans: var(--font-geist-sans), ...` was substituted in `:root`'s context
   where `--font-geist-sans` did not exist — the token computed to an empty string and every
   element silently fell back to the UA font stack. Geist was not applying anywhere.

---

### 2026-09-12 — S3: phase-ordering conflict in prompt 03, and how the flow was proven

Context:
`prompts/03-COMPOSER.md` acceptance says "upload → analysis → review → compose completes
against live Groq". It cannot, in this phase: the Groq adapter is S5 and the wardrobe
endpoints are S6. The prompt order is still right — the UI should be built against the
contract before the server implements it — but that one criterion is unmeetable at S3.

Decision:
1. **That acceptance criterion is deferred to S6**, explicitly, rather than fudged. Every
   other S3 criterion is met and verified.
2. **No client-side analyzer was written.** It would have made the flow demonstrable today
   and it is exactly what `AI-EVAL-CASES` Case 25 exists to prevent — a stub the running app
   can reach. The prompt's own wording ("component and E2E tests use stub adapters, but the
   running app never reaches them") is the rule that was followed.
3. **The flow is proven by e2e route interception instead.** Playwright stubs the HTTP layer
   and drives the real components: two photos become two independently-resolving cards, a
   refused photo costs one card, a low-confidence field is hedged and then settled by a
   correction. When S6 lands, those stubs document the contract the endpoints must satisfy.
4. **Error states were built in this phase, not deferred.** Clicking upload today hits a
   404 and surfaces the real failure copy, per-card. Building the unhappy paths alongside
   the happy one is cheaper than retrofitting them after the happy path exists.

Trade-off:
The wardrobe screen is not walkable by hand until S6. Accepted — the alternative was a
product-reachable stub, which is a worse thing to own.

---

### 2026-09-12 — Polling controllers are per job, not per effect run

A bug worth recording because the shape recurs.

`useAnalysisPolling` first used one `AbortController` for every poller started in an effect
run and aborted it in the effect's cleanup. `uploads` is a dependency and every
`updateUpload` mutates it, so the effect re-ran each time a photo resolved — and the cleanup
aborted all the *other* in-flight pollers. Combined with the guard that stops a job being
polled twice, a batch of eight photos produced exactly **one** card.

Fixed with one controller per job, aborted only on unmount. Found by the e2e assertion that
two photos produce two cards, not by review — the single-card result looks plausible enough
to miss.

General lesson, third instance this build: an effect whose dependency it also mutates will
re-run mid-flight. Anything long-lived started inside it must not be torn down by its own
cleanup.

---

### 2026-09-12 — Ownership is enforced by construction, not by discipline

Context:
prompts/04 requires that "every query filters on `user_id`; there is no unscoped read path,
not even for admin or debug". Written as a convention, that rule holds exactly as long as
everybody who adds a repository method remembers it.

Decision:
`app/repositories/wardrobe.py` builds **every** `select()` inside a `_scoped*` helper that
takes `user_id` and applies it. `tests/test_query_scoping.py` parses the package with `ast`
and fails if a `select()` appears anywhere else, if a `_scoped*` helper has a `where()` that
never mentions `user_id`, or if an owned row is loaded by primary key via `Session.get()`.

Alternatives:
Per-method tests asserting each read is scoped. Rejected: they pass today and say nothing
about the method added next month, which is when this actually breaks.

Why:
An unscoped read now has nowhere to live. `Session.get()` is called out separately because
it is the one bypass that looks like ordinary SQLAlchemy — it loads by primary key and
ignores the filter entirely.

Verified by mutation, not by assertion: deleting `.where(row.user_id == user_id)` from the
one builder turned **12 tests red** across four files. Reverted; suite back to 109 green.

---

### 2026-09-12 — Ownership re-validation issues no query

Context:
`docs/AI-SYSTEM.md` says an item id outside the retrieved set is "rejected, not fetched".
The tempting implementation asks the database whether the id exists for this user, so the
log can say whether it was a cross-user attempt.

Decision:
`validate_advice` compares only against `request.candidates`, in memory. No lookup, scoped
or otherwise. `UngroundedItemError` therefore carries the ids and the requesting user, and
**cannot** say who owns them.

Why:
Even a scoped existence check puts another user's id into a query. Keeping validation
query-free means the isolation property is assertable against the statements the engine
actually executed — `test_the_other_users_item_is_never_asked_for` reads the engine's
statement log and proves the id never appeared in one, which is stronger than proving it
was not returned. A filter applied in Python after an unscoped SELECT would pass the weaker
test and fail this one.

Consequence accepted: attributing a rejected id is the alerting layer's job, which has
legitimate admin scope outside the request path. The rejection itself is identical either
way, so nothing user-facing depends on the attribution.

Second mutation: replacing the ownership check with `ungrounded = []` turned 4 tests red,
including the forged-response case. Reverted.

---

### 2026-09-12 — Cross-user leakage is unrepresentable in the schema

Context:
`docs/DATA-MODEL.md` asks for composite foreign keys so that a cross-user `outfit_items`
row cannot be represented rather than merely being untested.

Decision:
`wardrobe_items` and `outfits` each carry `UNIQUE (id, user_id)` — redundant alone, since
`id` is already unique. `outfit_items` carries its own `user_id` and points at both parents
with composite foreign keys, so the database refuses a row whose outfit and garment belong
to different users. `app/db/session.py` sets `PRAGMA foreign_keys = ON` for SQLite, which
is off by default and would otherwise make every constraint here decoration.

Why:
Two independent defences on the one rule the product rests on: the repository checks
ownership before writing, and the schema refuses regardless. A bug in the layer above
becomes a failed insert instead of a leak.

Third mutation: weakening the `outfit_items` item foreign key to a single column turned the
constraint test red. Reverted.

---

### 2026-09-12 — DeterministicRanker deliberately does not implement OutfitAdvisor

Context:
The ranker is rung 4 of the fallback ladder. It takes the same input as an advisor and
returns the same type, so making it satisfy the `OutfitAdvisor` Protocol would be natural.

Decision:
It exposes `compose()`, not `advise()`, so `isinstance(DeterministicRanker(), OutfitAdvisor)`
is **False** and it cannot be injected where the real advisor goes. A test asserts this.

Why:
A fallback that is structurally substitutable for the product is one config line away from
becoming the product — which is demo mode returning through the back door (Case 25). Its
output also always carries `degradation_level` 4 or 5 and says so in the rationale: a
degraded answer that looks identical to a full one is the gimmick this project exists to
avoid.

---

### 2026-09-12 — The advisor writes the words; the system computes the number

Context:
An advisor returns a `match_score` alongside its rationale.

Decision:
`CompositionService._rescore` discards it and recomputes the score from the items via
`app/domain/scoring.py`. The name and rationale are kept as the advisor wrote them.

Why:
Two identical wardrobes must not show different Style Match figures because a model felt
differently on the day. Judgement is what the advisor is for; arithmetic is not. Style Match
remains a UX heuristic either way — `docs/PRD.md` — and `scoring.py` says so in its own
docstring rather than implying colour science.

---

### 2026-09-12 — Structured-output schemas are derived from the Pydantic models

Context:
Groq Structured Outputs needs a JSON Schema with `additionalProperties: false` and explicit
enums. The obvious approach is to write one next to the model.

Decision:
`app/domain/schemas.py` generates both schemas from `GarmentExtraction` and `OutfitAdvice`,
inlines `$defs`, and closes every nested object. Tests assert the property set matches the
model field set exactly.

Why:
Two hand-maintained copies of one contract drift, and the drift is silent — the symptom is
a field the provider is allowed to omit that the domain requires. Closing objects at every
depth rather than only the root matters because a nested object left open is precisely
where an unexpected field arrives.

Parsing lives in the domain rather than the Groq adapter so it is testable with no key, and
so the S8b agent crew validates against the same contract as the vision path.

---

### 2026-09-12 — Schema failure reasons name the field, never the value

Context:
A validation failure needs a reason that is useful in a log.

Decision:
`SchemaInvalidError.reason` names the field path and the rule it broke. It never echoes the
offending value, and a JSON parse failure reports line and column only.

Why:
Provider output is untrusted content, and text recovered from a photograph — a slogan, a
care label, a price tag — reaches us through exactly this path (Case 07). Echoing it into a
log is how injected text gets read by a human later. `docs/SECURITY-PRIVACY.md` already
forbids surfacing a raw provider message; this is the same rule applied to the log.

---

### 2026-09-12 — An unowned id in an outfit is fatal; in a trend note it is dropped

Context:
Both are references to an item outside the candidate set, so uniform treatment looks
tidier.

Decision:
An outfit slot naming an unowned id raises and the response is discarded. A trend note
whose `applies_to_items` names one is filtered out and the rest of the response is served.

Why:
The asymmetry tracks the harm. An outfit slot would put that garment on the user; a note is
context and cannot. Dropping rather than serving the note still matters, because a note
about an item the user does not own implies they do (Case 16). Hard-failing an entire
response over a discardable annotation would degrade answers for no safety gain.

---

### 2026-09-12 — No advisor call when a required role is empty

Context:
With three tops and no bottoms, the crew could still be asked and its answer rejected.

Decision:
`CompositionService.compose` checks `missing_roles` before building a request and returns
the gap statement directly. The advisor is never called; a test asserts `advisor.calls`
is empty.

Why:
Paying for a crew run to be told what a count already told us is waste. More importantly,
asking a model to style around a missing role is an invitation to fill it — the exact
failure Case 12 exists to prevent. Not asking is a stronger defence than rejecting.

---

### 2026-09-12 — tests/ai gets real content now, not in S8

Context:
The CI `ai-eval` job runs `pytest tests/ai -q`, and that directory held only a README. The
job has been red since S1.

Decision:
S4 lands `tests/ai/stubs.py` (the stub adapters prompts/04 asks for) and
`tests/ai/test_grounding.py` covering Cases 01, 11 and 12 — the cases the domain layer can
already answer in full. Its `conftest.py` puts `apps/api` on `sys.path` and deliberately
does **not** set `GROQ_API_KEY`; the suite is verified to pass with the variable unset.

Why:
The stubs needed a consumer in the directory they live in, otherwise `apps/api/tests` was
reaching across the repository by file path to use a module nothing local touched. And a
permanently-red CI job trains people to ignore CI.

Still red and honestly so: the second step of that job runs
`pytest tests/ai/test_ablation.py`, which is an S8b deliverable. Writing a placeholder
ablation test would be worse than leaving the step failing — the whole point of Case 21 is
that it must be able to fail.

---

### 2026-09-12 — Exception names carry the Error suffix

Context:
`SchemaInvalid`, `UngroundedItem` and `IncompatibleOutfit` read better without a suffix, but
ruff N818 is selected in `apps/api/pyproject.toml` and flagged all three.

Decision:
Renamed to `SchemaInvalidError`, `UngroundedItemError`, `IncompatibleOutfitError` rather
than adding `noqa`.

Why:
`DomainError` and `ConfigurationError` already follow the rule, so the family was
inconsistent either way. Suppressing a lint rule selected on purpose, to keep three names
slightly prettier, is how a ruleset stops meaning anything.

Noted for the record: `ruff format` is **not** part of the gate — CI runs `ruff check` only,
and `app/config.py` from S1 has never been format-clean. Reformatting was not adopted in S4
because it would reflow the deliberately column-aligned lookup tables in `scoring.py` into
sixty single-entry lines, which is worse to read for no correctness gain.

---

### 2026-09-12 — The mock replaces the transport, not the adapter

Context:
prompts/12 asks for a `MockGroqProvider` and sets the acceptance criterion "the domain layer
cannot tell whether it is using Groq or the mock adapter". The obvious reading is a second
`WardrobeAnalyzer` implementation.

Decision:
A narrow `ChatTransport` Protocol (`app/adapters/transport.py`) sits *below* the adapters:
one method for a schema-constrained completion, one for a model list. `MockGroqProvider`
implements that, so the real `GroqWardrobeAnalyzer` and `GroqOutfitAdvisor` run on top of it
with their real prompt construction, real parsing, real retry and real fallback logic.

Alternatives:
A mock adapter. Rejected — it would assert that a stub returns what the stub was told to
return. Every interesting behaviour in this phase (the fallback chain, the schema re-ask,
the error taxonomy) lives in the adapter, which a mock adapter replaces wholesale.

Why:
It also makes the acceptance criterion *true* rather than restated: both live adapters and
both test doubles satisfy the same Protocols because the substitution happens underneath
them. Only `groq_transport.py` imports the SDK, and the ast-based boundary test enforces it.

---

### 2026-09-12 — There is no code path from a confidence score to a model choice

Context:
`docs/AI-SYSTEM.md` and Case 24 forbid using the vision fallback for a low-confidence
extraction. Enforcing that with a rule means trusting every future editor to have read it.

Decision:
`GroqWardrobeAnalyzer` never reads `field_confidence`. The fallback chain is driven purely
by `ProviderError.use_fallback_model`, which is set on the exception type — timeout, rate
limit, deprecated model id — and never derived from a response body.

Why:
"We do not do X" is weaker than "there is nowhere to do X from". Writing the forbidden
behaviour is a deliberate edit to add a confidence lookup that does not otherwise exist,
rather than a plausible tweak to an existing branch.

Verified by mutation: adding that lookup — `if max(scores) < 0.7: continue` — turned
`test_a_low_confidence_extraction_never_triggers_the_fallback` red. Reverted.

This is the rule most likely to be broken by somebody trying to be helpful, which is why it
gets a mutation rather than just a test.

---

### 2026-09-12 — A schema failure retries; it does not change model

Context:
Two failure modes look similar from the call site: the provider could not answer, and the
model answered but ignored the output schema.

Decision:
The first moves down the availability chain. The second gets **one** re-ask on the same
model and then raises, leaving the caller to degrade to the deterministic ranker.

Why:
Changing model to fix a schema failure treats an instruction-following problem as an
availability problem. And a second re-ask is unlikely to help — Case 06 puts the
deterministic path below this, not a third attempt. `ProviderContractError` is a third,
separate case: a 200 with no choices means the model never answered, so sending it down the
re-ask path could not help either.

---

### 2026-09-12 — The adapter does not filter unowned ids, deliberately

Context:
`GroqOutfitAdvisor` holds the candidate list. Dropping any id the model invented would be
three lines and would look like good hygiene.

Decision:
It does not. It parses and schema-validates, and hands back whatever the model named.
`CompositionService` re-validates against the retrieved set afterwards.
`test_the_advisor_does_not_filter_an_unowned_id_itself` asserts the adapter lets it through.

Why:
An adapter that tidies up after the model hides how often the model needs tidying up after.
Concretely, the mutation that adds the filter makes the ownership rejection *disappear*:
`service.rejections` comes back empty, the CRITICAL log never fires, and the security event
becomes invisible while every test about the served output still passes. The helpful version
silently disables the audit.

Verified by mutation: adding the filter turned `test_the_advisor_does_not_filter_an_unowned_id_itself`
red in the unit suite **and** `test_case_11_a_cross_user_item_is_refused_through_the_real_adapter`
red in the proof layer. Reverted.

---

### 2026-09-12 — Provider error messages are ours, never the provider's

Context:
`str(error)` from an SDK exception is the most informative thing available at the boundary.

Decision:
`ProviderError.message` is written by `groq_transport._sanitised()` and names only the
exception type. The original is kept on `__cause__` for a debugger and never formatted into
the error. A JSON parse failure reports line and column, never the payload.

Why:
A provider message can quote the request, and the request contains text recovered from a
user's photograph — a slogan, a care label, a tag reading "ignore previous instructions"
(Case 07). Echoing that into a log is how injected text gets read by a human later.
`docs/SECURITY-PRIVACY.md` already forbids surfacing a raw provider message; this applies
the same rule to the log and to the audit trail.

---

### 2026-09-12 — A missing model is fatal at boot; an unreachable provider is not

Context:
`docs/AI-SYSTEM.md` says both model ids are "verified against Groq's model list at boot" and
that failures there should be loud. But the check has its own dependency, which can fail.

Decision:
Two outcomes, treated differently. A model id absent from the list raises
`ConfigurationError` and the app does not start. A list call that *fails* is logged at ERROR
and the app starts unverified, recording an empty `app.state.verified_models`.

Why:
`ConfigurationError` means we are configured wrong, which only a human can fix, and starting
up turns one deployment error into a stream of unexplained user-facing failures. A failed
list call may fix itself, and refusing to start on it means a provider blip during a rollout
takes down the parts of the service that never touch the provider.

A missing `GROQ_API_KEY` is unaffected and always fatal — it is caught earlier, by `Settings`
itself (Case 25).

---

### 2026-09-12 — `create_app(transport=...)` instead of a "skip the boot check" flag

Context:
The boot check calls the provider. The `client` test fixture originally used the module-level
`app`, whose lifespan built the real transport — so the suite made a live `models.list()`
call with the fake key on every run. It passed (the failure is tolerated by design) and took
ten seconds instead of four.

Decision:
`app/main.py` exposes `create_app(transport=None)`. Tests pass `MockGroqProvider`; production
gets the default. `app = create_app()` stays at module level so `uvicorn app.main:app` is
unchanged.

Alternatives:
A `verify_models_at_boot` setting defaulting to on. Rejected: a flag whose only purpose is
to switch off a safety check is a flag that eventually ships switched off.

Why:
The real `verify_models` now runs *in* the test suite, against a scripted model list, rather
than being skipped. And a unit suite that silently depends on the internet is a unit suite
that fails on a train.

---

### 2026-09-12 — Advisory sanitisation lands now, and exempts wardrobe gaps

Context:
`docs/ARCHITECTURE.md` section 6 step 8 is "drop unattributed trend notes and unsupportable
tips". S4 did the trend half and left the tips half outstanding. Case 22 forbids claims about
fibre content, durability, price, and the user's body.

Decision:
`app/domain/advisory.py` drops any tip, budget trick or rationale line making one of those
claims, and reports a reason per removal so the caller can log it. Claims are dropped whole,
never edited.

The fibre and durability rules **do not** apply to `wardrobe_gaps`. A gap names a kind of
garment that is absent, where the material word is how the category is named —
`docs/AI-EVAL-CASES.md` uses "a white leather sneaker" as its own example of a well-formed
gap, and `GAP_DESCRIPTIONS` offers "a simple leather belt". Neither launders a guess, because
there is no garment to have guessed about. Gaps are still checked for price, merchant, link
and body claims. A test asserts every built-in gap description passes its own filter — a
filter that rejected the product's own copy would be wrong about the spec it came from.

Rewriting rather than dropping was rejected: editing out "wool" leaves a sentence the model
never wrote, asserted with its authority, and nothing can check the edit preserved the
meaning.

Also recorded so nobody mistakes it for a security boundary: this is a word-list content
filter on presentational fields. It will miss a paraphrase, and the cost of a miss is a
hedged claim shown unhedged in cosmetic copy — not a wrong garment and not another user's
data. The rules that carry weight are enforced structurally, in SQL and in memory.

`shop` and `brand` are deliberately **not** in the commerce word list: "shop your own
wardrobe" is a legitimate budget trick and "brand new" is ordinary English, and the literal
word "brand" was never how a brand claim would arrive.

A test found a real hole while writing this: "pick one up at example.com" passed a
scheme-only URL check. The pattern now matches bare domains on a short TLD list, excluding
`.co` and `.in` as too ambiguous for prose.

---

### 2026-09-12 — The live suite skips without a key; the application never does

Context:
`tests/live/` makes real billed calls and CI runs it on `main` only, with the secret.

Decision:
`tests/live/conftest.py` skips the whole suite when `GROQ_API_KEY` is absent — or when it is
the fake `test-key…` value the unit suite sets. Two tests, five with the availability checks,
and nothing more.

Why:
A test that cannot run has not found a bug. This is the one place a missing key is not an
error, and it is worth being explicit that it is a *test* skipping and never the application
degrading: the app refuses to boot without a key (Case 25), asserted in `test_config.py`.

The suite is a canary for model deprecation, not a second test suite. Everything provable
with `MockGroqProvider` is proven there, free, on every push. `test_model_availability.py`
calls the same `verify_models` production calls at boot rather than a parallel
re-implementation — a canary that checks something slightly different from production is a
canary that can sing while production suffocates.

`data/samples/` holds the real photographs the extraction smoke test needs. Empty today, so
that test skips: a synthetic 1x1 pixel would only prove a model can describe a grey square.

---

### 2026-09-13 — S11: the application learns which environment it is in

Context:
Every default in `app/config.py` was chosen so a fresh clone runs, and each was right on its
own. `SESSION_SECRET` unset generates a per-process key. `DATABASE_URL` unset resolves to a
SQLite file in the working directory. `WEB_ORIGIN` defaults to `http://localhost:3000`. All
three are correct on a laptop, all three are broken in a container, and the application had
no way to tell the difference.

The failure mode is the expensive kind, because none of it looks like a crash: a deploy
silently logs every visitor out, or deletes every wardrobe, or fails CORS preflight in a way
that reads from outside exactly like the API being down.

Decision:
`APP_ENV`, defaulting to `local`. `app/preflight.py` checks the accommodations and, under
`production`, refuses to boot on the ones that make the application *incorrect* rather than
merely worse — reporting all of them in one message.

Locally it warns about exactly two: `SESSION_SECRET` and `EXA_API_KEY`, the two whose absence
changes what the application does right now. It says nothing about `WEB_ORIGIN`, which is
*correct* locally — a warning that fires when nothing is wrong is how a developer learns to
skim past preflight, including on the day it says something new.

Alternatives:
A `strict_config` flag defaulting to on. Rejected for the reason S6 rejected
`verify_models_at_boot`: a flag whose only purpose is to switch off a safety check is a flag
that eventually ships off. Deriving the environment from `DATABASE_URL` looking like
Postgres. Rejected — it makes the check's own trigger a thing somebody can get wrong, and a
staging environment on SQLite would be silently exempt.

Trade-offs:
One more environment variable in a deploy config, which is the one place somebody is already
setting environment variables. And a default of `local` means a misconfigured production
deployment that *forgot* `APP_ENV` gets no protection at all — accepted, because the reverse
default breaks every fresh clone on three settings nobody has heard of yet.

Follow-up:
`SESSION_SECRET` has a 32-character floor. A short secret is worse than an absent one:
absent is loud and generates 256 random bits, while `SESSION_SECRET=stylelab` is silent and
forges every session token and image capability in the system.

---

### 2026-09-13 — Rate limiting, because there is no authentication

Context:
`docs/SECURITY-PRIVACY.md` has asked for "rate limiting on upload and extraction
specifically" since S0 and nothing implemented it. What makes it urgent rather than tidy is
what sits beside it: there is no authentication (blocker B15). `POST /session` mints a token
for anyone who asks, and that token reaches `POST /wardrobe/items`, which calls a metered
vision model once per photograph.

So the exposure is not "someone floods the API". It is **someone drains the provider
budget**, without a credential, from a URL that is public by design. Every other protection
in this codebase is about one user reading another user's wardrobe; this is the first one
about the deployment surviving the afternoon.

Decision:
Token buckets (`app/services/ratelimit.py`) on the three operations that cost money: uploads
charged **per image**, compositions, and new sessions charged per client address.

Per image is the whole reason it is a bucket and not a counter. One POST carrying twelve
photographs is twelve provider calls, and a per-request limit would price them as one —
making the cheapest way to drain the key the same thing the documented primary flow does.

Alternatives:
A fixed window, which is easier and has a hole at the boundary: a client gets its whole
allowance at 11:59:59 and the whole of the next at 12:00:00, twice the intended burst at the
worst moment. Redis, which is correct and is a service this project does not have — the
interface takes a key and a cost, so it replaces the storage without touching a caller.

Trade-offs:
In-process, so the limit is **per instance** and two replicas allow twice as much. Recorded
in docs/DEPLOYMENT.md rather than hidden, because a limiter that is quietly per-instance is
one somebody will later size a deployment against.

Reads and corrections are deliberately unlimited. A limit there produces a product that
refuses to show somebody their own clothes, defending against an attacker who could have
requested the landing page just as cheaply.

Follow-up:
The session bucket keys on `request.client.host` and the API deliberately does not read
`X-Forwarded-For`. An unvalidated one is a limiter an attacker switches off by setting a
header — worse than none, because it looks like protection. Behind a proxy, uvicorn's
`--proxy-headers --forwarded-allow-ips` already knows which hops to trust, and this module
should not acquire a second opinion.

---

### 2026-09-13 — Deletion becomes true on disk (B16), and the copy that promised it changes

Context:
`deleted_at` stopped a photograph being served and left the bytes exactly where they were,
with nothing scheduled to remove them. The soft delete was a deliberate trade —
docs/DATA-MODEL.md wants deletion observable and reversible by support — and it was only
ever half a trade. "Delete my photographs" was a statement about a database column.

Meanwhile the landing page said **"Delete means delete"**, and underneath it, *"Remove one
garment or the whole wardrobe. We tell you which looks that breaks before you confirm."*
Three claims, and at the S11 audit none of them was quite true: deletion was soft, there was
no way to remove a whole wardrobe, and the affected looks were named *after* the removal.

Decision:
Build the missing half and rewrite the claim to match.

`app/services/retention.py` sweeps hourly and at boot, unlinking any asset whose thirty-day
window has closed and recording it in `assets.purged_at`. `DELETE /wardrobe/items` removes
the whole wardrobe in one request, with a two-tap confirmation in the interface that states
what deletion actually means. The privacy card now reads *"Delete removes it, then erases
it"* and names the thirty days.

Why the window is stated in three places — the landing copy, the confirmation, and the API
response — is that a retention period the product does not state is one the user has not
agreed to.

Alternatives:
Purging opportunistically when someone deletes something. Less code, and it answers the
wrong question: a user who deletes their wardrobe and never returns is exactly the user
whose photographs must go, and they are the one who never triggers it.

Making the affected looks a pre-check instead. Rejected as the wrong fix for the right
observation — the post-hoc message is fine *because* there is a window in which to change
your mind, and the copy was the thing that was wrong.

Trade-offs:
The sweep is in-process, like the job runner (B14). A deployment that scales to zero must run
it as a scheduled job, or deletion silently stops happening — said in docs/DEPLOYMENT.md.

Follow-up:
The sweep enumerates owners and asks the ownership-scoped repository once per owner, rather
than issuing the one obvious query. `select(AssetRow)` over every user is precisely the
unscoped read path `tests/test_query_scoping.py` exists to prevent, and a maintenance job is
exactly the "admin or debug" exception prompts/04 refuses to allow. Reading the set of
*owners* is not reading owned data. The extra queries are the price of the invariant.

---

### 2026-09-13 — Migrations (B12), and the failure that made them concrete

Context:
The schema existed wherever somebody had run `Base.metadata.create_all` — fine for tests and
a laptop, and it means a deployed database can never receive a change. B12 has been open
since S4 as an abstraction.

S11 made it concrete by accident. Adding `assets.purged_at` for the retention sweep, the
local database — created by `create_all` months of sessions ago — kept working until a query
touched the column, at which point **every upload failed** and the user-facing message was
*"Something went wrong on our side."* The correct message for an unclassified error, and a
useless one for a problem with a one-line fix.

`create_all` creates missing **tables**. It has never created a missing **column**, and
nothing in the application knew the difference.

Decision:
Alembic, with `alembic upgrade head` as a deploy step and `create_all` reserved for local and
test. Plus `preflight.verify_schema`, which compares the live database to the models at boot
using Alembic's own comparison and refuses to serve if they differ.

`verify_schema` is fatal in *every* environment, which is stricter than the rest of preflight.
The justification is that there is no degraded mode: a schema the queries do not match means
every request fails anyway, so the only question is whether the operator learns it from a
boot message naming the fix or from a stream of 500s that does not.

Alternatives:
Replaying the eight phases of schema history as revisions. Archaeology for an audience of
nobody — no deployed database exists whose history it would need to match. The initial
revision is a baseline.

Trade-offs:
A database created by `create_all` before this exists is not upgradeable by it, and stamping
it would claim a schema it does not have. Documented in docs/DEPLOYMENT.md with both fixes.

Follow-up:
`tests/test_migrations.py` asserts a migrated database and a `create_all` database are
indistinguishable — the same comparison `--autogenerate` makes, run as a test. That is the
part that keeps B12 closed, because the real failure mode is not "nobody wrote a migration",
it is somebody adding a column, watching every test pass, and shipping.

It also found a bug on the day it was written. Alembic's generated `env.py` calls
`logging.config.fileConfig` with its default, `disable_existing_loggers=True`, which disables
every logger not named in `alembic.ini` — every `stylelab.*` logger there is. It surfaced as
two unrelated logging tests going red, which is the lucky way to find it. The unlucky way is
a deployment that runs a migration in-process before serving and then never logs again.

---

### 2026-09-13 — A timeout is not a breach

Context:
The latency circuit breaker trips after exceeding p95 twice in a row, and "consecutive" was
carefully chosen: one slow compose is a slow compose, and a breaker that trips on a single
one makes the product visibly shallower for no reason a user can see.

Composing in a browser during the S11 audit showed what that rule does when the advisor does
not merely run late but is **cancelled**. The full crew exceeded 15s, the composition fell to
the deterministic ranker (rung 4), and the breaker recorded one breach. So the next compose
would spend the whole budget again and fall to the ranker again before the reduced crew
(rung 3) was ever reached — thirty seconds of a user's time to arrive at a rung the first
timeout was already sufficient evidence for.

Decision:
`LatencyCircuit.trip()`. A timeout opens the breaker on its own; ordinary slowness still
needs two in a row.

Why:
They are different events. A breach is a measurement — the advisor answered, and took too
long. A timeout is a failure to answer at all: the call was cancelled at the budget and the
whole of it bought nothing. Treating the stronger evidence as if it were the weaker made the
middle rung of the ladder unreachable in exactly the conditions it exists for.

Trade-offs:
None found. Recovery is unchanged — one run inside budget closes the breaker whichever way
it opened — so a single provider hiccup still costs one reduced composition rather than a
timer somebody guessed at.

---

### 2026-09-13 — No LangSmith or Arize, still; and no hosted object store

Context:
S8b recorded the reasoning for not wiring a vendor tracing backend: what exists instead is
the data such a backend consumes — structured events, computed rollups, one sink interface —
and shipping unverified integration config against a service this project has no account
with would be the same move as a stubbed ablation test.

S11 is the deploy phase, so the question came back, and with it a second one: `ObjectStore`
has had a `SupabaseObjectStore` named in its docstring as "S11" since S4.

Decision:
Neither. The reasoning is the same one and it has not weakened: an integration nobody can
run is not an integration, and calling the product "observable" or "hosted" on the strength
of config that has never executed is the claim this project exists not to make.

Trade-offs:
A deployment must mount a volume for `STORAGE_ROOT` or lose every photograph on the next
deploy. Preflight warns rather than refusing — refusing would mean no deployment could start
at all — and blocker **B20** carries it as an open item rather than a solved one.

---

### 2026-09-12 — Groq SDK over the OpenAI-compatible endpoint

Context:
prompts/12 allows "the official Groq SDK or its documented OpenAI-compatible interface".

Decision:
The official SDK, `groq>=0.30`, confined to `app/adapters/groq_transport.py`.

Why:
It carries a typed exception hierarchy — `RateLimitError`, `NotFoundError`,
`APITimeoutError`, `AuthenticationError` — and the error taxonomy in this phase is built on
telling those apart. Reimplementing that mapping over raw HTTP status codes would be work
with no upside, and the boundary test already guarantees the SDK cannot leak past one file.

A floor rather than a pin: Groq ships often and the surface used here
(`chat.completions.create`, `models.list`, the exception types) is stable. Structured Outputs
is supported as `response_format={"type": "json_schema", …}` with a `strict` flag, which is
what `SchemaSpec` maps onto.

---

### 2026-09-12 — The two greps in CLAUDE.md were never true; the ast test is

Context:
`CLAUDE.md` and `app/adapters/__init__.py` both stated the adapter boundary as two greps
coming back empty outside `adapters/`: `git grep -i groq` and `git grep -i crewai`. S5 was
the first phase where enough Groq code existed to check, and they do not come back empty.

What actually matches, all of it harmless:
- `app/config.py` — `groq_api_key`, `groq_text_model`, `agent_framework: Literal["crewai"]`.
  Those field names map to `GROQ_*` environment variables and cannot be renamed. CLAUDE.md
  itself designates this file as the sanctioned home for model ids.
- `app/domain/schemas.py`, `app/main.py` — docstring prose, and settings *attribute* reads
  for startup logging.

Decision:
Correct the claim in both places rather than contort the code to satisfy it, and add the
narrower rule that is worth enforcing: **no model id literal outside `app/config.py`**,
checked over string constants with `ast`. Matched on vendor prefixes rather than a list of
ids, because a test naming `qwen/qwen3.8-27b` would itself become a third place a model id
lives.

Why:
A rule stated as a command that does not produce the stated result is worse than no rule —
the first person to run it concludes the boundary is broken, or concludes the rule is
decorative. The three things the greps were reaching for are all checkable precisely, and
now are: no vendor import or symbol outside `adapters/`, no model id literal outside the
config, and `domain/` never importing `adapters/`.

The literal rule matters on its own terms: a model id baked into a route handler or a prompt
survives a config change and outlives the deprecation notice.

Verified by mutation: adding `MUTATED_DEFAULT = "qwen/qwen3.8-27b"` to `groq_vision.py`
turned the new test red. Reverted. A companion test asserts the ids *are* still in
`Settings`, so the first cannot pass vacuously by the ids moving somewhere untested.

---

### 2026-09-12 — Removed a contradictory blocker row from the ledger

`docs/PROGRESS.md` listed B10 twice: closed on the user's 2026-09-12 confirmation that they
had checked `.env` and `.env.example` by hand, and still open from S2. A source of truth that
contradicts itself is not one, so the stale open row is gone and the closure records that a
duplicate existed.

The underlying constraint is unchanged: the project's own `Read(./.env.*)` deny rule still
applies, those files remain uninspectable from here, and they are staged explicitly rather
than by `git add -A`.

---

# S6 — Upload + async analysis pipeline (2026-09-12)

## The live suite found two bugs a mock could not

The first real run of `tests/live` against a provisioned key failed three ways. One was a
test that was wrong. Two were product bugs that had been green in every offline suite since
S5, and both were invisible for the same structural reason: **`MockGroqProvider` returns
scripted content and never validates the schema it was handed.** The transport seam is still
the right design — it is what makes the real prompt, parser, retry and fallback testable for
free — but it cannot check the one thing only the provider can.

**1. Strict Structured Outputs requires every property in `required`.** Our schemas derive
`required` from Pydantic, and every field of `GarmentExtraction` has a default, so `required`
was absent entirely. Groq answered 400 naming all thirteen properties. Fixed by
`_require_all_properties`, which lists every property of every object at every depth;
optionality is carried by the nullable type Pydantic already emits. Strict mode cannot
express an optional key, so this is not a workaround — it is the contract.

**2. `field_confidence` was specified as an object permitted to hold nothing.** This is the
more serious of the two. `dict[str, float]` is the right domain type and an impossible
strict schema: strict mode needs `additionalProperties: false` on every object, and a
free-form map closed that way admits no keys at all. So the provider was being instructed,
in a schema it obeys, that per-field confidence must be **empty** — and per-field confidence
is the honesty signal the entire extraction screen is built on. Every offline test passed
because the fixtures supplied scores the model was forbidden from sending.

Fixed by enumerating the keys. Which keys is itself a decision: **exactly the fields the
user can correct** (`CORRECTABLE_FIELDS`). One list, one meaning — we can say we are unsure
about precisely the things you can settle. A hedge on a field with no correction path is a
dead end; a correctable field with no confidence never gets hedged and so never prompts.
Scores are nullable, because a model that did not assess a field should say so rather than
invent a number, and `null` is translated to the key's absence at the boundary.

Both now have regression tests asserted structurally rather than by re-listing the fields —
a `required` array written out in a test would be a third copy of the contract, which is the
problem the derivation exists to solve.

**The lesson recorded, not just the fix:** the offline suite proves our logic, and only a
live call proves the provider agrees. `tests/live` is not redundant with `tests/ai`; it
covers the class of failure where our JSON Schema is valid and the provider refuses it. It
paid for itself on its first run.

## A reasoning model with a small token ceiling returns nothing, not less

`openai/gpt-oss-120b` spends its budget thinking before it emits output, so
`max_completion_tokens=32` produces an **empty** message with `finish_reason="length"` — not
a short answer. The live connectivity canary had asked for 32 since S5 and was failing for a
reason with nothing to do with connectivity.

Two changes. `_to_result` now names that case instead of reporting a generic "empty
message", because the generic version sent this session looking for a schema problem when
the configured ceiling was the whole story. And `groq_vision_max_tokens` is now set
explicitly rather than left to a provider default: on these models a ceiling is a
**correctness** setting, not only a cost one.

## Identity: a signed bearer token, and why not a header

Every wardrobe route needs a `user_id`, and where it comes from decides whether the
ownership boundary is real. An `X-User-Id` header would have been three lines and would have
handed every wardrobe to anyone who could type somebody else's id — and would have made
every ownership test in S4 vacuous, since a scoped query is worth nothing if the requester
picks the scope.

So `POST /session` mints an HMAC-signed token and the server reads the subject out of its
own signature. A caller can hold a token or not; it cannot choose what is inside one. This
is **not** authentication (B15) — it is an identity seam of the right shape, and Supabase
auth in S11 replaces the minting and nothing else.

A bearer header rather than a cookie because the browser calls this API cross-origin in
development, and a cookie that works there needs `SameSite=None; Secure`, which needs HTTPS,
which a local run does not have. Same forgery resistance, no coupling to the deployment.

### The signing key may be generated at startup

`SESSION_SECRET` unset means a random per-process key, logged at WARNING. The safe
direction: nothing can be forged, and the only cost is that tokens stop verifying after a
restart. A hardcoded fallback would make every deployment forgeable by anyone who read the
file; refusing to boot would make a fresh clone unusable for a reason unrelated to the
product.

It is not the silent fallback this project forbids elsewhere. That rule is about product
truth — never serving fabricated AI output (Case 25). Nothing here affects what the model
said or whose wardrobe was read; the degradation is session lifetime, and it is announced.

This has a demo consequence, found while verifying in the browser and now recorded against
B6: without the secret set, a pre-seeded demo wardrobe becomes unreachable the moment the
process restarts.

## Image references: `SignedUrlSource` renamed to `ImageReferenceSource`

S5 named the Protocol for the answer it assumed — a signed URL. S6 found the assumption
wrong in the case that matters most: a local deployment's storage is a private directory,
its API is on `localhost`, and Groq's servers can fetch neither. The only reference that
works there is an inlined `data:` URL, and S5's own live test had already been forced to
implement `signed_url` returning one.

Renamed for what it returns. `InlineImageSource` is the local implementation and also does
the downscaling, because the provider payload ceiling is a property of sending an image to a
provider — putting it here means no future caller has to remember. `SignedUrlImageSource`
exists and raises, so that inlining looks like the local choice rather than the only one.

## The browser's image URL puts its token in the path

docs/SECURITY-PRIVACY.md: signed URLs are "never logged, never sent to analytics, never
placed in a query string". Object stores conventionally use a query parameter, which would
have meant arguing with the spec about what the sentence meant.

It does not have to. `/assets/{asset_id}/{token}` satisfies the rule literally, works in an
`<img src>` cross-origin with no cookie, and needs no `SameSite` relaxation.

Two further decisions fell out of it:

* **The owner is inside the signed subject**, not just the asset. The route therefore still
  reads through the ownership-scoped query rather than loading an asset by primary key —
  without it, this would have been the one place in the application that loads an owned row
  with no `user_id`, which is exactly the bypass `test_query_scoping.py` forbids.
* **The purpose is signed into every token.** One key signs sessions and image
  capabilities; without the purpose, an image token — the one that travels in a URL and is
  therefore most likely to be obtained — would be a valid session token for its subject.

And the rule about logging is enforced at the logging layer (`app/logging_setup.py`) rather
than by asking callers to remember. Uvicorn's access log records the request line, the
request line is the path, and the path is a live credential; the wardrobe screen would have
written a working link to every photograph in the session into a log file. Verified against
the real access log, not only in a unit test.

## Where the retries are, and why there are not more

Prompt 05 asks for "error classification and bounded retry". Both exist and neither is in
the pipeline layer: transient provider failures are retried in the transport (three attempts,
jittered backoff) and schema failures are re-asked once by the analyzer. Adding a third
would multiply — three transport attempts inside two analyzer attempts inside two job
attempts is twelve calls for one photograph of a shirt, most of them into a rate limit that
is already refusing us.

What this layer adds instead is honest classification and a stop. The retry belongs to the
person looking at the card.

`retryable` answers "would doing this again plausibly work?", not "is the system unwell". A
timeout, yes. A model id that no longer resolves, no — that is a deployment problem, and a
spinning retry button is a lie about it.

## The checksum cache is scoped to one user, and that is the whole story

A re-uploaded photograph costs nothing: `upload` finds a live asset with the same checksum
and hands back the existing item with a job that is already `completed`, so the client's
existing poller resolves it on the first tick with no special case. A third upload status
meaning "already done" would have added a branch to every card in the UI to save one round
trip.

The per-user scope is not an optimisation detail. A global checksum index would be a
deduplication table across wardrobes: upload a photograph somebody else had uploaded and you
would be handed their asset, their extraction and their garment. Two users who own the same
jacket get two analyses, and that is the correct answer rather than waste.

The cache is also honest about its limits. The checksum is over normalised pixels, so it is
invariant to the container and to metadata — the same photograph off two phones is one image
— but **not** to lossy re-compression. A phone that re-encoded the picture on the way out
produced different pixels and gets a different checksum. Asserted as a test so nobody reads
the cache as content addressing.

## Image ingest: two ceilings, and orientation before stripping

The byte ceiling and the pixel ceiling catch different attacks and neither subsumes the
other: a flat 12000x12000 PNG compresses to a few hundred kilobytes and decodes to 144
megapixels, which no byte limit can see; a 200MB file is refused before it is decoded at all.
The format is sniffed from magic bytes, because the declared `Content-Type` is a claim by
the uploader.

**EXIF orientation is applied before the metadata is dropped.** A phone writes portrait
photographs as landscape pixels plus an orientation tag; strip the tag without rotating the
pixels and every portrait garment in the wardrobe lies on its side — including in the image
sent to the vision model, which then reports the shoulders of a shirt as its hem.

### What actually strips the metadata, corrected by a mutation

The code claimed `clean.info = {}` was the safeguard. A mutation run says otherwise: remove
the line and every metadata assertion still passes, because Pillow 11.3's savers write EXIF,
an ICC profile or a DPI only when handed one explicitly. **Re-encoding from decoded pixels
is the whole mechanism.** The line is kept as belt-and-braces because that has not always
been true of Pillow, but the comment claiming it was would have sent the next reader to the
wrong place.

The mutation the tests *do* catch is the realistic one: adding `exif=`/`icc_profile=` to
those `save()` calls to make stored photographs render more faithfully. That is a
reasonable-sounding change which puts a user's GPS coordinates back in the database, and it
turns four tests red — including the checksum-invariance test, because metadata leaking back
in also defeats the cache.

## Text read off a garment is bounded, and not by the adapter

Case 07 is usually read as a prompt problem. The prompt rules and the SQL scope are the first
two layers, and both were in place. The third layer is the one that survives them: even a
perfectly obedient model puts the words it read into the field it was asked to fill — a
slogan legitimately belongs in `pattern` or `style_tags` — so the wardrobe stores
attacker-influenced strings which are later interpolated into the **advice** prompt, where a
downstream model with no memory of their origin reads them.

`app/domain/hygiene.py` makes the channel too small to carry a payload and too plain to carry
markup: per-field length ceilings, bounded list lengths, no control characters. It does not
try to detect intent. Fields are truncated rather than dropped, because a truncated colour is
still the user's garment and still correctable.

Called by the pipeline and **deliberately not by the adapter** — same rule as
`GroqOutfitAdvisor` not filtering unowned ids. A check inside the adapter looks done and
leaves the seam that matters untested; the adapter's job is to report faithfully what the
model said.

## The audit trail had to be reachable from the failure path

docs/DATA-MODEL.md wants `item_extractions` written for rejections too. It was not possible:
`analyze_with_audit` returned its attempts, and a failing analysis raises and has no return
value. The rejected attempts — the rows carrying the raw text that would not parse, which are
the most useful rows in the table — were unreachable, and the code path that appended a
synthetic attempt with `raw_output=""` threw the real ones away.

Fixed with an `on_attempt` callback that fires as each attempt completes, and a `finally`
that persists whatever it collected. An audit trail reachable only through a successful
return is an audit trail of successes.

## Soft deletion, and the read that was not excluding it

`delete_with_cascade` marks the item, marks the asset, and sets every outfit referencing it
to `incomplete` — one call, because the three writes have to agree, and `incomplete` rather
than discarded because the user composed that look and deserves to be told which piece is
missing (Case 14).

Building the API read on S4's `_row` exposed that it did not filter `deleted_at`. A deleted
garment kept answering 200, `DELETE` was idempotent-by-accident, and a correction or a
re-analysis could have been applied to a garment the user had thrown away. Fixed in `_row`
rather than at each call site. "Reversible by support" is not "still present in the product".

What is still true: the bytes stay on disk (B16). The file stops being served and the rows
are marked, but nothing unlinks it yet, so "delete my photographs" is not fully true at the
filesystem level until the retention timer lands in S11.

## `DATABASE_URL=` with no value means "not configured"

`.env.example` ships the key blank and pydantic-settings faithfully reports that as `""`
rather than as absent. S4's rule — refuse to boot rather than fall back — turned a correctly
followed setup instruction into a boot failure telling the developer to configure the thing
they had just configured.

Blank now resolves to a file-backed SQLite database in the working directory, gitignored,
with the **dialect** logged at boot (never the URL — a Postgres URL carries a password). That
is not the fallback the rule refuses: the prohibition is on an *in-memory* database, which
vanishes on restart while looking like it worked. A named file does not.

## The web app renders the photograph with a plain `<img>`

`next/image` would route every wardrobe photograph through the Next server's optimiser,
which writes them to an on-disk cache outside the private store — a second, unsigned,
unexpiring copy of the most sensitive asset in the product, and one the deletion flow knows
nothing about. Incompatible with private storage and short-lived signed access. The lint rule
is silenced with that reason inline, and the bandwidth argument it makes does not apply:
ingest already downscales.

## Mutations run

| Mutation | Result |
|---|---|
| Keep the EXIF block when re-encoding | **missed** — the line is not load-bearing under Pillow 11.3; see above |
| Write the metadata back explicitly (`exif=`, `icc_profile=`) | caught, 4 tests |
| Skip applying EXIF orientation | caught, 1 test |
| Trust the declared MIME type instead of the bytes | caught, 1 test |
| Make the checksum cache global instead of per-user | caught, 1 test |
| Let a soft-deleted item keep answering reads | caught, 2 tests |
| Write the audit trail only when the analysis succeeded | caught, 3 tests across 2 files |
| Trust the asset id in the path rather than the signed one | caught, 1 test |
| Drop the image token's purpose check | caught, 1 test |

The missed one is recorded rather than quietly re-scoped. It is not a coverage hole: there
is no mutation of that line which changes the output, because the line has no effect on this
version of Pillow. The property it was supposed to protect is guarded by the output-byte
assertions, which the realistic mutation does turn red.

---

# S7 — Result + swap (2026-09-13)

## Composing is a job; swapping is not

Both could have been either. They went opposite ways for the same reason: what is actually
on the other side of the call.

Composing reaches a provider. Today that is one text call; in S8b it is a crew behind the
same Protocol, and slower. A route that blocked now would have to change then, and every
client written against it with it. So `POST /outfits/compose` answers 202 with a job, the
stages come from CLAUDE.md's motion vocabulary, and the client polls the same
`GET /jobs/{id}` the upload screen already uses.

Swapping reaches nothing. It is a scoped read, a pure recompute over six dimensions, and one
row rewritten. Routing it through a queue and a poller to do arithmetic would make the
signature interaction — one slot changes, the rest stay still — the slowest thing on the
screen. It is synchronous because it is fast, and it is fast because the model is not in the
loop. `tests/live/test_compose_pipeline.py` asserts a live swap completes in under two
seconds, which is a ceiling an accidental model call could not fit under.

## Three of the five composition stages are emitted, not five

CLAUDE.md names five: reading your wardrobe → matching silhouettes → balancing palette →
building look → ready. This rung emits the first, the fourth and the last, because that is
how many separable pieces of work it does — read the wardrobe, ask the advisor, done.

"Matching silhouettes" and "balancing palette" happen *inside* the single advisor call at
this rung. Emitting them anyway would have been two stage transitions firing microseconds
apart, which is a spinner with a caption on it — exactly what the motion rules forbid. When
the crew lands in S8b those become real transitions, because a Silhouette agent finishing is
an event. The vocabulary was designed for the destination; the honest thing is to use the
part of it that is true today.

## A swap rewrites the words as well as the picture

The rationale and the pro tips were written about a combination that no longer exists. A tip
about the trouser the user just swapped out is the visual state disagreeing with the wardrobe
state, in prose — the same failure as a stale image, harder to notice.

So a swap replaces the rationale with `app.domain.scoring.describe`, which describes the
*scoring* (something the system knows first-hand), drops the pro tips, budget tricks and
trend notes, and says so in a line the user can read. Wardrobe gaps survive: they describe
the wardrobe, not the combination.

The alternative — keep the advisor's prose and re-ask it after every swap — would have made
the fast interaction slow and would have spent a provider call on a change the user made
themselves.

## The outfit row stores the preferences it was composed against

`preference_match` is one of the six scoring dimensions and it needs the vibe, the fit and
the colours the user asked for. Without them a swap would rescore against an empty question,
silently neutralising a fifth of the score the moment a slot changed — the number on screen
would move for a reason the user could not see and we could not explain.

Three columns (`vibe`, `fit_preference`, `color_preferences`) rather than a join to
`style_profiles`, because the question this look was scored against is a property of the
look. A user who changes their preferences later has not changed what this outfit was for.

## Alternatives are scored in the look, not on their own

`GET /outfits/{id}/alternatives` scores each candidate *with the other pieces currently on
screen* and reports the resulting look score plus the delta. A shortlist ordered by solo
score would recommend the best shoe in the wardrobe rather than the best shoe with this
shirt, which is a different and much less useful question.

A negative delta is shown as readily as a positive one. The score is a heuristic; a swap the
user wants for reasons it cannot see is still theirs to make, and hiding the number would be
deciding for them.

## Empty is an answer, and it has three different shapes

* **No complete outfit possible** — `POST /outfits/compose` completes with no `result_id` and
  a named gap inline on the job. Not a failed job: a failure offers a retry, and retrying
  cannot conjure a pair of trousers.
* **No alternatives for a slot** — 200 with `alternatives: []` and a generic description of
  what would unlock it. A user who owns one pair of shoes has a small wardrobe, not a broken
  request.
* **A garment deleted from under a saved look** — the slot keeps its place with `item: null`,
  the outfit reports `incomplete`, and the swap affordance becomes the repair (Case 14).

None of the three substitutes anything. That is the one rule the product rests on.

## An incomplete look shows no Style Match and no styling notes

Caught while looking at the screen rather than the tests. A look whose garment had been
deleted still displayed "84" and a pro tip about cuffing the chino — the chino that was no
longer in it. Both are true statements about a combination that no longer exists, sitting
next to a banner explaining that it no longer exists.

The swap path already rewrites the narration server-side. A deletion cannot: there is nothing
to rescore, because a look with a hole in it has no score. So the result screen holds the
number back until the look is whole and says why. Wardrobe gaps stay, because they describe
the wardrobe rather than the combination.

The alternative — recompute a score over the surviving pieces — would put a number on
something the user cannot wear.

## Share copies text, and deliberately not a link

A link to the result screen would only work for the person who composed it: the images are
served against a signed, expiring capability naming one owner. A URL that silently fails for
everyone the user sends it to is a worse feature than no URL, and making it work would mean
publishing someone's private photographs.

So "Copy the look" puts the garments on the clipboard as text. A rendered share card with no
live image capability is the real answer and it lands with `flags.shareCards`.

## Regenerate is the compose endpoint again

No `POST /outfits/{id}/regenerate`. The button fires its own analytics event and re-runs
composition with the preferences the client already holds. A second endpoint would have been
a synonym for the first with a different name in the log — and docs/ANALYTICS.md wanted the
distinction in the event, which is where it now is.

## `CompositionService` can be handed its candidates

The nine-step orchestration reads the candidate set in step 1 and then awaits a provider.
Held inside a request-scoped repository, that means a database connection checked out for the
length of an HTTP call to Groq — the exact thing `ingest.py` is structured to avoid on the
extraction path.

`compose()` now accepts `candidates`, and the job runner retrieves them in one short unit of
work before the advisor call and persists in another after it. The retrieval is still the one
scoped query; what changed is who holds the session while the model thinks.
`tests/test_compose_service.py` measures the property rather than asserting it in a comment:
the advisor records how many sessions were open when it was called, and the answer is zero.

## The vision token ceiling stayed at 2048 — after lowering it and putting it back

Worth recording as a wrong turn, because the reasoning was plausible and the measurement
said otherwise.

The account's on-demand tier reports 1000 requests and 8000 **input** tokens per minute in
its rate-limit headers, and enforces a separate **output** ceiling of 1000 tokens per minute
per model that the headers do not mention. It refuses before the model runs:

```text
2048 ceiling -> Limit 1000, Requested 1579
1024 ceiling -> Limit 1000, Requested 1024
```

The obvious reading is that the configured ceiling is compared to the limit, so S6's 2048
could never be admitted and a smaller number would fix it. That reading is wrong. Ceilings of
960, 896 and 800 were refused just as readily once the window had been spent, and 2048 has
produced successful extractions all through S6 and S7 whenever the minute was free. The
refusal tracks the **remaining budget**, not the number we send.

What lowering it does do is take the model's thinking room away. At 768 the request is
admitted and comes back `json_validate_failed` with nothing generated — the same
reasoning-budget failure S6 found at a ceiling of 32, except now it arrives as a burned call
and a failed card instead of a retryable refusal. A ceiling that fails *after* admission is
strictly worse than one that is occasionally refused before it: the refusal is classified,
retryable, and costs nothing.

So the number stayed. A real extraction emits ~205 output tokens (823 characters, measured);
the rest of the budget is where the model reasons before writing any of them.

The real constraint is the tier (blocker B17), and it binds on **concurrency**: three
photographs uploaded in one gesture are three requests against one minute's budget. That is
the documented primary flow, and on this account some of those calls are refused.

## The live suite skips on capacity rather than failing

A rate limit is not evidence about our schema. `AI_UNAVAILABLE` is what the API answers for
one, deliberately identical to an outage because the difference is our capacity problem and a
user can do nothing with it — right for the product, unhelpful for a canary.

`tests/live/capacity.py` reads the code and skips, with a message naming the tier limit, and
`conftest.VISION_PACING_S` spaces the vision-heavy modules a minute apart. Every module
passes on its own; a full run on this account skips what the provider refuses rather than
reporting a red that says nothing. Skipping on a genuine outage is the cost, and
`test_model_availability.py` is the canary for that case.

This was found the honest way: the first full run failed, and the failure moved between tests
depending on which one was running when the budget ran out.

## B6 confirmed itself during S7's verification

S6 predicted it: without `SESSION_SECRET` the API signs with a per-process key, so a restart
orphans every session. During S7's browser verification an edit to `config.py` triggered
uvicorn's reloader, and a wardrobe that had taken several minutes and a dozen provider calls
to seed became unreachable — the rows are still in the database, owned by a user whose token
can no longer be minted.

Nothing to fix in the code; the warning at boot says exactly this. But it moves B6 from a
predicted risk to an observed one, and the mitigation is one environment variable.

## What the rate limit says about the demo

The product behaves correctly under it — per-photograph failure with retryable copy, one card
affected, an honest gap instead of a fabricated outfit. That is the degradation ladder working
in production conditions rather than in a test.

It is still a demo risk (B6), and S7's own browser verification is the evidence: seeding a
four-garment wardrobe took several passes, with the retry button doing exactly what it is for.
Uploading six photographs at once in front of an interviewer, on this tier, will produce cards
that say "we're at capacity". Upload in twos, or pre-seed the wardrobe before the room is
watching.

Worth separating two things that look alike: the product's behaviour under this is correct and
was verified against the real provider — one card fails, the others resolve, the retry is
offered, and composition names the missing role instead of inventing a garment. What is wrong
is the tier, not the pipeline.

## Mutations run

| Mutation | Result |
|---|---|
| Read the swap replacement unscoped (cross-user) | caught, 2 tests |
| Drop the role-mismatch check | caught, 1 test |
| Score a candidate alone instead of in the look | caught, 3 tests across 2 files |
| Keep the words written about the previous look after a swap | caught, 1 test |
| Drop a deleted garment's slot instead of keeping it empty | caught, 2 tests |
| Report an insufficient wardrobe as a failed job | caught, 1 test |
| Hold the database session across the advisor call | caught, 1 test |
| Let a second save write a second row | caught, 1 test |
| Offer the garment already in the slot as its own alternative | caught, 2 tests |

Nine run, nine caught.

# S8 — AI evaluation harness (2026-09-13)

Prompt 10 is a validation phase, not a feature phase. Its worth is measured in what it
found, so that is what this section leads with.

## The harness prints and asserts the same objects

The acceptance criterion is that *a reviewer can intentionally make the model return an item
the user does not own — or one belonging to another user — or malformed JSON, and watch the
application refuse it*. Watching is the operative word: an assertion that passes silently is
not something anybody can be shown.

So a scenario returns a `Check` — what was injected, what was expected, what was observed,
and the evidence — rather than asserting inline. `runner.py` prints them and
`test_scenarios.py` asserts over them. One implementation, two audiences.

The alternative, a demo script beside the test suite, is the arrangement where the demo
passes while the product is broken. Both call `run_all()`, so they cannot disagree.

`runner.py --response FILE` is the criterion taken literally. Write what you want the model
to have said, point the runner at it, and watch. Nothing about the path differs from the
built-in scenarios; the bytes are the only variable.

## Coverage is resolved, not asserted

A registry mapping the twenty-five cases to the code that evidences them would be worth
nothing as prose — the failure mode is silent, because a renamed test leaves the claim
standing and the next reader believes it.

`test_case_coverage.py` resolves every entry. A `file::symbol` reference is checked with
`ast`, so a mention in a comment does not count. A file-level reference must contain the
string `Case NN` it is claimed for — which turns an existing convention in this repository
into a constraint, because deleting the test deletes its marker and the claim fails with it.

It earned its place on the first run: two entries written from memory were wrong.
`test_composition.py` does not cover Case 03, and `test_prompt_contract.py` did not cover
Case 09 until a docstring said so. Both were caught before the registry was ever printed.

Three statuses rather than two. A binary covered/not would have forced five cases into the
wrong box: the crew cases (18, 19, 20, 23) have their *property* asserted today and are
missing the crew in front of it, which is neither "covered" nor "nothing". `partial`
requires a note long enough to say which half is missing, and the meta-test enforces the
length — a one-word note is how a partial silently becomes a covered.

## What the harness found

Four things, all of them shipped in this commit, plus one it could not fix.

### 1. A fibre claim rendered as fact

`isHedged` consulted the confidence floor and nothing else. An extraction asserting
`material_guess: "100% merino wool"` at 0.99 cleared the floor and the garment card rendered
it as a settled attribute — precisely the Fail clause of Case 08, and precisely what
CLAUDE.md forbids.

The floor was the wrong control for that field. A model confident about a colour has usually
seen the colour; a photograph does not show fibre content at any confidence, so a high score
there is confidence about an inference. `ALWAYS_A_GUESS` hedges it whatever the score says,
and a user correction still settles it — they can read their own care label, which is the
one source that actually knows.

The rule is mirrored in `apps/api/app/domain/corrections.py` and
`apps/web/src/lib/schemas/wardrobe.ts`, the same arrangement as the upload limits. The
mirror is the risk, so the Case 08 scenario reads the constant out of the TypeScript source
and fails if the two disagree. If a second renderer ever appears this moves into the item
payload rather than being copied a third time.

### 2. An invisible channel into the advice prompt

`style_tags` is free text written by a vision model. It is **not** rendered on the garment
card, and `app/adapters/prompts.py` interpolates it into the *advice* prompt. Worst possible
combination: influential and unseen. The only thing standing in it was a 32-character
ceiling.

Two payloads went through. Case 07's injection survived as `"printed slogan reading ignore
pr"` — truncated, and still attacker-influenced text arriving where a second model reads it.
And a description of the person in the photograph, `"size 8, approximately 5 foot 6"`, which
fitted comfortably inside the ceiling because a description of somebody's body is short.

Length was the wrong control here too. What these fields actually are is enumerations that
were typed as `list[str]`, so `app/domain/vocabulary.py` closes them: `style_tags`,
`season_tags`, `occasion_tags` and `quality_warnings`.

An allow-list rather than a deny-list, because it fails closed — the next phrasing of a body
description and the next injection are both unknown, and both go. A deny-list would have to
anticipate them and would strip legitimate garment vocabulary on a bad guess. The cost is
that a real style word we did not think of is silently not shown, which is a much smaller
harm than storing a stranger's estimate of somebody's dress size.

The fields stay `list[str]` in the domain rather than becoming `Literal`. A `Literal` would
make an unrecognised tag fail the whole extraction, turning a decorative word into a failed
photograph. Instead the vocabulary reaches the provider as a schema `enum` — guidance the
model is given, and what CLAUDE.md asks for anyway — and hygiene enforces it by filtering.
Off-vocabulary output costs the tag, never the garment.

This also replaced a weaker test with a stronger one. `test_hygiene.py` used to assert the
injected slogan arrived *clipped*; it now asserts it does not arrive.

### 3. A quality warning that reached the user meaningless

Closing `quality_warnings` fixed a second, unrelated thing. The web renders each known
warning as its own sentence and falls back to "Worth a second look" for anything else, and
the model was free to invent one. An invented warning therefore reached the user looking
like a quality signal with its meaning removed. The fixture in this repository had exactly
that drift: `garment_partially_cropped` against a renderer that knows `cropped`.

### 4. No ceiling on a compose

The transport retries a retryable failure three times with backoff at a 30-second client
timeout, inside an advisor that re-asks once on a schema failure. Six provider calls, and
nothing above them had any idea a person was watching a spinner. `AGENT_LATENCY_BUDGET_MS`
existed in config and was wired to nothing.

It is now enforced around the whole advisor call, once, in `CompositionService`. Exceeding
it is an `advisor_timeout` rejection and a drop to the deterministic ranker over the same
candidates — Case 23's floor. `asyncio.wait_for` cancels rather than abandons, because an
orphaned provider request holds a connection and is still billed.

A timeout is a *different* rejection from an outage, deliberately. "The model was slow" and
"the model was broken" have different fixes and belong in different columns.

### What could not be fixed: free-text extraction fields

A person description landing in `subcategory` or `pattern` is still stored — the fixture
produces `"blouse worn by a slim woman in her late twen"`, bounded and intact. Those fields
are open sets in the world; a garment really can be a "wrap midi skirt", and closing them
would mean inventing a taxonomy of garments.

The argument for leaving them is that they are **rendered on the card and correctable in one
tap**, which is a different class of problem from a field only a downstream prompt ever
sees. It is not nothing, and it is not resolved. Case 09 is `partial` and the residual is
blocker B18.

## Generation telemetry, and the metric we cannot emit

Requirement 10 asks that generation events expose enough telemetry to measure quality and
latency. Every metric in docs/OBSERVABILITY.md's AI list was derivable in principle from
something — a log line, an `item_extractions` row, an `AdviceTelemetry` object the advisor
set and nobody read — and computable in practice from none of them.

One event type now, emitted by both generating paths, and one function that turns a stream
of them into that list. `generation_metrics()` is product code rather than a test helper on
purpose: a metric nothing computes is a metric nobody can be shown. The test that matters
computes the whole list from a deliberately unhealthy stream and fails if any one of them is
not computable — a field list would be satisfied by any field list.

One event per **call**, not per request. A photograph that took two calls is one failure and
one success, which is the only way `retry_rate` and `fallback_calls` mean anything.

Three deliberate constraints:

**Scalars only.** No garment text, no rationale, no raw output, no storage key. Enforced by
walking the annotations, the same trick the browser-side analytics module uses. `raw_output`
lives on `AnalysisAttempt` and goes to `item_extractions` — our own table, under the same
retention as the wardrobe. An audit trail keeps the evidence; telemetry keeps the count, and
telemetry is what gets shipped to a third party.

**Estimated cost is tokens, never currency.** A price per token hardcoded in that module
would be right for one plan on one day, would go stale silently, and would be believed.

**"Cross-user ownership rejection" is not separable from "unowned-item grounding failure".**
OBSERVABILITY asks for both. The domain cannot tell them apart and that is the design:
`app/domain/validation.py` refuses an unexpected id *without looking it up*, so that no other
user's id enters a query on the request path. Both arrive as `ungrounded_item`. Attribution
belongs to the alerting layer, which has admin scope. The spec is now amended to say so
rather than asking for something the architecture forbids.

One subtlety worth recording because it fabricates measurements when missed: the advisor is
long-lived and `last_telemetry` is the *last* call's. A provider outage that never reached
the model would otherwise be recorded against whatever model answered the previous user,
with that user's latency. `_emit` captures the object before the call and compares by
identity — same object means this call reported nothing, and the event says `unreported`
rather than guessing.

## `AdviceTelemetry` moved out of the Groq adapter

To `app/adapters/advice.py`, mirroring `analysis.py` and for the same reason:
`app/services/composition.py` consumes it and must not import a provider-specific module.
Nothing in those types names a vendor — a model id is a string, latency is an integer.

It stays an attribute rather than a return value because it has to be readable after the
call **raised**. A schema failure is the case most worth measuring and the one with no return
value to hang figures on.

## Mutations run

| Mutation | Result |
|---|---|
| Drop the vocabulary filter from `clean_tags` | caught, 5 tests |
| Keep the model's spelling instead of the canonical one | caught, 1 test |
| Remove the latency budget from the advisor call | caught, 4 tests |
| Report a timeout as `advisor_unavailable` | caught, 4 tests |
| Emit a generation event only on success | caught, 1 test |
| Attribute the previous call's telemetry to one that never reached the provider | caught, 1 test |
| Let a `dict` field onto `GenerationEvent` | caught, 1 test |
| Count anything that was not an outage as a success | caught, 2 tests |
| Interpolate the p95 instead of taking the nearest rank | caught, 1 test |
| Emit one extraction event per photograph instead of per call | caught, 1 test |
| Let a `covered` case name no evidence | caught, 1 test |
| Let a file-level claim pass without its `Case NN` marker | caught, 1 test |
| Let `isHedged` fall through to the floor for `material_guess` | caught, 1 test (web) |
| Resolve a coverage claim by substring instead of by `ast` | **survived**, then caught |

Fourteen run. Thirteen caught on the first pass; the fourteenth survived and is worth
recording, because the reason is instructive.

The meta-test parses with `ast` so that a symbol *mentioned* in a comment does not count as
a symbol *defined*. Swapping the parse for a substring check changed nothing, because every
symbol the registry references also happens to appear literally in its own file — the two
implementations agree on all valid data, and they differ only on the invalid data the test
exists to reject. The `ast` call was doing work nobody could observe, which is the same
thing as not doing it.

Fixed by extracting the rule into `unresolved()` and driving it with a reference that should
fail: a file that talks about `cross_user_item` in a comment, a docstring and a list without
defining it. The mutation now dies. The general lesson — a check that cannot be pointed at
bad input is a check with no evidence behind it — is the same one the ablation rule (Case
21) is about, arriving from a different direction.

# S8b — Agent crew + live trend grounding (2026-09-13)

## The corpus was dropped before it was ever built

`prompts/14` asked for `CorpusTrendSource` over a committed `data/trends/` directory, with
`WebTrendSource` as an opt-in. Superseded on instruction, and the instruction was right.

A hand-curated corpus is a snapshot of what somebody believed on the day they wrote it. It
goes stale silently; it reads to a user exactly like model recall, which is the thing the
whole trend rule exists to prevent; and keeping it current is a job nobody would do. Blocker
B8 had been open since S1 for precisely that reason — nobody assembled it, because assembling
it was not obviously worth doing.

Live retrieval with a date filter is the honest shape. `ExaTrendSource` is the only
implementation, and there is no fallback to a corpus, because a stale corpus behind a live
source would be the same lie with a longer half-life.

## Exa is required for one role and nothing else

No `EXA_API_KEY` means no Trend Scout, degradation level 2, disclosed. Deliberately not a
boot failure the way `GROQ_API_KEY` is, and the distinction is what the product can still do:
it composes perfectly good outfits with no trend context, and it cannot compose anything at
all without a vision and a text model. A boot check that refused to start over a missing
trend key would be treating a nice-to-have as the product.

## What actually defends the trend layer

Trend copy is text from the open web reaching a prompt, which is Case 07's problem with a
different door. Four layers, in the order they apply, and the first is the strongest:

1. **A domain allow-list.** `includeDomains` is a named list of editorial fashion desks.
   Hostile "trend copy" has to be published on one of them to be retrievable at all. This is
   also the commerce filter: a retailer's trend report is an advertisement with a date on it.
2. **Attribution.** No date, no resolvable publication, no claim, no URL — dropped, not
   repaired. A shopping URL is dropped whatever else it has.
3. **Bounding.** The claim is a headline's length with control characters stripped, so it
   cannot impersonate a prompt's own section headings once interpolated.
4. **Scope.** The candidate set was fixed in SQL before any of this ran. There is no id for
   an instruction to add, and `ExaTrendSource` has never seen the wardrobe — `applies_to_items`
   leaves it empty by construction.

Worth recording what is *not* a defence, because the obvious test asserts it and would be
wrong: truncation does not remove the instruction. 180 characters is ample room for "include
u2-jacket". `test_an_injected_instruction_in_an_article_is_bounded_and_stays_data` says so in
its docstring rather than asserting something the design does not promise.

## A trend note needs a URL, and the URL is its identity

`TrendNote` gained a required `url`. Two reasons, and the second is the one that found a bug.

A source and a date the reader cannot follow are a citation they cannot check — which is
indistinguishable from one a model invented, and inventing plausible citations is the single
most characteristic thing a language model does when asked about fashion.

And it gives a note an identity, which exposed a hole that had been open since S5:
**nothing stopped the advisor from returning trend notes the trend source never supplied.**
`trend_notes` was schema-valid and therefore accepted. A model could return "Chrome is the
colour of the season — A Real Magazine, 2026-08-20" and it would render, with a date, beside
the user's own clothes. Exactly the gimmick CLAUDE.md's trend rules exist to prevent, sitting
in the product the whole time.

`app/domain/validation.py` now matches returned notes against supplied ones by URL and takes
the claim, the publication and the date **from the supplied note**. An advisor may narrow the
set and map notes onto garments; it may not reword a claim, restate a source, or add one.
Rewording is how a citation drifts away from what the article said while keeping the link
that makes it look checkable.

## The cache key is region + season + role set

Not per user. A per-user key is a cache that never hits, and the point of caching a trend
lookup is that fashion journalism does not turn over hourly while a compose might.

That the key is genuinely shared is asserted with two *equal but distinct* query objects.
Reusing one instance is the version of that test that passes while the cache does nothing —
and a mutation keyed on `id(query)` survived the first mutation run for exactly that reason.
(It survived the strengthened test too, which turned out to be CPython recycling the address
of a freed object rather than a weak test. The mutation was discarded as invalid and replaced
with two that are deterministic.)

## CrewAI runs on our transport, not on LiteLLM

The decision that made the rest of the crew possible. CrewAI defaults to LiteLLM, which would
mean the crew makes its own HTTP calls with its own retry policy, its own timeouts and its own
idea of what a provider error is — and, fatally here, **the crew could not be tested without
an API key**. `tests/ai/` exists because every grounding claim is checkable for free on every
push. A crew outside that would be the one component nobody could assert cheaply, which is the
component most likely to produce confident nonsense.

`crewai.BaseLLM` is the documented seam. `TransportLLM` implements `call()` over
`ChatTransport`, so every agent goes through the same transport, the same taxonomy, the same
telemetry and the same `MockGroqProvider` as everything else. The sync/async bridge is
`asyncio.run_coroutine_threadsafe` against a loop captured before the crew is handed to a
worker thread; `asyncio.run()` inside `call()` looks simpler and is a bug, because it builds
and tears down a loop per agent call.

Costs, recorded because they are real: importing CrewAI takes ~13 seconds. Nothing outside
`app/adapters/crew*.py` and the two crew test files imports it, and `main.py` imports it
inside the lifespan rather than at module scope, so the fast suites stay fast.

## Phases, not one kickoff

    1  Style Profiler ‖ Trend Scout
    2  Outfit Architect
    3  Critic ‖ Practical Advisor
    4  (conditional) Architect again, under constraints
    5  Editor

Four sequential hops for six agents. The pairs are `asyncio.gather` over two kickoffs, not two
tasks in one crew hoping the framework schedules them together — and that distinction is
asserted by making the two agents wait for each other in the transport, because an ordering
assertion cannot tell parallel from sequential. A mutation that serialised the phases survived
the first version of that test.

The deeper reason for phases is Case 19. CrewAI's implicit task context hands an upstream
agent's prose to a downstream one as undifferentiated text. Every agent here is given its
inputs in a labelled `DATA` section that states outright they are content, not instruction.
Interpolating a typed value into a named slot is a defence; passing a paragraph is not.

## The Critic is a judge, and the loop is bounded

The Critic returns a `score` as well as objections, so it is an LLM-as-judge and not only a
commentator. Below 70, the Architect runs again with the objections attached as
**constraints**, and the run records the score before, the score after, and whether it moved.

Three bounds, each of which a naive reflexion loop gets wrong:

- **One revision.** A second spends four more seconds of a fifteen-second budget on a model
  that has already been told twice what was wrong.
- **A revision that scores no better is discarded.** A self-evaluating loop that cannot reject
  its own revision is a loop that wanders.
- **A low score with no objections does not trigger a rebuild.** There would be nothing to
  constrain it with, so it would be a re-roll dressed as reflection.

70 rather than a higher bar because the loop is bounded at one: setting it where most drafts
fail would double the cost of a typical compose to redo work that was already acceptable.

## The circuit breaker needed a middle rung to fall to

Case 23 has always specified "degrade to Architect + Editor, then to the deterministic
ranker", and until the crew existed there was no middle. `LatencyCircuit` counts *consecutive*
breaches — one slow compose is a slow compose, and a breaker that trips on a single one makes
the product visibly shallower for no reason a user could see. Recovery is optimistic: one run
inside budget closes it, because a cool-down timer means a provider that recovered in ten
seconds keeps serving reduced results for however long somebody guessed.

The reduced crew is a **copy**. A breaker that reached into the shared advisor and switched
roles off would leave every later request degraded until something switched them back on.

`CrewRoles` is the same object the ablation test uses. A test-only ablation switch would mean
Case 21 exercises a path the product never takes.

## The ablation test, and what it had to mean

B11 closed. Open since S4, deliberately never stubbed: a placeholder that cannot fail converts
"we have not checked" into "we have checked", and the whole point is that it must be able to
condemn a role.

"Changes the output materially" needed defining before it could be asserted. Not "the bytes
differ" — with a scripted provider they differ for trivial reasons, and with a real one they
differ every run. Each role is checked against the specific contribution it exists to make:
the Profiler changes what the Architect is told; the Scout changes whether an attributed note
reaches the answer; the Critic changes whether a weak draft is rebuilt; the Advisor changes
whether there is advisory content at all.

The Architect and the Editor are not ablatable and `CrewRoles.without` refuses to try.
Removing either does not degrade the crew, it removes the product. Asserting that they
"change the output" would be theatre.

Every role earned its place. Nobody had to be deleted.

## Observability

`TrendLookupEvent` is a second event type rather than a `GenerationEvent` with empty columns.
A generation is measured on quality and cost per token; a retrieval on latency, hit rate and
how often it left the crew a role short. Folding them together would produce one stream in
which half the rows have no model — the sort of tidiness that costs a dashboard.

Per-agent latency and tokens are on `CrewRun`, so "which role is expensive" is answerable
without reverse-engineering the framework. Same leak rule as S8: scalars only, no query text,
no prompt, no wardrobe.

What is **not** here: a vendor tracing backend. LangSmith or Arize would be an integration
against a service this project has no account with, and wiring one blind would produce
configuration nobody has ever seen work. What exists instead is the data those backends
consume — structured events with stable names, computed rollups, and one sink interface to
put in front of an exporter. Saying "observable" while shipping an unverified vendor client
would be the same move as a stubbed ablation test.

CrewAI's own telemetry and trace uploader are switched off in `app/adapters/__init__.py`,
before the framework can be imported, and again at every call site. This process handles
photographs of people's clothes; docs/SECURITY-PRIVACY.md has no exception for a dependency's
analytics, and a thing that phones home by default has to be turned off in code rather than in
a deployment checklist somebody can forget.

## What the crew actually costs, measured

The latency budget in `docs/AGENT-SYSTEM.md` has said 8s p50 / 15s p95 since S0 without
anybody measuring it. Now measured, on real Groq, five agents and no revision:

```text
  crew: 11,727 ms, 7,577 prompt / 3,836 completion
    style_profiler        1,937 ms   in=1,020  out=446
    outfit_architect      1,725 ms   in=1,033  out=553
    critic                1,991 ms   in=1,220  out=668
    practical_advisor     2,930 ms   in=1,562  out=1,000
    editor                3,144 ms   in=2,742  out=1,169
```

Inside the p95 budget, and the first measurement is not the interesting part. The first three
attempts came back at **58.9s, 33.7s and 65.9s**, and chasing the difference found two real
defects and one property of the account.

**Every agent was shipping its own class docstring to Groq.** Pydantic copies a model's
docstring into its JSON Schema `description`, and the docstrings in `crew_contracts.py` are
long because they explain to a reader why each agent exists. Six agents, every call: 31% of
the schema bytes, and this project explaining itself to a third party's request logs.
Stripped in `crew_llm._without_docstrings`, which keeps `Field(description=...)` — those are
written for the model — and drops only the object-level ones.

**One output ceiling for six agents was wrong, and wrong in an expensive way.** Under strict
Structured Outputs a truncated response is not a short answer, it is an invalid one: the
provider refuses it with `json_validate_failed` and names the properties that never arrived.
The Editor writes the whole merged answer and was being cut off mid-object at 800 tokens,
refused, and retried — 26 of one composition's 34 seconds. `OUTPUT_BUDGET` now scales per
role, the Editor gets 2.5x, and the field nothing ever read (`EditorOutput.critique`, a whole
nested object the Editor was paying to restate) is gone.

That is the same lesson S6 recorded from the other direction, and it is worth stating as a
rule rather than as two anecdotes: **with a strict schema, a token ceiling is a correctness
setting.** Too low does not truncate the answer, it destroys it.

**The rest was the account, not the crew.** Per-agent latency correlates with cumulative
tokens spent inside the minute, not with which agent is running: on a fresh window every call
lands in 1.7-3.1s, and on a spent one the same calls take 13-26s while the transport backs off
a 429. One composition costs ~7,600 input tokens against a measured 8,000 input-TPM ceiling
(blocker B17), so a second compose inside the same minute is throttled by arithmetic.

Two honest consequences, neither of which is "raise the budget until the test passes":

- On a healthy tier the documented budget holds and the 15s ceiling is right.
- On *this* tier a busy minute will trip the circuit breaker, and the product will serve
  Architect + Editor — two calls, about 3.5s — with the depth disclosed. That is the ladder
  working, and it is a better answer than either waiting a minute or pretending.

## Mutations run

| Mutation | Result |
|---|---|
| Accept a trend note the source never supplied | caught, 2 tests |
| Keep the advisor's wording instead of the source's | caught, 1 test |
| Let a trend note through with no publication date | caught, 1 test |
| Drop the editorial domain allow-list from the query | caught, 2 tests |
| Stop deduplicating near-identical headlines | caught, 1 test |
| Let a search failure raise instead of costing a rung | caught, 1 test |
| Key the trend cache per call so it never hits | caught, 2 tests |
| Ignore the cache entirely | caught, 2 tests |
| Put the wardrobe into the search query | caught, 1 test |
| Trip the circuit breaker on a single slow run | caught, 2 tests |
| Never close the circuit again once it opens | caught, 2 tests |
| Let an ablated role run anyway | caught, 2 tests |
| Accept a revision that scored worse | caught, 1 test |
| Rebuild on a low score with no objections behind it | caught, 1 test |
| Let the Editor set the score the user sees | caught, 1 test |
| Let a CrewAI parse failure escape as an outage | caught, 2 tests |
| Run the two parallel phases sequentially | **survived**, then caught |

Seventeen run, sixteen caught on the first pass.

The survivor is the one worth recording. `test_the_crew_runs_four_hops_not_six` asserted the
*order* of the schemas, which a sequential crew satisfies exactly as well as a parallel one —
so the concurrency claim in `docs/AGENT-SYSTEM.md` had no test behind it at all. Fixed by
making the two agents in each pair wait for each other inside the transport: a sequential
implementation never sends the second and fails on the timeout.

An eighteenth mutation was discarded rather than counted. Keying the cache on `id(query)`
survived, and the reason turned out to be CPython recycling the address of a freed object
rather than a weakness in the test. A mutation whose result depends on the allocator is not
evidence about anything; it was replaced with two deterministic ones, both caught.
