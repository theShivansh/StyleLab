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

### 2026-09-12 — Groq vision model default is contradictory (OPEN — resolve before S5)

Context:
The harness patch added an "AI provider rules" section to `CLAUDE.md` that names
`qwen/qwen3.6-27b` as the vision default "for cost", and calls `qwen/qwen3.8-27b`
a one-line env change for quality comparison. The rest of the kit disagrees:
`.env.example`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `README.md` and
`prompts/13-FINAL-AUTONOMOUS-BUILD.md` all name `qwen/qwen3.8-27b`.

`CLAUDE.md` is the only file Claude Code auto-loads, so the 3.6 default will win in
practice while every other doc says 3.8 — the exact drift the audit's finding #13 warns about.

Decision:
NOT TAKEN. Left contradictory on purpose rather than silently changing the project's
default model. Resolve before running `prompts/12-GROQ-INTEGRATION.md` (S5).

Alternatives:
(a) Align `.env.example` + `ARCHITECTURE.md` to `qwen/qwen3.6-27b` — follows CLAUDE.md's
    own rule that model IDs live in exactly two places, and takes the cheaper default.
(b) Align `CLAUDE.md` to `qwen/qwen3.8-27b` — matches the five existing kit docs.

Why:
Provider strategy is a real choice with a cost/quality trade-off, not a typo to sweep up.

Trade-offs:
Leaving it open risks S5 picking arbitrarily; that risk is why this entry exists.

Follow-up:
1. Verify both model IDs actually resolve against Groq's live model list before relying on
   either. The audit asserts both are live; that assertion is not independently confirmed here,
   and the same audit notes Groq has deprecated models on weeks of notice.
2. Pick (a) or (b), edit the two authorised locations only, and replace this entry's
   "Decision: NOT TAKEN" with the choice.

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
