# Build Progress Ledger

Source of truth across sessions. Claude Code reads this first via `/resume`.
Update the row + commit BEFORE ending a session. Never delete rows.

## Status

| S | Phase | Prompt | State | Commit | Gates passed | Notes / carry-over |
|---|-------|--------|-------|--------|--------------|--------------------|
| S0 | Recon + plan | 00 | done | (this commit) | n/a — no code | docs/PLAN.md written. Prompt 00 patched: 5 instructions superseded. No implementation, by design. |
| S1 | Foundation | 01 | done | (this commit) | L T U E B | pnpm workspace, Next 16 web, FastAPI api. Gate verified blocking. Python reversed to 3.11. |
| S2 | Design system + landing | 02 | done | (this commit) | L T U E B A | Landing coherent 390/768/1440. Contrast 0 fails/86 nodes. Reveal rewritten for robustness. |
| S2b | Reference → UI | 09 | skip? | — | — | only if refs provided |
| S3 | Onboarding + composer | 03 | done | (this commit) | L T U E B | Upload/analysis/correction built + proven via e2e stubs. The deferred "completes against live Groq" criterion was **met in S6** — see `tests/live/test_upload_pipeline.py`. Debt cleared. |
| S4 | Wardrobe domain | 04 | done | (this commit) | L T U AI | Cross-user isolation red→green, then verified by 3 mutations (12 / 4 / 1 tests red). 109 api + 4 ai-eval tests. |
| S5 | Groq adapter | 12 | done | (this commit) | L T U AI | Live adapters + transport seam. Mock replaces the transport, so real prompt/parse/retry/fallback run. 2 mutations verified. 259 tests. |
| S6 | Upload + analysis pipeline | 05 | done | (this commit) | L T U I E B AI | Live path verified end to end against real Groq on real photographs. EXIF+GPS strip, checksum cache, soft-delete cascade, signed image capabilities, named job stages. 8 mutations run. 424 api + 14 ai-eval + 8 live + 48 web tests. Found and fixed two S5 schema bugs no mock could see. |
| S7 | Result + swap | 06 | done | (this commit) | L T U I E B AI | Compose is an async job, swap is synchronous and calls no model. Result screen, alternatives scored in the look, save, share-as-text. 9 mutations, 9 caught. 463 api + 14 ai-eval + 57 web unit + 54 e2e (desktop + mobile). Live: a real look composed from real photographs against Groq. Measured the account's output-token limit and opened B17. |
| S8 | AI eval harness | 10 | done | (this commit) | L T U E B AI | Refusal harness a reviewer can drive (`python tests/ai/runner.py --response FILE`), 19 scenarios, and a case registry resolved against the repo. Found four real defects and fixed them: a fibre claim shown as fact, an unseen `style_tags` channel into the advice prompt, meaningless quality warnings, and no ceiling on a compose. Generation telemetry + the OBSERVABILITY metric rollup. 14 mutations, 13 caught first pass, 1 survived and was killed. 486 api + 72 ai-eval + 59 web unit + 56 e2e. |
| S8b | Agent crew + trends | 14 | todo | — | — | multi-agent advisory layer |
| S9 | Planner + analytics | 07 | todo | — | — | P1, cuttable |
| S10 | Recruiter demo | 11 | todo | — | — | |
| S11 | Harden + deploy | 08 | todo | — | — | |
| S12 | Final review | 13 | todo | — | — | review only |

States: `todo` · `in-progress` · `done` · `done-with-debt` · `skip`

## Gate legend

`L` lint · `T` typecheck · `U` unit · `I` integration · `E` e2e · `A` a11y · `B` build · `AI` ai-eval

`I` first appears in S6: `tests/live/` exercises the real provider end to end. It needs a
key, so it is a local-and-main gate rather than a per-push one.

## Open blockers

- [x] B1 — CLOSED by the wardrobe pivot (2026-09-12). No seed catalogue; the wardrobe is
      user-uploaded. Zero garment assets ship with the project.
- [x] B2 — CLOSED by the wardrobe pivot. No rendering step, so no pre-generated assets.
- [x] B3 — UI libraries verified 2026-09-12. Vengeance UI approved (MIT, pin by SHA);
      Skiper UI free tier only, attribution required, no public repo so vendor it;
      "Animaster" rejected — does not exist. Evidence in docs/DECISIONS.md.
- [x] B4 — CLOSED. VTO removed entirely; the result is a composed look built from the
      user's own garment photos.
- [x] B5 — RESOLVED 2026-09-12. Vision primary qwen/qwen3.8-27b, fallback
      qwen/qwen3.6-27b (availability only, never for quality). See docs/DECISIONS.md.
- [ ] B6 — Cold start. **Materially reduced by S6, and sharpened by S7.** The live path now
      runs end to end — upload, extract, compose, swap — so the risk is no longer "does it
      work". Three things still to do before a live demo:
        1. **Set `SESSION_SECRET`.** Without it the API signs with a per-process key, so a
           pre-seeded demo wardrobe becomes unreachable the moment the process restarts —
           which is exactly what happens when someone reloads a dev server mid-demo. Found
           the hard way while verifying S6 in the browser.
        2. **Do not upload six photographs at once on this account.** S7 measured the tier's
           limits (B17): concurrent extractions exceed the per-minute output budget and the
           provider refuses some of them. The product handles it correctly — one card fails
           with a retry, and composition names the gap rather than inventing a garment — but
           an interviewer would watch two cards fail. Pre-seed the wardrobe, or upload in
           twos with a pause.
        3. Rehearse and time the live path; hold the budget in docs/DEMO-SCRIPT.md.
- [x] B7 — CLOSED 2026-09-12. Key provisioned by the user in `.env`. It immediately paid
      for itself: the first real run of `tests/live` failed three ways, and two were
      genuine S5 bugs that **no mock could have caught** — a strict-mode schema Groq
      refused outright, and a `field_confidence` object specified so that the provider was
      forbidden from sending any scores at all. Both fixed in S6 with regression tests.
      Still open for CI: the `live-smoke` job needs the key as a **repo secret** before it
      can run on main. Everything else the key unlocked is now verified locally.
        1. `pytest tests/live -q` — 8 passed against the real models
        2. boot model-availability check — all three configured ids resolve
        3. the full upload path end to end — `tests/live/test_upload_pipeline.py`
- [x] B10 — CLOSED. User verified .env and .env.example by hand 2026-09-12. (A duplicate
      open row for the same blocker was carried from S2 and removed in S5 — the deny rule
      Read(./.env.*) still stands, so those files are staged explicitly, never by
      `git add -A`.)
- [x] B9 — RESOLVED in S1. Pinned to 3.11 in CI and locally; 3.12 was never installed and
      installing it is a system change. See docs/DECISIONS.md.
- [ ] B8 — Trend corpus (data/trends/) not yet assembled. Each entry needs source +
      published_at. Without it the Trend Scout is skipped (degradation level 2).
- [ ] B11 — CI job `ai-eval` step 2 runs `pytest tests/ai/test_ablation.py`, which does not
      exist until S8b. Step 1 is green as of S4. Deliberately not stubbed: an ablation test
      that cannot fail is worthless (Case 21). The job stays red until S8b lands.
- [ ] B12 — No migrations. `Base.metadata.create_all` covers tests and local work only;
      Alembic (or Supabase migrations) lands with deployment in S11. Until then the schema
      only exists where someone has run create_all. S6 made the local default concrete: an
      unconfigured `DATABASE_URL` resolves to a file-backed SQLite database in the working
      directory, gitignored, logged by dialect at boot.
- [ ] B14 — The job runner is in-process (`BackgroundJobs`, asyncio tasks). It survives a
      single instance and nothing more: a restart loses queued extractions, and a second
      instance knows nothing of the first's jobs. The seam is deliberate — `submit` takes a
      factory and returns nothing, so a durable queue replaces the class without touching
      the pipeline. Lands with deployment in S11. What is **not** deferred is the part that
      would be expensive to retrofit: nothing above the runner assumes a synchronous result.
- [ ] B15 — No real authentication. `POST /session` mints a signed token for anyone who
      asks and creates an anonymous user to go with it; there is no password, no
      verification and no revocation. The **shape** is right and is what matters: identity
      arrives as a bearer token this API signed, and `user_id` is read out of that signature
      rather than from the request, so no caller can choose whose wardrobe to read. Supabase
      auth in S11 replaces the minting and changes nothing else. Also: set `SESSION_SECRET`
      in any environment where sessions must survive a restart or a second instance (B6).
- [ ] B17 — Provider tier limits. Measured in S7 from a live response header plus the 429
      body: 1000 requests/minute and 8000 **input** tokens/minute, alongside a separate
      **output** tokens-per-minute ceiling of 1000 per model that the headers do not report.
      Three consequences, two already addressed:
        1. Lowering `groq_vision_max_tokens` looked like the fix and is not — tried,
           measured, reverted to 2048. Smaller ceilings are refused just as readily once the
           minute is spent, and at 768 the model has no room to reason and returns nothing.
           Recorded in docs/DECISIONS.md so nobody repeats it. **Closed as a wrong turn.**
        2. `tests/live/` paces its vision-heavy modules and skips on a capacity refusal
           rather than failing, since a rate limit is not evidence about our schema. **Done.**
        3. Still open: the documented primary flow uploads three to six photographs in one
           gesture, concurrently, and on this tier some of those calls are refused. The
           product degrades correctly (per-card failure, retry offered, honest gap) but the
           experience is worse than it should be. Either a paid tier or client-side batching
           of concurrent uploads — decide before the demo (B6).
- [ ] B18 — Free-text extraction fields can still carry a description of the person in the
      photograph. S8 closed the channel that mattered most: `style_tags` is a closed
      vocabulary now, because it is never rendered to the user and *is* interpolated into the
      advice prompt, so a 32-character ceiling was letting "size 8, approximately 5 foot 6"
      through to a second model unseen. What remains is `subcategory`, `pattern`,
      `color_primary`, `color_secondary` and `fit`: genuinely open sets in the world, so they
      cannot be closed without inventing a taxonomy of garments. The mitigations are real but
      partial — the prompt forbids it, the values are bounded, and every one of these fields
      is rendered on the card and correctable in one tap, so a bad value is visible to its
      subject. Case 09 is `partial` until this is decided. Options: a narrower `subcategory`
      vocabulary derived from the extractions we actually see, or a second cheap model pass
      that classifies rather than describes. Not a demo blocker; decide in S9.
- [ ] B16 — Uploaded images are only ever soft-deleted. `deleted_at` is set on the item and
      the asset and the file stops being served, but the bytes stay on disk — deliberate,
      because docs/DATA-MODEL.md wants deletion reversible by support. A retention timer
      that actually unlinks them belongs with the privacy flow in S11, and until it exists
      "delete my photographs" is not fully true at the filesystem level.
- [x] B13 — CLOSED 2026-09-12. Three photographs supplied by the user. They happen to be a
      shirt, a pair of chinos and a white sneaker — a top, a bottom and footwear, which is
      exactly one complete outfit and the minimum the composer needs. Live extraction reads
      all three correctly, with `material_guess` hedged at 0.2/0.7/0.8 rather than asserted.
      These are the demo wardrobe as well as the fixture (overlaps B6).

## Decisions taken mid-build

Append to `docs/DECISIONS.md`, not here. This file only points at them.
