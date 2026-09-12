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
| `stubs.py` | Test doubles and domain fixtures. **Not** a demo mode. Nothing under `apps/api/app/` may import them, and `apps/api/tests/test_query_scoping.py` enforces that (Case 25). |
| `fixtures/groq/` | Recorded provider responses, loaded verbatim so a truncated payload stays truncated. |
| `test_grounding.py` | Cases 01, 11, 12 with the **advisor** substituted. |
| `test_adapter_grounding.py` | Cases 01, 06, 07, 11, 16, 22, 24 with only the **transport** substituted — the real Groq adapters run. |
| `conftest.py` | Puts `apps/api` on `sys.path` so the directory runs from the repository root as well as in CI. |

## Two levels of double, and why both

- **`MockGroqProvider`** replaces the transport. The real `GroqWardrobeAnalyzer` and
  `GroqOutfitAdvisor` sit on top and run their real prompt construction, parsing, retry and
  fallback logic. This is what makes prompt 12's acceptance criterion checkable: *the domain
  layer cannot tell whether it is using Groq or the mock adapter.*
- **`ScriptedAdvisor` / `ScriptedAnalyzer`** replace the adapter, for testing everything
  above it without caring how a response was produced.

`ScriptedAdvisor` returns whatever a test hands it, including a well-formed, confident
response naming an item belonging to somebody else — the only way to prove that ownership
re-validation, rather than the prompt, is what refuses it.

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
