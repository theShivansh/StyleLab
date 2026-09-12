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
- colour extraction from pixels (demo analyzer)
- confidence-floor logic
- corrected_fields merge on re-analysis
- missing-role detection
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
- an item ID outside the candidate set
- **an item owned by another user (must 404, not 403)**
- insufficient wardrobe
- multi-image upload with one bad file
- delete asset and its cascade

## 4. Contract tests

Validate:
- API request/response schemas
- database model constraints
- WardrobeAnalyzer contract (live and stub implementations indistinguishable to the domain)
- OutfitAdvisor contract
- TrendSource contract — every note carries source + published_at
- AnalyticsClient contract

## 5. Frontend component tests

Cover:
- multi-image picker
- progressive analysis cards
- confidence hedging and inline correction
- wardrobe grid
- filters
- dialogs/bottom sheets
- analysis and composition states
- result cards
- swap controls
- insufficient-wardrobe state
- error states
- keyboard interaction

## 6. E2E tests

Use Playwright.

Critical flow:

```text
Landing
→ Upload 3+ photos
→ Analysis
→ Review / correct a field
→ Compose
→ Result
→ Swap
→ Save
```

E2E runs against stub adapters — test doubles, not a product mode. This is the recruiter
path, so it is `@critical`. Real-key coverage lives in the `live-smoke` CI job on main.

Additional:
- invalid upload, and a batch where one file of several is invalid
- correction persists through regeneration
- insufficient wardrobe
- retry
- mobile viewport
- delete image and see dependent outfits marked incomplete

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
- upload + analysis
- wardrobe grid
- result
- swap
- planner

Only approve intentional diffs.

## 9. AI evaluation

Keep fixtures in:
`tests/ai/fixtures`

Each fixture has:
- input style profile
- the owning user's wardrobe
- **a second user's wardrobe, to prove isolation**
- expected allowed item-ID set
- expected category roles
- prohibited outputs
- minimum constraints

Example checks:
- 100% of returned IDs exist AND belong to the requesting user, through the full crew
- every trend note carries source and published_at, or was dropped
- no brand, price, merchant or link in any advisory field
- no unowned item, including under a crafted/forged model response
- category composition valid
- requested occasion satisfied
- stated reasons do not assert facts the system does not hold
- guessed fields are never phrased as observations

AI tests run on stub adapters with no API calls. This keeps the regression suite
deterministic, free, and runnable on fork pull requests — a suite that costs money per run
stops being run. Real-key coverage is the `live-smoke` CI job on main.

### Agent ablation

`tests/ai/test_ablation.py` disables each agent role in turn and asserts the output
changes materially. A role that can be removed without changing the result is decoration.
This test is the difference between a multi-agent system and multi-agent theatre — run it
before claiming the crew adds value.

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
- prompt injection fixtures: text inside an uploaded image, trend copy from the web, and
  agent-to-agent messages
- a well-formed crew response containing another user's item must still hard-fail
- EXIF/GPS stripped on ingest
- signed URLs absent from logs and analytics
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
