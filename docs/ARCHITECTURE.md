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

Two adapters, both behind interfaces: vision (garment extraction) and text (ranking).
The VTO adapter and the commerce adapter are gone — see `docs/DECISIONS.md` (2026-09-12).

## 2. Groq AI architecture

### Model roles

`GROQ_TEXT_MODEL`
- default candidate: `openai/gpt-oss-120b`
- purpose: outfit ranking, rationale, gap naming

`GROQ_VISION_MODEL`
- purpose: garment extraction from user photos — the product's primary AI path
- default is contested; resolve before S5 (`docs/DECISIONS.md`, open entry)

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

interface OutfitRanker {
  rank(input: RankRequest): Promise<RankedOutfit>
}
```

Implementations:
- `GroqWardrobeAnalyzer` / `GroqOutfitRanker` — live
- `DeterministicWardrobeAnalyzer` / `DeterministicRanker` — `APP_MODE=demo`, no credentials

The demo analyzer measures colour and quality from actual pixels and takes category from
the user's upload selection; it does not fabricate fields. See `docs/AI-SYSTEM.md`.

The domain layer must not be able to tell which implementation it holds. `git grep -i groq`
outside the adapter directory returning nothing is the check.

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
4. ask the text model to rank the retrieved set
5. validate structured output
6. **re-validate every returned ID against the retrieved set and the same `user_id`**
7. deterministic final score
8. detect unfilled roles → report the gap rather than filling it
9. persist

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

provider timeout · bounded retry · exponential backoff · idempotency keys · circuit
breaking where useful · partial-batch success · explicit error codes

No curated fallback outfit — a fallback made of unowned garments would violate the
grounding rule. Degrade to the deterministic ranker over the same wardrobe, then to an
honest statement of the gap.

## 9. Observability

Record: request ID · job ID · provider · model · duration · token usage · retry count ·
status · error class · extraction confidence · correction events.

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
