# AI Eval

Run and report the grounding harness. Runs on stub adapters and never requires
GROQ_API_KEY — those are test doubles, not a product mode. The app itself has no
offline path.

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
   - a trend note lacking source or published_at
   - a trend that would introduce an unowned garment
   - injection via trend copy, and agent-to-agent injection
   - a confident full-crew response containing another user's item
   - agent latency budget exceeded (circuit breaker → degradation ladder)
   - vision fallback fired for low confidence rather than provider error
4. For each failure path, state which layer caught it (schema / business / ownership) and what the user saw.
5. If any invalid model output could reach the UI — above all an item the user does not
   own — that is a P0. Fix it, then rerun.

6. Run the ablation suite. Report, per agent role, whether disabling it changed the
   output. **Any role that did not is decoration — say so plainly and recommend deleting
   it.** Do not defend a role on the grounds that it "adds depth".

7. Report measured p50/p95 composition latency against the 8s/15s budget. Measured, not
   estimated.

Report a table. No prose summary of what the tests "should" do — only what they did.
