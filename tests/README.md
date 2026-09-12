# tests/

Cross-cutting test layers that belong to neither app.

## `tests/ai/`

The grounding and evaluation harness. Every case in `docs/AI-EVAL-CASES.md` runs here,
against stub adapters, with **no API key**.

This directory stays at the repository root deliberately. `CLAUDE.md` names it the
cross-cutting proof layer: it exercises the domain contract independently of either app, and
folding it into `apps/api` would make it look like an API detail rather than the project's
central evidence. Do not move it.

Stub adapters here are test doubles for an external dependency. They are **not** a demo
mode — the running application has no offline path and must never reach them
(`docs/AI-EVAL-CASES.md` Case 25).

## `tests/live/`

Real-provider smoke tests. Requires `GROQ_API_KEY`, costs tokens, runs on `main` only via
the `live-smoke` CI job. Asserts the configured model IDs still resolve and still satisfy
the schema — Groq deprecates models on weeks of notice.
