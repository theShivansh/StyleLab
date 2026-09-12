# STYLELAB — Codex Agent Instructions

Read:
- CLAUDE.md
- docs/PRD.md
- docs/ARCHITECTURE.md
- docs/UX-UI-SPEC.md
- docs/TESTING.md
- docs/AI-SYSTEM.md

## Mission

Build STYLELAB as a production-minded, company-agnostic AI fashion-commerce application.

## Priorities

1. End-to-end product experience
2. Grounded AI
3. Premium responsive UX
4. Reliability
5. Testing
6. Analytics
7. Deployment readiness

## AI

Default provider: Groq.

Text:
`openai/gpt-oss-120b`

Vision:
`qwen/qwen3.8-27b`

Do not hardcode model IDs throughout the app. Read configuration from environment.

Never trust model output.
Validate structured output and then validate catalogue/business rules.

## UI

Use Skiper UI and Vengeance UI selectively.
Do not invent an Animaster package.
Inspect exact source/package before integrating it.

## Tests

Every meaningful feature must include tests.
Critical path must have E2E coverage.
AI behavior must have deterministic fixtures.

## Done

Do not declare completion until:
- lint passes
- typecheck passes
- unit tests pass
- integration tests pass
- critical E2E passes
- build passes
- accessibility smoke passes
- AI evaluation passes
- docs are updated
