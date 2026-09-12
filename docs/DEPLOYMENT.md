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
- `WARDROBE_ANALYZER`
- `MAX_UPLOAD_BYTES`
- `STORAGE_BUCKET`
- `SENTRY_DSN`

Never expose server-only variables through `NEXT_PUBLIC_*`.

## Runtime requirements

There is no demo mode and no offline path. `GROQ_API_KEY` is required; the application
fails loudly at boot without it rather than degrading into a stub.

At startup, verify:
- `GROQ_API_KEY` present and accepted
- `GROQ_TEXT_MODEL`, `GROQ_VISION_MODEL` and `GROQ_VISION_FALLBACK_MODEL` all resolve
  against Groq's live model list
- `TREND_CORPUS_PATH` readable, and its newest entry within `TREND_MAX_AGE_DAYS`
  (a stale corpus is a warning and disables the Trend Scout, not a boot failure)

Fail at boot, not at a user's first request. Groq deprecates models on weeks of notice,
so a deployment that sat idle can wake up broken.

## CI secrets

`GROQ_API_KEY` must be present in repository secrets for the `live-smoke` job. That job
runs on `main` only — fork pull requests cannot read secrets, and real calls cost tokens.
Every other CI job runs on stub adapters with no key.

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
