"""The evaluation runner — the part a reviewer runs rather than reads.

    python tests/ai/runner.py                 every scenario, as a readable report
    python tests/ai/runner.py --case 11       just the cross-user isolation case
    python tests/ai/runner.py --coverage      docs/AI-EVAL-CASES.md, with what covers each
    python tests/ai/runner.py --response FILE your own model output, through the same stack
    python tests/ai/runner.py --json          the same results, for CI

No API key, no network, no cost. Exit code 1 if any check did not hold, so this is usable
as a gate as well as a demonstration.

The scenarios themselves are in `scenarios.py` and are the same objects `test_scenarios.py`
asserts over. This file only decides how they are printed — which matters, because a demo
that runs different code from the suite is a demo that can pass while the product is broken.

`--response` is prompts/10's acceptance criterion taken literally: write what you want the
model to have said into a file, point this at it, and watch what the application does with
it. Try naming `u2-jacket` (another user's garment), an id nobody owns, or a sentence of
English where JSON was required.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # so `python tests/ai/runner.py` works from the repo root
    sys.path.insert(0, str(HERE))
if str(HERE.parents[1] / "apps" / "api") not in sys.path:
    sys.path.insert(0, str(HERE.parents[1] / "apps" / "api"))

from cases import CASES, coverage_table
from scenarios import Check, custom_response, run_all

TICK, CROSS = "PASS", "FAIL"
RULE = "-" * 78


def _wrap(text: str, indent: int = 16, width: int = 78) -> str:
    """Soft-wrap a value under its label, so a long observation stays readable."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width - indent:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return f"\n{' ' * indent}".join(lines)


def render(check: Check) -> str:
    body = [
        f"  case {check.case:>2}  {check.name}",
        f"      injected  {_wrap(check.injected)}",
        f"      expected  {_wrap(check.expected)}",
        f"      observed  {_wrap(check.observed)}",
    ]
    for line in check.evidence:
        if line:
            body.append(f"      evidence  {_wrap(line)}")
    body.append(f"      {TICK if check.held else CROSS}")
    return "\n".join(body)


def _header() -> str:
    return (
        "\nSTYLELAB — AI evaluation runner\n"
        "the real adapter stack over scripted provider bytes: no API key, no network\n"
        f"{RULE}"
    )


async def _scenarios(case: str | None, as_json: bool) -> int:
    report = await run_all(case)

    if as_json:
        print(
            json.dumps(
                {
                    "checks": [
                        {
                            "case": c.case,
                            "name": c.name,
                            "injected": c.injected,
                            "expected": c.expected,
                            "observed": c.observed,
                            "held": c.held,
                            "evidence": list(c.evidence),
                        }
                        for c in report.checks
                    ],
                    "ok": report.ok,
                },
                indent=2,
            )
        )
        return 0 if report.ok else 1

    print(_header())
    for check in report.checks:
        print(render(check))
        print()
    held = len(report.checks) - len(report.broken)
    print(RULE)
    print(f"{held}/{len(report.checks)} checks held")
    if report.broken:
        print("\nnot held:")
        for check in report.broken:
            print(f"  case {check.case}  {check.name}")
    return 0 if report.ok else 1


async def _custom(path: Path, as_json: bool) -> int:
    content = path.read_text(encoding="utf-8")
    check = await custom_response(content, label=f"your response from {path.name}")

    if as_json:
        print(json.dumps({"held": check.held, "observed": check.observed}, indent=2))
    else:
        print(_header())
        print("  the wardrobe: eval-u1 owns own-top, own-second-top, own-bottom, own-shoe.")
        print("  eval-u2 owns u2-jacket, which eval-u1 must never be shown.\n")
        print(render(check))
        print(f"\n{RULE}")
        print(
            "held means no garment outside eval-u1's wardrobe reached the answer.\n"
            "It does not mean the response was accepted — read `observed` for that."
        )
    return 0 if check.held else 1


def _coverage(as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "case": c.case,
                        "title": c.title,
                        "status": c.status,
                        "covered_by": list(c.covered_by),
                        "note": c.note,
                    }
                    for c in CASES
                ],
                indent=2,
            )
        )
        return 0
    print(_header())
    print(coverage_table())
    return 0


def main(argv: list[str] | None = None) -> int:
    # The report is prose about a fashion product, so it contains em dashes and the odd
    # accent. A Windows console defaults to cp1252 and raises on them, which would make the
    # runner unusable on the machine this was built on.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="runner.py",
        description="Run the STYLELAB AI evaluation cases with no API key.",
    )
    parser.add_argument("--case", help="only scenarios evidencing this case id, e.g. 11")
    parser.add_argument(
        "--response",
        type=Path,
        metavar="FILE",
        help="feed your own provider output through the real stack and watch what happens",
    )
    parser.add_argument("--coverage", action="store_true", help="the case registry, as a table")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if args.coverage:
        return _coverage(args.as_json)
    if args.response is not None:
        return asyncio.run(_custom(args.response, args.as_json))
    return asyncio.run(_scenarios(args.case, args.as_json))


if __name__ == "__main__":
    raise SystemExit(main())
