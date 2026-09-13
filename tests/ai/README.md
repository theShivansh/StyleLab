# AI evaluation harness

Proof that the AI pipeline is not a fake UI demo. Cases live in `docs/AI-EVAL-CASES.md`.

Runs with **no API key** — verified, not assumed: `conftest.py` deliberately does not set
`GROQ_API_KEY`, and the whole directory passes with the variable unset. A regression suite
that costs money per run stops being run.

```bash
pytest tests/ai -q          # 107 tests, ~70 seconds (13s of it is importing CrewAI)
python tests/ai/runner.py   # the same scenarios, printed
```

## Watch it refuse something

This is the part worth doing by hand. Write whatever you want the model to have said into a
file and feed it through the real stack:

```bash
python tests/ai/runner.py --response my-response.json
```

The wardrobe it runs against: **eval-u1** owns `own-top`, `own-second-top`, `own-bottom`,
`own-shoe`. **eval-u2** owns `u2-jacket`, which eval-u1 must never be shown. Things worth
trying:

- an outfit naming `u2-jacket` — another user's garment, in a confident, schema-valid response
- an outfit naming `nice-loafer` — an id nobody owns
- `not JSON, mate` — prose where the schema was required
- a valid response — the control, so you can see the harness accept something

What you should see for the first two is `refused (ungrounded_item)`, a CRITICAL log line,
and an outfit built from eval-u1's own garments at degradation 4. The exit code is non-zero
if any garment outside the wardrobe reached the answer.

## What is here

| File | |
|---|---|
| `runner.py` | The CLI. `--case`, `--coverage`, `--response`, `--json`. Exit 1 on any failure. |
| `crew_fixtures.py` | Scripted crew answers, keyed by the schema each agent asks for. |
| `test_crew.py` | The crew: Cases 19 and 20, the reflexion loop, per-agent telemetry. |
| `test_crew_ladder.py` | The degradation ladder end to end, including the circuit breaker. |
| `test_ablation.py` | Case 21. Every role must change the output, or it gets deleted. |
| `scenarios.py` | The 19 refusal scenarios. Each returns a `Check` instead of asserting, so the CLI and pytest consume the same objects. |
| `cases.py` | The case registry: all 25 cases, their status, and what evidences each. |
| `harness.py` | One wardrobe and one assembled stack, shared by everything above. |
| `stubs.py` | Test doubles and domain fixtures. **Not** a demo mode — nothing under `apps/api/app/` may import them, and `apps/api/tests/test_query_scoping.py` enforces that (Case 25). |
| `fixtures/groq/` | Recorded provider responses, loaded verbatim so a truncated payload stays truncated. |
| `test_scenarios.py` | Every scenario, as a gate. Parameterised over the registry, so a new scenario cannot be added without one. |
| `test_case_coverage.py` | The meta-test. Resolves every coverage claim against the repository. |
| `test_grounding.py` | Cases 01, 11, 12 with the **advisor** substituted. |
| `test_adapter_grounding.py` | Cases 01, 06, 07, 11, 16, 22, 24 with only the **transport** substituted. |

## Coverage, and how the claim is kept honest

```bash
python tests/ai/runner.py --coverage
```

24 of 25 cases covered, 1 partial, 0 deferred. The one partial is Case 09, and its note says
exactly which half is missing and why (blocker B18).

The registry would be worthless as prose, so `test_case_coverage.py` resolves it:

- every case in the markdown is in the registry, and nothing in the registry is invented
- every `file::symbol` reference names something actually defined in that file, by `ast`
- every file-level reference actually contains the case id it is claimed for
- a deferred case claims no evidence and names its session; a partial one says which half

That third rule is the one with teeth. This repository already writes `Case NN` into the
docstring of the test that covers it; the meta-test turns that habit into a constraint.
Rename the test and the reference stops resolving; delete it and the marker goes with it.

It earned its keep immediately. Two of the claims in the first draft of the registry were
written from memory and were simply wrong — `test_composition.py` does not cover Case 03,
and `test_prompt_contract.py` did not cover Case 09 — and both failed on the first run.

## Three levels of double, and why all three

- **`MockGroqProvider`** replaces the *transport*. The real `GroqWardrobeAnalyzer` and
  `GroqOutfitAdvisor` sit on top and run their real prompt construction, parsing, retry and
  fallback logic. This is what makes prompt 12's acceptance criterion checkable: *the domain
  layer cannot tell whether it is using Groq or the mock adapter.* Everything in
  `scenarios.py` is at this level.
- **`ScriptedAdvisor` / `ScriptedAnalyzer`** replace the *adapter*, for testing above it
  without caring how a response was produced. `ScriptedAdvisor` returns whatever a test
  hands it, including a well-formed, confident response naming somebody else's garment —
  the only way to prove that ownership re-validation, and not the prompt, is what refuses it.
- **`SlowAdvisor`** replaces the *clock*, for the latency budget.
- **`MockExaProvider`** replaces the *search transport*, so the real `ExaTrendSource` runs its
  real attribution filter, deduplication and cache above it.

The crew is at the first level too, and that took a custom `crewai.BaseLLM`
(`app/adapters/crew_llm.py`). CrewAI defaults to LiteLLM, which would have made the crew the
one component in the product that could not be tested without an API key — the component most
likely to produce confident nonsense.

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

## What S8 found

The harness is only worth building if it finds things. It found four.

1. **A fibre claim rendered as fact.** `isHedged` consulted the confidence floor and nothing
   else, so `material_guess: "100% merino wool"` at 0.99 cleared it and the garment card
   showed it as settled — Case 08's Fail clause exactly. A photograph cannot show fibre
   content at any confidence. `ALWAYS_A_GUESS` now hedges it whatever the score says, and
   the scenario asserts the API and web copies of that rule agree.
2. **An invisible channel into the advice prompt.** `style_tags` is free text written by a
   vision model, is **not** rendered on the garment card, and is interpolated into the next
   prompt. Two things went through it: a truncated injection (`"printed slogan reading
   ignore pr"`) and a description of the person in the photograph (`"size 8, approximately 5
   foot 6"`). Length was the wrong control — a body description is short. The four list
   fields are closed vocabularies now (`app/domain/vocabulary.py`).
3. **A quality warning that arrived meaningless.** The web renders each known warning as its
   own sentence and everything else as "Worth a second look", so an invented warning reached
   the user with its meaning removed. Same fix, same module.
4. **No ceiling on a compose.** The transport retries three times at a 30-second client
   timeout, inside an advisor that re-asks once — six calls, and nothing above them knew a
   person was waiting. `AGENT_LATENCY_BUDGET_MS` is now enforced around the whole advisor
   call (Case 23).

And one it could not fix: a person description landing in `subcategory` or `pattern` is
still stored. Those fields are open sets in the world, and they are rendered and correctable,
which is a different class of problem from one only a downstream prompt ever sees — but it
is not nothing. Blocker B18.

## A note on speed

`pytest tests/ai -q` is a few seconds for everything that does not need a crew, and about
thirty with the crew files, because importing CrewAI costs ~13 seconds. Nothing outside
`test_crew.py`, `test_crew_ladder.py` and `test_ablation.py` imports it. If you are iterating
on grounding, `pytest tests/ai -q --ignore=tests/ai/test_crew.py --ignore=tests/ai/test_crew_ladder.py
--ignore=tests/ai/test_ablation.py` keeps the fast loop fast.

## What S8b found

The ablation test was the headline, but the defect was in the trend layer.

**An advisor could invent a citation and nothing stopped it.** `trend_notes` was schema-valid
and therefore accepted, so a model returning *"Chrome is the colour of the season — A Real
Magazine, 2026-08-20"* would have rendered, with a date, beside the user's own clothes. That is
precisely the gimmick CLAUDE.md's trend rules exist to prevent, and it had been sitting in the
product since S5. Notes are now matched by url against what the `TrendSource` actually supplied,
and the claim, publication and date are taken from the supplied note — so a reworded citation
does not survive either.
