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
- `ExaTrendSource` (`app/adapters/exa_trends.py`) over Exa `POST /search`, the only
  implementation. No committed corpus — see docs/AGENT-SYSTEM.md on why there was never a
  good version of one. Required for the Trend Scout and for nothing else: absent a key the
  crew runs a role short and discloses degradation level 2.
- stub implementations in `tests/ai/` — test doubles only; the running app never reaches them

The domain layer must not be able to tell which implementation it holds.

This used to be stated as two greps coming back empty outside `adapters/`. They never did
and never could: `Settings` has to call its fields `groq_api_key` and `groq_text_model`
because they map to `GROQ_*` environment variables, and a docstring explaining why Groq
lives behind an adapter is not coupling. Corrected in S5; recorded here in S6 because this
file was still asserting it.

What is enforced, by `apps/api/tests/test_adapter_boundary.py` parsing with `ast` so prose
does not trip it:

1. no vendor module imported or referenced outside `app/adapters/`
2. no model **id** written as a literal outside `app/config.py`
3. `app/domain/` never imports `app.adapters` — the dependency runs one way

## 4. Image input

- validate MIME type, byte size, and resolution before storage
- store privately; never in a public bucket
- generate short-lived signed URLs when a provider needs to fetch
- pass a reference, never raw bytes, through domain code
- never log image content
- key the analysis cache on checksum so re-uploading the same photo costs nothing

Implemented in S6 (`app/services/images.py`, `app/services/storage.py`). Four details the
list above does not make obvious, each with a reason:

- **Two ceilings, not one.** A byte limit cannot see a 12000x12000 PNG that compresses to a
  few hundred kilobytes; a pixel limit cannot see a 200MB file. The pixel check reads the
  header, before the image is decoded.
- **The format is sniffed from magic bytes.** The declared `Content-Type` is a claim by the
  uploader and is used only to write a clearer refusal.
- **EXIF orientation is applied before the block is dropped**, or every portrait photograph
  is stored on its side — including the copy sent to the vision model.
- **"A short-lived signed URL" is not always what a provider can fetch.** A local
  deployment's storage is a private directory and its API is on `localhost`, so the
  reference is an inlined, downscaled `data:` URL. The Protocol is named
  `ImageReferenceSource` for what it returns rather than for one implementation of it.

The cache is scoped to one user. A global checksum index would deduplicate across wardrobes
and hand one user another's extraction.

### Closed vocabularies on the list fields

`style_tags`, `season_tags`, `occasion_tags` and `quality_warnings` are enumerations that
were typed as `list[str]`. They are closed by `app/domain/vocabulary.py`: the vocabulary
reaches the provider as a schema `enum`, and `app/domain/hygiene.py` enforces it by filtering
so that off-vocabulary output costs the tag rather than the photograph.

The reason is specific to those fields. `style_tags` is written by a vision model, is **not**
rendered on the garment card, and is interpolated into the *advice* prompt — influential and
unseen. A 32-character ceiling was the only thing in it, and both a truncated injection and a
description of the person in the photograph fit comfortably inside one. Length is the wrong
control for a channel nobody looks at (docs/DECISIONS.md, S8).

The free-text fields — `subcategory`, `pattern`, `color_primary`, `color_secondary`, `fit` —
stay open, bounded by length. They are open sets in the world and they are rendered and
correctable, so a bad value is visible to the user and fixable by them. Blocker B18 tracks
the residue.

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

## Composition and swap (S7)

Two calls with opposite shapes, decided by what is on the other side of each.

`POST /outfits/compose` is a job. It reaches a provider — one text call now, the crew behind
the same Protocol in S8b — so the route returns 202 and the client polls the stages. The
runner (`app/services/compose.py`) retrieves the candidate set in one short unit of work,
awaits the advisor holding **no** database session, and persists in another. That is the same
rule the extraction pipeline follows, and it is measured rather than asserted:
`apps/api/tests/test_compose_service.py` has the advisor count the open sessions.

`POST /outfits/{id}/swap` is synchronous and calls nothing. A scoped read, a recompute over
the six scoring dimensions, one row rewritten. The other slots keep their garments *and their
rank*, which is the persistence half of the product promise — changing one item changes one
item. It returns the whole look rather than a patch, so the client renders a payload it did
not assemble; merging a partial response into local state is how a screen ends up disagreeing
with the wardrobe.

`GET /outfits/{id}/alternatives` scores each candidate **in the look**, against the pieces
actually on screen, and reports the delta. Ordering is by score then id, so the sheet does not
reshuffle between openings.

Nothing in this path can introduce a garment. Candidates come from the one ownership-scoped
query; the advisor's response is re-validated against that set in memory; a swap's replacement
is read through the same scoped repository, so an id belonging to someone else is
indistinguishable from one that does not exist.

Implemented in S6. The runner is in-process (blocker B14) and the seam is `submit`, which
takes a factory and returns nothing — a durable queue replaces it without touching the
pipeline. What is not deferred is the property that would be expensive to retrofit: the
upload route holds no reference to an extraction and cannot wait for one.

Stages are named work, from `app/services/jobs.py`, and `progress` is derived from the stage
so the two cannot disagree. One job per image, never one per batch: a batch-level job has
one status, and one status means one spinner over eight photographs.

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

Step 5 runs inside a wall-clock budget (`AGENT_LATENCY_BUDGET_MS`), applied once around the
whole advisor call and enforced in `CompositionService`. Nothing below that line knows a
person is waiting: the transport retries three times at a 30-second client timeout, inside
an advisor that re-asks once on a schema failure, so a fully patient compose is six provider
calls. Exceeding the budget cancels the call — an abandoned request holds a connection and
is still billed — and drops to step 9 over the same candidates.

## Migrations (S11)

Alembic, in `apps/api/migrations`, with `alembic upgrade head` as a deploy step. `create_all`
remains for tests and local work and is **not** called when `APP_ENV=production` — it creates
whatever is missing, which papers over a migration that did not run and leaves the database
in a state no revision describes.

`migrations/env.py` reads the URL from `Settings.resolved_database_url` rather than from
`alembic.ini`. A second place that names the database is the one nobody updates, and the
result is a migration that runs against a developer's SQLite file while the application talks
to Postgres.

The initial revision is a **baseline**, not a replayed history: it creates the schema as it
stood at S11, because no deployed database exists whose history it would need to match.
`tests/test_migrations.py` asserts a migrated database and a `create_all` database are
indistinguishable, which is what stops the models and the migrations drifting apart in
silence.

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

**Boot knows which environment it is in (S11).** `app/preflight.py` checks the settings that
are correct on a laptop and wrong in a container — an ephemeral signing key, SQLite in the
working directory, a `localhost` CORS origin — and under `APP_ENV=production` refuses to
start on the ones that make the application incorrect rather than merely worse. It reports
all of them at once, because fixing three settings one deploy apiece is three container
builds to learn three things that were knowable before the first.

It also verifies the **schema matches the models**, in every environment. `create_all` adds
missing tables and never missing columns, so a database created before a column was added
stays silently wrong until a query touches it — which is exactly what happened during the
S11 audit and surfaced as *"Something went wrong on our side"* on every upload.

No curated fallback outfit — a fallback made of unowned garments would violate the
grounding rule. Degrade to the deterministic ranker over the same wardrobe, then to an
honest statement of the gap.

## 9. Observability

Record: request ID · job ID · provider · model · **model fallback activations** ·
**per-agent latency and tokens** · **crew degradation level** · duration · token usage ·
retry count · status · error class · extraction confidence · correction events ·
**publication date of every trend note shown**.

Do not record: raw image content · secrets · inferences about the person in a photo.

Both generating paths emit one `GenerationEvent` per model call into a single
`GenerationLog` (`app/services/telemetry.py`), and `generation_metrics()` rolls a stream of
them into the AI list in docs/OBSERVABILITY.md. Events carry scalars only; the raw output
stays on `item_extractions`, which is ours and under the wardrobe's retention.

## 10. Security boundaries

- authentication / authorisation
- **row-level ownership on every wardrobe read, enforced in the query**
- signed private image access
- upload validation
- rate limiting on upload and analysis specifically — they are the expensive paths.
  Built in S11 (`app/services/ratelimit.py`): token buckets keyed by user, charged **per
  image** rather than per request, plus a per-address bucket on session creation. With no
  authentication (B15), an unlimited supply of identities would be an unlimited supply of
  everything else. Per instance; see docs/DEPLOYMENT.md.
- response security headers on the web tier (S11) — CSP, `frame-ancestors 'none'`,
  `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS
- **hard deletion on a retention timer** (S11, `app/services/retention.py`). Soft deletion
  stops a photograph being served; the sweep is what makes it stop existing, thirty days
  later, which is what the privacy copy promises
- environment secrets
- sanitised provider errors
- validated AI output

## 11. Performance

Frontend: SSR static content · image optimisation · lazy-load heavy modules ·
progressive card rendering during analysis.

AI: parallel per-image analysis · checksum cache · deterministic prefilter before ranking ·
bounded output tokens · never re-analyse an unchanged image.
