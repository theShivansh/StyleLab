# Agent System — STYLELAB

A crew of specialist agents on `openai/gpt-oss-120b` via Groq, orchestrated by CrewAI
behind the `OutfitAdvisor` interface. Decision and trade-offs: `docs/DECISIONS.md`.

The point is not that there are agents. The point is that a second opinion, a trend
lens, and a practical-tips lens each change the answer — and each is independently
testable.

## Roles

| # | Agent | Model | Reads | Produces |
|---|-------|-------|-------|----------|
| 1 | Wardrobe Analyst | `GROQ_VISION_MODEL` | one garment image | structured garment metadata + confidence |
| 2 | Style Profiler | text | wardrobe + stated prefs | the user's aesthetic, in their clothes' terms |
| 3 | Trend Scout | text | wardrobe + `TrendSource` | dated, cited trends that apply to owned items |
| 4 | Outfit Architect | text | wardrobe + profile + trends | candidate combinations, roles filled |
| 5 | Critic | text | candidates | proportion, palette, occasion and weather objections |
| 6 | Practical Advisor | text | wardrobe + candidates | pro tips, alternatives, budget tricks, gaps |
| 7 | Editor | text | everything above | one merged, schema-valid response |

The Wardrobe Analyst runs at upload time, once per image. Agents 2-7 run at composition time.

## Dataflow

```text
                    wardrobe (ownership-scoped SQL)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      2. Style Profiler              3. Trend Scout ◄── TrendSource (dated, cited)
              └───────────────┬───────────────┘
                              ▼
                     4. Outfit Architect
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
          5. Critic                  6. Practical Advisor
              └───────────────┬───────────────┘
                              ▼
                          7. Editor
                              │
                              ▼
        schema → business → OWNERSHIP validation → response
```

Critical path is four sequential hops, not seven. 2‖3 and 5‖6 run in parallel.

**Latency budget:** 8s p50, 15s p95. Exceeding p95 twice in a row trips the circuit
breaker and falls back to the deterministic ranker. Groq's throughput is what makes this
shape viable; do not port it to a slower provider without re-measuring.

**Style Profiler output is cached.** A user's aesthetic changes far more slowly than their
outfit request. Invalidate on wardrobe change, not per request.

## Progress stages

The agent DAG maps onto the staged progress UI already required by `CLAUDE.md` — each
stage names real work in progress, which is the whole reason that rule exists:

```text
reading your wardrobe → finding your aesthetic → checking what's current
→ building looks → pressure-testing them → finding the tricks → ready
```

## Output contract

```json
{
  "outfit": { "item_ids": ["..."], "name": "...", "occasion": "..." },
  "rationale": ["..."],
  "confidence": 0.87,
  "critique": { "considered": ["..."], "tradeoffs": ["..."] },
  "pro_tips": [{ "tip": "...", "type": "styling|proportion|care" }],
  "alternatives": [{ "swap_role": "bottom", "item_id": "...", "why": "..." }],
  "combinations": [{ "item_ids": ["..."], "occasion": "...", "name": "..." }],
  "budget_tricks": [{ "trick": "...", "unlocks_outfits": 3 }],
  "wardrobe_gaps": [{ "category": "footwear",
                      "generic_description": "a white leather sneaker",
                      "unlocks_outfits": 5 }],
  "trend_notes": [{ "trend": "...", "source": "...", "published_at": "2026-07-14",
                    "applies_to_items": ["..."] }]
}
```

`wardrobe_gaps.generic_description` carries no brand, price, merchant or link — see the
commerce-free decision. `trend_notes` without `source` and `published_at` are dropped by
the Editor, not rendered unattributed.

## Validation

Every agent's output is untrusted, including the Editor's.

- Any `item_id` absent from the ownership-scoped candidate set is stripped.
- Any `item_id` belonging to another user is a hard failure: log, alert, never retry into it.
- A trend note without attribution is dropped.
- A tip asserting a fact about fibre, fit or the wearer is dropped.
- Schema → business → ownership, in that order, on the merged response. No agent's
  self-assessment substitutes for any of these.

An agent asked to critique is not thereby trusted. The Critic can be wrong, and the
ownership validator does not read its reasoning.

## Anti-theatre requirement

Each role must earn its tokens. `tests/ai/test_ablation.py` runs the crew with each agent
disabled in turn and asserts the output changes materially. A role that can be removed
without changing the result is decoration — delete it and say so in `DECISIONS.md`.

Run the ablation before claiming multi-agent value to anyone.

## Failure and degradation

1. full crew
2. crew minus Trend Scout (if `TrendSource` is unavailable or stale beyond threshold)
3. Architect + Editor only (if the latency circuit breaker trips)
4. deterministic ranker over the same wardrobe
5. an honest statement of the gap

Never a curated outfit — a fallback assembled from unowned garments breaks the one rule
the product rests on, and that holds no matter how many agents agreed.

## Cost controls

- cap crew size; adding an agent requires an ablation result
- bounded output tokens per agent
- cache the style profile; invalidate on wardrobe change
- never re-run the crew for a single-slot swap — swap re-runs Architect and Editor only
- record per-agent tokens and latency (`docs/OBSERVABILITY.md`)

## Prompt injection

Two untrusted channels feed this crew: text inside uploaded images, and trend text from
the web. Neither may alter instructions, change the schema, or widen retrieval scope.
Agent-to-agent messages are also untrusted — a compromised upstream agent must not be
able to instruct a downstream one.
