# Deployment

## Frontend

Recommended:
Vercel

Environment:
- `NEXT_PUBLIC_API_URL`
- public analytics key only where appropriate

## Backend

Recommended:
Railway / Render / another managed container service.

Environment:
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GROQ_API_KEY`
- `GROQ_TEXT_MODEL`
- `GROQ_VISION_MODEL`
- `VTO_PROVIDER`
- `VTO_API_KEY`
- `STORAGE_BUCKET`
- `SENTRY_DSN`

Never expose server-only variables through `NEXT_PUBLIC_*`.

## Demo mode

Set:

`APP_MODE=demo`

Demo mode must:
- use seeded catalogue
- use deterministic profile
- use pre-generated VTO
- exercise the same frontend state machine
- avoid requiring external secrets

## Production mode

Set:
`APP_MODE=production`

Production provider availability should be checked at startup.

## CI

Run:
- install
- lint
- typecheck
- unit tests
- integration tests
- E2E smoke
- build

## Rollback

Keep deployment immutable.

If AI provider fails:
- switch model/provider config
- enable deterministic fallback
- do not hot-edit application logic in production.
