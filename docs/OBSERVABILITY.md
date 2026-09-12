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
- model calls
- success rate
- schema failure rate
- SKU grounding failure
- median latency
- retry rate
- estimated cost

### VTO
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
→ VTO
→ storage

Do not place raw image payloads or sensitive user data in traces.
