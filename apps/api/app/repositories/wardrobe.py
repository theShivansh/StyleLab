"""Ownership-scoped persistence.

prompts/04: "every query filters on `user_id`; there is no unscoped read path, not even for
admin or debug". That is a rule about every future method as much as the ones written here,
so it is enforced by construction rather than by discipline:

* **`_scoped_select` is the only place a `select()` is built.** Every read in this module
  goes through it, including the reads that back a write. Adding a method that forgets the
  filter is not a subtle bug to be caught in review — there is nowhere to put it.
* **`_scoped_extractions` is the one exception, and it is the same rule.**
  `item_extractions` carries no `user_id` of its own (docs/DATA-MODEL.md), so it joins
  through `wardrobe_items` and filters there.
* **No `Session.get()` on an owned row.** Primary-key loads bypass the filter entirely;
  that is the obvious way around a scoped select, so `tests/test_query_scoping.py` forbids
  it explicitly.

The repository returns frozen domain objects, never live ORM rows. A caller that cannot
reach a row cannot mutate one by accident, and the domain stays free of SQLAlchemy.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import (
    AssetRow,
    ItemExtractionRow,
    OutfitItemRow,
    OutfitRow,
    SavedOutfitRow,
    UserRow,
    WardrobeItemRow,
)
from app.domain.compatibility import ROLE_ORDER
from app.domain.corrections import apply_correction, merge_extraction
from app.domain.models import (
    Formality,
    GarmentCategory,
    GarmentExtraction,
    ItemStatus,
    WardrobeItem,
)

_Owned = TypeVar(
    "_Owned", AssetRow, WardrobeItemRow, OutfitRow, OutfitItemRow, SavedOutfitRow
)


def _scoped_select(user_id: str, row: type[_Owned]) -> Select[tuple[_Owned]]:
    """The only select in this module. Filters on `user_id`, always.

    Generic over the row type so there is one builder rather than one per table — a second
    builder is a second place to forget the filter.
    """
    return select(row).where(row.user_id == user_id)


def _scoped_extractions(user_id: str, wardrobe_item_id: str) -> Select[tuple[ItemExtractionRow]]:
    """Audit rows for one item, scoped by joining through the item that owns them."""
    return (
        select(ItemExtractionRow)
        .join(WardrobeItemRow, WardrobeItemRow.id == ItemExtractionRow.wardrobe_item_id)
        .where(
            WardrobeItemRow.user_id == user_id,
            ItemExtractionRow.wardrobe_item_id == wardrobe_item_id,
        )
        .order_by(ItemExtractionRow.id)
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _to_domain(row: WardrobeItemRow) -> WardrobeItem:
    """Row to frozen domain object. The domain speaks garments, not tables."""
    return WardrobeItem(
        item_id=row.id,
        user_id=row.user_id,
        status=ItemStatus(row.status),
        corrected_fields=list(row.corrected_fields or []),
        extraction=GarmentExtraction(
            category=GarmentCategory(row.category) if row.category else None,
            subcategory=row.subcategory,
            color_primary=row.color_primary,
            color_secondary=row.color_secondary,
            pattern=row.pattern,
            material_guess=row.material_guess,
            fit=row.fit,
            formality=Formality(row.formality) if row.formality else None,
            season_tags=list(row.season_tags or []),
            occasion_tags=list(row.occasion_tags or []),
            style_tags=list(row.style_tags or []),
            field_confidence=dict(row.field_confidence or {}),
            quality_warnings=list(row.quality_warnings or []),
        ),
    )


def _to_stored(row: WardrobeItemRow) -> StoredItem:
    return StoredItem(
        item=_to_domain(row),
        asset_id=row.asset_id,
        analyzed_by=row.analyzed_by,
        analyzed_at=row.analyzed_at,
    )


def _write_extraction(row: WardrobeItemRow, item: WardrobeItem) -> None:
    """Copy a domain item's extraction onto its row."""
    extraction = item.extraction
    row.status = item.status.value
    row.corrected_fields = list(item.corrected_fields)
    row.category = extraction.category.value if extraction.category else None
    row.subcategory = extraction.subcategory
    row.color_primary = extraction.color_primary
    row.color_secondary = extraction.color_secondary
    row.pattern = extraction.pattern
    row.material_guess = extraction.material_guess
    row.fit = extraction.fit
    row.formality = extraction.formality.value if extraction.formality else None
    row.season_tags = list(extraction.season_tags)
    row.occasion_tags = list(extraction.occasion_tags)
    row.style_tags = list(extraction.style_tags)
    row.field_confidence = dict(extraction.field_confidence)
    row.quality_warnings = list(extraction.quality_warnings)


@dataclass(frozen=True, slots=True)
class OutfitSlot:
    """One role in a composed look, and whatever is currently filling it.

    `item` is `None` when the garment was deleted after the look was composed. The slot
    survives the deletion on purpose: the result screen has to say *which* piece went
    missing and offer a swap for that role, which it cannot do from a shorter list
    (docs/AI-EVAL-CASES.md Case 14).
    """

    role: str
    item_id: str
    item: StoredItem | None

    @property
    def filled(self) -> bool:
        return self.item is not None


@dataclass(frozen=True, slots=True)
class StoredOutfit:
    outfit_id: str
    user_id: str
    name: str
    occasion: str
    match_score: int
    rationale: list[str]
    status: str
    degradation_level: int
    item_ids: list[str]
    #: Pro tips, budget tricks, gaps, trend notes — read whole, never queried.
    advisory: dict[str, Any] = field(default_factory=dict)
    #: The preferences this look was composed against, kept so a swap can rescore it the
    #: same way it was scored the first time.
    vibe: str | None = None
    fit_preference: str | None = None
    color_preferences: list[str] = field(default_factory=list)
    slots: list[OutfitSlot] = field(default_factory=list)
    saved: bool = False

    @property
    def missing_roles(self) -> list[str]:
        """Roles whose garment is gone. Empty for a look that is still whole."""
        return [slot.role for slot in self.slots if not slot.filled]


@dataclass(frozen=True, slots=True)
class StoredItem:
    """A wardrobe item plus the row facts the domain has no use for.

    `WardrobeItem` is the domain object and stays free of storage and provider concepts, so
    the asset id and the model that produced the current reading travel beside it rather
    than inside it. The API needs both — one to mint an image URL, one for the audit panel.
    """

    item: WardrobeItem
    asset_id: str | None
    analyzed_by: str | None
    analyzed_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredAsset:
    asset_id: str
    user_id: str
    storage_key: str
    mime_type: str
    byte_size: int
    width: int | None
    height: int | None
    checksum: str | None


@dataclass(frozen=True, slots=True)
class DeletionResult:
    """What a delete actually did, so the UI can say what else changed.

    `affected_outfits` is the point. Deleting a garment silently leaving a hole in a saved
    outfit is docs/AI-EVAL-CASES.md Case 14 failing: the outfit must report itself
    incomplete rather than render a gap.
    """

    deleted: bool
    affected_outfits: list[str]


@dataclass(frozen=True, slots=True)
class PurgeableAsset:
    """An expired asset, reduced to the two things the sweep needs.

    Not a `StoredAsset`. The sweep has no business holding a mime type, a checksum or an
    owner — it unlinks a file and records that it did. Handing it the full row would mean
    the one unscoped read in the repository returned everything about everyone.
    """

    asset_id: str
    storage_key: str


@dataclass(frozen=True, slots=True)
class WardrobeDeletion:
    """What clearing a whole wardrobe did.

    Counts rather than ids: the caller is a user deleting everything, and a list of the
    hundred ids they just destroyed is not an answer to anything they asked.
    """

    items: int
    assets: int
    outfits: int


@dataclass(frozen=True, slots=True)
class StoredExtraction:
    provider: str
    model: str
    raw_output: object
    schema_valid: bool
    rejected_reason: str | None
    latency_ms: int


class WardrobeRepository:
    """Reads and writes a single user's wardrobe. Every method names the owner."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- users -------------------------------------------------------------------------

    def add_user(self, user_id: str, email: str) -> None:
        """Present so tests and the upload path can establish an owner. Real account
        creation is an auth concern and lands with deployment."""
        self._session.add(UserRow(id=user_id, email=email))
        self._session.flush()

    # --- items -------------------------------------------------------------------------

    def add_item(self, item: WardrobeItem, *, asset_id: str | None = None) -> None:
        """Insert a garment. The owner comes from the item, which carries it by type."""
        row = WardrobeItemRow(id=item.item_id, user_id=item.user_id, asset_id=asset_id)
        _write_extraction(row, item)
        self._session.add(row)
        self._session.flush()

    def get(self, user_id: str, item_id: str) -> WardrobeItem | None:
        row = self._row(user_id, item_id)
        return _to_domain(row) if row else None

    def candidates(
        self,
        user_id: str,
        *,
        roles: Sequence[GarmentCategory] | None = None,
        statuses: Sequence[ItemStatus] = (ItemStatus.READY,),
        limit: int | None = None,
    ) -> list[WardrobeItem]:
        """The candidate set handed to the advisor.

        Scoped, status-filtered and soft-delete-aware in SQL, before any prompt exists. This
        is step 2 of docs/ARCHITECTURE.md section 6 and half of the grounding guarantee;
        prompt wording is never what keeps another user's garment out of this list.

        Ordered by id so the same wardrobe produces the same candidate set every time.
        """
        statement = _scoped_select(user_id, WardrobeItemRow).where(
            WardrobeItemRow.deleted_at.is_(None),
            WardrobeItemRow.status.in_([s.value for s in statuses]),
        )
        if roles is not None:
            statement = statement.where(
                WardrobeItemRow.category.in_([r.value for r in roles])
            )
        statement = statement.order_by(WardrobeItemRow.id)
        if limit is not None:
            statement = statement.limit(limit)

        return [_to_domain(row) for row in self._session.execute(statement).scalars()]

    def count_by_role(self, user_id: str) -> dict[GarmentCategory, int]:
        """Ready items per role, for gap messaging. Roles with none are reported as 0 rather
        than omitted — the absence is the interesting part."""
        counts = dict.fromkeys(ROLE_ORDER, 0)
        for item in self.candidates(user_id):
            role = item.extraction.category
            if role is not None:
                counts[role] = counts.get(role, 0) + 1
        return counts

    def save_correction(self, user_id: str, item_id: str, field: str, value: object) -> bool:
        """Apply a user correction. Returns False when the item is not this user's.

        The domain decides what a correction means — the field is recorded and its
        confidence score dropped (`app.domain.corrections`). This method only persists it.
        """
        row = self._row(user_id, item_id)
        if row is None:
            return False

        corrected = apply_correction(_to_domain(row), field, value)
        _write_extraction(row, corrected)
        self._session.flush()
        return True

    def save_extraction(
        self,
        user_id: str,
        item_id: str,
        extraction: GarmentExtraction,
        *,
        analyzed_by: str | None = None,
    ) -> bool:
        """Store a fresh reading, preserving every field the user corrected (Case 13).

        The merge rule lives in the domain; applying it here is what stops a re-analysis job
        from writing the model's answer straight over the user's.
        """
        row = self._row(user_id, item_id)
        if row is None:
            return False

        merged = merge_extraction(_to_domain(row), extraction)
        _write_extraction(row, merged)
        row.analyzed_by = analyzed_by
        row.analyzed_at = _now()
        self._session.flush()
        return True

    def set_status(self, user_id: str, item_id: str, status: ItemStatus) -> bool:
        row = self._row(user_id, item_id)
        if row is None:
            return False
        row.status = status.value
        self._session.flush()
        return True

    def soft_delete_item(self, user_id: str, item_id: str) -> bool:
        """Mark an item deleted. Returns False when it is not this user's.

        Soft, because docs/DATA-MODEL.md needs deletion observable and reversible by
        support. Scoped, because a delete is a read plus an update and the read is the part
        that leaks.
        """
        row = self._row(user_id, item_id)
        if row is None:
            return False
        row.deleted_at = _now()
        self._session.flush()
        return True

    def delete_with_cascade(self, user_id: str, item_id: str) -> DeletionResult:
        """Soft-delete an item, its asset, and mark the outfits that now have a hole.

        The cascade runs asset-ward and outfit-ward from one call because the three writes
        have to agree. A deleted item whose asset survives leaves the photograph on disk
        after the user asked for it gone; a deleted item inside a `ready` outfit leaves the
        result screen rendering a garment that no longer exists.

        Outfits are marked `incomplete` rather than deleted. The user composed it, and the
        honest response to one missing piece is to say which piece and offer a swap
        (docs/AI-EVAL-CASES.md Case 14) — not to quietly discard their look.
        """
        row = self._row(user_id, item_id)
        if row is None:
            return DeletionResult(deleted=False, affected_outfits=[])

        now = _now()
        row.deleted_at = now

        if row.asset_id:
            asset = self._session.execute(
                _scoped_select(user_id, AssetRow).where(AssetRow.id == row.asset_id)
            ).scalar_one_or_none()
            if asset is not None:
                asset.deleted_at = now

        affected = sorted(
            {
                join.outfit_id
                for join in self._session.execute(
                    _scoped_select(user_id, OutfitItemRow).where(
                        OutfitItemRow.wardrobe_item_id == item_id
                    )
                ).scalars()
            }
        )
        for outfit_id in affected:
            outfit = self._session.execute(
                _scoped_select(user_id, OutfitRow).where(OutfitRow.id == outfit_id)
            ).scalar_one_or_none()
            if outfit is not None:
                outfit.status = "incomplete"

        self._session.flush()
        return DeletionResult(deleted=True, affected_outfits=affected)

    def delete_all(self, user_id: str) -> WardrobeDeletion:
        """Soft-delete everything this user owns, in one transaction.

        docs/SECURITY-PRIVACY.md: *"A user must be able to remove their entire wardrobe in
        one action."* That sentence has been in the spec since S0 and nothing implemented
        it — the only deletion was per item, so exercising the right meant tapping delete
        once per photograph and hoping none was missed.

        Written as three scoped statements rather than by calling `delete_with_cascade` in
        a loop. The loop would be N+1 queries and, worse, N transactions worth of partial
        state: a failure halfway through a hundred-item wardrobe leaves the user having
        asked to delete everything and looking at a screen with forty garments on it.

        Outfits become `incomplete` rather than being deleted, the same as a single
        deletion. It looks odd for an empty wardrobe and it is the consistent rule, and an
        outfit row is the record that the user composed something — not a garment.
        """
        now = _now()

        items = list(
            self._session.execute(
                _scoped_select(user_id, WardrobeItemRow).where(
                    WardrobeItemRow.deleted_at.is_(None)
                )
            ).scalars()
        )
        for item in items:
            item.deleted_at = now

        assets = list(
            self._session.execute(
                _scoped_select(user_id, AssetRow).where(AssetRow.deleted_at.is_(None))
            ).scalars()
        )
        for asset in assets:
            asset.deleted_at = now

        outfits = list(
            self._session.execute(
                _scoped_select(user_id, OutfitRow).where(OutfitRow.status != "incomplete")
            ).scalars()
        )
        for outfit in outfits:
            outfit.status = "incomplete"

        self._session.flush()
        return WardrobeDeletion(
            items=len(items), assets=len(assets), outfits=len(outfits)
        )

    # --- reads that carry row facts ------------------------------------------------------

    def stored(self, user_id: str, item_id: str) -> StoredItem | None:
        """One item with its asset id. The read behind `GET /wardrobe/items/{id}`."""
        row = self._row(user_id, item_id)
        return _to_stored(row) if row else None

    def items(
        self,
        user_id: str,
        *,
        category: GarmentCategory | None = None,
        statuses: Sequence[ItemStatus] | None = None,
    ) -> list[StoredItem]:
        """The caller's wardrobe, newest first.

        Unlike `candidates`, this includes items still analysing and items that failed —
        the wardrobe screen has to show a card for a photo that could not be read, or the
        user's file appears to have vanished. `candidates` is the narrower set the advisor
        sees and stays restricted to `ready`.
        """
        statement = _scoped_select(user_id, WardrobeItemRow).where(
            WardrobeItemRow.deleted_at.is_(None)
        )
        if category is not None:
            statement = statement.where(WardrobeItemRow.category == category.value)
        if statuses is not None:
            statement = statement.where(
                WardrobeItemRow.status.in_([s.value for s in statuses])
            )
        statement = statement.order_by(WardrobeItemRow.created_at.desc(), WardrobeItemRow.id)
        return [_to_stored(row) for row in self._session.execute(statement).scalars()]

    # --- outfits -----------------------------------------------------------------------

    def save_outfit(
        self,
        user_id: str,
        *,
        outfit_id: str,
        name: str,
        occasion: str,
        item_ids: Sequence[str],
        match_score: int = 0,
        rationale: Sequence[str] = (),
        degradation_level: int = 1,
        advisory: dict[str, Any] | None = None,
        vibe: str | None = None,
        fit_preference: str | None = None,
        color_preferences: Sequence[str] = (),
    ) -> StoredOutfit:
        """Persist a composed outfit.

        Ownership is checked here *and* enforced by the composite foreign keys in
        `app.db.models`. Two independent defences on purpose: this is the one rule the
        product rests on, and a check in application code is only as good as the next
        person's memory.

        The preferences are stored with the look rather than derived later. A swap rescores
        what the user is looking at, and it has to score it against the same question that
        was asked the first time.
        """
        by_id = {item.item_id: item for item in self.candidates(user_id)}
        foreign = [item_id for item_id in item_ids if item_id not in by_id]
        if foreign:
            raise ValueError(f"not owned by {user_id}: {', '.join(sorted(foreign))}")

        self._session.add(
            OutfitRow(
                id=outfit_id,
                user_id=user_id,
                name=name,
                occasion=occasion,
                match_score=match_score,
                rationale=list(rationale),
                degradation_level=degradation_level,
                advisory=dict(advisory or {}),
                vibe=vibe,
                fit_preference=fit_preference,
                color_preferences=list(color_preferences),
            )
        )
        # The parent row goes in first, explicitly. `outfit_items` points at `outfits` with
        # a composite foreign key, so a join row written before its outfit is refused by the
        # database. This used to happen by accident — a second candidates() query autoflushed
        # the outfit on its way past — which is an ordering guarantee nobody could see.
        self._session.flush()

        for rank, item_id in enumerate(item_ids):
            role = by_id[item_id].extraction.category
            self._session.add(
                OutfitItemRow(
                    outfit_id=outfit_id,
                    wardrobe_item_id=item_id,
                    user_id=user_id,
                    role=role.value if role else "",
                    rank=rank,
                )
            )
        self._session.flush()

        stored = self.get_outfit(user_id, outfit_id)
        assert stored is not None  # just written, in this session
        return stored

    def get_outfit(self, user_id: str, outfit_id: str) -> StoredOutfit | None:
        """One look, with each slot resolved to the garment currently filling it.

        A slot whose garment has since been deleted comes back with `item=None` rather than
        being dropped. The result screen needs the role to offer a swap for it, and a look
        that quietly got shorter is the silent gap Case 14 forbids.
        """
        row = self._session.execute(
            _scoped_select(user_id, OutfitRow).where(OutfitRow.id == outfit_id)
        ).scalar_one_or_none()
        if row is None:
            return None

        joins = list(
            self._session.execute(
                _scoped_select(user_id, OutfitItemRow)
                .where(OutfitItemRow.outfit_id == outfit_id)
                .order_by(OutfitItemRow.rank)
            ).scalars()
        )
        item_ids = [join.wardrobe_item_id for join in joins]

        live = {}
        if item_ids:
            rows = self._session.execute(
                _scoped_select(user_id, WardrobeItemRow).where(
                    WardrobeItemRow.id.in_(item_ids),
                    WardrobeItemRow.deleted_at.is_(None),
                )
            ).scalars()
            live = {row_.id: _to_stored(row_) for row_ in rows}

        saved = (
            self._session.execute(
                _scoped_select(user_id, SavedOutfitRow).where(
                    SavedOutfitRow.outfit_id == outfit_id
                )
            ).scalars().first()
            is not None
        )

        return StoredOutfit(
            outfit_id=row.id,
            user_id=row.user_id,
            name=row.name,
            occasion=row.occasion,
            match_score=row.match_score,
            rationale=list(row.rationale or []),
            status=row.status,
            degradation_level=row.degradation_level,
            item_ids=item_ids,
            advisory=dict(row.advisory or {}),
            vibe=row.vibe,
            fit_preference=row.fit_preference,
            color_preferences=list(row.color_preferences or []),
            slots=[
                OutfitSlot(
                    role=join.role,
                    item_id=join.wardrobe_item_id,
                    item=live.get(join.wardrobe_item_id),
                )
                for join in joins
            ],
            saved=saved,
        )

    def swap_slot(
        self,
        user_id: str,
        outfit_id: str,
        *,
        role: str,
        replacement_item_id: str,
        match_score: int,
        status: str,
        rationale: Sequence[str],
        advisory: dict[str, Any],
    ) -> bool:
        """Point one role at a different garment. Returns False when the slot is not there.

        One row is rewritten and the rest are not touched, which is the persistence half of
        the product promise: changing one item changes one item. The caller supplies the new
        score because scoring is the domain's job, not the repository's.
        """
        join = self._session.execute(
            _scoped_select(user_id, OutfitItemRow).where(
                OutfitItemRow.outfit_id == outfit_id, OutfitItemRow.role == role
            )
        ).scalar_one_or_none()
        if join is None:
            return False

        outfit = self._session.execute(
            _scoped_select(user_id, OutfitRow).where(OutfitRow.id == outfit_id)
        ).scalar_one_or_none()
        if outfit is None:
            return False

        # The replacement has to be a live garment of this user's. The composite foreign key
        # would refuse a cross-user write anyway; this makes it a 404 instead of a 500.
        if self._row(user_id, replacement_item_id) is None:
            return False

        join.wardrobe_item_id = replacement_item_id
        outfit.match_score = match_score
        outfit.status = status
        # The narration is rewritten, not kept. Both the rationale and the advisory content
        # were written about a combination that no longer exists, and a tip about the
        # trouser the user just swapped out is worse than no tip at all — it is the visual
        # state disagreeing with the wardrobe state, in prose.
        outfit.rationale = list(rationale)
        outfit.advisory = dict(advisory)
        self._session.flush()
        return True

    def mark_saved(self, user_id: str, outfit_id: str) -> bool:
        """Keep a look. Idempotent — a second press is a no-op, not a second row.

        Returns False when the outfit is not this user's, so the route can answer 404
        without a second lookup.
        """
        outfit = self._session.execute(
            _scoped_select(user_id, OutfitRow).where(OutfitRow.id == outfit_id)
        ).scalar_one_or_none()
        if outfit is None:
            return False

        existing = self._session.execute(
            _scoped_select(user_id, SavedOutfitRow).where(
                SavedOutfitRow.outfit_id == outfit_id
            )
        ).scalars().first()
        if existing is not None:
            return True

        self._session.add(
            SavedOutfitRow(
                id=f"saved_{uuid.uuid4().hex[:16]}", user_id=user_id, outfit_id=outfit_id
            )
        )
        self._session.flush()
        return True

    # --- internals ---------------------------------------------------------------------

    def _row(self, user_id: str, item_id: str) -> WardrobeItemRow | None:
        """The scoped single-row load.

        Deliberately not `Session.get(WardrobeItemRow, item_id)`: a primary-key load skips
        the filter and would hand back any user's garment.

        Soft-deleted rows are excluded here rather than at each call site. S6 added the read
        behind `GET /wardrobe/items/{id}` on top of this method and a deleted garment kept
        answering 200 — deletion looked like it worked in the list view and had not happened
        anywhere else. The same omission made `DELETE` idempotent-by-accident (a second
        delete reported success) and would have let a correction or a re-analysis be applied
        to a garment the user had thrown away.

        `deleted_at` is what makes deletion observable and reversible by support
        (docs/DATA-MODEL.md). "Reversible by support" is not "still present in the product".
        """
        return self._session.execute(
            _scoped_select(user_id, WardrobeItemRow).where(
                WardrobeItemRow.id == item_id, WardrobeItemRow.deleted_at.is_(None)
            )
        ).scalar_one_or_none()


class ExtractionAuditRepository:
    """The append-only evidence trail behind every wardrobe field.

    Rows are written for accepted *and* rejected attempts. An audit trail that only keeps
    the successes cannot show that anything was ever caught, which is the entire point of
    keeping one (docs/DATA-MODEL.md).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        user_id: str,
        wardrobe_item_id: str,
        *,
        provider: str,
        model: str,
        raw_output: Any,
        schema_valid: bool,
        latency_ms: int,
        rejected_reason: str | None = None,
    ) -> None:
        """Append one attempt.

        `raw_output` is stored as returned, before validation — a normalised copy is not
        evidence of what the provider actually said. It is never rendered to a user and
        never logged; it lives here so an extraction can be replayed.
        """
        owner_check = self._session.execute(
            _scoped_select(user_id, WardrobeItemRow).where(
                WardrobeItemRow.id == wardrobe_item_id
            )
        ).scalar_one_or_none()
        if owner_check is None:
            raise ValueError(f"not owned by {user_id}: {wardrobe_item_id}")

        self._session.add(
            ItemExtractionRow(
                wardrobe_item_id=wardrobe_item_id,
                provider=provider,
                model=model,
                raw_output=raw_output,
                schema_valid=schema_valid,
                rejected_reason=rejected_reason,
                latency_ms=latency_ms,
            )
        )
        self._session.flush()

    def for_item(self, user_id: str, wardrobe_item_id: str) -> list[StoredExtraction]:
        """Attempts for one item, oldest first. Empty when the item is not this user's."""
        rows = self._session.execute(_scoped_extractions(user_id, wardrobe_item_id)).scalars()
        return [
            StoredExtraction(
                provider=row.provider,
                model=row.model,
                raw_output=row.raw_output,
                schema_valid=row.schema_valid,
                rejected_reason=row.rejected_reason,
                latency_ms=row.latency_ms,
            )
            for row in rows
        ]


class AssetRepository:
    """Private image records. One row per uploaded file.

    Holds no bytes — `app.services.storage` owns those. This is the index that maps an
    asset id to a storage key, plus the checksum that makes re-uploading a photograph free.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        user_id: str,
        *,
        asset_id: str,
        storage_key: str,
        mime_type: str,
        byte_size: int,
        width: int | None,
        height: int | None,
        checksum: str,
    ) -> StoredAsset:
        self._session.add(
            AssetRow(
                id=asset_id,
                user_id=user_id,
                storage_key=storage_key,
                mime_type=mime_type,
                byte_size=byte_size,
                width=width,
                height=height,
                checksum=checksum,
            )
        )
        self._session.flush()
        return StoredAsset(
            asset_id=asset_id,
            user_id=user_id,
            storage_key=storage_key,
            mime_type=mime_type,
            byte_size=byte_size,
            width=width,
            height=height,
            checksum=checksum,
        )

    def get(self, user_id: str, asset_id: str) -> StoredAsset | None:
        row = self._session.execute(
            _scoped_select(user_id, AssetRow).where(
                AssetRow.id == asset_id, AssetRow.deleted_at.is_(None)
            )
        ).scalar_one_or_none()
        return _to_stored_asset(row) if row else None

    def by_checksum(self, user_id: str, checksum: str) -> StoredAsset | None:
        """The checksum cache lookup, **scoped to one user**.

        The scope is the whole security story of this method. An unscoped checksum index
        would be a global deduplication table: upload a photograph somebody else already
        uploaded and you would be handed their asset, their extraction and their garment.
        Two users who own the same jacket and photograph it identically get two assets, two
        analyses and two rows, and that is the correct answer rather than waste.
        """
        row = self._session.execute(
            _scoped_select(user_id, AssetRow).where(
                AssetRow.checksum == checksum, AssetRow.deleted_at.is_(None)
            )
        ).scalars().first()
        return _to_stored_asset(row) if row else None

    def expired(self, user_id: str, *, cutoff: datetime, limit: int) -> list[PurgeableAsset]:
        """This user's assets whose retention window closed and whose bytes are still there.

        Scoped, like everything else here, and that cost something worth naming. A retention
        sweep wants to ask "which assets anywhere are past their window", and answering it
        directly would have been one query instead of one per user — but it would also have
        been the unscoped read path `tests/test_query_scoping.py` exists to make impossible,
        arriving through the back door as a maintenance job.

        So the sweep enumerates owners first (`app/services/retention.py`) and comes back
        here per user. The invariant is that no read of **owned data** is unscoped; the set
        of owners is not owned data. The extra queries are the price, and at this project's
        scale they are not a price worth arguing about.

        `limit` bounds the batch. A sweep that unlinked a year of accumulated files in one
        transaction would hold a lock for as long as the object store took.
        """
        rows = (
            self._session.execute(
                _scoped_select(user_id, AssetRow)
                .where(
                    AssetRow.deleted_at.is_not(None),
                    AssetRow.deleted_at < cutoff,
                    AssetRow.purged_at.is_(None),
                )
                .order_by(AssetRow.deleted_at)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [PurgeableAsset(asset_id=row.id, storage_key=row.storage_key) for row in rows]

    def mark_purged(self, user_id: str, asset_id: str, *, at: datetime | None = None) -> None:
        """Record that the bytes are gone.

        Set **after** the store has been asked to delete them, never before. The other order
        would mean a failure mid-sweep leaves a row claiming a file is gone while the file
        is still there — a record that is worse than no record, because somebody would
        answer a deletion request from it.
        """
        row = self._session.execute(
            _scoped_select(user_id, AssetRow).where(AssetRow.id == asset_id)
        ).scalar_one_or_none()
        if row is not None:
            row.purged_at = at or _now()

    def item_for_asset(self, user_id: str, asset_id: str) -> str | None:
        """The live wardrobe item backed by this asset, if any."""
        row = self._session.execute(
            _scoped_select(user_id, WardrobeItemRow).where(
                WardrobeItemRow.asset_id == asset_id, WardrobeItemRow.deleted_at.is_(None)
            )
        ).scalars().first()
        return row.id if row else None


def _to_stored_asset(row: AssetRow) -> StoredAsset:
    return StoredAsset(
        asset_id=row.id,
        user_id=row.user_id,
        storage_key=row.storage_key,
        mime_type=row.mime_type,
        byte_size=row.byte_size,
        width=row.width,
        height=row.height,
        checksum=row.checksum,
    )


__all__ = [
    "AssetRepository",
    "DeletionResult",
    "ExtractionAuditRepository",
    "OutfitSlot",
    "PurgeableAsset",
    "StoredAsset",
    "StoredExtraction",
    "StoredItem",
    "StoredOutfit",
    "WardrobeDeletion",
    "WardrobeRepository",
]
