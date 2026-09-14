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
discloses degradation 2 — outfits are unaffected) and `STORAGE_BACKEND` (see *Storage*
below). The storage warning used to key on `SUPABASE_URL`, which was the wrong question: a
deployment can have a Supabase project — this one does, for its database — and still be
writing photographs to a container disk that will not survive the next release.

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
# Models. This file and the adapter config are the only two places a model id may appear.
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
AGENT_LATENCY_BUDGET_MS=30000      # 15000 timed out every second compose on an 8,000 TPM tier
AGENT_MAX_OUTPUT_TOKENS=600
AGENT_REASONING_EFFORT=low         # agents only; the provider default truncated the crew's JSON
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
TRUSTED_PROXY_HOPS=0               # proxies in front; 1 on a managed platform

# Operations. Enables GET /internal/db-activity; unset means that endpoint answers 503.
# Not a session secret and deliberately a separate variable — see "Database activity" below.
DB_ACTIVITY_TOKEN=

# Storage and identity
STORAGE_BACKEND=local              # `local` or `database` — see "Storage" below
JOB_BACKEND=memory                 # `memory` or `database` — see "Jobs" below
STORAGE_ROOT=var/uploads           # only read when STORAGE_BACKEND=local
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

**Run by a person, from anywhere with the production `DATABASE_URL`.** FastAPI Cloud has no
release phase and no start command to hang this on, and that is the right answer rather than
a gap: the platform autoscales and rolls out gradually, so a migration at process start would
race between instances, and old code and new code are live at the same time regardless.

That means the ordering rule is the operator's to keep, and it is the ordinary one:

- **adding** something (a column, a table) — migrate **before** deploying the code that uses
  it, because the running old code must tolerate the new schema
- **removing** something — deploy the code that stopped using it **first**, migrate after

**That rule was not true of this codebase until S13b**, and it is worth knowing why. Boot's
schema check refused *any* difference, including a table the running release had never heard
of — so migrating first would have stopped the live release surviving its next cold start,
which on a platform that scales to zero is minutes away. Deploying first fails too, because the
new release is missing its table. The check now tolerates what the database has and the models
do not, and refuses only what the models need and the database lacks. That asymmetry is what
makes "add, then deploy" safe. An additive column must be nullable or carry a server default,
or the release still running will fail its inserts.

Migrations 0002 (`asset_blobs`) and 0003 (`jobs`) are both additive and unused by default:
apply them, deploy, then set `STORAGE_BACKEND=database` and `JOB_BACKEND=database`.

Nothing has to remember to check afterwards. Boot verifies the schema against the models and
refuses to serve if they differ, so a deployment that went out ahead of its migration fails
verification and the platform keeps the previous version running. A missed migration is a
failed deploy rather than a working site with a broken page.

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

It is in-process, so on a platform that scales to zero the hourly timer stops with the
instance. What saves it is that the sweep also runs **once at boot**, and a runtime that
scales to zero boots often — every cold start is a sweep. The honest bound is therefore *an
expired photograph is erased the next time somebody uses the product*, not *within an hour*,
and an application nobody opens for a month erases nothing in that month.

That is acceptable here and would not be under a deletion SLA. The fix if it ever matters is
the same shape as `db-activity`: a scheduled workflow calling a token-protected endpoint. The
sweep is idempotent and safe to run concurrently, so two replicas both running it costs
nothing.

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

## Jobs

`JOB_BACKEND` picks where async job records live — an upload's analysis and a composition,
each followed by the browser through `GET /jobs/{id}`.

| Value | Where records live | Correct when |
|---|---|---|
| `memory` (default) | the process that created the job | a laptop, or exactly one process forever |
| `database` | a `jobs` row in `DATABASE_URL` | anything with a rollout, a restart or a second replica |

**On FastAPI Cloud it must be `database`.** Found by the deployed site rather than by review:
an upload reached one instance, the poll after it reached another, and the card read *"That
item isn't in your wardrobe"* for a photograph that was being read correctly.
`apps/api/tests/test_jobs_across_instances.py` reproduces it with two applications over one
database, and shows the database store closing it.

The record moved; the work did not. Analysis still runs in the process that accepted the
upload, so an instance stopped mid-extraction leaves its job `processing` until the client's
ninety-second ceiling offers a retry. A durable queue is still blocker B14.

The web client no longer depends on this alone. A job that answers 404 makes the card re-read
the garment, whose status lives in the database every instance shares, and a passing 5xx or
dropped connection is retried a few times before a card gives up
(`apps/web/src/lib/analysis-poll.ts`).

## Storage

`STORAGE_BACKEND` picks one of two `ObjectStore` implementations. Nothing above
`app/services/storage.py` knows which one it holds.

| Value | Where bytes go | Correct when |
|---|---|---|
| `local` (default) | a directory at `STORAGE_ROOT` | a laptop, or a host with a volume mounted there |
| `database` | an `asset_blobs` row in `DATABASE_URL` | a runtime with no durable disk |

**On FastAPI Cloud it must be `database`.** Not as a preference — `local` there is wrong. The
platform scales to zero when idle and replaces containers on every release, so the directory
stops existing between two visits while the `assets` rows pointing into it do not. The
product then looks like it remembers a wardrobe and shows broken pictures of it, which is a
worse failure than losing the wardrobe outright because it takes longer to notice.

A bucket would still be better and is still blocker B20. The database is what was reachable
without adding a vendor, a credential and an adapter to a deployment that already has a
Postgres — and unlike a volume, it is shared by every replica, which a disk is not.

What it costs: one row per photograph, up to `MAX_UPLOAD_BYTES`. Postgres stores a `bytea`
that size out of line and compresses it, and the ingest path stores a re-encoded image rather
than the original upload, so the practical figure is a few hundred kilobytes each. Against a
free tier's 500 MB that is roughly a thousand garments — comfortable for a demo, and the
first thing to move to a bucket if this ever carries real use. The thirty-day retention sweep
deletes these rows on exactly the same schedule as it deleted the files.

Preflight warns when a production boot leaves `STORAGE_BACKEND=local` rather than refusing,
because a mounted volume is a perfectly good answer and preflight cannot see whether there is
one.

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

**Behind a proxy, set `TRUSTED_PROXY_HOPS`.** The session limiter keys on the caller's
address, and on a managed platform every request arrives from the platform — so left at `0`
the whole internet shares one bucket and the eleventh visitor in fifteen minutes is refused a
session. On FastAPI Cloud the value is `1`.

It is a count of proxies rather than a switch because the entry to believe is the one the
nearest trusted proxy appended, and `X-Forwarded-For` grows on the right. So the value counts
back from the end: with one proxy in front, the last entry is the address that proxy saw,
which is the one entry a caller cannot write. Reading the leftmost entry instead — the thing
that looks equivalent — is a limiter anyone switches off with a header.

A wrong value fails safe in the over-throttling direction: too many hops, or an entry that is
not an IP address, falls back to the socket peer and everyone shares a bucket again. It never
falls back to trusting something the caller chose.

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

**Frontend:** Vercel, root directory `apps/web`. **Backend:** FastAPI Cloud, application
directory `apps/api`. **Database:** Supabase Postgres.

### The backend

FastAPI Cloud builds from the directory holding `pyproject.toml`, installs the project, and
serves `[tool.fastapi] entrypoint` with `fastapi run`. There is no Dockerfile, no start
command and no port to choose, which removes most of what a deployment file usually carries
and leaves four things this repository has to get right — each one checked by
`apps/api/tests/test_deploy_fastapi_cloud.py`:

| | Where |
|---|---|
| Application Directory `apps/api` | the dashboard, or app Settings |
| `fastapi[standard]` in dependencies | `apps/api/pyproject.toml` — the bare package has no CLI to run |
| `entrypoint = "app.main:app"` | `apps/api/pyproject.toml`, `[tool.fastapi]` |
| `.python-version` | `apps/api/`, and it must match the version CI tests on |

Connecting the GitHub repository deploys every push to the default branch. Only the default
branch — there are no preview deployments for pull requests.

Environment variables go in the dashboard or through `fastapi cloud env set --secret NAME
VALUE`; the secret form cannot be read back afterwards, which is the right shape for
`GROQ_API_KEY`, `SESSION_SECRET`, `DATABASE_URL` and `DB_ACTIVITY_TOKEN`.

Set at minimum:

```bash
APP_ENV=production
STORAGE_BACKEND=database     # `local` has no durable disk here — see Storage
JOB_BACKEND=database         # or a poll that reaches another instance calls a running job missing
TRUSTED_PROXY_HOPS=1         # or every visitor shares one rate-limit bucket
```

### What the plan costs this application

Worth knowing before the first slow morning, because none of it shows up as an error:

- **Scale to zero.** An idle app stops. The next visitor waits for a cold start, and a cold
  start here is not trivial: importing the agent framework takes about fourteen seconds on a
  developer machine and the Hobby plan allows 0.1 CPU with a burst to 0.5. That import happens
  during boot rather than during a request, so the platform absorbs it — but the first person
  after a quiet spell waits for it.
- **512 MB.** The application idles around 80 MB and reaches roughly 190 MB once CrewAI is
  loaded. Decoding images is what is left, and `MAX_IMAGE_PIXELS=40000000` allows a single
  upload that decodes to about 160 MB. A batch of large photographs is the plausible way to
  run out of memory; lower that ceiling before raising anything else.
- **Two replicas, maximum.** The rate-limit buckets are per instance, so the effective limit
  is double what is configured.

`GET /health` is liveness only and deliberately does not touch the provider: an outage is
reported through the error envelope, not by making the container look dead.

### The frontend

Vercel, root directory `apps/web`, with `NEXT_PUBLIC_API_URL` set to the FastAPI Cloud origin.
It is read at **build** time, so changing it is a rebuild rather than a restart — and it must
match `WEB_ORIGIN` on the API in the other direction, or CORS refuses every request in a way
that reads exactly like the API being down.

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
