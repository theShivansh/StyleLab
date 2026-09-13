"""SQLAlchemy schema. Mirrors docs/DATA-MODEL.md.

## The composite keys

`wardrobe_items` and `outfits` each carry a unique constraint on `(id, user_id)` — redundant
on its own, since `id` is already unique. It exists so that `outfit_items` can hold its own
`user_id` and point at both parents with a **composite foreign key**. The effect is that a
row joining one user's outfit to another user's garment cannot be written at all: the
database refuses it.

docs/DATA-MODEL.md asks for exactly that — cross-user leakage "unrepresentable rather than
merely untested". A repository bug then surfaces as a failed insert instead of a leak, and
the ownership invariant survives a mistake in the layer above it.

## What is absent, and must stay absent

`brand`, `price`, `commerce_url`, `active`. The product sells nothing, so nothing in these
tables can misstate a commerce fact. `tests/test_persistence.py` fails if one is added.

Phase note: schema migrations arrive with deployment in S11. `Base.metadata.create_all` is
enough for the test suite and local work; it is not a migration strategy.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssetRow(Base):
    """Private image storage record. One row per uploaded file.

    Never holds image bytes and never a public URL: access is signed and time-limited
    (docs/SECURITY-PRIVACY.md).
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_assets_id_user"),
        Index("ix_assets_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Analyse each image once, cache by checksum (docs/AI-SYSTEM.md cost controls).
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    #: Soft deletion: the privacy flow needs deletion observable, not silent.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the **bytes** were unlinked from the object store, which is a different event
    #: from when the user asked. `deleted_at` starts the retention window and stops the file
    #: being served; this is set when the window expires and the file is actually gone
    #: (`app/services/retention.py`).
    #:
    #: A column rather than an inference, because the two states have to be distinguishable
    #: for the sweep to be idempotent and for anyone to be able to answer "is that
    #: photograph still on a disk somewhere" with a query rather than a guess. Nullable, so
    #: it is also the flag: null means the retention window is still running.
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WardrobeItemRow(Base):
    """A garment the user owns. Not a product for sale."""

    __tablename__ = "wardrobe_items"
    __table_args__ = (
        # The composite target that makes outfit_items' cross-user join unrepresentable.
        UniqueConstraint("id", "user_id", name="uq_wardrobe_items_id_user"),
        Index("ix_wardrobe_items_user_status", "user_id", "status"),
        Index("ix_wardrobe_items_user_category", "user_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: The ownership root. NOT NULL, and every retrieval filters on it in SQL.
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16))

    category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color_primary: Mapped[str | None] = mapped_column(String(32), nullable=True)
    color_secondary: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: A guess, named as one. Never rendered as fact (docs/AI-EVAL-CASES.md Case 08).
    material_guess: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    formality: Mapped[str | None] = mapped_column(String(16), nullable=True)

    season_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    occasion_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    style_tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    #: Per-field map. Drives which fields the UI hedges and offers for correction.
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    #: Fields the user overrode. Re-analysis must never overwrite these.
    corrected_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    quality_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    #: Model id that produced the current reading. Nullable before the first analysis.
    analyzed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ItemExtractionRow(Base):
    """Append-only audit of what a model claimed, including rejected attempts.

    The evidence trail behind every wardrobe field. It is what makes the grounding story
    demonstrable rather than assertable, so rows are never updated and never pruned here.

    No `user_id` column of its own, per docs/DATA-MODEL.md — reads join through
    `wardrobe_items`, which is where ownership lives.
    """

    __tablename__ = "item_extractions"
    __table_args__ = (Index("ix_item_extractions_item", "wardrobe_item_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wardrobe_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("wardrobe_items.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    #: As returned, before validation. A normalised copy is not evidence.
    raw_output: Mapped[object] = mapped_column(JSON)
    schema_valid: Mapped[bool] = mapped_column(Boolean)
    #: Null when accepted.
    rejected_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OutfitRow(Base):
    __tablename__ = "outfits"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_outfits_id_user"),
        Index("ix_outfits_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128))
    occasion: Mapped[str] = mapped_column(String(32))
    match_score: Mapped[int] = mapped_column(Integer, default=0)
    rationale: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: `incomplete` when a referenced item was deleted (Case 14) — never a silent gap.
    status: Mapped[str] = mapped_column(String(16), default="ready")
    #: Which rung of the ladder produced it. Disclosed, not hidden.
    degradation_level: Mapped[int] = mapped_column(Integer, default=1)

    #: Advisory content as produced — pro tips, budget tricks, gaps, trend notes, the
    #: advisor's own confidence. One JSON column rather than four, because none of it is
    #: ever queried: it is read whole, with the look it belongs to. What *is* queried has
    #: its own column.
    advisory: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

    #: What the user asked for when this look was composed. Stored because a swap rescores
    #: the look, and `preference_match` is one of the six dimensions — recomputing without
    #: them would silently neutralise a fifth of the score the moment a slot changed, and
    #: the number on screen would move for a reason the user could not see.
    vibe: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fit_preference: Mapped[str | None] = mapped_column(String(32), nullable=True)
    color_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OutfitItemRow(Base):
    """The join that could leak, and the constraint that stops it.

    Carries `user_id` so both foreign keys can be composite. The database then cannot hold a
    row whose outfit and garment belong to different users.
    """

    __tablename__ = "outfit_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfits.id", "outfits.user_id"],
            name="fk_outfit_items_outfit_same_user",
        ),
        ForeignKeyConstraint(
            ["wardrobe_item_id", "user_id"],
            ["wardrobe_items.id", "wardrobe_items.user_id"],
            name="fk_outfit_items_item_same_user",
        ),
        Index("ix_outfit_items_outfit", "outfit_id", "rank"),
    )

    outfit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    wardrobe_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Shared by both composite keys — this column is the whole mechanism.
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16))
    rank: Mapped[int] = mapped_column(Integer, default=0)


class SavedOutfitRow(Base):
    """A look the user chose to keep.

    Separate from `outfits` rather than a `saved` flag on it, per docs/DATA-MODEL.md. Every
    composition writes an `outfits` row — it has to, because a swap needs something to swap
    against — so a flag would mean the table held mostly unsaved rows and "saved" would be
    the exception the schema was not shaped for. A join table also makes saving idempotent
    in the schema rather than in a handler: the unique constraint is what makes the second
    press of the button a no-op.
    """

    __tablename__ = "saved_outfits"
    __table_args__ = (
        # Idempotency, enforced where it cannot be forgotten.
        UniqueConstraint("user_id", "outfit_id", name="uq_saved_outfits_user_outfit"),
        # Composite again: a save may only point at the saver's own outfit.
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfits.id", "outfits.user_id"],
            name="fk_saved_outfits_outfit_same_user",
        ),
        Index("ix_saved_outfits_user", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outfit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StyleProfileRow(Base):
    __tablename__ = "style_profiles"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_style_profiles_id_user"),
        Index("ix_style_profiles_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vibe: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fit_preference: Mapped[str | None] = mapped_column(String(32), nullable=True)
    color_preferences: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


__all__ = [
    "AssetRow",
    "Base",
    "ItemExtractionRow",
    "OutfitItemRow",
    "OutfitRow",
    "SavedOutfitRow",
    "StyleProfileRow",
    "UserRow",
    "WardrobeItemRow",
]
