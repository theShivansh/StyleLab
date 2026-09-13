---
title: STYLELAB API
emoji: 👕
colorFrom: gray
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
short_description: Reads photos of clothes you own and styles outfits from them.
---

# STYLELAB API

The backend for [STYLELAB](https://github.com/) — an AI wardrobe stylist. The user
photographs clothes they own, a vision model turns those photos into structured garment
data, and a crew of agents composes outfits **only** from that wardrobe. It sells nothing
and links to no merchant.

This Space is the API. The web app is deployed separately.

## This Space will not start without secrets

There is no demo mode. A missing key is a loud boot failure, never a silent downgrade into a
stub — so the four below are not optional, and the container will tell you which one is
missing rather than serving something fabricated.

Set these under **Settings → Variables and secrets**.

| Name | Kind | Value |
|---|---|---|
| `GROQ_API_KEY` | secret | from console.groq.com |
| `SESSION_SECRET` | secret | 32+ random characters — `openssl rand -base64 32` |
| `DATABASE_URL` | secret | a Postgres URL (see below) |
| `WEB_ORIGIN` | variable | the deployed web app's origin, e.g. `https://stylelab.vercel.app` |
| `APP_ENV` | variable | `production` |
| `EXA_API_KEY` | secret | optional — without it the Trend Scout is skipped |
| `DB_ACTIVITY_TOKEN` | secret | 32+ random characters, matching the GitHub Actions secret of the same name |

`DATABASE_URL` is a secret rather than a variable because a Postgres URL carries a password.
Nothing logs it; the boot line records the dialect only.

## Why `DATABASE_URL` matters more here than elsewhere

**A Space's filesystem does not survive a restart** unless persistent storage is attached.
Without an external database the wardrobe is gone the next time the container sleeps and
wakes — which on the free tier happens after 48 hours of inactivity, and on any tier happens
whenever the Space is rebuilt.

With `APP_ENV=production` the API refuses to boot without `DATABASE_URL` for exactly this
reason, and the refusal names it. Any free Postgres works: Supabase, Neon, Railway.

With Supabase, use the **Session pooler** string and change the scheme to
`postgresql+psycopg://`. The direct host is IPv6-only, which a Space may not be able to
route, and the transaction pooler on 6543 breaks SQLAlchemy's prepared statements. Full note
in `docs/DEPLOYMENT.md`.

A free Supabase project also **pauses** after a stretch of inactivity. `GET
/internal/db-activity` and the daily GitHub Actions workflow exist to prevent that, and to
turn a sleeping or unreachable database into a red build rather than a bad first impression.

Uploaded **images** have the same problem and no equivalent fix here: `STORAGE_ROOT`
defaults to a path inside the container. Attach persistent storage and point it at
`/data/uploads`, or accept that photographs last as long as the container does. This is
recorded as blocker B20 rather than papered over.

## Cold start

First request after a sleep is slow — the agent framework takes about thirteen seconds to
import, and the boot check verifies every configured model id against Groq's live list
before serving. That check is deliberate: Groq deprecates models on weeks of notice, and a
deployment that sat idle can wake up configured for a model that no longer exists. Better to
find out in a boot log than in a user's first upload.

## Endpoints

`GET /health` is liveness only and deliberately does not touch the provider — an outage is
reported through the normal error envelope, not by making the container look dead.

The API surface is documented at `/docs`, and in full in `docs/API-SPEC.md` in the source
repository.

## Rate limits

Three token buckets, because there is no authentication and the upload path calls a metered
vision model once per photograph: 24 images, 12 compositions and 10 new sessions per
15 minutes. Over-quota is `429` with a `Retry-After`.
