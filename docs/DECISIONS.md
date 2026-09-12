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
