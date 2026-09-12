# PHASE 5 — Virtual Try-On Job Pipeline

Build a provider-agnostic VTO layer.

Implement:
- upload asset handling
- try-on request
- async job creation
- status endpoint
- provider adapter
- mock provider
- error classification
- retry policy
- image storage abstraction
- result persistence

Frontend:
- meaningful generation stages
- skeleton/preview
- retry
- curated fallback/demo result

Do not couple frontend to a specific VTO vendor.

Acceptance:
- demo provider completes end-to-end
- provider failures are recoverable
- no blocked synchronous HTTP request for the long generation
- job status is observable
