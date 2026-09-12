# NO-GIMMICK AI VALIDATION

Act as an AI product reliability engineer.

Inspect the current STYLELAB AI pipeline and prove that it is not a fake UI demo.

You must verify:

1. Every recommendation is grounded in wardrobe items the requesting user owns.
2. Model output is schema validated.
3. Business validation runs after schema validation.
4. No garment attribute is presented as fact when the model guessed it.
5. Invalid model outputs trigger retry/fallback.
6. Prompt injection fixtures are handled.
7. AI calls have timeout/retry boundaries.
8. The eval suite runs on stub adapters with no API key, while the product itself has no
   offline path and fails loudly without one.
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
A reviewer can intentionally make the model return an item the user does not own — or one belonging to another user — or malformed JSON, and watch the application refuse it.
