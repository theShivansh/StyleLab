# PHASE — Groq Integration

Implement the Groq AI layer using the official Groq SDK or its documented OpenAI-compatible interface.

Requirements:

## Configuration

Read:
- GROQ_API_KEY
- GROQ_TEXT_MODEL
- GROQ_VISION_MODEL

Never expose the key to the browser.

## Text orchestration

Use the configured text model for:
- outfit ranking
- concise rationale
- planner composition

Prefer Structured Outputs / JSON Schema where supported.

All strict schemas should:
- define required fields
- set additionalProperties=false
- use explicit enums where useful

## Vision

Use the configured vision model for:
- broad image understanding
- style/garment visual cues
- photo quality feedback

Do not infer unnecessary sensitive attributes.

## Reliability

Implement:
- timeout
- bounded retry
- structured error mapping
- request ID logging
- provider-agnostic interface

## Testing

Create:
- MockGroqProvider
- successful fixture
- malformed output fixture
- unknown SKU fixture
- prompt injection fixture
- timeout fixture

CI must not require GROQ_API_KEY.

## Acceptance

The production adapter talks to Groq.
The domain layer cannot tell whether it is using Groq or the mock adapter.
Invalid AI results never reach the commerce-facing UI.
