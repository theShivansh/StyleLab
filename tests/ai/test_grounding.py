"""Grounding regression — the cross-cutting proof layer.

Runs with **no API key and no network**: stub adapters from `stubs.py`, the real domain
rules, and a real (in-memory) database. Every assertion here is about the contract, not
about a provider, which is why this directory sits at the repository root rather than
inside `apps/api` (`tests/README.md`).

S4 lands the three cases the domain layer can already answer in full. The rest of
`docs/AI-EVAL-CASES.md` — extraction accuracy, the agent crew, trends, ablation — needs the
adapters and the crew, and arrives with the harness in S8 and S8b.

  * Case 01 — wardrobe grounding
  * Case 11 — cross-user isolation
  * Case 12 — insufficient wardrobe

If this file ever needs a key to run, something has been wired the wrong way round: a
regression suite that costs money per run stops being run.
"""

from __future__ import annotations

import pytest
from app.db.models import Base
from app.db.session import build_engine, session_factory
from app.domain.models import GarmentCategory as C
from app.repositories.wardrobe import WardrobeRepository
from app.services.composition import CompositionService
from stubs import ScriptedAdvisor, garment

U1, U2 = "eval-u1", "eval-u2"


@pytest.fixture
def repository():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        repo = WardrobeRepository(session)
        repo.add_user(U1, "u1@example.test")
        repo.add_user(U2, "u2@example.test")
        yield repo
    engine.dispose()


def _full_wardrobe(repo: WardrobeRepository, user_id: str, prefix: str) -> None:
    for suffix, category in (
        ("top", C.TOP),
        ("bottom", C.BOTTOM),
        ("shoe", C.FOOTWEAR),
    ):
        repo.add_item(garment(f"{prefix}-{suffix}", user_id, category=category))


async def test_case_01_output_references_only_owned_items(repository):
    """An id that is plausible and simply does not exist is still refused."""
    _full_wardrobe(repository, U1, "ITEM")
    advisor = ScriptedAdvisor.naming("ITEM-top", "ITEM-bottom", "ITEM-D")

    advice = await CompositionService(repository, advisor=advisor).compose(
        U1, occasion="college"
    )

    assert advice.outfit is not None
    assert set(advice.outfit.item_ids) <= {"ITEM-top", "ITEM-bottom", "ITEM-shoe"}
    assert "ITEM-D" not in advice.outfit.item_ids


async def test_case_11_another_users_item_is_never_retrieved(repository):
    _full_wardrobe(repository, U1, "u1")
    repository.add_item(garment("u2-jacket", U2, category=C.OUTERWEAR))

    advisor = ScriptedAdvisor.naming("u1-top", "u1-bottom", "u1-shoe")
    await CompositionService(repository, advisor=advisor).compose(U1, occasion="everyday")

    candidates = {c.item_id for call in advisor.calls for c in call.candidates}
    assert "u2-jacket" not in candidates
    assert candidates == {"u1-top", "u1-bottom", "u1-shoe"}


async def test_case_11_a_forged_response_is_refused(repository):
    """The half a prompt cannot give you: the response is well formed, confident, and names
    a real item belonging to somebody else."""
    _full_wardrobe(repository, U1, "u1")
    repository.add_item(garment("u2-jacket", U2, category=C.OUTERWEAR))

    advisor = ScriptedAdvisor.naming("u1-top", "u1-bottom", "u2-jacket", confidence=0.99)
    service = CompositionService(repository, advisor=advisor)

    advice = await service.compose(U1, occasion="everyday")

    assert advice.outfit is not None
    assert "u2-jacket" not in advice.outfit.item_ids
    assert [r.reason for r in service.rejections] == ["ungrounded_item"]
    # Degraded, not failed: the user still gets a look from their own wardrobe.
    assert advice.degradation_level == 4


async def test_case_12_insufficient_wardrobe_names_the_gap(repository):
    """Three tops and no bottoms. No invented garment, no one-item outfit, no silence."""
    for index in range(3):
        repository.add_item(garment(f"u1-top-{index}", U1, category=C.TOP))

    advisor = ScriptedAdvisor.naming("u1-top-0")
    advice = await CompositionService(repository, advisor=advisor).compose(
        U1, occasion="everyday"
    )

    assert advice.outfit is None
    assert advice.missing_roles == [C.BOTTOM, C.FOOTWEAR]
    assert {gap.category for gap in advice.wardrobe_gaps} == {C.BOTTOM, C.FOOTWEAR}
    # Generic descriptions only — the product sells nothing.
    for gap in advice.wardrobe_gaps:
        assert not any(
            token in gap.generic_description.lower() for token in ("$", "buy", "shop", "http")
        )
