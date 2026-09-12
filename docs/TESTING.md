# Testing Strategy — STYLELAB

The product must prove that the AI layer is a real system rather than a UI gimmick.

## 1. Test pyramid

```text
                 E2E
               /     \
          Integration
          /           \
      API/Contract     AI eval
         /               \
   Domain/Unit       Component tests
```

## 2. Unit tests

Test pure functions:

- outfit compatibility
- colour scoring
- silhouette scoring
- deterministic ranker
- style profile normalization
- price totals
- event payload validation
- job state transitions

Target:
high coverage on deterministic domain code.

## 3. API integration tests

Use FastAPI test client / HTTP-level tests.

Cover:
- valid requests
- invalid schemas
- auth/ownership
- job creation
- retry behavior
- provider timeout
- invalid AI output
- invalid SKU
- delete asset

## 4. Contract tests

Validate:
- API request/response schemas
- database model constraints
- CommerceAdapter contract
- VirtualTryOnProvider contract
- AnalyticsClient contract

## 5. Frontend component tests

Cover:
- garment selection
- filters
- dialogs/bottom sheets
- generation states
- result cards
- remix controls
- error states
- keyboard interaction

## 6. E2E tests

Use Playwright.

Critical flow:

```text
Landing
→ Demo
→ Composer
→ Compose
→ Generation
→ Result
→ Remix
→ Save
```

Additional:
- invalid upload
- retry
- mobile viewport
- delete image

## 7. Accessibility

Automated:
- axe/playwright accessibility checks

Manual:
- keyboard
- focus
- reduced motion
- semantic labels
- screen-reader sensible names

## 8. Visual regression

Use Playwright screenshots for:
- landing desktop/mobile
- composer
- generation
- result
- remix
- planner

Only approve intentional diffs.

## 9. AI evaluation

Keep fixtures in:
`tests/ai/fixtures`

Each fixture has:
- input style profile
- candidate catalogue
- expected allowed SKU set
- expected category roles
- prohibited outputs
- minimum constraints

Example checks:
- 100% returned IDs exist
- no unknown SKU
- category composition valid
- requested occasion satisfied
- stated reasons do not assert unavailable facts

AI tests must be able to run in mock mode without API calls.

## 10. Reliability testing

Test:
- duplicate generation requests
- retries
- stale job polling
- provider timeout
- malformed provider response
- result missing from storage
- partial persistence

## 11. Performance

Measure:
- initial page load
- route transitions
- image load
- API latency
- AI latency
- generation duration

Use seeded load tests for API endpoints where appropriate.

## 12. Security tests

- upload MIME spoofing
- oversized upload
- unauthorized asset access
- unauthorized outfit access
- prompt injection fixtures
- secret scanning
- dependency audit

## 13. Release gates

Block release on:
- failed build
- failed typecheck
- failed lint
- failed unit tests
- failed critical E2E
- critical accessibility violation
- critical security issue
- AI grounding regression
