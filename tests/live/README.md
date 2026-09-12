# Live smoke tests

Real Groq calls. `main` branch only, via the `live-smoke` CI job — fork pull requests cannot
read secrets, and these cost tokens.

Populated in S5, first actually run in S6. Eight tests, three files:

| | |
|---|---|
| `test_model_availability.py` | All three configured model ids resolve against Groq's live model list, plus one cheap connectivity call and one that asserts a too-small token ceiling names itself. Runs the same `verify_models` the app runs at boot — a canary that checks something slightly different from production is a canary that can sing while production suffocates. |
| `test_real_inference.py` | One real extraction and one real composition. The question no mock can answer: does the live model actually honour the schema we send it? |
| `test_upload_pipeline.py` | The whole API — routes, ingest, storage, EXIF strip, real analyzer, real transport — over the photographs in `data/samples/`, plus the availability fallback provoked with a retired model id. The criterion S3 deferred. |

## What the first real run found

Three failures, and only one was a bad test.

- **Strict Structured Outputs requires every property in `required`.** Our schemas derived
  it from Pydantic, where every extraction field has a default, so it was absent entirely.
  A 400 naming all thirteen properties.
- **`field_confidence` was an object permitted to hold nothing.** A free-form
  `dict[str, float]` closed with `additionalProperties: false` admits no keys, so the
  provider was being instructed that per-field confidence must be empty — while the offline
  fixtures supplied the scores it was forbidden from sending. The honesty signal the whole
  extraction screen rests on, specified as unreachable.
- **A reasoning model with a small token ceiling returns nothing, not less.** The
  connectivity canary asked for 32 tokens and got an empty message with
  `finish_reason="length"`. That one was the test's fault, and the error message is now
  specific enough that the next person does not go looking for a schema problem.

This is what the suite is for. `tests/ai/` proves our logic for free on every push; only a
real call can tell us the provider agrees. Both product bugs had been green offline since S5
and neither was findable there, because `MockGroqProvider` never validates the schema it is
handed.

**Skips without a key** rather than failing — a test that cannot run has not found a bug.
This is the only place in the repository where a missing `GROQ_API_KEY` is tolerated, and it
is a *test* skipping, never the application degrading: the app refuses to boot without a key
(Case 25), asserted in `apps/api/tests/test_config.py`. The fake `test-key…` value the unit
suite sets also skips.

The extraction tests need real photographs from `data/samples/`, which now holds three (blocker B13 closed) — a shirt, chinos and a sneaker, which is also one complete outfit. They skip if the directory is emptied rather than inventing an image: a synthetic 1x1 pixel would only prove a model can describe a grey square.

Keep this suite small. It is a canary for model deprecation, not a second test suite —
everything provable with `MockGroqProvider` is proven in `tests/ai/`, free, on every push.
