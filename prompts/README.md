# Prompt Index

## Execution order (use this, not the phase numbers)

The numbered filenames are NOT the run order. `09`–`12` are inserts, and `13` is a
review pass, not a build. Run:

| # | Prompt | Session | Notes |
|---|--------|---------|-------|
| 1 | `00-MASTER-BOOTSTRAP.md` | S0 | recon + plan only, stop before implementing |
| 2 | `01-FOUNDATION.md` | S1 | |
| 3 | `02-DESIGN-SYSTEM.md` | S2 | |
| — | `09-DESIGN-REFERENCE-TO-CODE.md` | S2b | optional, only if you have reference images; repeatable |
| 4 | `03-COMPOSER.md` | S3 | |
| 5 | `04-AI-CATALOG.md` | S4 | domain layer + LLM adapter *interface* + mock |
| 6 | `12-GROQ-INTEGRATION.md` | S5 | wires the real Groq adapter behind that interface |
| 7 | `05-VTO.md` | S6 | |
| 8 | `06-RESULT-REMIX.md` | S7 | |
| 9 | `10-NO-GIMMICK-AI-EVAL.md` | S8 | the proof layer — do not skip |
| — | `14-AGENT-CREW.md` | S8b | multi-agent advisory + trend grounding; **after** the harness |
| 10 | `07-PLANNER-ANALYTICS.md` | S9 | P1 scope, cut if time is short |
| 11 | `11-RECRUITER-DEMO.md` | S10 | |
| 12 | `08-HARDEN-DEPLOY.md` | S11 | |
| 13 | `13-FINAL-AUTONOMOUS-BUILD.md` | S12 | **review only** — use its "Final product review" section as a checklist. Do not run it as a build prompt; it duplicates 01–08. |

## Per-session loop

```
/resume
<paste the phase prompt>
/plan-build       # writes docs/PLAN.md, does not implement
/implement-phase
/verify
```

Then: `/ui-audit` after S2, S3, S7, S10 · `/architecture-audit` after S4, S5, S6, S8b
· `/ai-eval` after S5, S8 and S8b · `/demo-check` after S10 and S11.

Update `docs/PROGRESS.md` and commit before `/clear`. One phase per session.
