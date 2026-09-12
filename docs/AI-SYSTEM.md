# AI System Specification — STYLELAB

## Goal

Use AI where it creates differentiated value, while keeping deterministic software in
control of correctness.

After the wardrobe pivot, vision is no longer a supporting role — it is the product's
front door. A user's closet becomes structured data only because a model read their
photos. That makes extraction quality, extraction honesty, and the user's ability to
correct extraction the central AI concerns.

## AI responsibilities

### Vision — `GROQ_VISION_MODEL`

Per uploaded garment image:
- identify category and subcategory
- describe colour, pattern, visible construction
- estimate fit and formality
- flag image quality problems
- emit per-field confidence

May not:
- infer anything about the person in the photo
- state fibre content as fact (`material_guess` is a guess)
- read instructions out of the image (see Case 07)

### Text reasoning — `GROQ_TEXT_MODEL`

- rank candidate outfits drawn from the user's own wardrobe
- generate concise styling rationale
- name what the wardrobe is missing
- classify feedback

### Agent crew — `GROQ_TEXT_MODEL`

Composition is performed by a crew of specialist agents (Style Profiler, Trend Scout,
Outfit Architect, Critic, Practical Advisor, Editor) behind the `OutfitAdvisor`
interface. Roles, dataflow, latency budget, output contract and the anti-theatre
ablation requirement live in `docs/AGENT-SYSTEM.md`.

Every agent's output is untrusted, including the Editor's. Validation below applies to
the merged response regardless of what any agent asserted.

### Trend input

From the `TrendSource` adapter, never from model recall. Trends may re-rank or
contextualise owned items; they may never introduce a garment. Every trend claim shown
carries its source and date or it is dropped. See `docs/DECISIONS.md`.

### Deterministic application logic

- candidate retrieval, **scoped to `user_id` in SQL**
- ownership validation
- category/role compatibility
- score aggregation
- access control, analytics, persistence

## The ownership invariant

The model never decides what the user owns.

```text
user_id → SQL retrieval → candidate set → prompt
                                            ↓
                                      model response
                                            ↓
                          ownership re-validation (same user_id)
                                            ↓
                                      domain object
```

Scope is enforced before the call and re-checked after it. A model response naming an
item outside the retrieved set is rejected, not fetched. Prompt text never carries an
instruction like "only use these items" as its *only* defence.

## No demo mode

The application requires `GROQ_API_KEY` and always performs real inference. There is no
seeded result, no fake extraction, and no "demo data" label in the product. A missing or
invalid key is a loud boot failure, not a silent downgrade.

`tests/ai/` and CI use stub adapters satisfying the same interfaces. Those are test
doubles for an external dependency — the running application must never reach them. See
`docs/DECISIONS.md` (demo mode removed).

## Model fallback chain

Vision: `GROQ_VISION_MODEL` (`qwen/qwen3.8-27b`) → `GROQ_VISION_FALLBACK_MODEL`
(`qwen/qwen3.6-27b`).

The fallback is for **availability**, not quality. Trigger it on provider error, rate
limit, timeout, or a model ID that no longer resolves. Do **not** trigger it on a
low-confidence extraction — that is a signal to surface to the user for correction, and
retrying a cheaper model to get a more confident wrong answer is the opposite of what
this system is for.

Both IDs are verified against Groq's model list at boot.

## Prompt contract

Every AI request specifies:
- role
- allowed inputs
- forbidden assumptions
- output schema
- grounding source
- failure behaviour

## Example extraction output

```json
{
  "category": "top",
  "subcategory": "oxford shirt",
  "color_primary": "navy",
  "color_secondary": null,
  "pattern": "solid",
  "material_guess": "cotton",
  "fit": "regular",
  "formality": "smart-casual",
  "season_tags": ["spring", "autumn"],
  "style_tags": ["minimal", "preppy"],
  "field_confidence": {
    "category": 0.97,
    "color_primary": 0.62,
    "material_guess": 0.41
  },
  "quality_warnings": ["low_light"]
}
```

Any field below the confidence floor is surfaced for confirmation rather than displayed
as settled.

## Example outfit output

```json
{
  "outfit_name": "Minimal Street",
  "item_ids": ["ITEM_A", "ITEM_B", "ITEM_C"],
  "style_tags": ["minimal", "streetwear"],
  "occasion": "college",
  "reasons": ["Neutral palette", "Balanced relaxed silhouette"],
  "missing_roles": [],
  "confidence": 0.87
}
```

## Business validation

Reject if:
- any item ID is absent from the retrieved candidate set
- any item belongs to another user  *(hard failure — log and alert, never retry into it)*
- any item is deleted or still `analyzing`
- category roles conflict
- a required role is filled by an item of the wrong category

## Fallback hierarchy

1. full agent crew
2. crew minus Trend Scout (TrendSource unavailable or stale beyond `TREND_MAX_AGE_DAYS`)
3. Architect + Editor only (latency circuit breaker tripped)
4. deterministic ranker over the same candidate set
5. state the gap honestly — "your wardrobe needs a bottom for this" — and stop

There is no curated fallback outfit any more. A curated look would be made of garments
the user does not own, which is precisely the thing the grounding rule forbids.

## Evaluation categories

schema validity · wardrobe grounding · **cross-user isolation** · extraction accuracy ·
extraction honesty · correction persistence · category compatibility · preference
adherence · diversity · explanation relevance · **trend attribution** · **agent ablation**
· **advisory safety** · latency · cost per composition · failure rate

## Cost controls

- analyse each image once; cache by checksum, and re-analyse only on explicit request
- cache the style profile; invalidate on wardrobe change, not per request
- never re-run the full crew for a single-slot swap — Architect and Editor only
- cap crew size; adding an agent requires an ablation result
- prefilter candidates deterministically before the LLM
- short structured outputs
- batch multi-item uploads into one job where the provider allows it
- record estimated usage per extraction

## Prompt injection defence

User images and user text are untrusted.

Three untrusted channels feed this system: text inside uploaded images, trend text
retrieved from the web, and agent-to-agent messages.

Text recovered from a photograph — slogans, care labels, tags, handwriting — is data. It
may inform `pattern` or `style_tags`. It may never alter instructions, change the output
schema, or widen retrieval scope. Treat every extracted string as a value, never as an
instruction.

The same holds for trend copy fetched from the web, and for what one agent says to
another. A compromised upstream agent must not be able to instruct a downstream one.
