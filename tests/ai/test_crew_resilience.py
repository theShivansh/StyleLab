"""The crew under the failures the deployed site actually produced.

Every deployed composition fell to the deterministic ranker. Two causes, and neither was
visible to the mock suite, because nothing here had ever refused a call the way a busy
provider does:

* the Trend Scout's answer was cut off by its output ceiling, the provider refused the
  truncated JSON (`json_validate_failed`), and that one optional agent's refusal ended the
  whole crew
* the crew spent more tokens than the account's minute allows, overran its latency budget,
  and was discarded — first draft and all

What is pinned down here: a truncated answer gets one retry with more room; an optional role
that fails is left out and disclosed on the rung; a rebuild that cannot finish in time is not
started; nothing CrewAI does on its own spends a call we did not ask for; and no prompt pays
for a schema the provider already enforces.
"""

from __future__ import annotations

import json

import pytest
from app.adapters.crew import CrewAIOutfitAdvisor, CrewRoles
from app.adapters.provider_errors import (
    ProviderOutputInvalidError,
    ProviderRateLimitedError,
    ProviderRefusedError,
)
from app.domain.errors import SchemaInvalidError
from app.domain.models import AdviceRequest
from app.domain.models import GarmentCategory as C
from app.services.composition import CompositionService
from crew_fixtures import LOOK, crew_script
from harness import OWNED, U1
from stubs import MockGroqProvider, garment, trend_note

TREND_URL = "https://example-publication.test/neutral-palettes"

#: A Critic that wants the look rebuilt, with something a rebuild could act on.
WEAK = json.dumps(
    {
        "considered": ["formality"],
        "tradeoffs": [],
        "objections": ["the shoe is too formal for the occasion"],
        "score": 40,
    }
)
GOOD = json.dumps({"considered": [], "tradeoffs": [], "objections": [], "score": 88})


def candidates():
    return [
        garment(item_id, U1, category=category, color_primary=colour)
        for item_id, category, colour in OWNED
    ]


def request_for(**over):
    payload = {
        "user_id": U1,
        "candidates": candidates(),
        "occasion": "everyday",
        "required_roles": [C.TOP, C.BOTTOM, C.FOOTWEAR],
    }
    payload.update(over)
    return AdviceRequest(**payload)


def truncated() -> ProviderOutputInvalidError:
    """What the transport raises for `json_validate_failed`."""
    error = ProviderOutputInvalidError("the generation was cut off", model="eval/text")
    error.provider_code = "json_validate_failed"
    return error


def busy() -> ProviderRateLimitedError:
    return ProviderRateLimitedError("the minute is spent", model="eval/text")


def crew(transport: MockGroqProvider, **over) -> CrewAIOutfitAdvisor:
    return CrewAIOutfitAdvisor(transport, model="eval/text", **over)


# --- an optional role that fails is left out, not fatal -----------------------------------------


async def test_a_refused_trend_scout_costs_a_rung_not_the_crew():
    """The deployed failure, exactly: articles retrieved, the scout's answer refused, and —
    before this — the ranker served in place of everything else the crew had done."""
    transport = MockGroqProvider(by_schema=crew_script(trend_application=truncated()))
    subject = crew(transport)

    advice = await subject.advise(request_for(trend_notes=[trend_note(url=TREND_URL)]))

    assert advice.outfit is not None
    assert advice.outfit.item_ids == LOOK
    assert advice.trend_notes == []
    assert advice.degradation_level == 2
    assert subject.last_run.dropped_roles == ["trend_scout"]
    assert transport.schemas_called[-1] == "editor_output"


@pytest.mark.parametrize(
    ("schema", "role"),
    [
        ("style_profile", "style_profiler"),
        ("critique", "critic"),
        ("practical_advice", "practical_advisor"),
    ],
)
async def test_a_deliberating_role_that_fails_is_disclosed_as_a_shorter_round(schema, role):
    transport = MockGroqProvider(by_schema=crew_script(**{schema: busy()}))
    subject = crew(transport)

    advice = await subject.advise(request_for())

    assert advice.outfit is not None
    assert advice.degradation_level == 3
    assert subject.last_run.dropped_roles == [role]


@pytest.mark.parametrize("schema", ["outfit_draft", "editor_output"])
async def test_the_architect_and_the_editor_are_still_required(schema):
    """Leaving out the role that builds the look, or the one that returns it, is not a
    degradation. It is the absence of an answer, and the service's ranker is what follows."""
    transport = MockGroqProvider(
        by_schema=crew_script(**{schema: ProviderRefusedError("no", model="eval/text")})
    )

    with pytest.raises(ProviderRefusedError):
        await crew(transport).advise(request_for())


async def test_the_composition_shows_the_rung_the_crew_actually_ran_at():
    """The service used to overwrite the advisor's rung with the trend lookup's, so a crew
    that served without its Critic still said "full crew" on screen."""
    transport = MockGroqProvider(by_schema=crew_script(critique=busy()))
    service = CompositionService(repository=None, advisor=crew(transport))

    advice = await service.compose(U1, occasion="everyday", candidates=candidates())

    assert advice.outfit is not None
    assert advice.degradation_level == 3


async def test_a_spent_day_is_named_where_the_ranker_is_served(caplog):
    """Every deployed composition fell to the ranker with "advisor unavailable" in the log, and
    the reason — the account's tokens for the day were gone — was only in Groq's message, which
    is never logged. The limit and the wait are attributes, and the log line carries them."""
    import logging

    spent = ProviderRateLimitedError("no", model="eval/text", retry_after_s=181, limit="TPD")
    transport = MockGroqProvider(by_schema=crew_script(outfit_draft=spent))
    service = CompositionService(repository=None, advisor=crew(transport))

    with caplog.at_level(logging.WARNING):
        advice = await service.compose(U1, occasion="everyday", candidates=candidates())

    assert advice.degradation_level == 4
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "advisor unavailable (AI_RATE_LIMITED limit=TPD retry_after_s=181)" in logged


# --- a truncated answer gets one retry with more room ---------------------------------------------


async def test_a_truncated_answer_is_retried_once_with_twice_the_room():
    transport = MockGroqProvider(
        by_schema=crew_script(outfit_draft=[truncated(), crew_script()["outfit_draft"]])
    )
    subject = crew(transport, max_tokens=800)

    advice = await subject.advise(request_for())

    ceilings = [call.max_tokens for call in transport.calls if call.schema_name == "outfit_draft"]
    assert ceilings == [800, 1600]
    assert advice.outfit is not None
    assert advice.degradation_level == 1
    assert subject.last_run.dropped_roles == []


async def test_a_required_role_truncated_twice_is_a_schema_failure_after_exactly_two_calls():
    """Counted as a schema failure rather than an outage, and bounded: the first call, the one
    retry with more room, and nothing else."""
    transport = MockGroqProvider(by_schema=crew_script(editor_output=truncated()))
    subject = crew(transport, max_tokens=800)

    with pytest.raises(SchemaInvalidError):
        await subject.advise(request_for())

    assert transport.schemas_called.count("editor_output") == 2


async def test_the_framework_never_re_runs_a_failed_agent_on_its_own():
    """CrewAI re-executes a failed task twice by default. Each re-run is a whole agent call
    against a per-minute token limit, and the deployed log showed a refusal nested three deep."""
    transport = MockGroqProvider(by_schema=crew_script(critique=busy()))

    await crew(transport).advise(request_for())

    assert transport.schemas_called.count("critique") == 1


# --- the rebuild -------------------------------------------------------------------------------


async def test_a_rebuild_that_cannot_finish_in_time_is_not_started():
    transport = MockGroqProvider(by_schema=crew_script(critique=WEAK))
    # A budget already spent by the time the Critic answers.
    subject = crew(transport, latency_budget_s=1e-9)

    advice = await subject.advise(request_for())

    assert advice.outfit is not None
    assert transport.schemas_called.count("outfit_draft") == 1
    assert subject.last_run.revision_skipped is True
    assert subject.last_run.revised is False
    # The Critic asked for more reasoning than the look got, and the rung says so.
    assert advice.degradation_level == 3


async def test_a_rebuild_with_time_left_still_happens():
    """The control. A cutoff that never lets a rebuild run has deleted the reflexion loop."""
    transport = MockGroqProvider(by_schema=crew_script(critique=[WEAK, GOOD]))
    subject = crew(transport, latency_budget_s=600)

    advice = await subject.advise(request_for())

    assert transport.schemas_called.count("outfit_draft") == 2
    assert subject.last_run.revised is True
    assert subject.last_run.revision_skipped is False
    assert advice.degradation_level == 1


async def test_a_rebuild_that_fails_keeps_the_first_draft():
    first = crew_script()["outfit_draft"]
    transport = MockGroqProvider(
        by_schema=crew_script(critique=WEAK, outfit_draft=[first, busy()])
    )
    subject = crew(transport)

    advice = await subject.advise(request_for())

    assert advice.outfit is not None
    assert advice.outfit.item_ids == LOOK
    assert subject.last_run.revision_skipped is True
    assert advice.degradation_level == 3


# --- what the crew sends ---------------------------------------------------------------------------


async def test_no_prompt_pays_for_a_schema_the_provider_already_enforces():
    """CrewAI pastes an `output_pydantic` model's whole JSON Schema into the task prompt, class
    docstring included, while the same schema goes to the provider as strict structured output.
    Captured from a live Editor call: most of its prompt was that block."""
    transport = MockGroqProvider(by_schema=crew_script())

    await crew(transport).advise(request_for(trend_notes=[trend_note(url=TREND_URL)]))

    assert transport.calls
    for call in transport.calls:
        assert "OpenAPI schema" not in call.text
        assert '"additionalProperties"' not in call.text
        assert "Untrusted like every other agent" not in call.text
        assert "LLM-as-judge" not in call.text
    # Not vacuous: the block was there to be replaced, on every call.
    assert all("schema is enforced" in call.text for call in transport.calls)


@pytest.mark.parametrize("effort", ["low", None])
async def test_every_agent_call_carries_the_configured_reasoning_effort(effort):
    transport = MockGroqProvider(by_schema=crew_script())

    await crew(transport, reasoning_effort=effort).advise(
        request_for(trend_notes=[trend_note(url=TREND_URL)])
    )

    assert {call.reasoning_effort for call in transport.calls} == {effort}


async def test_a_reduced_crew_keeps_the_reasoning_effort():
    """The breaker's rung-3 copy is built from the original. A copy that forgot the setting
    would reason at the provider's default exactly when the account is already struggling."""
    transport = MockGroqProvider(by_schema=crew_script())
    subject = crew(transport, reasoning_effort="low", latency_budget_s=15)

    reduced = subject.with_roles(CrewRoles.architect_and_editor_only(), degradation_level=3)
    await reduced.advise(request_for())

    assert {call.reasoning_effort for call in transport.calls} == {"low"}
