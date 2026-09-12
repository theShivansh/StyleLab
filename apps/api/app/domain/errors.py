"""Explicit domain errors.

Three separate failures, kept separate because they call for three different responses:

* `SchemaInvalidError` — the provider did not answer in the agreed shape. Retryable.
* `UngroundedItemError` — the answer names something outside the retrieved candidate
  set. Not retryable into, and never served. Logged at CRITICAL: an advisor naming an id we did not
  give it is a serious event whoever that id belongs to.
* `IncompatibleOutfitError` — the answer is well formed and grounded, but is not an outfit.

Note what `UngroundedItemError` deliberately does *not* carry: whether the id belongs to
another user. Answering that would require reading outside the requesting user's scope, and
docs/AI-SYSTEM.md is explicit that such an id is "rejected, not fetched". Attribution is a
job for the alerting layer, which has legitimate admin scope outside the request path.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class, so a caller can catch the domain without catching everything."""


class SchemaInvalidError(DomainError):
    """Provider output did not satisfy the structured-output contract."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UngroundedItemError(DomainError):
    """A response named an item that was not in the candidate set given to the model."""

    def __init__(self, item_ids: list[str], *, user_id: str) -> None:
        super().__init__(f"{len(item_ids)} ungrounded item id(s) in response")
        #: Sorted, so a log line is stable and diffable.
        self.item_ids = sorted(item_ids)
        self.user_id = user_id

    @property
    def detail(self) -> str:
        return ", ".join(self.item_ids)


class IncompatibleOutfitError(DomainError):
    """A grounded response that is not a valid outfit — a missing or doubled role."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class ConfigurationError(DomainError):
    """A required setting is absent. Raised at boot, never papered over with a default —
    a silent fallback is how a demo mode gets back in (AI-EVAL-CASES Case 25)."""


__all__ = [
    "ConfigurationError",
    "DomainError",
    "IncompatibleOutfitError",
    "SchemaInvalidError",
    "UngroundedItemError",
]
