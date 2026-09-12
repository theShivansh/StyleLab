# Security & Privacy — STYLELAB

## Image handling

Before upload, explain:
- why the photo is needed
- how it is used
- how the user can delete it

Limit:
- file size
- MIME types
- resolution where appropriate

Reject unsupported formats safely.

## Storage

Use private object storage for personal images.

Use signed access where possible.

Demo/static product images may be public.

## Secrets

Never expose:
- LLM API keys
- VTO provider keys
- database service-role keys

Use environment variables on the server.

## API

Apply:
- authentication
- authorization
- ownership checks
- rate limiting
- input validation
- request IDs

## AI safety/product integrity

AI output is untrusted data.

Validate:
- schema
- garment IDs
- product existence
- product state

Never trust an LLM-generated:
- price
- availability
- URL
- SKU
- brand

## Sensitive attributes

Do not infer, persist, or display unnecessary sensitive personal attributes.

Style and appearance preferences should be explicit and user-controlled.

## Logging

Use structured logs without raw uploaded image content.

## Deletion

User-triggered image deletion should have a clear success/failure state.

Document retention behavior in production deployment notes.
