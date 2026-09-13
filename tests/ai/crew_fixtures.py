"""Scripted crew responses, keyed by the schema each agent asks for.

Every agent in the crew uses the same model id and requests a different structured output, so
the **schema name** is the only thing that identifies which agent is speaking. `MockGroqProvider`
scripts on it (`by_schema`), which makes these fixtures order-independent — necessary, because
two pairs of agents run concurrently and there is no stable call order to script against.

`crew_script()` returns a fresh dict every time so a test can mutate one role's answer without
leaking into the next test. That has already caught one bug in this file.
"""

from __future__ import annotations

import json
from typing import Any

#: The wardrobe every crew test composes from — the same ids `harness.py` owns, so a forged
#: cross-user response can be dropped straight into these scripts.
LOOK = ["own-top", "own-bottom", "own-shoe"]


def _profile(**over: Any) -> str:
    return json.dumps(
        {
            "aesthetic": "quiet, neutral, softly tailored",
            "recurring_colours": ["navy", "stone", "white"],
            "preferred_silhouettes": ["relaxed top", "straight leg"],
            "observations": ["reaches for neutrals before anything else"],
            **over,
        }
    )


def _draft(item_ids: list[str] | None = None, **over: Any) -> str:
    return json.dumps(
        {
            "item_ids": item_ids or LOOK,
            "name": "Quiet Weekday",
            "occasion": "everyday",
            "rationale": ["The palette holds together.", "The volumes balance."],
            **over,
        }
    )


def _critique(score: int = 84, objections: list[str] | None = None, **over: Any) -> str:
    return json.dumps(
        {
            "considered": ["proportion", "palette"],
            "tradeoffs": ["a softer shoe would lift it"],
            "objections": objections or [],
            "score": score,
            **over,
        }
    )


def _practical(**over: Any) -> str:
    return json.dumps(
        {
            "pro_tips": [{"tip": "Half-tuck the shirt to shorten the torso.", "type": "proportion"}],
            "budget_tricks": ["Worn open over a tee this shirt is a second outfit."],
            "wardrobe_gaps": [
                {
                    "category": "outerwear",
                    "generic_description": "an unstructured jacket that layers over a shirt",
                    "unlocks_outfits": 3,
                }
            ],
            **over,
        }
    )


def _editor(item_ids: list[str] | None = None, **over: Any) -> str:
    payload: dict[str, Any] = {
        "item_ids": item_ids or LOOK,
        "name": "Quiet Weekday",
        "occasion": "everyday",
        "rationale": ["The palette holds together."],
        "confidence": 0.84,
        "pro_tips": [{"tip": "Half-tuck the shirt to shorten the torso.", "type": "proportion"}],
        "budget_tricks": ["Worn open over a tee this shirt is a second outfit."],
        "wardrobe_gaps": [],
        "applied_trends": [],
    }
    payload.update(over)
    return json.dumps(payload)


def crew_script(**over: str) -> dict[str, str]:
    """A complete, healthy crew run. Override any single role by schema name.

    A fresh dict each call: these get mutated by tests, and a module-level constant would
    carry one test's forged Editor into the next one.
    """
    script = {
        "style_profile": _profile(),
        "trend_application": json.dumps({"applied": []}),
        "outfit_draft": _draft(),
        "critique": _critique(),
        "practical_advice": _practical(),
        "editor_output": _editor(),
    }
    script.update(over)
    return script


__all__ = [
    "LOOK",
    "crew_script",
]
