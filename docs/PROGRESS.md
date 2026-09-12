# Build Progress Ledger

Source of truth across sessions. Claude Code reads this first via `/resume`.
Update the row + commit BEFORE ending a session. Never delete rows.

## Status

| S | Phase | Prompt | State | Commit | Gates passed | Notes / carry-over |
|---|-------|--------|-------|--------|--------------|--------------------|
| S0 | Recon + plan | 00 | todo | — | — | |
| S1 | Foundation | 01 | todo | — | — | |
| S2 | Design system + landing | 02 | todo | — | — | |
| S2b | Reference → UI | 09 | skip? | — | — | only if refs provided |
| S3 | Onboarding + composer | 03 | todo | — | — | |
| S4 | Wardrobe domain | 04 | todo | — | — | |
| S5 | Groq adapter | 12 | todo | — | — | |
| S6 | Upload + analysis pipeline | 05 | todo | — | — | |
| S7 | Result + swap | 06 | todo | — | — | |
| S8 | AI eval harness | 10 | todo | — | — | |
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
- [ ] B5 — Groq vision model default contested (CLAUDE.md says 3.6, five docs say 3.8).
      Resolve before S5. See docs/DECISIONS.md.
- [ ] B6 — Cold start is now the top product risk: no demo wardrobe means a live upload
      must succeed in front of an interviewer. Stage presenter garment photos before any
      demo; hold the 90s budget in docs/DEMO-SCRIPT.md.

## Decisions taken mid-build

Append to `docs/DECISIONS.md`, not here. This file only points at them.
