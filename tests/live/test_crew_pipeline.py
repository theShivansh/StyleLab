"""The crew against real Groq — the six schemas no mock can validate.

`tests/ai/` proves the crew's logic for free on every push. It cannot prove that Groq accepts
what we send it: `MockGroqProvider` returns scripted content and never validates the JSON
Schema it was handed. S8b added **six new strict schemas** in one go, which is exactly the
class of change S6 learned to distrust — two schema bugs were green in the mock suite for a
whole phase and failed on the first real call.

So this file asks the only question a real call answers, and records the per-agent latency
while it is there, because that number is the one `docs/AGENT-SYSTEM.md` makes a claim about.

Billed, `smoke`-marked, and pointedly small: one composition.
"""

from __future__ import annotations

import pytest
from app.adapters.crew import OUTPUT_BUDGET, CrewAIOutfitAdvisor, CrewRoles
from app.domain.models import (
    AdviceRequest,
    GarmentExtraction,
    ItemStatus,
    WardrobeItem,
)
from app.domain.models import GarmentCategory as C
from capacity import tolerating_capacity


def item(item_id: str, category: C, subcategory: str, colour: str) -> WardrobeItem:
    return WardrobeItem(
        item_id=item_id,
        user_id="live",
        status=ItemStatus.READY,
        corrected_fields=[],
        extraction=GarmentExtraction(
            category=category,
            subcategory=subcategory,
            color_primary=colour,
            pattern="solid",
            material_guess="cotton",
            fit="regular",
            field_confidence={"category": 0.95},
            style_tags=["minimal"],
        ),
    )


WARDROBE = [
    item("shirt", C.TOP, "oxford shirt", "white"),
    item("chino", C.BOTTOM, "chino", "stone"),
    item("sneaker", C.FOOTWEAR, "sneaker", "white"),
]


@pytest.mark.smoke
async def test_the_crew_composes_a_real_look_and_every_agent_schema_holds(
    transport, settings, capsys
):
    """One live composition. Six strict schemas, six real answers.

    The Trend Scout is off: it needs `EXA_API_KEY` and a live search, and this test is about
    whether Groq accepts the crew's structured outputs. Its schema is exercised by
    `tests/ai/test_crew.py` and its retrieval by `apps/api/tests/test_exa_trends.py`.
    """
    advisor = CrewAIOutfitAdvisor(
        transport,
        model=settings.groq_text_model,
        roles=CrewRoles(trend_scout=False),
        max_tokens=settings.agent_max_output_tokens,
    )
    request = AdviceRequest(
        user_id="live",
        candidates=WARDROBE,
        occasion="everyday",
        required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR],
    )

    with tolerating_capacity():
        advice = await advisor.advise(request)

    run = advisor.last_run
    assert advice.outfit is not None
    # Grounded: the crew may only ever name what it was given.
    assert set(advice.outfit.item_ids) <= {i.item_id for i in WARDROBE}
    assert advice.rationale
    # A set, not a sequence. The Critic and the Practical Advisor run concurrently, so which
    # of them finishes first is genuinely undefined — asserting an order here would be a test
    # that fails half the time to enforce something the design deliberately does not promise.
    assert set(run.roles_run) == {
        "style_profiler",
        "outfit_architect",
        "critic",
        "practical_advisor",
        "editor",
    }
    assert run.roles_run[0] == "style_profiler"
    assert run.roles_run[-1] == "editor"
    # The judge produced a real number, and the loop either accepted or rejected on it.
    assert run.score_before is not None and 0 <= run.score_before <= 100

    # Printed rather than asserted. The wall-clock claim in docs/AGENT-SYSTEM.md is about a
    # healthy provider, and this account is rate-limited (blocker B17) in a way that makes any
    # threshold here a test of somebody else's capacity. `-s` to read it.
    with capsys.disabled():
        print(f"\n  crew: {run.latency_ms} ms, {run.prompt_tokens} in / {run.completion_tokens} out")
        for call in run.calls:
            revision = "  [revision]" if call.revision else ""
            print(
                f"    {call.role:<20} {call.latency_ms:>6} ms  "
                f"in={call.prompt_tokens} out={call.completion_tokens}{revision}"
            )


@pytest.mark.smoke
async def test_the_editor_has_room_to_finish_its_answer(transport, settings):
    """The regression for a bug only a live call could show.

    Under strict Structured Outputs an unfinished response is not a short answer, it is an
    *invalid* one: the provider refuses it with `json_validate_failed`, naming the properties
    that never arrived. At a flat 800-token ceiling the Editor was truncated mid-object,
    refused, and retried — 26 of one composition's 34 seconds.

    Asserted against the response rather than the ceiling: what matters is that the last agent
    finishes, whatever `OUTPUT_BUDGET` happens to say tomorrow.
    """
    assert OUTPUT_BUDGET["editor"] > OUTPUT_BUDGET["critic"], "the editor writes the most"

    advisor = CrewAIOutfitAdvisor(
        transport,
        model=settings.groq_text_model,
        roles=CrewRoles.architect_and_editor_only(),
        max_tokens=settings.agent_max_output_tokens,
    )
    request = AdviceRequest(
        user_id="live",
        candidates=WARDROBE,
        occasion="everyday",
        required_roles=[C.TOP, C.BOTTOM, C.FOOTWEAR],
    )

    with tolerating_capacity():
        advice = await advisor.advise(request)

    assert advice.outfit is not None
    assert advice.outfit.name
    # The fields that were being cut off. Empty is a legitimate answer; missing is not, and a
    # truncated generation never reaches here at all.
    assert advice.budget_tricks is not None
    assert advice.wardrobe_gaps is not None
