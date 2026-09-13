"""What each agent is contractually obliged to return.

`docs/AGENT-SYSTEM.md`: *per-agent structured output schemas — no free-text handoffs between
agents.* This file is that requirement, written down.

The reason is not tidiness. A crew that passes prose between roles has two failure modes that
are invisible until they matter: a downstream agent silently misreads an upstream one, and —
worse — an upstream agent's text can contain instructions. Case 19 says agent-to-agent
messages are untrusted. A typed field cannot carry an instruction; it can only carry a value
of that type, in a slot the downstream prompt puts in a named place.

These are **adapter** types, not domain types. They describe how the crew talks to itself,
which is an implementation detail of one `OutfitAdvisor`. Only the Editor's output maps onto
`OutfitAdvice`, and even that mapping is untrusted — schema, business and ownership
validation all run on it afterwards, exactly as they do for the single-call advisor.

Every list is bounded. An agent that returns four hundred pro tips has not been helpful, and
an unbounded list is a token bill and a rendering bug waiting to happen.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Same posture as the domain models: unknown fields are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid")


class StyleProfile(Strict):
    """Agent 2 — the user's aesthetic, described in their own clothes' terms.

    Deliberately has no field for the person. A style profile is a reading of a wardrobe,
    never of a body: CLAUDE.md forbids inferring attributes of anyone in a photograph, and
    the cheapest way to hold that here is to give the model nowhere to put it.
    """

    aesthetic: str = Field(max_length=200)
    recurring_colours: list[str] = Field(default_factory=list, max_length=6)
    preferred_silhouettes: list[str] = Field(default_factory=list, max_length=6)
    #: What the wardrobe suggests they reach for, as observations rather than instructions.
    observations: list[str] = Field(default_factory=list, max_length=4)


class AppliedTrend(Strict):
    """One supplied trend, mapped onto garments the user owns."""

    #: The identity of the note as supplied. The agent may not restate the claim, the source
    #: or the date — `app.domain.validation` takes those from the supplied note by this URL.
    url: str
    item_ids: list[str] = Field(default_factory=list, max_length=6)
    why: str = Field(default="", max_length=200)


class TrendApplication(Strict):
    """Agent 3 — which of the supplied trends touch this wardrobe, and where.

    The Trend Scout does not fetch. `ExaTrendSource` fetches, before the crew runs, and the
    notes arrive in the prompt. This agent's only job is the mapping, which is why it cannot
    introduce a trend: there is no field for one.
    """

    applied: list[AppliedTrend] = Field(default_factory=list, max_length=4)


class OutfitDraft(Strict):
    """Agent 4 — one candidate look."""

    item_ids: list[str] = Field(min_length=1, max_length=8)
    name: str = Field(max_length=60)
    occasion: str = Field(max_length=40)
    rationale: list[str] = Field(default_factory=list, max_length=4)


class Critique(Strict):
    """Agent 5 — the second opinion, and the auto-evaluation that drives the revision loop.

    `score` makes this an LLM-as-judge as well as a commentator, which is what lets the
    Architect be re-run *with constraints* rather than re-run and hoped over. The number is
    never shown to a user and is never the Style Match: that is computed deterministically
    from the garments (`app.domain.scoring`), because two identical wardrobes must not show
    different figures depending on how a model felt.
    """

    considered: list[str] = Field(default_factory=list, max_length=4)
    tradeoffs: list[str] = Field(default_factory=list, max_length=4)
    #: Concrete, actionable objections. These become the constraints on a revision, so a
    #: vague one costs a whole extra pass and buys nothing.
    objections: list[str] = Field(default_factory=list, max_length=4)
    #: 0-100. Below `REVISION_THRESHOLD` the Architect is asked again.
    score: int = Field(ge=0, le=100)


class ProTipOut(Strict):
    tip: str = Field(max_length=200)
    type: str = Field(default="styling", max_length=24)


class GapOut(Strict):
    category: str = Field(max_length=32)
    generic_description: str = Field(max_length=160)
    unlocks_outfits: int = Field(default=0, ge=0, le=20)


class PracticalAdvice(Strict):
    """Agent 6 — what to do with the look, and what the wardrobe is missing.

    No brand, price, merchant or link is representable here, and that is the whole design of
    the type. `app.domain.advisory` still filters the text afterwards, because a model can
    write a price into a sentence — but it cannot write one into a field that does not exist.
    """

    pro_tips: list[ProTipOut] = Field(default_factory=list, max_length=4)
    budget_tricks: list[str] = Field(default_factory=list, max_length=3)
    wardrobe_gaps: list[GapOut] = Field(default_factory=list, max_length=3)


class EditorOutput(Strict):
    """Agent 7 — one merged answer, and the only one that becomes an `OutfitAdvice`.

    Untrusted like every other agent, and the docstring says so because this is the one
    somebody will eventually be tempted to trust: it has read everything, it is last, and it
    is the one whose output looks like the product. Schema, business and ownership validation
    all run on it. The Critic having approved it is not evidence (Case 20).
    """

    item_ids: list[str] = Field(min_length=1, max_length=8)
    name: str = Field(max_length=60)
    occasion: str = Field(max_length=40)
    rationale: list[str] = Field(default_factory=list, max_length=4)
    confidence: float = Field(default=0.8, ge=0, le=1)
    # No `critique` field. It was here, nothing read it, and it cost the Editor the tokens to
    # restate a whole nested object — which is how a live run came back `json_validate_failed`
    # with the response truncated before `budget_tricks`. The Critic's output is already in
    # hand where it is needed; asking the last agent to copy it out again bought nothing.
    pro_tips: list[ProTipOut] = Field(default_factory=list, max_length=4)
    budget_tricks: list[str] = Field(default_factory=list, max_length=3)
    wardrobe_gaps: list[GapOut] = Field(default_factory=list, max_length=3)
    applied_trends: list[AppliedTrend] = Field(default_factory=list, max_length=4)


#: A critique at or above this is served. Below it, the Architect gets one more attempt with
#: the objections attached as constraints.
#:
#: 70 rather than a higher bar because the loop is bounded at one revision: setting it where
#: most drafts fail would double the cost of a typical compose to re-roll work that was
#: already acceptable. Tuned by looking at scores on real wardrobes, and recorded in
#: docs/DECISIONS.md as a number arrived at rather than chosen.
REVISION_THRESHOLD = 70

#: How many times the Architect may be re-run. One. A second revision is another four
#: seconds of a fifteen-second budget for a model that has already been told what was wrong
#: with its first two attempts.
MAX_REVISIONS = 1


__all__ = [
    "MAX_REVISIONS",
    "REVISION_THRESHOLD",
    "AppliedTrend",
    "Critique",
    "EditorOutput",
    "GapOut",
    "OutfitDraft",
    "PracticalAdvice",
    "ProTipOut",
    "StyleProfile",
    "TrendApplication",
]
