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
| S4 | Catalogue + domain | 04 | todo | — | — | |
| S5 | Groq adapter | 12 | todo | — | — | |
| S6 | VTO pipeline | 05 | todo | — | — | |
| S7 | Result + remix | 06 | todo | — | — | |
| S8 | AI eval harness | 10 | todo | — | — | |
| S9 | Planner + analytics | 07 | todo | — | — | P1, cuttable |
| S10 | Recruiter demo | 11 | todo | — | — | |
| S11 | Harden + deploy | 08 | todo | — | — | |
| S12 | Final review | 13 | todo | — | — | review only |

States: `todo` · `in-progress` · `done` · `done-with-debt` · `skip`

## Gate legend

`L` lint · `T` typecheck · `U` unit · `I` integration · `E` e2e · `A` a11y · `B` build · `AI` ai-eval

## Open blockers

- [ ] B1 — seed catalogue (~60 garments) + CC0 imagery not sourced
- [ ] B2 — pre-generated VTO result assets not produced
- [x] B3 — UI libraries verified 2026-09-12. Vengeance UI approved (MIT, pin by SHA);
      Skiper UI free tier only, attribution required, no public repo so vendor it;
      "Animaster" rejected — does not exist. Evidence in docs/DECISIONS.md.
- [ ] B4 — VTO production provider unchosen (mock is the ship target)

## Decisions taken mid-build

Append to `docs/DECISIONS.md`, not here. This file only points at them.
