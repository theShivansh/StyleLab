# Deployment

Rewritten in S11, the release phase. What was here before described an intention; this
describes what the application actually does at boot, what it refuses to start without, and
the two things a deployment must run that nothing runs for it.

## The one setting that changes everything

```bash
APP_ENV=production
```

Every default in `apps/api/app/config.py` leans toward *a fresh clone runs*: an ephemeral
signing key, a SQLite file in the working directory, a CORS origin of
`http://localhost:3000`. Each is right on a laptop and broken in a container, and until S11
nothing could tell the difference.

`APP_ENV=production` turns those accommodations into refusals. `app/preflight.py` checks
them all at once and fails with the whole list rather than one at a time, because an
operator fixing three settings one deploy apiece is three container builds to learn three
things that were knowable before the first.

**Fatal in production:**

| Setting | Why it cannot be left | What happens if it is |
|---|---|---|
| `SESSION_SECRET` | signs session tokens and image capabilities | a deploy logs everyone out; a second replica rejects the first's tokens, so a wardrobe vanishes roughly half the time |
| `DATABASE_URL` | otherwise SQLite in the working directory | a container filesystem does not survive a deploy; every wardrobe is deleted on the next release |
| `WEB_ORIGIN` | the CORS allow-list | preflight refuses the deployed front end and every request fails in a way that looks like the API being down |

`SESSION_SECRET` must be at least 32 characters. A short one is worse than none: unset
generates 256 random bits and logs a warning, while `SESSION_SECRET=stylelab` is silent and
forges every token in the system to anyone who guesses the product name.

**Warned, not fatal:** `EXA_API_KEY` (the Trend Scout is skipped and every composition
discloses degradation 2 — outfits are unaffected) and `SUPABASE_URL` (see *Storage* below).

## Environment

### API — required

```bash
APP_ENV=production
GROQ_API_KEY=                      # no demo mode; boot fails without it
DATABASE_URL=                      # postgresql+psycopg://…
SESSION_SECRET=                    # 32+ chars, e.g. `openssl rand -base64 32`
WEB_ORIGIN=https://your-web-host   # exactly one origin, never a wildcard
```

### API — optional, with the defaults that apply

```bash
# Models. These and .env.example are the only two places a model id may appear.
GROQ_TEXT_MODEL=openai/gpt-oss-120b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
GROQ_VISION_FALLBACK_MODEL=qwen/qwen3.6-27b   # availability only, never for quality
GROQ_VISION_MAX_TOKENS=2048                   # a correctness setting, not a cost one

# Trends. Required for the Trend Scout and for nothing else.
EXA_API_KEY=
EXA_SEARCH_TYPE=auto
EXA_MAX_RESULTS=8
EXA_TIMEOUT_S=8.0
TREND_CACHE_TTL_S=86400
TREND_REGION=global
TREND_MAX_AGE_DAYS=120             # articles older than this are dropped

# Agents
AGENT_LATENCY_BUDGET_MS=15000
AGENT_MAX_OUTPUT_TOKENS=800
AGENT_TREND_SCOUT_ENABLED=true

# Uploads
MAX_UPLOAD_BYTES=10485760
MAX_IMAGES_PER_BATCH=12
MIN_IMAGE_EDGE_PX=128
MAX_IMAGE_PIXELS=40000000
ANALYSIS_MAX_EDGE_PX=1024

# Rate limits (S11). One window, three quotas. See "Rate limiting" below.
RATE_LIMIT_WINDOW_S=900
RATE_LIMIT_IMAGES=24               # images, not requests
RATE_LIMIT_COMPOSES=12
RATE_LIMIT_SESSIONS=10             # per client address

# Operations. Enables GET /internal/db-activity; unset means that endpoint answers 503.
# Not a session secret and deliberately a separate variable — see "Database activity" below.
DB_ACTIVITY_TOKEN=

# Storage and identity
STORAGE_ROOT=var/uploads
STORAGE_BUCKET=stylelab-private
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SESSION_TTL_S=2592000
IMAGE_URL_TTL_S=1800
CONFIDENCE_FLOOR=0.7
```

### Web

```bash
NEXT_PUBLIC_API_URL=https://your-api-host
```

`NEXT_PUBLIC_API_URL` is read at **build** time, twice: by the application and by the
Content-Security-Policy in `apps/web/next.config.ts`, which has to name the API origin
because the browser both fetches from it and loads `<img>` capabilities from it. Changing
where the API lives means a rebuild, not a restart.

Never expose a server-only variable through `NEXT_PUBLIC_*`. `GROQ_API_KEY` must never reach
the browser, and CI must pass with it unset.

## Two things a deployment must run

### 1. Migrations

```bash
cd apps/api && alembic upgrade head
```

`create_all` is **not** called when `APP_ENV=production` (S11). It would be actively
harmful: it creates whatever is missing, which papers over a migration that did not run and
leaves the database in a state no revision describes.

Boot then verifies the schema matches the models and refuses to serve if it does not. That
check exists because of a failure observed during the S11 audit itself: a local database
created by `create_all` before `assets.purged_at` was added kept working until a query
touched the column, at which point every upload returned *"Something went wrong on our
side"* — a correct message for an unclassified error and a useless one for a problem with a
one-line fix.

`alembic upgrade head --sql` prints the SQL instead of running it, for review.

### The Postgres driver

`psycopg[binary]` is a declared dependency as of S12. It was not before, and this file had
been telling operators to set `postgresql+psycopg://` since S11 — an instruction and a
dependency list that had never been in the same room. The container would have built and
then failed at boot on `ModuleNotFoundError`. `tests/test_migrations.py` now reads the URL
scheme out of *this file* and asserts `pyproject.toml` declares it, so the two cannot drift
apart again.

### Connecting to Supabase specifically

Use the **Session pooler** string from Project Settings → Database, not the direct one:

```
postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Two reasons, both of which produce confusing failures otherwise. The direct host
(`db.<ref>.supabase.co`) resolves to IPv6 only, and plenty of container platforms have no
IPv6 route — the symptom is a connection timeout that looks like a firewall. And the
*transaction* pooler on port 6543 does not support the server-side prepared statements
SQLAlchemy uses by default, which surfaces later as intermittent `prepared statement
"__asyncpg_" already exists` style errors rather than as a clean failure at boot.

Note the scheme: Supabase shows `postgresql://`, and SQLAlchemy needs `postgresql+psycopg://`
to select the driver this project installs.

**A database that predates the migrations** (created by `create_all` before S11) is not
described by any revision — `upgrade` will fail on tables that already exist, and stamping
it would claim a schema it does not have. Either recreate it, or apply the missing columns
by hand and then `alembic stamp head`.

### 2. The retention sweep

`RetentionSweeper` runs inside the API process: once at boot, then hourly. It unlinks the
stored bytes of any asset whose thirty-day window has closed, which is what makes
`DELETE /wardrobe/items` true at the filesystem level rather than only in a column.

It is in-process, so **a deployment that scales to zero must run the sweep as a scheduled
job instead** — otherwise the timer simply never fires and deletion silently stops
happening. The sweep is idempotent and safe to run concurrently, so two replicas both
running it costs nothing.

## Database activity

`GET /internal/db-activity` runs `SELECT 1` through the application's own engine and returns
a dialect, a duration and a timestamp. `.github/workflows/db-activity.yml` calls it daily and
on `workflow_dispatch`.

It exists because a Supabase project on the free tier pauses after a stretch with no
database activity, and a paused project means the next visitor meets a cold start or an
outage. **It is a real connectivity check rather than a keep-alive dressed as one**: if
Postgres is unreachable, misconfigured, out of connections or asleep, the scheduled job goes
red. A workflow that pinged a static route would keep the project awake and tell nobody
anything.

| Where | Name | Value |
|---|---|---|
| API environment | `DB_ACTIVITY_TOKEN` | 32+ random characters |
| GitHub Actions → Secrets | `DB_ACTIVITY_TOKEN` | the same value |
| GitHub Actions → Variables | `API_BASE_URL` | the API origin, no trailing path |

The same value in both places, and nowhere else — not in `.env.example`, not in this file,
not in the workflow. The workflow passes it to `curl` on **stdin** via `--config -` rather
than as an argument, because arguments are visible in the process list and are echoed by
`set -x`.

Behaviour:

- correct token → `200` with `{"database": "ok", "dialect": …, "latency_ms": …}`
- missing or wrong token → `401`
- `DB_ACTIVITY_TOKEN` unset → `503`, not `200`. Unconfigured is closed, not open

The response never contains the database URL, a host or a user. A Postgres URL carries a
password, which is the same reason the boot log records only the dialect.

**It deliberately does not use `/health`.** That endpoint is liveness-only by design: it
answers without touching the database so a dependency outage is reported through the error
envelope rather than by making the container look dead to an orchestrator that would then
restart it. Giving it a query would turn every Postgres hiccup into a restart loop.

To verify by hand:

```bash
curl -i -H "X-DB-Activity-Token: $DB_ACTIVITY_TOKEN" https://<api-host>/internal/db-activity
```

Or from GitHub: Actions → **DB activity** → Run workflow.

## Storage

`LocalObjectStore` writes to `STORAGE_ROOT`, which must be a **mounted volume**. There is no
hosted `ObjectStore` implementation yet (blocker B20), so a container with an ephemeral
filesystem loses every photograph on the next deploy. Preflight warns about this rather than
refusing, because refusing would mean no deployment could start at all.

## Rate limiting

There is no authentication (blocker B15): `POST /session` mints a token for anyone who asks,
and that token reaches an endpoint that calls a metered vision model once per photograph. So
the exposure is not "someone floods the API", it is **someone drains the provider budget**,
from a URL that is public by design.

Three token buckets — uploads (charged **per image**), compositions, and new sessions (per
client address). Over-quota is `429 RATE_LIMITED` with a `Retry-After`.

The buckets are in-process, so the limit is **per instance**: two replicas allow twice as
much. Size accordingly, or put a limiter in front. The interface takes a key and a cost, so
Redis replaces the storage without touching a caller.

Behind a proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy>`. The
session limiter keys on `request.client.host`, and without that it sees the proxy's address
for every caller — one shared bucket for the internet. The API deliberately does not read
`X-Forwarded-For` itself: an unvalidated one is a limiter an attacker switches off by
setting a header.

## Response headers

Set by `apps/web/next.config.ts` (S11): `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and
`poweredByHeader: false`.

`script-src` still needs `'unsafe-inline'` for Next's inlined bootstrap and flight data;
a nonce through middleware is blocker B21. `'unsafe-eval'` is added **only** when
`NODE_ENV !== "production"`, because React's development build needs it — found by loading
the page, which rendered blank until the console explained why.

## Boot sequence

In order, in `app/main.py`:

1. settings load — `GROQ_API_KEY` absent is a `ValidationError` here
2. log redaction installed, before the first request can write an image token to a log
3. `verify_deployment` — the environment table above
4. `verify_models` — every configured model id resolves against Groq's live list. A model
   that does not resolve is **fatal**; a list call that fails is logged at ERROR and
   tolerated, because the check's own dependency can be down
5. schema verification — `verify_schema`
6. wiring, then the retention sweeper starts

Fail at boot, not at a user's first request. Groq deprecates models on weeks of notice, so a
deployment that sat idle can wake up broken.

## Hosting

**Frontend:** Vercel. **Backend:** Railway, Render, or another managed container service —
with a persistent volume for `STORAGE_ROOT` and a Postgres instance for `DATABASE_URL`.

```bash
uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port $PORT \
  --proxy-headers --forwarded-allow-ips='*'
```

`--forwarded-allow-ips='*'` is correct only when the container is reachable *exclusively*
through the platform's proxy, which is the normal arrangement on both platforms above. If it
is reachable directly, name the proxy instead — otherwise any caller can set their own
address and the session limiter has no floor.

`GET /health` is liveness only and deliberately does not touch the provider: an outage is
reported through the error envelope, not by making the container look dead.

## CI secrets

`GROQ_API_KEY` must be a repository secret for the `live-smoke` job, which runs on `main`
only — fork pull requests cannot read secrets, and real calls cost tokens. Every other job
runs on stub adapters with no key.

## Rollback

Keep deployments immutable. If the provider fails: switch the model configuration and
redeploy. Do not hot-edit application logic in production, and do not add a fallback that
serves a garment the user does not own — there is no rung of the degradation ladder where
that is acceptable, which is the whole point of the ladder.

Migrations are reversible one step at a time (`alembic downgrade -1`), and every revision is
required to have a real `downgrade` — `tests/test_migrations.py` fails if one does not.
