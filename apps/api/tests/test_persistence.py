"""Schema-level guarantees.

docs/DATA-MODEL.md asks for cross-user leakage to be *unrepresentable* rather than merely
untested: composite foreign keys on `(id, user_id)` mean a row joining one user's outfit to
another user's garment cannot be written at all. A repository bug is then a failed insert,
not a leak.

`item_extractions` is the append-only evidence trail behind every wardrobe field, including
the attempts that were rejected. Those are the rows that make extraction auditable.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.models import GarmentCategory as C
from app.repositories.wardrobe import ExtractionAuditRepository, WardrobeRepository

U1, U2 = "u1", "u2"


@pytest.fixture
def repo(session, stubs):
    r = WardrobeRepository(session)
    r.add_user(U1, "one@example.test")
    r.add_user(U2, "two@example.test")
    r.add_item(stubs.garment("u1-top", U1, category=C.TOP))
    r.add_item(stubs.garment("u1-bottom", U1, category=C.BOTTOM))
    r.add_item(stubs.garment("u2-top", U2, category=C.TOP))
    session.commit()
    return r


def test_foreign_keys_are_enforced(engine, session):
    """SQLite ignores foreign keys unless asked. If this regresses, every constraint below
    becomes decoration."""
    from sqlalchemy import text

    assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_an_outfit_cannot_reference_another_users_garment(repo, session):
    """The constraint that makes the invariant structural.

    Written directly against the table, bypassing the repository entirely — the point is
    that the database refuses it, so going through a method that already checks ownership
    would prove nothing. This is what protects the invariant when the layer above has a bug.
    """
    from app.db.models import OutfitItemRow

    repo.save_outfit(U1, outfit_id="o1", name="Mine", occasion="everyday", item_ids=["u1-top"])
    session.commit()

    session.add(
        OutfitItemRow(
            outfit_id="o1", wardrobe_item_id="u2-top", user_id=U1, role=C.TOP.value, rank=1
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_an_outfit_can_reference_its_own_users_garments(repo, session):
    repo.save_outfit(
        U1, outfit_id="o1", name="Mine", occasion="everyday", item_ids=["u1-top", "u1-bottom"]
    )
    session.commit()

    stored = repo.get_outfit(U1, "o1")
    assert stored is not None
    assert stored.item_ids == ["u1-top", "u1-bottom"]


def test_another_user_cannot_read_that_outfit(repo, session):
    repo.save_outfit(U1, outfit_id="o1", name="Mine", occasion="everyday", item_ids=["u1-top"])
    session.commit()

    assert repo.get_outfit(U2, "o1") is None


def test_saving_an_outfit_with_an_unowned_item_is_refused_before_the_database(repo, session):
    """Belt and braces: the repository refuses, and the schema would refuse anyway. Two
    independent defences, because this is the one rule the product rests on."""
    with pytest.raises(ValueError, match="not owned"):
        repo.save_outfit(U1, outfit_id="o2", name="x", occasion="everyday", item_ids=["u2-top"])


# --- the extraction audit trail ----------------------------------------------------------


def test_an_accepted_extraction_is_recorded(repo, session):
    audit = ExtractionAuditRepository(session)
    audit.record(
        U1,
        "u1-top",
        provider="stub",
        model="test-model",
        raw_output={"category": "top"},
        schema_valid=True,
        latency_ms=412,
    )
    session.commit()

    rows = audit.for_item(U1, "u1-top")
    assert len(rows) == 1
    assert rows[0].schema_valid is True
    assert rows[0].rejected_reason is None


def test_a_rejected_extraction_is_recorded_too(repo, session):
    """prompts/04: "including rejected attempts". An audit trail that only keeps the
    successes cannot show that anything was ever caught."""
    audit = ExtractionAuditRepository(session)
    audit.record(
        U1,
        "u1-top",
        provider="stub",
        model="test-model",
        raw_output="{truncated",
        schema_valid=False,
        rejected_reason="schema_invalid",
        latency_ms=88,
    )
    session.commit()

    rows = audit.for_item(U1, "u1-top")
    assert len(rows) == 1
    assert rows[0].schema_valid is False
    assert rows[0].rejected_reason == "schema_invalid"


def test_the_audit_trail_is_append_only(repo, session):
    """Two attempts on one item keep both rows, newest last. Overwriting would destroy the
    evidence that a correction was ever needed."""
    audit = ExtractionAuditRepository(session)
    for index, valid in enumerate([False, True]):
        audit.record(
            U1,
            "u1-top",
            provider="stub",
            model="test-model",
            raw_output={"attempt": index},
            schema_valid=valid,
            rejected_reason=None if valid else "schema_invalid",
            latency_ms=100 + index,
        )
    session.commit()

    rows = audit.for_item(U1, "u1-top")
    assert [r.schema_valid for r in rows] == [False, True]


def test_the_audit_trail_is_scoped_to_the_owner(repo, session):
    """`item_extractions` carries no user_id of its own, so the read joins through the item.
    Without that join it would be an unscoped read path by accident."""
    audit = ExtractionAuditRepository(session)
    audit.record(
        U2,
        "u2-top",
        provider="stub",
        model="test-model",
        raw_output={"category": "top"},
        schema_valid=True,
        latency_ms=120,
    )
    session.commit()

    assert audit.for_item(U1, "u2-top") == []
    assert len(audit.for_item(U2, "u2-top")) == 1


def test_recording_against_another_users_item_is_refused(repo, session):
    audit = ExtractionAuditRepository(session)
    with pytest.raises(ValueError, match="not owned"):
        audit.record(
            U1,
            "u2-top",
            provider="stub",
            model="test-model",
            raw_output={},
            schema_valid=True,
            latency_ms=1,
        )


def test_raw_output_is_stored_verbatim_for_replay(repo, session):
    """"as returned, before validation" (docs/DATA-MODEL.md). A normalised copy is not
    evidence of what the provider actually said."""
    audit = ExtractionAuditRepository(session)
    raw = {"category": "top", "unexpected_field": [1, 2, 3], "field_confidence": {"category": 0.9}}
    audit.record(
        U1,
        "u1-top",
        provider="stub",
        model="test-model",
        raw_output=raw,
        schema_valid=False,
        rejected_reason="schema_invalid",
        latency_ms=7,
    )
    session.commit()

    assert audit.for_item(U1, "u1-top")[0].raw_output == raw


# --- storage round trip ------------------------------------------------------------------


def test_an_item_round_trips_through_the_database_unchanged(session, stubs):
    repo = WardrobeRepository(session)
    repo.add_user(U1, "one@example.test")
    original = stubs.garment(
        "rt",
        U1,
        category=C.OUTERWEAR,
        subcategory="chore jacket",
        color_primary="olive",
        color_secondary="ecru",
        pattern="solid",
        material_guess="cotton twill",
        fit="relaxed",
        style_tags=["workwear", "minimal"],
        season_tags=["autumn"],
        occasion_tags=["everyday"],
        field_confidence={"category": 0.95, "material_guess": 0.38},
        quality_warnings=["busy_background"],
    )
    repo.add_item(original)
    session.commit()
    session.expire_all()

    assert repo.get(U1, "rt") == original


def test_a_stored_item_keeps_no_commerce_field(session, stubs):
    """The product sells nothing, so the table cannot misstate a commerce fact."""
    from app.db.models import WardrobeItemRow

    columns = set(WardrobeItemRow.__table__.columns.keys())
    for banned in {"brand", "price", "commerce_url", "active", "merchant"}:
        assert banned not in columns
