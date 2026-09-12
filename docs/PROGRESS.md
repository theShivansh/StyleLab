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
| S3 | Onboarding + composer | 03 | done-with-debt | (this commit) | L T U E B | Upload/analysis/correction built + proven via e2e stubs. "Completes against live Groq" deferred to S6 — endpoints do not exist yet. |
| S4 | Wardrobe domain | 04 | done | (this commit) | L T U AI | Cross-user isolation red→green, then verified by 3 mutations (12 / 4 / 1 tests red). 109 api + 4 ai-eval tests. |
| S5 | Groq adapter | 12 | todo | — | — | |
| S6 | Upload + analysis pipeline | 05 | todo | — | — | |
| S7 | Result + swap | 06 | todo | — | — | |
| S8 | AI eval harness | 10 | todo | — | — | |
| S8b | Agent crew + trends | 14 | todo | — | — | multi-agent advisory layer |
| S9 | Planner + analytics | 07 | todo | — | — | P1, cuttable |
| S10 | Recruiter demo | 11 | todo | — | — | |
| S11 | Harden + deploy | 08 | todo | — | — | |
| S12 | Final review | 13 | todo | — | — | review only |

States: `todo` · `in-progress` · `done` · `done-with-debt` · `skip`

## Gate legend

`L` lint · `T` typecheck · `U` unit · `I` integration · `E` e2e · `A` a11y · `B` build · `AI` ai-eval

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
- [ ] B6 — Cold start is the top product risk: no demo wardrobe AND no demo mode means a
      live upload and live Groq calls must both succeed in front of an interviewer. Stage
      presenter garment photos in advance; hold the budget in docs/DEMO-SCRIPT.md.
- [ ] B7 — GROQ_API_KEY is now required to run anything. Provision it, add it to repo
      secrets for the live-smoke CI job, and rehearse against the live path.
      Not blocking S1-S4 (interfaces and stubs only); blocking from S5.
- [x] B10 — CLOSED. User verified .env and .env.example by hand 2026-09-12.
- [x] B9 — RESOLVED in S1. Pinned to 3.11 in CI and locally; 3.12 was never installed and
      installing it is a system change. See docs/DECISIONS.md.
- [ ] B10 — .env.example has an uninspectable uncommitted change (deny rule Read(./.env.*)
      matches it). It is TRACKED and not gitignored. Verify by hand that no real key is
      in it before the next `git add -A`. See docs/PLAN.md section 5.
- [ ] B8 — Trend corpus (data/trends/) not yet assembled. Each entry needs source +
      published_at. Without it the Trend Scout is skipped (degradation level 2).
- [ ] B11 — CI job `ai-eval` step 2 runs `pytest tests/ai/test_ablation.py`, which does not
      exist until S8b. Step 1 is green as of S4. Deliberately not stubbed: an ablation test
      that cannot fail is worthless (Case 21). The job stays red until S8b lands.
- [ ] B12 — No migrations. `Base.metadata.create_all` covers tests and local work only;
      Alembic (or Supabase migrations) lands with deployment in S11. Until then the schema
      only exists where someone has run create_all.

## Decisions taken mid-build

Append to `docs/DECISIONS.md`, not here. This file only points at them.
