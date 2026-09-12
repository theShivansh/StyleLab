# Live smoke tests

Real Groq calls. `main` branch only, via the `live-smoke` CI job — fork pull requests cannot
read secrets, and these cost tokens.

Populated in S5. Five tests, two files:

| | |
|---|---|
| `test_model_availability.py` | All three configured model ids resolve against Groq's live model list, plus one cheap connectivity call. Runs the same `verify_models` the app runs at boot — a canary that checks something slightly different from production is a canary that can sing while production suffocates. |
| `test_real_inference.py` | One real extraction and one real composition. The question no mock can answer: does the live model actually honour the schema we send it? |

**Skips without a key** rather than failing — a test that cannot run has not found a bug.
This is the only place in the repository where a missing `GROQ_API_KEY` is tolerated, and it
is a *test* skipping, never the application degrading: the app refuses to boot without a key
(Case 25), asserted in `apps/api/tests/test_config.py`. The fake `test-key…` value the unit
suite sets also skips.

The extraction test needs a real photograph from `data/samples/`, which is empty today, so
it skips too (blocker B13). A synthetic 1x1 pixel would only prove a model can describe a
grey square.

Keep this suite small. It is a canary for model deprecation, not a second test suite —
everything provable with `MockGroqProvider` is proven in `tests/ai/`, free, on every push.
