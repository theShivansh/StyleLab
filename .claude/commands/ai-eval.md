# AI Eval

Run and report the grounding harness. Never requires GROQ_API_KEY.

1. Run the eval suite in mock mode (`tests/ai/`), covering every case in `docs/AI-EVAL-CASES.md`.
2. Report per-case: pass/fail, what was asserted, what the system did on failure.
3. Explicitly exercise the failure paths, not just the happy path:
   - an item ID the user does not own
   - an item belonging to ANOTHER user, injected into a crafted response
   - malformed / truncated JSON
   - missing required field
   - prompt injection via text inside an uploaded image
   - provider timeout
   - insufficient wardrobe for the requested roles
   - a user-corrected field overwritten by re-analysis
4. For each failure path, state which layer caught it (schema / business / ownership) and what the user saw.
5. If any invalid model output could reach the UI — above all an item the user does not
   own — that is a P0. Fix it, then rerun.

Report a table. No prose summary of what the tests "should" do — only what they did.
