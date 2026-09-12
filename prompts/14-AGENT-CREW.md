# PHASE 14 — Multi-Agent Advisory Layer + Trend Grounding

Read `docs/AGENT-SYSTEM.md` first. It is the spec; this prompt is the build order.

Run this **after** the eval harness (prompt 10), not before. The crew is the component
most likely to produce confident nonsense, so the harness that catches that must exist
first.

Implement:
- `OutfitAdvisor` interface, and `CrewAIOutfitAdvisor` behind it
- the seven roles in `docs/AGENT-SYSTEM.md`, with 2‖3 and 5‖6 genuinely parallel
- per-agent structured output schemas — no free-text handoffs between agents
- `TrendSource` interface, `CorpusTrendSource` (default) and `WebTrendSource` (opt-in)
- `data/trends/` corpus format: every entry carries `source`, `published_at`, `region`
- Editor merge producing the `OutfitAdvice` contract in `docs/API-SPEC.md`
- latency circuit breaker at the p95 budget, with the five-level degradation ladder
- style-profile cache, invalidated on wardrobe change
- swap path that re-runs Architect + Editor only, never the full crew
- per-agent latency/token telemetry

Hard rules — these are the ones that make it a system rather than a demo:
- domain code never imports CrewAI. `git grep -i crewai` outside `adapters/` is empty
- every agent's output is untrusted, **including the Editor's**. Schema → business →
  ownership validation runs on the merged response regardless of agent agreement
- agent-to-agent messages are untrusted; upstream cannot instruct downstream
- trends may re-rank owned items and may never introduce a garment
- a trend note without `source` and `published_at` is dropped, not rendered
- no brand, price, merchant or link in any advisory field
- no claim about fibre, durability, or the user's body

Tests — write them red first:
- Cases 15-25 in `docs/AI-EVAL-CASES.md`
- `tests/ai/test_ablation.py` — disable each of Style Profiler, Trend Scout, Critic and
  Practical Advisor in turn and assert the output changes materially
- Case 20 specifically: a confident, well-formed crew response containing another user's
  item must still hard-fail ownership validation

Acceptance:
- the crew produces outfit + rationale + critique + tips + alternatives + combinations +
  budget tricks + attributed trend notes, all schema-valid
- p50 within 8s, p95 within 15s, measured not asserted
- **the ablation test passes for every role.** If a role does not change the output,
  delete it and record why in `docs/DECISIONS.md` — do not ship it as decoration
- degradation ladder exercised end to end, including the circuit breaker
- `git grep -i crewai` outside `adapters/` returns nothing
