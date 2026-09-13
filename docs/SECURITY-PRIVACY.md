# Security & Privacy — STYLELAB

The pivot raised the stakes here. Users now upload many photographs of their own
possessions, taken inside their homes. Closet imagery is personal data with incidental
background content the user did not intend to share. Treat the wardrobe as sensitive by
default.

## Image handling

Before the first upload, explain plainly:
- why the photos are needed
- that they are stored privately and never shown to anyone else
- how to delete them, and what deletion removes

Validate before storing:
- MIME type allow-list
- byte size ceiling
- resolution bounds
- reject unsupported formats safely, with a message the user can act on

Strip EXIF on ingest — **including GPS**. A photo of a jacket on a bedroom floor should
not carry the user's home coordinates into the database.

## Storage

- private object storage, never a public bucket
- short-lived signed URLs, generated per request
- signed URLs never logged, never sent to analytics, never placed in a query string
- no public product imagery exists any more; there is no "safe to expose" image class

### How the "never in a query string" rule is met (S6)

The token sits in the **path**: `/api/v1/assets/{asset_id}/{token}`. Object stores
conventionally use a query parameter, and doing the same would have meant arguing with this
line about what it meant. A path segment satisfies it literally, works in an `<img src>`
cross-origin with no cookie, and needs no `SameSite` relaxation.

The token is capability-only and short-lived: it names one owner and one asset, it is signed
for the `image` purpose so a session token cannot be substituted, and it is minted fresh on
each read of the item.

**"Never logged" is enforced at the logging layer, not by convention.** Uvicorn's access log
records the request line, which is the path, which is a live credential — so the wardrobe
screen would write a working link to every photograph in the session into a log file.
`apps/api/app/logging_setup.py` redacts the token and keeps the asset id; verified against
the real access log, not only in a unit test.

### EXIF (S6)

Stripped by re-encoding from decoded pixels — Pillow's savers write metadata only when handed
it explicitly, and nothing does. Orientation is **applied first**, or a portrait photograph
is stored on its side. Covers GPS, camera model, serial number, timestamps, thumbnails, ICC
profile, DPI and PNG text chunks. Asserted on the output bytes.

## Provider exposure

Sending an image to a model provider is a disclosure. Say so in the privacy copy.

- send the minimum: one garment image per extraction call
- never send a user's face or body photo — the product has no try-on path and no reason
  to hold one
- prefer providers that do not retain inputs for training; record the choice in
  `docs/DECISIONS.md`
- there is no offline mode: every garment photo the user uploads is sent to Groq. Say so
  in the privacy copy, plainly, before the first upload

## Secrets

Never expose LLM provider keys or storage service-role keys. Server-side environment
variables only. `GROQ_API_KEY` must never reach the browser, and CI must pass with it unset.

`SESSION_SECRET` signs session tokens and image capabilities. Unset, the API generates a
random per-process key and says so at WARNING: nothing can be forged, and the cost is that
tokens stop verifying after a restart. Set it in any environment where a session must survive
a deploy or run on more than one instance — and as of S11, `APP_ENV=production` refuses to
boot without it, along with a `SESSION_SECRET` shorter than 32 characters. A short secret is
worse than an absent one: absent is loud and generates 256 random bits, while
`SESSION_SECRET=stylelab` is silent and forges every token in the system. Never log a database URL either — a Postgres URL
carries a password; log the dialect.

## API

authentication · authorisation · ownership checks on every wardrobe read and write ·
rate limiting on upload and extraction specifically · input validation · request IDs

### Rate limiting (built in S11)

This line sat here from S0 with nothing implementing it, and what made it urgent is what
sits beside it: there is no authentication (blocker B15). `POST /session` mints a token for
anyone who asks, and that token reaches an endpoint that calls a metered vision model once
per photograph. The exposure is not "someone floods the API" — it is **someone drains the
provider budget**, without a credential, from a URL that is public by design.

Three token buckets in `app/services/ratelimit.py`: uploads, compositions, and new sessions.
Uploads are charged **per image**, because one POST carrying twelve photographs is twelve
provider calls and a per-request limit would price them as one. Reads and corrections are
deliberately not limited — a limit there produces a product that refuses to show somebody
their own clothes, against an attacker who could have requested the landing page instead.

Per instance, not per deployment, and said out loud in docs/DEPLOYMENT.md rather than
discovered by someone sizing a cluster against it.

### Request IDs (built in S11)

Every response carries `X-Request-ID`, and every error body repeats it. It matters here
specifically because the user-facing messages are deliberately vague — they never quote a
provider and never say which quota was hit — so without an id a user reporting a problem has
nothing to give support but the time of day.

A caller-supplied id is kept so a trace survives the hop, after being filtered to characters
that cannot forge a header or a log line. Anything else gets ours: an unvalidated header
echoed into both a response header and a log is a header-injection primitive on one side and
log forging on the other.

Return 404, not 403, for an item the caller does not own. Do not confirm that another
user's item exists.

## AI safety / product integrity

AI output is untrusted data.

Validate: schema · item IDs · ownership · item state.

Never trust a model-generated item ID. Never let text recovered from an image act as an
instruction (`docs/AI-EVAL-CASES.md` Case 07).

## Sensitive attributes

Do not infer, persist, or display attributes of the person in a photograph — body shape,
age, gender, ethnicity, or health. The vision model's job is the garment, not the wearer.
Style preferences are explicit and user-controlled.

If a person is visible in a wardrobe photo, extract the garment and say nothing about them.

## Logging

Structured logs with no raw image content, no signed URLs, no extracted free text that
might contain incidental personal information.

## Deletion

- user-triggered deletion has a clear success state
- deletion names its consequences — which outfits become incomplete
- deleting an asset cascades to the wardrobe item
- document retention and the soft-delete window in the deployment notes

A user must be able to remove their entire wardrobe in one action.

### The retention window (built in S11 — blocker B16)

Deletion is **soft, then real**. `DELETE /wardrobe/items/{id}` and `DELETE /wardrobe/items`
set `deleted_at`, the file stops being served immediately, and the garment leaves the
wardrobe. **Thirty days later the bytes are unlinked** by the sweep in
`app/services/retention.py`, and `assets.purged_at` records that it happened.

Until S11 only the first half existed. docs/DATA-MODEL.md wants deletion observable and
reversible by support, which is a good reason for the window and not a reason to stop there
— without the sweep, "delete my photographs" was a statement about a database column while
the photographs sat on a disk indefinitely with nothing scheduled to change that.

Thirty days is stated in the interface, not only here. The privacy copy on the landing page
says it, the confirmation before clearing a wardrobe says it, and
`DELETE /wardrobe/items` returns `images_erased_after_days` — because a retention period the
product does not state is one the user has not agreed to. Changing
`RETENTION_WINDOW_S` without changing those is changing the terms without telling anyone.

A deployment that scales to zero must run the sweep as a scheduled job; the in-process timer
cannot fire in a container that is not running. See docs/DEPLOYMENT.md.

## Response headers (built in S11)

`apps/web/next.config.ts` sets `Content-Security-Policy`, `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, a
`Permissions-Policy` denying camera, microphone, geolocation, payment and USB, and HSTS —
and disables `X-Powered-By`.

Until the release audit there were none of these. The product serves private photographs of
the inside of people's homes and was taking every default a browser applies when a site says
nothing, which are the permissive ones. `frame-ancestors 'none'` is the one that stops a
clickjacking overlay over somebody's wardrobe; `Referrer-Policy` is the one that stops an
outfit URL leaking to the publications cited on the result screen.

`script-src` still carries `'unsafe-inline'` for Next's inlined bootstrap and flight data.
Named rather than quietly omitted — it is the one directive weaker than it looks, and a
nonce through middleware is blocker B21.
