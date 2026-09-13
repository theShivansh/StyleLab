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
| S8b | Agent crew + trends | 14 | done | (this commit) | L T U E B AI | Six-role CrewAI crew on our own transport (`crewai.BaseLLM`), so the whole crew runs with no API key. Live trend grounding via Exa behind a `SearchTransport` seam; the committed corpus was dropped rather than built. Self-evaluating Critic with a bounded revision loop, latency circuit breaker, and the ablation test — **B8 and B11 closed**. Found that an advisor could invent a trend citation and nothing stopped it. 24/25 eval cases covered, 0 deferred. 17 mutations, 16 caught first pass. 522 api + 107 ai-eval + 60 web unit + 58 e2e. Live: a real look from the full crew, all six strict schemas accepted, 11.7s for five agents. |
| S9 | Planner + analytics | 07 | skipped | — | — | Skipped by the user's instruction, S11 taken first. The **analytics** half was not skipped with it: S11's audit found the whole capture side of the funnel uninstrumented and built it (`images_selected` through `wardrobe_cleared`), which is the part docs/ANALYTICS.md calls the entire cold-start risk. The **planner** is genuinely not built and `flags.planner` is `false`. |
| S10 | Recruiter demo | 11 | skipped | — | — | Skipped by the user's instruction. docs/DEMO-SCRIPT.md exists and was updated in S11 with the measured pacing constraint. |
| S11 | Harden + deploy | 08 | done | (this commit) | L T U I E B A AI | Release audit. **B12 and B16 closed.** Environment-aware boot (`APP_ENV`, `app/preflight.py`) that refuses production on a local default and refuses *any* environment on a schema mismatch; Alembic with a baseline revision and a drift test; rate limiting on the three paths that cost money; request ids; a retention sweep that makes deletion true on disk; whole-wardrobe deletion; response security headers. Seven defects found by running the thing rather than reading it — a stale local schema failing every upload, a CSP that blanked the dev server, a duplicated degradation disclosure, a raw enum in user-facing copy, an 18px touch target, a flaky ordering assertion, and a circuit breaker that made its own middle rung unreachable. The formatting gate, listed in every phase prompt, ran for the first time. 593 api + 109 ai-eval + 66 web unit + 64 e2e. Live: the whole path on real photographs — upload, extract, correct, compose, result — plus the ladder's middle rung measured at **4.4s** for Architect + Editor against a 15s budget, which is what the breaker change makes reachable. |
| S12 | Final review | 13 | todo | — | — | review only |

States: `todo` · `in-progress` · `done` · `done-with-debt` · `skip` · `skipped`

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
- [ ] B6 — Cold start. **Materially reduced by S6, sharpened by S7, and measured in S11.**
      S11 ran the whole path in a browser on real photographs: upload three, watch them
      resolve, compose, see the result screen. It works, and it produced the one number the
      demo script needed — see item 2 below, which is now a measurement rather than a
      caution. The live path now
      runs end to end — upload, extract, compose, swap — so the risk is no longer "does it
      work". Three things still to do before a live demo:
        1. **Set `SESSION_SECRET`.** Without it the API signs with a per-process key, so a
           pre-seeded demo wardrobe becomes unreachable the moment the process restarts —
           which is exactly what happens when someone reloads a dev server mid-demo. Found
           the hard way while verifying S6 in the browser.
        2. **Do not upload six photographs at once, and pause before composing.** S7
           measured the tier's upload limits (B17). S11 measured the other half by doing it:
           three extractions followed immediately by a compose put the crew over its 15s
           budget, and the look came back styled by the deterministic ranker with the depth
           disclosed on screen. That is the ladder working exactly as designed and it is not
           the version to show an interviewer. About a minute between the last upload and
           the compose is enough. Recorded in docs/DEMO-SCRIPT.md.
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
- [x] B8 — CLOSED 2026-09-13, by deciding not to build it. The blocker was "assemble a
      trend corpus", and it stayed open from S1 because assembling one was never obviously
      worth doing: a hand-curated `data/trends/` is a snapshot of what somebody believed on
      the day they wrote it, it goes stale silently, and to a reader it is indistinguishable
      from model recall — the exact thing the trend rule exists to prevent. Replaced by live
      retrieval with a date filter and an editorial domain allow-list (`ExaTrendSource`).
      What is now open in its place is operational, not architectural: **`EXA_API_KEY` must
      be set** or the Trend Scout is skipped and every composition reports degradation 2.
      Outfits are unaffected either way.
- [x] B11 — CLOSED 2026-09-13. `tests/ai/test_ablation.py` exists and passes: eleven tests,
      every ablatable role checked against the specific contribution it exists to make, and
      the two load-bearing roles refusing to be ablated at all. Open from S4 to S8b and
      deliberately never stubbed — a placeholder that cannot fail converts "we have not
      checked" into "we have checked". Every role earned its place; nobody was deleted.
- [x] B12 — CLOSED 2026-09-13. Alembic in `apps/api/migrations`, `alembic upgrade head` as
      a deploy step, and `create_all` no longer called when `APP_ENV=production` — it creates
      whatever is missing, which papers over a migration that did not run.
      **It closed by biting first.** Adding `assets.purged_at` for the retention sweep broke
      the local database, which `create_all` had built months of sessions earlier:
      `create_all` adds missing *tables* and has never added a missing *column*, so every
      upload failed on `no such column` while the user-facing message read "Something went
      wrong on our side." So the close includes `preflight.verify_schema`, which compares the
      live database to the models at boot and refuses to serve if they differ — fatal in every
      environment, because a schema the queries do not match means every request fails anyway
      and the only question is whether the operator learns it from a boot message naming the
      fix. `tests/test_migrations.py` keeps it closed by asserting a migrated database and a
      `create_all` database are indistinguishable.
- [ ] B14 — The job runner is in-process (`BackgroundJobs`, asyncio tasks). It survives a
      single instance and nothing more: a restart loses queued extractions, and a second
      instance knows nothing of the first's jobs. The seam is deliberate — `submit` takes a
      factory and returns nothing, so a durable queue replaces the class without touching
      the pipeline. What is **not** deferred is the part that would be expensive to retrofit:
      nothing above the runner assumes a synchronous result.
      **Not closed in S11, and the phase made the shape of it clearer rather than smaller.**
      Two more things are now in-process for the same reason and with the same seam: the rate
      limiter (per instance, so two replicas allow twice the quota) and the retention sweeper
      (a deployment that scales to zero must run it as a scheduled job, or deletion silently
      stops happening). All three are documented in docs/DEPLOYMENT.md rather than assumed,
      because the failure in each case is quiet.
- [ ] B15 — No real authentication. `POST /session` mints a signed token for anyone who
      asks and creates an anonymous user to go with it; there is no password, no
      verification and no revocation. The **shape** is right and is what matters: identity
      arrives as a bearer token this API signed, and `user_id` is read out of that signature
      rather than from the request, so no caller can choose whose wardrobe to read. Supabase
      auth replaces the minting and changes nothing else. Also: set `SESSION_SECRET` in any
      environment where sessions must survive a restart or a second instance — as of S11,
      `APP_ENV=production` refuses to boot without it, and refuses one shorter than 32
      characters.
      **Deliberately not closed in S11**, and the prompt's own acceptance criterion is why:
      *"a recruiter can... reach a composed outfit they can swap — with no account and no
      credentials."* Real accounts would defeat the thing the phase is graded on. What S11
      did instead was make the consequence survivable: with identities free, the quotas that
      matter are rate-limited (B15's cost was always that anonymous tokens are unlimited,
      not that they are anonymous).
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
        3. S8b measured the text side too, and it binds the same way. One crew composition
           costs ~7,600 input tokens against the 8,000 input-TPM ceiling, so a second compose
           inside the same minute is throttled by arithmetic: per-agent latency goes from
           1.7-3.1s on a fresh window to 13-26s on a spent one, all of it backoff. The
           circuit breaker handles it correctly — two composes over budget and the crew drops
           to Architect + Editor with the depth disclosed — but a demo that composes twice in
           a minute will visibly get shallower. Same decision as below: a paid tier, or pace
           the demo.
        4. Still open: the documented primary flow uploads three to six photographs in one
           gesture, concurrently, and on this tier some of those calls are refused. The
           product degrades correctly (per-card failure, retry offered, honest gap) but the
           experience is worse than it should be. Either a paid tier or client-side batching
           of concurrent uploads — decide before the demo (B6).
- [ ] B19 — CrewAI costs ~13 seconds to import, which is now the floor on any test session
      that touches the crew. Contained rather than solved: nothing outside
      `app/adapters/crew*.py` and the two crew test files imports it, and `app/main.py`
      imports it inside the lifespan rather than at module scope, so `pytest tests/ai -q`
      stays under five seconds for the 100-odd tests that do not need a crew. Worth revisiting
      only if the framework starts earning less than it costs — the ablation test is the thing
      that would say so.
- [ ] B20 — No hosted `ObjectStore`. `LocalObjectStore` writes to `STORAGE_ROOT`, so a
      deployment must mount a volume or lose every photograph on the next deploy.
      `SupabaseObjectStore` has been named in `app/services/storage.py` as "S11" since S4 and
      S11 did not build it, for the reason S8b gave about vendor tracing: an integration
      nobody can run is not an integration, and there is no Supabase project to verify it
      against. Preflight warns rather than refusing — refusing would mean no deployment could
      start at all. The seam is four methods and the same `ObjectStore` Protocol.
- [ ] B21 — The Content-Security-Policy carries `script-src 'unsafe-inline'`. Next inlines
      its bootstrap and its streamed flight data as `<script>` elements, so a strict policy
      needs a nonce plumbed through middleware. Named rather than quietly omitted: it is the
      one directive in the list weaker than it looks, and everything around it —
      `frame-ancestors 'none'`, `object-src 'none'`, `base-uri`, `form-action`, and the
      `img-src`/`connect-src` allow-lists — is real. Worth doing before any deployment that
      renders content this project did not write.
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
      that classifies rather than describes. Not a demo blocker.
      **S11 found the second consequence.** docs/ANALYTICS.md asks
      `extraction_field_corrected` to carry "field name, from → to", and the values in that
      arrow are exactly these fields — so the event as specified would pipe the channel we
      already know is imperfect to a third party. S11 shipped the field name only; the KPI
      the spec actually wants (extraction acceptance rate) is a count per field either way.
      Reopen the values if and when B18 closes.
      **And the third.** `white solid_color sneaker` was rendering on the result screen: the
      raw model value reaching the user unchanged. Fixed in presentation
      (`describeGarment`), which is where a machine-shaped word should stop being one — the
      stored value is still what the model said, because that is what the audit trail is for.
- [x] B16 — CLOSED 2026-09-13. `app/services/retention.py` sweeps at boot and hourly,
      unlinking any asset whose thirty-day window has closed and recording it in
      `assets.purged_at`. Soft deletion was always half a trade — docs/DATA-MODEL.md wants
      deletion reversible by support, which is a good reason for a window and not a reason to
      stop there.
      Closing it also caught the copy: the landing page said **"Delete means delete"** over
      *"Remove one garment or the whole wardrobe. We tell you which looks that breaks before
      you confirm"* — and at the audit none of the three claims was quite true. Deletion was
      soft, there was no way to remove a whole wardrobe, and affected looks were named after
      the fact. `DELETE /wardrobe/items` now exists with a two-tap confirmation, and the copy
      states the window in three places: the landing card, the confirmation, and the API
      response. A retention period the product does not state is one the user has not agreed
      to.
- [x] B13 — CLOSED 2026-09-12. Three photographs supplied by the user. They happen to be a
      shirt, a pair of chinos and a white sneaker — a top, a bottom and footwear, which is
      exactly one complete outfit and the minimum the composer needs. Live extraction reads
      all three correctly, with `material_guess` hedged at 0.2/0.7/0.8 rather than asserted.
      These are the demo wardrobe as well as the fixture (overlaps B6).

## Decisions taken mid-build

Append to `docs/DECISIONS.md`, not here. This file only points at them.
