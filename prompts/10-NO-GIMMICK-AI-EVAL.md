# NO-GIMMICK AI VALIDATION

Act as an AI product reliability engineer.

Inspect the current STYLELAB AI pipeline and prove that it is not a fake UI demo.

You must verify:

1. Every recommendation is grounded in known catalogue IDs.
2. Model output is schema validated.
3. Business validation runs after schema validation.
4. Price/URL/availability are database sourced.
5. Invalid model outputs trigger retry/fallback.
6. Prompt injection fixtures are handled.
7. AI calls have timeout/retry boundaries.
8. Demo mode can run without external AI.
9. AI evaluation fixtures can run deterministically.
10. Generation events expose enough telemetry to measure quality and latency.

Create or improve:
- tests/ai fixtures
- evaluation runner
- mock Groq adapter
- invalid-response fixtures
- grounding checks
- README instructions

Do not merely mock the final successful response. Test failure paths and invalid model behavior.

Acceptance:
A reviewer can intentionally make the model return an unknown SKU or malformed JSON and the application refuses to present invalid commerce data.
