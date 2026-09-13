"""The case registry — docs/AI-EVAL-CASES.md, wired to the code that evidences it.

A coverage claim written in prose is a coverage claim nobody can check, and the failure mode
is silent: a test gets renamed or deleted, the doc still says the case is covered, and the
next person to read it believes the doc. So the mapping lives here as data and
`test_case_coverage.py` resolves every entry:

* every case in the markdown appears here, and nothing here is invented
* every `file::symbol` reference names something that is actually defined in that file
* every file-level reference actually mentions the case id it is claimed for
* a `deferred` case names the session that owns it, and claims no coverage
* a `partial` case says exactly which half is missing

The third rule is what gives the registry teeth. Tests in this repository already carry
`Case NN` in their docstrings by convention; the meta-test turns that convention into a
constraint, so deleting the test deletes the marker and the claim fails with it.

`covered_by` is deliberately not exhaustive. It names the evidence a reviewer should read,
not every assertion that touches the subject — a list of forty test names is a list nobody
opens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["covered", "partial", "deferred"]


@dataclass(frozen=True, slots=True)
class EvalCase:
    case: str
    title: str
    status: Status
    #: Repository-relative paths, optionally `::symbol`. Resolved by the meta-test.
    covered_by: tuple[str, ...] = ()
    #: Required for `partial` and `deferred`. What is missing, and who owns it.
    note: str = ""


S = "tests/ai/scenarios.py"

CASES: tuple[EvalCase, ...] = (
    EvalCase(
        "01",
        "Wardrobe grounding",
        "covered",
        (
            f"{S}::invented_item",
            "tests/ai/test_grounding.py",
            "apps/api/tests/test_composition.py",
        ),
    ),
    EvalCase(
        "02",
        "Category validity",
        "covered",
        (
            f"{S}::two_tops",
            f"{S}::duplicate_garment",
            "apps/api/tests/test_compatibility.py",
        ),
    ),
    EvalCase("03", "Occasion", "covered", ("apps/api/tests/test_ranker.py",)),
    EvalCase(
        "04",
        "Preference adherence",
        "covered",
        ("apps/api/tests/test_ranker.py", "apps/api/tests/test_compose_service.py"),
    ),
    EvalCase("05", "Swap", "covered", ("apps/api/tests/test_compose_service.py",)),
    EvalCase(
        "06",
        "Invalid model output",
        "covered",
        (
            f"{S}::prose_response",
            f"{S}::truncated_response",
            f"{S}::empty_response",
            f"{S}::wrong_types",
            "apps/api/tests/test_output_schema.py",
            "apps/api/tests/test_groq_adapter.py",
        ),
    ),
    EvalCase(
        "07",
        "Prompt injection via image",
        "covered",
        (
            f"{S}::image_text_injection",
            "apps/api/tests/test_hygiene.py",
            "apps/api/tests/test_prompt_contract.py",
            "apps/api/tests/test_ingest.py",
        ),
    ),
    EvalCase(
        "08",
        "Extraction honesty",
        "covered",
        (
            f"{S}::asserted_material",
            "apps/api/tests/test_prompt_contract.py",
            "apps/web/src/lib/schemas/wardrobe.test.ts",
        ),
    ),
    EvalCase(
        "09",
        "Vision uncertainty",
        "partial",
        (
            f"{S}::person_inference",
            f"{S}::no_fallback_on_low_confidence",
            "apps/api/tests/test_prompt_contract.py",
            "apps/api/tests/test_hygiene.py",
        ),
        note=(
            "The uncertainty half holds in full: a dark or cropped photograph comes back "
            "with quality warnings and low confidences, is hedged, and is offered for "
            "correction rather than retried for a better number. The person-inference half "
            "holds for the closed list fields, which are dropped, and not for the free-text "
            "ones — a description landing in `subcategory` is bounded, rendered and "
            "correctable, but it is stored. Blocker B18, S9."
        ),
    ),
    EvalCase("10", "Diversity", "covered", ("apps/api/tests/test_ranker.py",)),
    EvalCase(
        "11",
        "Cross-user isolation",
        "covered",
        (
            f"{S}::cross_user_item",
            f"{S}::foreign_item_absent_from_prompt",
            "apps/api/tests/test_ownership.py",
            "apps/api/tests/test_outfit_routes.py",
            "tests/ai/test_grounding.py",
        ),
    ),
    EvalCase(
        "12",
        "Insufficient wardrobe",
        "covered",
        (
            f"{S}::insufficient_wardrobe",
            "apps/api/tests/test_compatibility.py",
            "tests/ai/test_grounding.py",
        ),
    ),
    EvalCase(
        "13",
        "Correction persistence",
        "covered",
        ("apps/api/tests/test_corrections.py", "apps/api/tests/test_ingest.py"),
    ),
    EvalCase(
        "14",
        "Deleted item",
        "covered",
        ("apps/api/tests/test_outfit_routes.py", "apps/api/tests/test_wardrobe_routes.py"),
    ),
    EvalCase(
        "15",
        "Trend attribution",
        "covered",
        (
            "apps/api/tests/test_domain_models.py",
            "apps/api/tests/test_composition.py",
            "apps/api/tests/test_exa_trends.py",
        ),
    ),
    EvalCase(
        "16",
        "Trend cannot introduce a garment",
        "covered",
        (
            f"{S}::trend_names_unowned",
            "apps/api/tests/test_composition.py",
            "apps/api/tests/test_prompt_contract.py",
        ),
    ),
    EvalCase(
        "17",
        "Stale trend data",
        "covered",
        ("apps/api/tests/test_exa_trends.py",),
    ),
    EvalCase(
        "18",
        "Injection via trend copy",
        "covered",
        (f"{S}::injected_rationale", "apps/api/tests/test_exa_trends.py", "tests/ai/test_crew.py::test_case_19_an_upstream_agent_cannot_instruct_a_downstream_one"),
    ),
    EvalCase(
        "19",
        "Agent-to-agent injection",
        "covered",
        (
            f"{S}::injected_rationale",
            "apps/api/tests/test_prompt_contract.py",
            "tests/ai/test_crew.py::test_case_19_an_upstream_agent_cannot_instruct_a_downstream_one",
        ),
    ),
    EvalCase(
        "20",
        "Crew output still fails ownership",
        "covered",
        (
            "tests/ai/test_crew.py::test_case_20_a_confident_crew_response_still_fails_ownership",
            "tests/ai/test_crew_ladder.py",
            f"{S}::cross_user_item",
        ),
    ),
    EvalCase("21", "Agent ablation", "covered", ("tests/ai/test_ablation.py",)),
    EvalCase(
        "22",
        "Advisory safety",
        "covered",
        (f"{S}::unsafe_tips", "apps/api/tests/test_advisory.py", "apps/api/tests/test_ranker.py"),
    ),
    EvalCase(
        "23",
        "Latency circuit breaker",
        "covered",
        (
            f"{S}::latency_budget",
            "apps/api/tests/test_circuit.py",
            "tests/ai/test_crew_ladder.py",
            "apps/api/tests/test_composition.py",
        ),
    ),
    EvalCase(
        "24",
        "Vision fallback is availability-only",
        "covered",
        (
            f"{S}::fallback_on_outage",
            f"{S}::no_fallback_on_low_confidence",
            "apps/api/tests/test_groq_adapter.py",
            "apps/api/tests/test_ingest.py",
        ),
    ),
    EvalCase(
        "25",
        "No silent stub in production",
        "covered",
        (
            "apps/api/tests/test_boot.py",
            "apps/api/tests/test_config.py",
            "apps/api/tests/test_query_scoping.py",
        ),
    ),
)

BY_ID: dict[str, EvalCase] = {case.case: case for case in CASES}


MARKS: dict[str, str] = {"covered": " ok ", "partial": "part", "deferred": "todo"}


def coverage_table(width: int = 88) -> str:
    """The registry as something a person reads. Printed by `runner.py --coverage`."""
    lines = [f"  {'case':<5}{'':<7}{'title':<40}evidence", f"  {'-' * (width - 2)}"]

    for case in CASES:
        mark = f"[{MARKS[case.status]}]"
        evidence = case.covered_by or ("—",)
        lines.append(f"  {case.case:<5}{mark:<7}{case.title:<40}{evidence[0]}")
        for extra in evidence[1:]:
            lines.append(f"  {'':<52}{extra}")
        if case.note:
            for line in _fold(case.note, width - 13):
                lines.append(f"  {'':<11}{line}")

    tally = {status: sum(1 for c in CASES if c.status == status) for status in MARKS}
    lines.append(f"  {'-' * (width - 2)}")
    lines.append(
        f"  {len(CASES)} cases: "
        + ", ".join(f"{count} {status}" for status, count in tally.items())
    )
    return "\n".join(lines)


def _fold(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


__all__ = ["BY_ID", "CASES", "MARKS", "EvalCase", "Status", "coverage_table"]
