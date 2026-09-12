# PHASE 4 — Wardrobe Domain + AI Recommendation Layer

Build the domain layer. No Groq in this phase — interfaces and mocks only. Phase 12
wires the real provider in behind them.

Implement:
- `wardrobe_item` schema and repository
- **ownership-scoped retrieval** — every query filters on `user_id`; there is no
  unscoped read path, not even for admin or debug
- deterministic filtering by role and compatibility
- compatibility scoring
- `WardrobeAnalyzer` interface (Groq implementation lands in phase 12)
- `OutfitAdvisor` interface (agent crew lands in phase 14)
- `DeterministicRanker` — a degradation step in the fallback ladder, not a product mode
- stub implementations for `tests/ai/` only
- structured output schemas for extraction and for ranking
- ownership re-validation of every model-returned item ID
- `item_extractions` audit writes, including rejected attempts
- `corrected_fields` handling — a user correction is never recomputed
- insufficient-wardrobe detection that names the missing roles

Preferred scoring:
style compatibility · colour harmony · silhouette balance · occasion fit ·
preference match · wardrobe variety

The LLM may rank and explain candidates. It may never introduce an item ID that was not
in the retrieved candidate set.

`DeterministicRanker` is the fourth rung of the fallback ladder in `docs/AI-SYSTEM.md` —
it ranks owned items without an LLM when the crew is unavailable. It is not a demo mode
and the app must never route to it while the provider is healthy.

Add tests for — **write them red first, then green**:
- an item ID outside the candidate set is rejected
- **an item belonging to another user is rejected even when injected into a crafted
  model response** (`docs/AI-EVAL-CASES.md` Case 11)
- incompatible category combinations
- insufficient wardrobe returns a named gap, never a partial outfit
- a corrected field survives re-analysis
- deterministic filtering is stable
- schema validation rejects malformed and truncated output

Acceptance:
Given a user's wardrobe and a style profile, return a valid outfit composed only of items
that user owns — or an honest statement of what is missing. There is no curated fallback.
