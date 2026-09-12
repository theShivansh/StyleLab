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

## Provider exposure

Sending an image to a model provider is a disclosure. Say so in the privacy copy.

- send the minimum: one garment image per extraction call
- never send a user's face or body photo — the product has no try-on path and no reason
  to hold one
- prefer providers that do not retain inputs for training; record the choice in
  `docs/DECISIONS.md`
- in `APP_MODE=demo` nothing leaves the machine — the deterministic analyzer runs locally

## Secrets

Never expose LLM provider keys or storage service-role keys. Server-side environment
variables only. `GROQ_API_KEY` must never reach the browser, and CI must pass with it unset.

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
