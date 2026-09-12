# AI System Specification — STYLELAB

## Goal

Use AI where it creates differentiated value, while keeping deterministic software in control of correctness.

## AI responsibilities

### Vision
Groq multimodal model:
- understand broad visual context
- identify visible garment/category/style cues
- provide non-sensitive style descriptors
- describe image quality issues

### Text reasoning
Groq text model:
- rank candidate outfits
- generate concise styling rationale
- generate planner variations
- classify feedback

### Deterministic application logic
Application code:
- candidate retrieval
- SKU validity
- pricing
- availability
- score aggregation
- access control
- analytics
- persistence

## Prompt contract

Every AI request should specify:
- role
- allowed inputs
- forbidden assumptions
- output schema
- grounding source
- failure behavior

## Example outfit output

```json
{
  "outfit_name": "Minimal Street",
  "garment_ids": ["SKU1", "SKU2", "SKU3"],
  "style_tags": ["minimal", "streetwear"],
  "occasion": "college",
  "reasons": [
    "Neutral palette",
    "Balanced relaxed silhouette"
  ],
  "confidence": 0.87
}
```

## Business validation

Reject if:
- any SKU does not exist
- any SKU is inactive
- category roles conflict
- generated price differs from database
- URL is not database-sourced

## AI fallback hierarchy

1. Groq structured response
2. retry with constrained prompt
3. deterministic ranker
4. curated fallback outfit

Never return an invented catalogue object.

## Evaluation categories

- schema validity
- SKU grounding
- category compatibility
- preference adherence
- diversity
- explanation relevance
- latency
- failure rate

## Cost controls

- limit candidates before LLM
- short structured outputs
- no unnecessary repeated image analysis
- cache stable profile analysis
- use lower-cost model for simple tasks when configured
- record estimated usage for evaluation

## Prompt injection defense

Product/user text is untrusted.

Do not allow:
- product descriptions
- user notes
- image text
to override system instructions.

Treat catalogue fields as data, not executable instructions.
