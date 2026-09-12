# AI evaluation harness

Populated in S8 (`prompts/10-NO-GIMMICK-AI-EVAL.md`) and extended in S8b
(`prompts/14-AGENT-CREW.md`).

Cases live in `docs/AI-EVAL-CASES.md`. The two that matter most:

- **Case 11 — cross-user isolation.** Another user's item is never retrieved, never enters
  a prompt, and is rejected by ownership re-validation even when injected into a crafted
  model response.
- **Case 21 — agent ablation.** Each agent role is disabled in turn; every one must change
  the output. A role that can be removed without changing the result is decoration.

Runs with no API key. A regression suite that costs money per run stops being run.
