# Live smoke tests

Real Groq calls. `main` branch only, via the `live-smoke` CI job — fork pull requests cannot
read secrets, and these cost tokens.

Populated in S5 (`prompts/12-GROQ-INTEGRATION.md`). Asserts:

- `GROQ_TEXT_MODEL`, `GROQ_VISION_MODEL` and `GROQ_VISION_FALLBACK_MODEL` all resolve
  against Groq's live model list
- one real extraction and one real composition still satisfy the schema

Keep this suite small. It is a canary for model deprecation, not a second test suite.
