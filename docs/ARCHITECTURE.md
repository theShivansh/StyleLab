# Architecture — STYLELAB

## 1. High-level architecture

```text
                    Next.js Web
                        |
                  typed API client
                        |
                     FastAPI
                        |
       +----------------+----------------+
       |                |                |
   Wardrobe      AI Orchestrator     Analytics
       |                |
   Postgres    +--------+--------+
       |       |                 |
  Object   Vision Adapter   Text Adapter
  Storage       |                 |
           extraction         ranking
                |                 |
                +--------+--------+
                         |
              ownership re-validation
                         |
                  Outfit composition
```

Three adapters, all behind interfaces: vision (garment extraction), advisory (the agent
crew), and trend (sourced, dated trend input). The VTO and commerce adapters are gone.
See `docs/DECISIONS.md` (2026-09-12).

## 2. Groq AI architecture

### Model roles

`GROQ_TEXT_MODEL`
- default candidate: `openai/gpt-oss-120b`
- purpose: outfit ranking, rationale, gap naming

`GROQ_VISION_MODEL` — `qwen/qwen3.8-27b`
- purpose: garment extraction from user photos — the product's primary AI path

`GROQ_VISION_FALLBACK_MODEL` — `qwen/qwen3.6-27b`
- purpose: availability only. Provider error, rate limit, timeout, or an ID that no
  longer resolves. Never triggered by low confidence.

Model IDs are configuration. They appear in `.env.example` and the adapter config, and
nowhere else.

### Output strategy

```text
prompt
→ Groq (JSON Schema, strict where supported)
→ Pydantic validation
→ business validation
→ ownership validation
→ domain object
```

Business and ownership validation remain mandatory even when schema validity is guaranteed.
Schema validity is not business validity, and neither is authorisation.

## 3. Adapter interfaces

```ts
interface WardrobeAnalyzer {
  analyze(input: GarmentImage): Promise<GarmentExtraction>
}

interface OutfitAdvisor {
  advise(input: AdviceRequest): Promise<OutfitAdvice>
}

interface TrendSource {
  current(input: TrendQuery): Promise<TrendNote[]>   // each carries source + published_at
}
```

Implementations:
- `GroqWardrobeAnalyzer` — live, with the vision fallback chain
- `CrewAIOutfitAdvisor` — the agent crew (`docs/AGENT-SYSTEM.md`)
- `DeterministicRanker` — degradation step, not a product mode
- `CorpusTrendSource` (default, `data/trends/`) · `WebTrendSource` (opt-in)
- stub implementations in `tests/ai/` — test doubles only; the running app never reaches them

The domain layer must not be able to tell which implementation it holds. Two greps,
both returning nothing outside `adapters/`: `git grep -i groq` and `git grep -i crewai`.

## 4. Image input

- validate MIME type, byte size, and resolution before storage
- store privately; never in a public bucket
- generate short-lived signed URLs when a provider needs to fetch
- pass a reference, never raw bytes, through domain code
- never log image content
- key the analysis cache on checksum so re-uploading the same photo costs nothing

## 5. Orchestration — upload to wardrobe

```text
POST /wardrobe/items (n images)
→ validate each independently
→ store assets
→ enqueue analyze_item job per image
→ worker: vision adapter → schema → business validation
→ wardrobe_item (status ready, field_confidence set)
→ item_extractions row written either way, including rejections
→ client receives cards progressively
```

One bad image fails one job. It must never fail the batch.

## 6. Orchestration — wardrobe to outfit

1. normalise style preferences
2. **retrieve candidates with `WHERE user_id = :user AND status = 'ready'`**
3. deterministic prefilter by role and compatibility
4. fetch dated trend notes from `TrendSource` (parallel with step 3)
5. run the agent crew over the retrieved set (`docs/AGENT-SYSTEM.md`)
6. validate structured output
7. **re-validate every returned ID against the retrieved set and the same `user_id`**
8. drop unattributed trend notes and unsupportable tips
9. deterministic final score
10. detect unfilled roles → report the gap rather than filling it
11. persist

Steps 5 and 7 are separated on purpose: no amount of agent deliberation substitutes for
the ownership check, and a Critic agent that approved a response is not evidence.

Step 2 and step 6 are the grounding guarantee. Neither may be replaced by prompt wording.

## 7. Async jobs

```text
POST → job created → worker queue → adapter → validation → persist → job completed
```

`analyze_item` is the async path that matters; it runs per image, in parallel, and streams
results back as each completes. `compose_outfit` is fast enough to run inline but uses the
same job envelope so the progress UI is uniform.

Frontend: polling for MVP, SSE later.

## 8. Reliability

provider timeout · bounded retry · exponential backoff · idempotency keys ·
**vision model fallback chain** · **agent latency circuit breaker (8s p50 / 15s p95)** ·
partial-batch success · explicit error codes

There is no offline path. A missing or invalid `GROQ_API_KEY` fails loudly at boot
alongside the model-availability check, never silently into a stub.

No curated fallback outfit — a fallback made of unowned garments would violate the
grounding rule. Degrade to the deterministic ranker over the same wardrobe, then to an
honest statement of the gap.

## 9. Observability

Record: request ID · job ID · provider · model · **model fallback activations** ·
**per-agent latency and tokens** · **crew degradation level** · duration · token usage ·
retry count · status · error class · extraction confidence · correction events ·
**trend corpus age at time of use**.

Do not record: raw image content · secrets · inferences about the person in a photo.

## 10. Security boundaries

- authentication / authorisation
- **row-level ownership on every wardrobe read, enforced in the query**
- signed private image access
- upload validation
- rate limiting on upload and analysis specifically — they are the expensive paths
- environment secrets
- sanitised provider errors
- validated AI output

## 11. Performance

Frontend: SSR static content · image optimisation · lazy-load heavy modules ·
progressive card rendering during analysis.

AI: parallel per-image analysis · checksum cache · deterministic prefilter before ranking ·
bounded output tokens · never re-analyse an unchanged image.
