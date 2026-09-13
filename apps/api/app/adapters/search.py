"""The search seam — where the mock Exa provider plugs in.

Exactly the arrangement `transport.py` uses for Groq, and for exactly the same reason. The
seam sits **below** `ExaTrendSource`, so a test that replaces it still runs the real query
construction, the real normalisation, the real attribution rules, the real deduplication and
the real cache. A double that replaced `TrendSource` instead would assert that a stub returns
what the stub was told to return.

Nothing in this file names Exa. A search result is a title, a URL, a date and some text —
that shape is not a vendor's, and `app/services/` has no business knowing whose API produced
it. `exa_search.py` is the only module that does.

## Why a separate seam from `ChatTransport`

They look similar and are not the same thing. A chat completion is a generation and is
measured as one; a search is a retrieval, is cached, and is billed per request rather than
per token. Folding them together would mean one `GenerationEvent` stream in which half the
rows had no tokens and no model, which is the sort of tidiness that costs you a dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One document a search engine returned, in provider-neutral form.

    Everything except `url` is optional, because everything except `url` genuinely can be
    missing from a real result — and the whole attribution rule (Case 15) exists because of
    that. Modelling `published_at` as required here would push the failure into a parse error
    and lose the ability to say *which* field was absent.
    """

    url: str
    title: str | None = None
    published_at: date | None = None
    author: str | None = None
    #: Short extracts the engine judged relevant. Untrusted text from the open web, subject
    #: to the same rules as text found inside an uploaded photograph (Case 18).
    highlights: tuple[str, ...] = ()
    text: str | None = None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """The results, plus what the call cost us to make."""

    hits: tuple[SearchHit, ...] = ()
    latency_ms: int = 0
    request_id: str | None = None
    #: What the engine decided to run when asked for `auto`. Recorded, never chosen from.
    resolved_type: str | None = None
    #: Some engines report this per call. `None` means they did not.
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """One search, in the terms the caller thinks in."""

    query: str
    #: `auto` lets the engine pick between keyword and neural retrieval per query.
    search_type: str = "auto"
    max_results: int = 8
    #: Ask for the engine's own extracts rather than whole pages. A trend note is a sentence;
    #: pulling full article text would mean paying to download an advertising-laden page in
    #: order to throw away all but forty words of it.
    highlights: bool = True
    #: Oldest publication date worth returning. A trend is a claim about *now*.
    published_after: date | None = None
    domains: tuple[str, ...] = field(default=())


@runtime_checkable
class SearchTransport(Protocol):
    """A web search endpoint. The one thing `MockExaProvider` has to satisfy."""

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Raises a `SearchError`, never a vendor or HTTP exception."""
        ...


class SearchError(Exception):
    """Anything the search provider did wrong, in our vocabulary.

    `reason` is a short stable token — it goes into telemetry as `fallback_reason` and into
    nothing a user reads. A provider message can quote the query, and the query is built from
    a user's wardrobe.
    """

    reason = "search_unavailable"
    retryable = True

    def __init__(self, message: str = "the search provider did not answer") -> None:
        super().__init__(message)


class SearchTimeoutError(SearchError):
    reason = "timeout"


class SearchRateLimitedError(SearchError):
    reason = "rate_limited"


class SearchRefusedError(SearchError):
    """A bad key, a malformed request — retrying spends quota for the same answer."""

    reason = "refused"
    retryable = False


class SearchContractError(SearchError):
    """The provider answered, and not in the shape it documents."""

    reason = "malformed_response"
    retryable = False


__all__ = [
    "SearchContractError",
    "SearchError",
    "SearchHit",
    "SearchQuery",
    "SearchRateLimitedError",
    "SearchRefusedError",
    "SearchResponse",
    "SearchTimeoutError",
    "SearchTransport",
]
