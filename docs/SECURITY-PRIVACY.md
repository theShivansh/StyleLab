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
a deploy or run on more than one instance. Never log a database URL either — a Postgres URL
carries a password; log the dialect.

## API

authentication · authorisation · ownership checks on every wardrobe read and write ·
rate limiting on upload and extraction specifically · input validation · request IDs

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
