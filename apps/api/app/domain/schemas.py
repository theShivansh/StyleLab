"""Structured-output contracts for extraction and for ranking.

Two things live here, and the relationship between them is the point:

* `EXTRACTION_JSON_SCHEMA` / `ADVICE_JSON_SCHEMA` — what gets handed to Groq's Structured
  Outputs, with `additionalProperties: false` on every object and explicit enums.
* `parse_extraction` / `parse_advice` — what validates the response that comes back.

Both schemas are **derived from the Pydantic models** rather than written beside them. Two
hand-maintained copies of one contract drift, the drift is silent, and the symptom is a
field the provider is allowed to omit that the domain requires. Deriving them means a new
model field appears in the schema automatically, and `tests/test_output_schema.py` asserts
the two stay in step.

Parsing lives in the domain rather than in the Groq adapter so that it is testable with no
provider and no key, and so that S8b's agent crew validates against exactly the same
contract as the vision path. Schema validity is not business validity and neither is
authorisation (CLAUDE.md) — `app.domain.validation` runs after this, always.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.corrections import CORRECTABLE_FIELDS
from app.domain.errors import SchemaInvalidError
from app.domain.models import GarmentExtraction, OutfitAdvice


def _close_objects(node: Any) -> Any:
    """Set `additionalProperties: false` on every object, at every depth.

    Pydantic emits it only where it is implied. A nested object left open is precisely where
    an unexpected field actually arrives, so every one is closed explicitly.
    """
    if isinstance(node, dict):
        closed = {key: _close_objects(value) for key, value in node.items()}
        if closed.get("type") == "object" or "properties" in closed:
            closed.setdefault("type", "object")
            closed["additionalProperties"] = False
        return closed
    if isinstance(node, list):
        return [_close_objects(item) for item in node]
    return node


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref`/`$defs` into one self-contained document.

    Groq's Structured Outputs accepts references, but a flat schema is far easier to read
    in a prompt log and removes a class of provider-side incompatibility we would only find
    in production.
    """
    definitions: dict[str, Any] = schema.pop("$defs", {})

    def resolve(node: Any, seen: frozenset[str] = frozenset()) -> Any:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/$defs/"):
                name = reference.split("/")[-1]
                if name in seen:
                    # Self-referential model; leave the ref rather than recursing forever.
                    return {"type": "object", "additionalProperties": False}
                target = dict(definitions.get(name, {}))
                overrides = {k: v for k, v in node.items() if k != "$ref"}
                return {**resolve(target, seen | {name}), **overrides}
            return {key: resolve(value, seen) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        return node

    return resolve(schema)


def _require_all_properties(node: Any) -> Any:
    """List every property of every object in its `required` array.

    Strict Structured Outputs demands it: a provider that guarantees adherence has to know
    the full key set up front, so "optional" is not a thing a strict schema can express.
    Optionality is carried by the *type* instead — Pydantic already emits
    `anyOf: [{...}, {"type": "null"}]` for every `X | None` field, so a required-and-nullable
    field is exactly the field that was optional.

    Derived rather than declared, for the same reason the schemas are: a new model field
    would otherwise be absent from `required` and silently become a field the provider is
    allowed to omit.

    This was missing until S6 and could not have been caught by a mock — `MockGroqProvider`
    returns scripted content and never validates the schema it was handed. The live suite
    found it on its first real run, with a 400 naming all thirteen properties.
    """
    if isinstance(node, dict):
        rebuilt = {key: _require_all_properties(value) for key, value in node.items()}
        properties = rebuilt.get("properties")
        if isinstance(properties, dict):
            rebuilt["required"] = list(properties)
        return rebuilt
    if isinstance(node, list):
        return [_require_all_properties(item) for item in node]
    return node


#: The fields a per-field confidence score may describe.
#:
#: Deliberately the same set the user can correct (`app.domain.corrections`). The score's
#: only job is to decide what the UI hedges and offers for confirmation, so a score for
#: something the user cannot then fix would be a hedge with no way out of it. One list, one
#: meaning: *we can tell you we are unsure about exactly the things you can settle.*
CONFIDENCE_FIELDS: tuple[str, ...] = tuple(sorted(CORRECTABLE_FIELDS))


def _confidence_schema() -> dict[str, Any]:
    """A fixed-key object for `field_confidence`, because an open map is inexpressible here.

    `dict[str, float]` is the right domain type and an impossible strict schema: strict mode
    requires `additionalProperties: false` on every object, which for a free-form map means
    an object permitted to hold nothing at all. That is what S5 generated, and the effect
    was worse than a validation error — the provider was being told, in a schema it obeys,
    that per-field confidence must be **empty**. The honesty signal the whole extraction
    path rests on was specified as unreachable, and every mock-backed test passed because a
    fixture supplied the scores the model was forbidden to send.

    Enumerating the keys fixes it and reads better in a prompt log. Scores are nullable
    because a model that did not assess a field should say so rather than invent a number;
    `_strip_absent_confidence` drops the nulls before validation.
    """
    return {
        "type": "object",
        "description": (
            "Confidence in each field, 0-1. Null for a field you did not assess. "
            "A low score is useful and expected; do not inflate one."
        ),
        "properties": {
            field: {
                "anyOf": [{"type": "number", "minimum": 0, "maximum": 1}, {"type": "null"}]
            }
            for field in CONFIDENCE_FIELDS
        },
        "required": list(CONFIDENCE_FIELDS),
        "additionalProperties": False,
    }


def _schema_for(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(mode="serialization")
    return _require_all_properties(_close_objects(_inline_refs(schema)))


EXTRACTION_JSON_SCHEMA: dict[str, Any] = _schema_for(GarmentExtraction)
EXTRACTION_JSON_SCHEMA["properties"]["field_confidence"] = _confidence_schema()

ADVICE_JSON_SCHEMA: dict[str, Any] = _schema_for(OutfitAdvice)


def _strip_absent_confidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop unassessed confidence scores before validation.

    The wire schema asks for every key so that strict mode can hold; `null` there means "not
    assessed", which the domain represents by the key's absence from `dict[str, float]`.
    Translating at the boundary keeps `GarmentExtraction` free of the provider's requirement
    that nothing be optional.
    """
    scores = payload.get("field_confidence")
    if not isinstance(scores, dict):
        return payload
    return {
        **payload,
        "field_confidence": {
            field: score for field, score in scores.items() if score is not None
        },
    }


def _as_mapping(raw: object, *, what: str) -> dict[str, Any]:
    """Coerce a provider response into a mapping, or fail with a loggable reason.

    Accepts a mapping directly, or text. Text is what providers actually return, and a
    fenced ```json block is common enough that refusing it would mean discarding good
    extractions — recovering a complete payload from a fence is not the same as tolerating
    malformed output, and the tests draw that line explicitly.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise SchemaInvalidError(
            f"{what}: expected an object or JSON text, got {type(raw).__name__}"
        )

    text = raw.strip()
    if not text:
        raise SchemaInvalidError(f"{what}: empty response")

    if text.startswith("```"):
        # Strip the fence and any language tag; keep everything up to a closing fence.
        body = text.split("\n", 1)[1] if "\n" in text else ""
        text = body.split("```", 1)[0].strip()
        if not text:
            raise SchemaInvalidError(f"{what}: fenced block contained no payload")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        # The message names the position, never the payload: a truncated response can carry
        # anything, including text lifted out of a user's photo.
        raise SchemaInvalidError(
            f"{what}: response is not valid JSON (line {error.lineno}, column {error.colno})"
        ) from error

    if not isinstance(parsed, dict):
        raise SchemaInvalidError(f"{what}: expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _describe(error: ValidationError, *, what: str) -> str:
    """A reason that is useful in a log and safe in one.

    Names the offending field and the rule it broke; never echoes the value. Provider output
    is untrusted content — text recovered from a photograph reaches us through this path,
    and docs/SECURITY-PRIVACY.md forbids surfacing a raw provider message.
    """
    parts: list[str] = []
    for detail in error.errors():
        location = ".".join(str(piece) for piece in detail["loc"]) or "(root)"
        parts.append(f"{location}: {detail['type']}")
    return f"{what}: " + "; ".join(parts)


def parse_extraction(raw: object) -> GarmentExtraction:
    """Validate one vision response. Raises `SchemaInvalidError`, never returns a partial."""
    payload = _strip_absent_confidence(_as_mapping(raw, what="extraction"))
    try:
        return GarmentExtraction.model_validate(payload)
    except ValidationError as error:
        raise SchemaInvalidError(_describe(error, what="extraction")) from error


def parse_advice(raw: object) -> OutfitAdvice:
    """Validate one advisory response.

    Passing this means the shape is right. It says nothing about whether the user owns the
    items named — that is `app.domain.validation`, and it is not optional.
    """
    payload = _as_mapping(raw, what="advice")
    try:
        return OutfitAdvice.model_validate(payload)
    except ValidationError as error:
        raise SchemaInvalidError(_describe(error, what="advice")) from error


__all__ = [
    "ADVICE_JSON_SCHEMA",
    "CONFIDENCE_FIELDS",
    "EXTRACTION_JSON_SCHEMA",
    "parse_advice",
    "parse_extraction",
]
