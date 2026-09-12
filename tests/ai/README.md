# AI evaluation harness

Cases live in `docs/AI-EVAL-CASES.md`. Runs with **no API key** — verified, not assumed:
`conftest.py` deliberately does not set `GROQ_API_KEY`, and the suite passes with the
variable unset. A regression suite that costs money per run stops being run.

```bash
pytest tests/ai -q
```

## What is here

| File | |
|---|---|
| `stubs.py` | Stub adapters and domain fixtures. Test doubles for an external dependency — **not** a demo mode. Nothing under `apps/api/app/` may import them, and `apps/api/tests/test_query_scoping.py` enforces that (Case 25). |
| `test_grounding.py` | Cases 01, 11 and 12 — the cases the domain layer can answer in full today. |
| `conftest.py` | Puts `apps/api` on `sys.path` so the directory runs from the repository root as well as in CI. |

`ScriptedAdvisor` is the important one. It returns whatever a test hands it, including a
well-formed, confident response naming an item belonging to somebody else — the only way to
prove that ownership re-validation, rather than the prompt, is what refuses it.

## Still to come

Extended in S8 (`prompts/10-NO-GIMMICK-AI-EVAL.md`) with the full runner and the extraction
cases, and in S8b (`prompts/14-AGENT-CREW.md`) with the crew, the trend layer and
`test_ablation.py`.

The two cases that matter most:

- **Case 11 — cross-user isolation.** Another user's item is never retrieved, never enters a
  prompt, and is rejected by ownership re-validation even when injected into a crafted model
  response. Covered as of S4, and verified by mutation — see `docs/DECISIONS.md`.
- **Case 21 — agent ablation.** Each agent role is disabled in turn; every one must change
  the output. A role that can be removed without changing the result is decoration.
  **Not yet written** (S8b). CI references it and that step is red until it exists — a
  placeholder ablation test would defeat the purpose, since the whole point is that it must
  be able to fail.
