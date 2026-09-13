"""The meta-test: does the coverage claim survive contact with the repository?

`docs/AI-EVAL-CASES.md` lists twenty-five cases and `cases.py` says what evidences each one.
Neither is worth much on its own — a doc nobody checks and a list nobody resolves — so this
file makes the pair load-bearing:

* every case in the markdown is in the registry, and nothing in the registry is invented
* every `file::symbol` reference names something actually defined in that file
* every file-level reference actually contains the case id it is claimed for
* a case claiming coverage claims some, and one claiming none says who owns it
* the scenarios' own registrations agree with the registry

The third rule is the one that bites. This repository already writes `Case NN` into the
docstring of the test that covers it; this turns that habit into a constraint. Rename the
test and the reference stops resolving. Delete it and its marker goes with it. There is no
way to keep the claim while removing the thing it claims.

Cheap by design: `ast` and `str.__contains__`, no imports of the files being checked, so this
runs in milliseconds and can sit in front of every push.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from cases import BY_ID, CASES
from scenarios import REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "docs" / "AI-EVAL-CASES.md"

#: `## Case 07 — Prompt injection via image`
_HEADING = re.compile(r"^##\s+Case\s+(\d{2})\s+[—-]\s+(.+?)\s*$", re.MULTILINE)


def documented() -> dict[str, str]:
    return {number: title for number, title in _HEADING.findall(SPEC.read_text(encoding="utf-8"))}


def defined_symbols(source: str) -> set[str]:
    """Top-level function and class names in Python source.

    Parsed, not searched. A substring check for `cross_user_item` matches a mention in a
    comment, a docstring, or a `# TODO: write cross_user_item` — which is precisely the kind
    of false confidence this file exists to remove.

    Takes source rather than a path so the property can be tested directly. A mutation that
    swapped the parse for a substring check survived the first mutation run, because every
    symbol currently referenced also happens to appear literally in its file: the two agreed
    on today's data and the parse was doing no work anybody could see.
    """
    tree = ast.parse(source)
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


# --- the registry against the specification ----------------------------------------------


def test_the_registry_and_the_specification_list_the_same_cases():
    assert set(BY_ID) == set(documented())


def test_every_registered_title_matches_the_specification():
    """Titles drift when a case is reworded in the doc and nowhere else, and a reviewer
    reading the runner's table would then be reading a stale name for a live case."""
    spec = documented()

    assert {case.case: case.title for case in CASES} == spec


# --- the registry against the code ---------------------------------------------------------


def unresolved(reference: str, case: str, root: Path = REPO_ROOT) -> str | None:
    """Why this coverage claim does not hold, or `None` if it does.

    A function rather than a block of asserts inside the parameterised test, so the rule can
    be driven with a reference that *should* fail. Inline, it could only ever be run against
    a registry in which everything resolves — which tests that the happy path is happy and
    leaves the interesting half unexercised.
    """
    path_part, _, symbol = reference.partition("::")
    path = root / path_part
    if not path.exists():
        return f"names {path_part}, which does not exist"

    source = path.read_text(encoding="utf-8")
    if symbol:
        if symbol not in defined_symbols(source):
            return f"names {reference}, but {symbol} is not defined there"
        return None

    # A whole-file claim has to be visible in the file, in the convention this repository
    # already follows.
    if f"Case {case}" in source:
        return None
    return f"claims {path_part}, which never mentions Case {case}"


@pytest.mark.parametrize("case", CASES, ids=[case.case for case in CASES])
def test_every_reference_resolves(case):
    for reference in case.covered_by:
        problem = unresolved(reference, case.case)
        assert problem is None, f"case {case.case} {problem}"


def test_a_symbol_that_is_only_mentioned_does_not_resolve(tmp_path):
    """The property the `ast` parse buys, driven through the real resolution path.

    A mutation that swapped the parse for a substring check survived the first mutation run:
    every symbol the registry references also happens to appear literally in its file, so the
    two implementations agreed on today's data and the parse was doing no work anybody could
    observe. They differ on a file that talks about a test without having one, which is
    exactly the drift this whole file exists to catch — so that is what is asserted.
    """
    (tmp_path / "pretend.py").write_text(
        '"""Case 99 — a module that talks about cross_user_item without having one."""\n'
        "# TODO: write cross_user_item\n"
        'PLANNED = ["cross_user_item"]\n\n'
        "def something_else():\n"
        '    """Related to cross_user_item."""\n',
        encoding="utf-8",
    )

    assert unresolved("pretend.py::cross_user_item", "99", tmp_path) is not None
    assert unresolved("pretend.py::something_else", "99", tmp_path) is None
    # And the file-level form still resolves on the marker, so the two rules stay distinct.
    assert unresolved("pretend.py", "99", tmp_path) is None
    assert unresolved("pretend.py", "01", tmp_path) is not None


def test_a_covered_case_names_its_evidence():
    for case in CASES:
        if case.status == "covered":
            assert case.covered_by, f"case {case.case} claims coverage and names nothing"


def test_a_deferred_case_claims_nothing_and_says_who_owns_it():
    """The honest half of the ledger, and the reason it is trustworthy.

    B11 is the precedent: the ablation test does not exist, CI's `ai-eval` step is red
    because of it, and nobody stubbed it green. A registry that could quietly mark a case
    covered would undo that.
    """
    for case in CASES:
        if case.status == "deferred":
            assert not case.covered_by, f"case {case.case} is deferred but names evidence"
            assert case.note, f"case {case.case} is deferred with no explanation"
            assert "S8b" in case.note or "S9" in case.note, (
                f"case {case.case} is deferred without naming the session that owns it"
            )


def test_a_partial_case_says_which_half_is_missing():
    for case in CASES:
        if case.status == "partial":
            assert case.covered_by, f"case {case.case} is partial but names no evidence"
            assert len(case.note) > 80, (
                f"case {case.case} is partial with a note too short to say what is missing"
            )


# --- the scenarios against the registry -------------------------------------------------------


def test_every_scenario_names_a_case_that_exists():
    for case, name, _ in REGISTRY:
        assert case in BY_ID, f"scenario {name!r} evidences case {case}, which is not a case"


def test_every_scenario_is_claimed_by_the_case_it_evidences():
    """A scenario the registry does not know about is work a reviewer will never be shown."""
    claimed = {
        reference.partition("::")[2]
        for case in CASES
        for reference in case.covered_by
        if reference.startswith("tests/ai/scenarios.py::")
    }
    registered = {fn.__name__ for _, _, fn in REGISTRY}

    assert registered == claimed


def test_the_status_counts_are_what_the_ledger_says():
    """A tripwire, not a tautology.

    S8 leaves seven cases short of full coverage: six wait on the agent crew and one (09)
    waits on a decision about free-text extraction fields, blocker B18. If that number
    changes, docs/PROGRESS.md and the S8b plan are both stale, and this is the thing that
    says so out loud rather than letting the drift sit.
    """
    counts = {
        status: sum(1 for case in CASES if case.status == status)
        for status in ("covered", "partial", "deferred")
    }

    assert counts == {"covered": 18, "partial": 5, "deferred": 2}
