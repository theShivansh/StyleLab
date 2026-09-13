# Observability — STYLELAB

## Logs

Structured JSON logs.

Required fields:
- timestamp
- level
- service
- request_id
- route
- duration_ms
- error_code

AI requests additionally:
- provider
- model
- operation
- job_id
- estimated token usage if available

## Metrics

### API
- request count
- p50/p95 latency
- 4xx
- 5xx

### AI

Computed from the `GenerationEvent` stream by `generation_metrics()` in
`apps/api/app/services/telemetry.py`. One event per model **call**, not per request, which
is what makes the retry and fallback figures mean anything. The rollup is product code
rather than a query somebody writes later: a metric nothing computes is a metric nobody can
be shown, and `apps/api/tests/test_telemetry.py` computes this whole list from a
deliberately unhealthy stream and fails if any line of it is not derivable.

- model calls
- success rate — `ok` only. A schema-valid, confident response naming somebody else's
  garment is a failure here, not a success with a caveat.
- schema failure rate
- unowned-item grounding failure
- median latency, and p95 by nearest rank (not interpolated: with four calls in a minute
  the honest 95th percentile is the slowest one)
- retry rate
- timeouts and provider errors, counted separately — "the model was slow" and "the model was
  broken" have different fixes
- estimated cost, **in tokens**. Never currency: a price per token hardcoded in the service
  would be right for one plan on one day, would go stale silently, and would be believed.

**Not emitted: cross-user ownership rejection, as a figure distinct from unowned-item
grounding failure.** The domain cannot tell them apart, by design —
`apps/api/app/domain/validation.py` refuses an unexpected id *without looking it up*, so
that no other user's id enters a query on the request path. Both arrive as
`ungrounded_item`, which is logged at CRITICAL and never retried into. Attribution is the
alerting layer's job, and it has admin scope outside the request path. This spec asked for
the split before the architecture existed; the architecture is right and the spec is
corrected here rather than the other way round (docs/DECISIONS.md, S8).

Events carry scalars only — no garment text, no rationale, no raw model output, no storage
key — enforced by walking the annotations. What the model actually said lives on
`item_extractions`, our own table under the wardrobe's retention. An audit trail keeps the
evidence; telemetry keeps the count, and telemetry is what leaves the building.

### Extraction
- jobs started
- completed
- failed
- median duration
- timeout rate

### Product
- composer activation
- generation success
- remix rate
- save rate
- product click rate

## Tracing

Use OpenTelemetry-compatible boundaries where practical.

Trace:
web request
→ API
→ recommendation
→ Groq
→ extraction
→ storage

Do not place raw image payloads or sensitive user data in traces.
