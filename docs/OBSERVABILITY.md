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
- unowned-item grounding failure
- cross-user ownership rejection (alert, never retry)
- median latency
- retry rate
- estimated cost

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
