# PHASE 4 — Catalogue + AI Recommendation Layer

Build the domain layer.

Implement:
- garment schema
- catalogue repository
- deterministic filtering
- compatibility scoring
- LLM adapter
- structured output schema
- outfit ranker
- validation that every returned product ID exists

Preferred scoring:
style compatibility
colour harmony
silhouette balance
occasion fit
preference match
trend score

The LLM may rank/explain candidates but may never invent SKU data.

Add tests for:
- invalid SKU rejection
- incompatible category combinations
- deterministic filtering
- schema validation
- stable ranking

Acceptance:
Given a style profile + selected garments, return a valid outfit composed only of known catalogue items.
