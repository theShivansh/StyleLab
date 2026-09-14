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
| 3 | Trend Scout | text | wardrobe + `TrendSource` | supplied dated trends mapped onto owned items |
| 4 | Outfit Architect | text | wardrobe + profile + trends | candidate combinations, roles filled |
| 5 | Critic | text | candidates | proportion, palette, occasion and weather objections |
| 6 | Practical Advisor | text | wardrobe + candidates | pro tips, alternatives, budget tricks, gaps |
| 7 | Editor | text | everything above | one merged, schema-valid response |

The Wardrobe Analyst runs at upload time, once per image. Agents 2-7 run at composition time.

**The Trend Scout does not fetch.** `ExaTrendSource` retrieves before the crew starts and the
notes arrive in that agent's prompt; its only job is deciding which supplied claims touch which
owned garments. That is why it cannot introduce a trend — its output schema has no field for
one — and why a provider outage costs a rung rather than an agent.

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

**Latency budget:** 30s, from `AGENT_LATENCY_BUDGET_MS` (15s until S13c). Measured in S8b at
**11.7s** for five agents on a clean provider window (1.7-3.1s each); the same crew takes
13-26s per call once the minute's token budget is spent, which is backoff and not the model.
S13c measured the deployed account through the real composition service: at 15s a second
compose 40s after the first timed out every time, and at 30s both served the full crew (29.4s
with a rebuild, 18.8s without).
See docs/DECISIONS.md and blocker B17. Exceeding p95 twice in a
row trips the circuit breaker (`app/services/circuit.py`) and the next composition runs
Architect + Editor only. One run back inside budget closes it again. Groq's throughput is what
makes this shape viable; do not port it to a slower provider without re-measuring.

Consecutive breaches, not two breaches: one slow compose is a slow compose, and a breaker that
trips on a single one makes the product visibly shallower for no reason a user can see.

**A timeout is not a breach, and opens the breaker on its own (S11).** The distinction was
found by composing in a browser rather than by reading this paragraph. A breach is a
measurement — the advisor answered, and took too long. A timeout is a failure to answer at
all: the call is cancelled at the budget and the whole of it is spent for nothing. Requiring
two of those in a row made rung 3 unreachable in exactly the conditions it exists for. The
observed sequence was fifteen seconds to the deterministic ranker, fifteen more to the ranker
again, and only then the reduced crew that takes about four — thirty seconds of a user's time
to arrive at a rung the first timeout was already sufficient evidence for.

Recovery is unchanged: one run inside budget closes it, whichever way it opened.

**Style Profiler output is cached.** A user's aesthetic changes far more slowly than their
outfit request. Invalidate on wardrobe change, not per request.

## Progress stages

The agent DAG maps onto the staged progress UI already required by `CLAUDE.md` — each
stage names real work in progress, which is the whole reason that rule exists:

```text
reading your wardrobe → finding your aesthetic → checking what's current
→ building looks → pressure-testing them → finding the tricks → ready
```

## Trend supply — Exa

`TrendSource` has one implementation, `ExaTrendSource` (`app/adapters/exa_trends.py`), over
Exa's `POST /search`. **Exa is a required runtime dependency for the Trend Scout and for
nothing else**: with no `EXA_API_KEY` the crew runs without that role and every composition
discloses degradation level 2. Deliberately not a boot failure, unlike `GROQ_API_KEY` — the
product composes perfectly good outfits with no trend context, and cannot compose anything at
all without a vision and a text model.

There is no committed corpus, and there was never a good version of one. A hand-curated
`data/trends/` directory is a snapshot of what somebody believed on the day they wrote it: it
goes stale silently, it reads to a user exactly like model recall, and keeping it current is a
job nobody would do. Retrieval with a date filter is the honest shape.

Request: `type=auto`, `numResults` 6-8, `contents.highlights=true`, `startPublishedDate` at the
staleness window, and `includeDomains` restricted to a named list of editorial fashion desks.
That last one is the strongest single defence in this layer — hostile trend copy (Case 18) has
to be published on one of those domains to be retrievable at all.

Normalisation, in order, and every step drops rather than repairs:

1. no `publishedDate`, or one outside the window, or in the future -> dropped
2. no resolvable publication host -> dropped
3. a commerce URL (`/shop`, `/product`, `/buy`, ...) -> dropped; the product sells nothing
4. no claim in either the highlight or the title -> dropped
5. exact duplicate URL, or a near-duplicate headline by content-word overlap -> dropped

What survives carries `trend`, `source`, `published_at` and `url`. **All four are required**,
and the url is also the note's identity: `app/domain/validation.py` matches what the crew
returned against what the source supplied, by url, and takes the claim, the publication and the
date from the supplied note. An advisor may narrow the set and map notes onto garments. It may
not reword a claim, restate a source, or add a note that was never retrieved.

Normalised results are cached for 24 hours by **region + season + role set** — never per user,
which would be a cache that never hits. Nothing about a user reaches Exa: a query is built from
region, season and role names, and carries no item id, no user id, and no text read off
anybody's photograph.

Every lookup emits a `TrendLookupEvent`: provider, outcome, latency, cache hit, result count,
how many were dropped, and the fallback reason when there was one.

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

## Reasoning effort, and the budget that actually binds

Agents run at `AGENT_REASONING_EFFORT=low`. Measured on the deployed account in S13c: at the
model's default the crew emitted 473-876 output tokens per agent and the Trend Scout's answer
was cut off by its ceiling. At `low` the production-shaped crew — six agents, eight real trend
articles — emitted 183-949 per agent, was refused nothing, and finished in 8.1s.

What decides whether a composition fits its budget is the account, not the model: 8,000 tokens
per minute on the text model, counting each request's input **and** its requested output
ceiling. So prompts carry no duplicated schema (CrewAI pastes one into every task; the provider
already enforces it) and handoffs are compact JSON. A Critic-driven rebuild adds two calls and
waits on the same minute, so it only starts inside the first fifth of the budget; later than
that it is skipped, and the composition discloses rung 3.

## Failure and degradation

1. full crew
2. crew minus Trend Scout — no key, a provider failure, or nothing inside the date window
3. a shorter round of reasoning — the latency circuit breaker has tripped (Architect + Editor
   only), a deliberating role failed and was left out, or the Critic asked for a rebuild there
   was no time for
4. deterministic ranker over the same wardrobe — the Architect or the Editor failed, or the
   crew overran its budget
5. an honest statement of the gap

Only the Architect and the Editor are required. Any other role that fails is left out and the
composition is served on the rung that describes what is missing, rather than discarding the
work of every role that did answer. Until S13c that sentence was true of this document and not
of the code: one refused call from the Trend Scout sent every deployed composition to the
ranker. A truncated answer (`json_validate_failed`) gets one retry with twice its output
ceiling before a role counts as failed, and CrewAI's own re-runs are switched off.

The rung is the crew's to report for 1-3 and the service's for 4-5. `CompositionService` takes
the higher of the advisor's rung and the trend lookup's; before S13c it kept only the latter,
and rung 3 had never reached a screen.

Exercised end to end in `tests/ai/test_crew_ladder.py`, which also asserts the property that
holds on every rung: **no depth of crew ever serves a garment the user does not own.**

Never a curated outfit — a fallback assembled from unowned garments breaks the one rule
the product rests on, and that holds no matter how many agents agreed.

## Self-evaluation

The Critic returns a `score` as well as objections, which makes it an LLM-as-judge and not only
a commentator. Below 70 the Architect runs again with those objections attached as
**constraints**, and the run records the score before, the score after, and whether it moved.

Bounded at one revision. A second spends four more seconds of a fifteen-second budget on a
model that has already been told twice what was wrong. If the revision scores no better the
first draft is kept — a loop that cannot reject its own output is not evaluating anything — and
a low score with no actionable objection behind it does not trigger a rebuild at all, because
there would be nothing to constrain the rebuild with.

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

That last rule is why the crew is orchestrated in phases rather than as one `Crew.kickoff()`.
CrewAI's implicit task context hands an upstream agent's prose to a downstream one as
undifferentiated text; every agent here is instead given its inputs in a labelled `DATA`
section that states outright they are content. Interpolating a typed value into a named slot is
a defence. Passing a paragraph is not.

## Framework boundary

CrewAI is confined to `app/adapters/crew*.py`, and its LLM calls go through our own
`ChatTransport` via `crewai.BaseLLM` (`app/adapters/crew_llm.py`) rather than LiteLLM. Two
consequences, both deliberate:

- the crew is testable with **no API key**, on the same mock provider as everything else. A
  crew making its own HTTP calls would be the one component nobody could assert cheaply —
  which is the component most likely to produce confident nonsense.
- retry policy, timeouts, the error taxonomy and telemetry stay the product's rather than the
  framework's. A `ConverterError` from CrewAI reaches the service as `SchemaInvalidError`, so
  an agent refusing its schema is counted as a model-quality failure and not as an outage.

CrewAI's usage telemetry and execution-trace uploader are switched off in
`app/adapters/__init__.py`, before the framework can be imported, and again at every call site.
This process handles photographs of people's clothes, and docs/SECURITY-PRIVACY.md has no
exception for a dependency's own analytics.
