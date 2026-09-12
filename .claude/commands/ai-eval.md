# AI Eval

Run and report the grounding harness. Never requires GROQ_API_KEY.

1. Run the eval suite in mock mode (`tests/ai/`), covering every case in `docs/AI-EVAL-CASES.md`.
2. Report per-case: pass/fail, what was asserted, what the system did on failure.
3. Explicitly exercise the failure paths, not just the happy path:
   - unknown SKU in model output
   - malformed / truncated JSON
   - missing required field
   - prompt injection in a product title
   - provider timeout
   - model price disagreeing with DB price
4. For each failure path, state which layer caught it (schema / business / catalogue) and what the user saw.
5. If any invalid model output could reach commerce-facing UI, that is a P0. Fix it, then rerun.

Report a table. No prose summary of what the tests "should" do — only what they did.
