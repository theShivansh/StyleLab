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

## Demo mode without credentials

`APP_MODE=demo` must complete the full upload → wardrobe → outfit path with
`GROQ_API_KEY` unset. There is no seeded demo closet, so the mock cannot simply replay
canned items — it has to respond to whatever the user actually uploaded.

`DeterministicWardrobeAnalyzer` therefore does real, cheap, local analysis:

- **Colour** — measured from the pixels (dominant colour clustering, mapped to a named
  palette). Genuinely derived from the image.
- **Dimensions / quality** — measured: resolution, aspect ratio, brightness, blur proxy.
  Drives the same quality warnings the real path uses.
- **Category / subcategory** — taken from the user's own selection at upload time, which
  the UI asks for anyway as a correction affordance.
- **Fit, formality, tags** — left null with `confidence: 0`, surfaced as "not analyzed in
  demo mode", never guessed.

Everything on screen in demo mode is therefore either measured from the image or supplied
by the user. Nothing is fabricated, so the demo makes no claim the code cannot support.
The adapter satisfies the same interface and the same schema as the Groq analyzer, so the
domain layer cannot tell them apart — which is exactly what Case 01 and Case 11 assert.

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

1. Groq structured response
2. retry with a constrained prompt
3. deterministic ranker over the same candidate set
4. state the gap honestly — "your wardrobe needs a bottom for this" — and stop

There is no curated fallback outfit any more. A curated look would be made of garments
the user does not own, which is precisely the thing the grounding rule forbids.

## Evaluation categories

schema validity · wardrobe grounding · **cross-user isolation** · extraction accuracy ·
extraction honesty · correction persistence · category compatibility · preference
adherence · diversity · explanation relevance · latency · failure rate

## Cost controls

- analyse each image once; cache by checksum, and re-analyse only on explicit request
- prefilter candidates deterministically before the LLM
- short structured outputs
- batch multi-item uploads into one job where the provider allows it
- record estimated usage per extraction

## Prompt injection defence

User images and user text are untrusted.

Text recovered from a photograph — slogans, care labels, tags, handwriting — is data. It
may inform `pattern` or `style_tags`. It may never alter instructions, change the output
schema, or widen retrieval scope. Treat every extracted string as a value, never as an
instruction.
