"""Structured output schemas — AI-EVAL-CASES Case 06.

Schema validity is not business validity, and neither is authorisation (CLAUDE.md). These
three run in order and none substitutes for another; this file tests the first of them.

Parsing lives in the domain rather than in the Groq adapter so that it is testable without a
provider, and so that S8b's agent crew validates against exactly the same contract. The
JSON Schema handed to Structured Outputs is *derived from* the Pydantic models rather than
written alongside them — two hand-maintained copies of one contract drift, and the drift is
silent.
"""

from __future__ import annotations

import json

import pytest

from app.domain.errors import SchemaInvalidError
from app.domain.models import GarmentExtraction, OutfitAdvice
from app.domain.schemas import (
    ADVICE_JSON_SCHEMA,
    EXTRACTION_JSON_SCHEMA,
    parse_advice,
    parse_extraction,
)

VALID_EXTRACTION = {
    "category": "top",
    "subcategory": "oxford shirt",
    "color_primary": "navy",
    "color_secondary": None,
    "pattern": "solid",
    "material_guess": "cotton",
    "fit": "regular",
    "formality": "smart-casual",
    "season_tags": ["spring", "autumn"],
    "occasion_tags": [],
    "style_tags": ["minimal", "preppy"],
    "field_confidence": {"category": 0.97, "color_primary": 0.62, "material_guess": 0.41},
    "quality_warnings": ["low_light"],
}

VALID_ADVICE = {
    "outfit": {
        "item_ids": ["ITEM_A", "ITEM_B", "ITEM_C"],
        "name": "Minimal Street",
        "occasion": "college",
        "match_score": 87,
    },
    "rationale": ["Neutral palette", "Balanced relaxed silhouette"],
    "confidence": 0.87,
}


def test_the_documented_example_parses():
    """docs/AI-SYSTEM.md prints these two payloads. If the docs and the parser disagree, one
    of them is lying to the next person who reads it."""
    assert parse_extraction(VALID_EXTRACTION).category == "top"
    advice = parse_advice(VALID_ADVICE)
    assert advice.outfit is not None
    assert advice.outfit.item_ids == ["ITEM_A", "ITEM_B", "ITEM_C"]


def test_a_json_string_is_accepted_as_well_as_a_mapping():
    """Providers return text. Accepting both keeps the adapter from hand-rolling json.loads
    and swallowing the error."""
    assert parse_extraction(json.dumps(VALID_EXTRACTION)).color_primary == "navy"


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        ('{"category": "top", "color_primary": "na', "truncated mid-string"),
        ('{"category": "top",', "truncated after a key"),
        ("", "empty response"),
        ("Sure! Here is the JSON you asked for:", "prose instead of JSON"),
        ("```json\n{unclosed", "fenced and truncated"),
    ],
)
def test_malformed_and_truncated_output_is_rejected(payload, label):
    with pytest.raises(SchemaInvalidError) as raised:
        parse_extraction(payload)
    assert raised.value.reason, label


def test_a_fenced_but_complete_payload_is_recovered():
    """Models wrap JSON in a code fence often enough that refusing it would mean discarding
    good extractions. Recovering it is not the same as tolerating malformed output."""
    fenced = "```json\n" + json.dumps(VALID_EXTRACTION) + "\n```"
    assert parse_extraction(fenced).subcategory == "oxford shirt"


def test_an_unknown_field_is_rejected_rather_than_dropped():
    """extra='forbid'. A provider inventing `price` must fail loudly — silently discarding
    it is how a commerce field ends up half-implemented."""
    with pytest.raises(SchemaInvalidError):
        parse_extraction({**VALID_EXTRACTION, "price": 4999})


def test_a_bad_enum_value_is_rejected():
    with pytest.raises(SchemaInvalidError):
        parse_extraction({**VALID_EXTRACTION, "category": "trousers-ish"})


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(SchemaInvalidError):
        parse_advice({**VALID_ADVICE, "confidence": 1.4})


def test_a_missing_required_field_inside_the_outfit_is_rejected():
    outfit = {k: v for k, v in VALID_ADVICE["outfit"].items() if k != "item_ids"}
    with pytest.raises(SchemaInvalidError):
        parse_advice({**VALID_ADVICE, "outfit": outfit})


def test_advice_with_no_outfit_and_a_named_gap_is_valid():
    """Not an error. Naming the gap is a complete answer (USER-FLOWS Flow 5)."""
    advice = parse_advice(
        {
            "outfit": None,
            "missing_roles": ["footwear"],
            "wardrobe_gaps": [
                {
                    "category": "footwear",
                    "generic_description": "a white leather sneaker",
                    "unlocks_outfits": 5,
                }
            ],
            "degradation_level": 5,
        }
    )
    assert advice.outfit is None
    assert advice.confidence is None


def test_an_unattributed_trend_note_fails_the_schema():
    """Case 15, enforced at the type level so no downstream code has to remember."""
    with pytest.raises(SchemaInvalidError):
        parse_advice(
            {**VALID_ADVICE, "trend_notes": [{"trend": "Wide legs are back"}]},
        )


def test_the_reason_names_the_field_without_echoing_the_payload():
    """docs/SECURITY-PRIVACY.md: never surface a raw provider message. The reason has to be
    useful in a log and safe in one."""
    with pytest.raises(SchemaInvalidError) as raised:
        parse_extraction({**VALID_EXTRACTION, "category": "not-a-category"})

    reason = raised.value.reason
    assert "category" in reason
    assert "not-a-category" not in reason


# --- the schema handed to the provider ---------------------------------------------------


@pytest.mark.parametrize("schema", [EXTRACTION_JSON_SCHEMA, ADVICE_JSON_SCHEMA])
def test_every_object_in_the_schema_forbids_extra_properties(schema):
    """CLAUDE.md requires additionalProperties: false throughout, not just at the root —
    a nested object left open is where an unexpected field actually arrives."""
    def walk(node, path="$"):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, f"{path} is open"
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(schema)


def test_the_extraction_schema_covers_every_domain_field():
    """Guards the derivation. If a field is added to the model and the schema is generated
    from something else, this fails."""
    properties = set(EXTRACTION_JSON_SCHEMA["properties"])
    assert set(GarmentExtraction.model_fields) == properties


def test_the_advice_schema_covers_every_domain_field():
    properties = set(ADVICE_JSON_SCHEMA["properties"])
    assert set(OutfitAdvice.model_fields) == properties


def test_the_schema_names_the_category_enum_explicitly():
    """Explicit enums, per CLAUDE.md — a free-text category is a category we cannot rank."""
    rendered = json.dumps(EXTRACTION_JSON_SCHEMA)
    for category in ("top", "bottom", "footwear", "outerwear", "accessory"):
        assert f'"{category}"' in rendered
