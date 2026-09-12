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
| `fixtures/groq/` | see above — extraction and advice payloads, including malformed and hostile ones. |
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

## What this suite cannot prove

It runs with no key, which is what makes it runnable on every push — and which means the
provider is never asked whether it accepts what we send it. `MockGroqProvider` returns
scripted content; it does not validate the JSON Schema it was handed.

S6 found out what that costs. Two schema bugs had been green here since S5 and failed on the
first real call: strict Structured Outputs requires every property in `required`, and a
free-form `dict[str, float]` closed with `additionalProperties: false` is an object permitted
to hold nothing — so the provider was being told that per-field confidence must be empty,
while the fixtures here supplied scores it was forbidden from sending.

`tests/live/` covers exactly that class of failure and nothing else. It is not a second copy
of this suite: it is the question only a real call can answer. Treat a green run here as
proof of *our* logic, never of the contract.

## Still to come

Extended in S8 (`prompts/10-NO-GIMMICK-AI-EVAL.md`) with the full runner and the extraction
cases, and in S8b (`prompts/14-AGENT-CREW.md`) with the crew, the trend layer and
`test_ablation.py`.

The two cases that matter most:

- **Case 11 — cross-user isolation.** Another user's item is never retrieved, never enters a
  prompt, and is rejected by ownership re-validation even when injected into a crafted model
  response. Covered as of S4, and verified by mutation — see `docs/DECISIONS.md`. S6 added
  the upload half: the checksum cache is scoped per user, so the same photograph uploaded by
  two people produces two wardrobes rather than one shared asset.
- **Case 07 — injection via image text.** Three layers, and this suite asserts the order of
  them: the prompt rules, the SQL scope, and — new in S6 — `app.domain.hygiene` bounding the
  text once it is inside a legitimate field. The adapter deliberately does **not** bound it,
  for the same reason the advisor does not filter unowned ids: a check there looks done and
  leaves the real seam untested.
- **Case 21 — agent ablation.** Each agent role is disabled in turn; every one must change
  the output. A role that can be removed without changing the result is decoration.
  **Not yet written** (S8b). CI references it and that step is red until it exists — a
  placeholder ablation test would defeat the purpose, since the whole point is that it must
  be able to fail.
