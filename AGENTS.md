# STYLELAB — Codex Agent Instructions

Read:
- CLAUDE.md
- docs/PRD.md
- docs/ARCHITECTURE.md
- docs/UX-UI-SPEC.md
- docs/TESTING.md
- docs/AI-SYSTEM.md

## Mission

Build STYLELAB as a production-minded AI wardrobe stylist: the user photographs clothes
they own, a vision model extracts structured garment data, and outfits are composed only
from that wardrobe. No commerce, no merchant links, no try-on rendering.

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
garment extraction — default model ID is an open decision, see docs/DECISIONS.md

Do not hardcode model IDs throughout the app. Read configuration from environment.

Never trust model output.
Validate structured output, then business rules, then ownership — every item ID must
belong to the requesting user. Scope retrieval in SQL, not in prompt text.

## UI

Use Vengeance UI (primary) and Skiper UI (secondary, free tier, attribution required).
"Animaster" does not exist — do not import it. Both approved libraries are shadcn
source-drop registries; see docs/DECISIONS.md for terms. Inspect source before integrating.

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
