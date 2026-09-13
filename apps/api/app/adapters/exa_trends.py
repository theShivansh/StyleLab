"""`ExaTrendSource` — dated, cited trend context from the live web.

The rule this implements is CLAUDE.md's, and it is the reason the whole layer exists:

> Trend input comes from the `TrendSource` adapter, never from model recall. Asking a model
> what is currently fashionable returns confident output from a training cutoff with no
> source and no date — that is the gimmick this project exists to avoid.

So a trend note here is a **retrieved document**, and it carries a claim, a publication, a
date and a link. Anything missing one of those is dropped rather than shown, because a
citation the reader cannot follow is indistinguishable from an invented one.

## What this may and may not do

A trend may re-rank or contextualise garments the user already owns. It may never introduce
one. That is enforced twice and neither is in a prompt: nothing here reads the wardrobe, so
a note cannot name an item; and `app.domain.validation` matches the advisor's returned notes
back against the ones supplied here, by URL, so the crew cannot invent a citation either.

Nothing about a user reaches Exa. A query is built from region, season and a fixed style
vocabulary — never a garment description, an item id, a user id, or text extracted from
somebody's photograph. Their wardrobe is not a search term.

## Failure is a rung, not an error

Timeout, rate limit, refusal, malformed response, no results — all of them return an empty
list and record why. The crew then runs without the Trend Scout at degradation level 2,
which the UI discloses. A trend lookup is the least important call in the request and must
never be the one that fails it.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from app.adapters.search import (
    SearchContractError,
    SearchError,
    SearchHit,
    SearchQuery,
    SearchRateLimitedError,
    SearchTimeoutError,
    SearchTransport,
)
from app.domain.models import GarmentCategory, TrendNote, TrendQuery
from app.services.telemetry import NullTrendLog, TrendLog, TrendLookupEvent, TrendOutcome

logger = logging.getLogger("stylelab.trends")

PROVIDER = "exa"

#: Longest a trend claim may be once normalised. A headline, not an article — and a bound on
#: untrusted web text before it reaches a prompt (Case 18, and the same argument as
#: `app.domain.hygiene`).
MAX_TREND_CHARS = 180

#: Publications whose fashion desks date their work and are not shopping catalogues. Not a
#: quality judgement so much as a commerce filter: the product sells nothing, and a
#: retailer's "trend report" is an advertisement with a date on it.
EDITORIAL_DOMAINS: tuple[str, ...] = (
    "vogue.com",
    "businessoffashion.com",
    "wwd.com",
    "highsnobiety.com",
    "gq.com",
    "esquire.com",
    "theguardian.com",
    "nytimes.com",
    "ft.com",
    "dazeddigital.com",
    "another-mag.com",
    "papermag.com",
    "hypebeast.com",
    "fashionista.com",
)

#: Words that mark a result as commerce rather than journalism. A URL carrying any of them
#: is dropped before it can become a note.
COMMERCE_MARKERS: tuple[str, ...] = (
    "/shop",
    "/product",
    "/buy",
    "/sale",
    "/cart",
    "/checkout",
    "add-to-bag",
    "?utm_campaign=shopping",
)

_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WORD = re.compile(r"[a-z0-9]+")

#: Words too common in fashion copy to carry any signal when comparing two headlines.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "is", "are",
        "this", "that", "with", "how", "why", "what", "your", "you", "we", "it",
        "fashion", "style", "trend", "trends", "season", "wear", "wearing", "look",
        "looks", "best", "new", "now", "guide", "2026", "2027",
    }
)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    collapsed = _WHITESPACE.sub(" ", _CONTROL.sub(" ", text)).strip()
    return collapsed[:MAX_TREND_CHARS] if collapsed else None


def _publication(url: str) -> str | None:
    """The publication name, from the host. `www.` dropped, nothing else invented."""
    match = re.match(r"https?://([^/]+)", url)
    if match is None:
        return None
    host = match.group(1).lower().removeprefix("www.")
    return host or None


def _fingerprint(note_text: str) -> frozenset[str]:
    """Content words in a headline, for near-duplicate detection."""
    return frozenset(
        word for word in _WORD.findall(note_text.lower()) if word not in _STOPWORDS
    )


def season_for(moment: date) -> str:
    """Northern-hemisphere meteorological season.

    A simplification, stated rather than hidden: it is wrong for half the planet, and it is
    a cache key and a search term rather than a claim shown to anybody. A per-region season
    lands when `trend_region` becomes per-user in S9.
    """
    return ("winter", "spring", "summer", "autumn")[(moment.month % 12) // 3]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    notes: tuple[TrendNote, ...]
    expires_at: float


@dataclass
class ExaTrendSource:
    """`TrendSource` over a `SearchTransport`.

    The transport is injected, which is what lets `MockExaProvider` drive this exact class —
    the real query construction, the real attribution filter, the real deduplication, the
    real cache — with no key and no network.
    """

    transport: SearchTransport
    max_results: int = 8
    search_type: str = "auto"
    region: str = "global"
    #: How stale a published article may be and still count as a trend.
    max_age_days: int = 120
    cache_ttl_s: int = 24 * 60 * 60
    telemetry: TrendLog = field(default_factory=NullTrendLog)
    #: Overridable so a test can age the cache without sleeping for a day.
    now: object = None

    _cache: dict[str, _CacheEntry] = field(default_factory=dict, init=False, repr=False)

    # --- the Protocol ---------------------------------------------------------------------

    async def current(self, query: TrendQuery) -> list[TrendNote]:
        """Dated, attributed notes for this query, or an empty list and a recorded reason."""
        key = self.cache_key(query)
        cached = self._cached(key)
        if cached is not None:
            self._record("cached", 0, cache_hit=True, results=len(cached))
            return list(cached)

        started = time.perf_counter()
        try:
            response = await self.transport.search(self._query_for(query))
        except SearchTimeoutError:
            return self._skipped("timeout", started)
        except SearchRateLimitedError:
            return self._skipped("rate_limited", started)
        except SearchContractError:
            return self._skipped("malformed", started)
        except SearchError:
            return self._skipped("unavailable", started)
        except Exception:
            # A trend lookup must not be able to fail a compose, whatever went wrong in it.
            logger.warning("trend lookup failed unexpectedly", exc_info=True)
            return self._skipped("unavailable", started)

        notes, dropped = self.normalise(response.hits)
        self._cache[key] = _CacheEntry(
            notes=tuple(notes), expires_at=self._monotonic() + self.cache_ttl_s
        )
        self._record(
            "ok" if notes else "empty",
            response.latency_ms,
            results=len(notes),
            dropped=dropped,
            request_id=response.request_id,
        )
        return notes

    # --- query construction ----------------------------------------------------------------

    def _query_for(self, query: TrendQuery) -> SearchQuery:
        return SearchQuery(
            query=self.phrase(query),
            search_type=self.search_type,
            max_results=max(6, min(8, self.max_results)),
            highlights=True,
            published_after=self._today() - timedelta(days=self.max_age_days),
            domains=EDITORIAL_DOMAINS,
        )

    def phrase(self, query: TrendQuery) -> str:
        """The search string, built from region and season and nothing personal.

        Region-aware because "what is current" genuinely differs by market, and because a
        query that says nothing about where the reader is returns American department-store
        copy by default.

        Categories are named at the level of "outerwear", never at the level of a garment the
        user owns. `TrendQuery.categories` is the set of *roles the outfit needs*, which is
        the same for every user asking for the same kind of outfit — so it carries no
        information about anybody's wardrobe.
        """
        region = (query.region or self.region or "global").strip()
        where = "" if region.lower() in ("", "global") else f" in {region}"
        categories = ", ".join(sorted(_readable(c) for c in query.categories))
        subject = categories or "everyday wardrobe"
        return (
            f"{season_for(self._today())} {self._today().year} fashion trends"
            f"{where}: {subject} — editorial analysis, not shopping"
        )

    def cache_key(self, query: TrendQuery) -> str:
        """Region + season + style profile, exactly as the caching rule specifies.

        The style profile here is the requested role set, which is what actually changes the
        query. Keying on anything more specific — a user id, a wardrobe hash — would make the
        cache per-user and it would never hit, which is a cache in name only.
        """
        region = (query.region or self.region or "global").strip().lower()
        roles = "+".join(sorted(c.value for c in query.categories)) or "any"
        return f"{region}|{season_for(self._today())}|{roles}"

    # --- normalisation ------------------------------------------------------------------------

    def normalise(self, hits: Sequence[SearchHit]) -> tuple[list[TrendNote], int]:
        """Search results to trend notes, dropping everything that cannot be attributed.

        Returns the notes and how many were discarded. The gap between what the provider
        returned and what survived is the number worth watching: a sudden rise in it means
        the queries have drifted into somebody's shop.
        """
        notes: list[TrendNote] = []
        seen_urls: set[str] = set()
        seen_fingerprints: list[frozenset[str]] = []
        dropped = 0

        for hit in hits:
            note = self._note(hit)
            if note is None:
                dropped += 1
                continue

            # Exact duplicates: the same article syndicated under two query terms.
            canonical = note.url.split("?")[0].rstrip("/").lower()
            if canonical in seen_urls:
                dropped += 1
                continue

            # Near duplicates: two outlets running the same story. Compared on content words
            # rather than on the whole headline, because "wide-leg trousers are back" and
            # "why wide-leg trousers are back for AW26" are one trend and not two.
            fingerprint = _fingerprint(note.trend)
            if any(_overlaps(fingerprint, seen) for seen in seen_fingerprints):
                dropped += 1
                continue

            seen_urls.add(canonical)
            seen_fingerprints.append(fingerprint)
            notes.append(note)

        return notes, dropped

    def _note(self, hit: SearchHit) -> TrendNote | None:
        """One hit to a note, or `None` with the reason implied by which check failed.

        Four things are required and none of them is negotiable: a claim, a publication, a
        date and a link. A fifth check drops commerce.
        """
        if hit.published_at is None:
            return None
        if hit.published_at < self._today() - timedelta(days=self.max_age_days):
            return None
        if hit.published_at > self._today() + timedelta(days=1):
            # A future publication date is a parsing artefact or a broken CMS, not news.
            return None

        url = hit.url
        lowered = url.lower()
        if any(marker in lowered for marker in COMMERCE_MARKERS):
            return None

        source = _publication(url)
        if source is None:
            return None

        # The claim: the engine's own extract if it produced one, else the headline. The
        # extract is closer to what the article actually argues; the title is often a tease.
        claim = _clean(hit.highlights[0] if hit.highlights else None) or _clean(hit.title)
        if not claim:
            return None

        return TrendNote(
            trend=claim,
            source=source,
            published_at=hit.published_at,
            url=url,
            # Never set here. Which owned garments a trend applies to is the crew's judgement
            # over the candidate set, and this module has never seen the wardrobe.
            applies_to_items=[],
        )

    # --- cache, clock, telemetry ------------------------------------------------------------------

    def _cached(self, key: str) -> tuple[TrendNote, ...] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._monotonic():
            del self._cache[key]
            return None
        return entry.notes

    def _today(self) -> date:
        if callable(self.now):
            return self.now()  # type: ignore[operator]
        return datetime.now(UTC).date()

    @staticmethod
    def _monotonic() -> float:
        return time.monotonic()

    def _skipped(self, reason: TrendOutcome, started: float) -> list[TrendNote]:
        """Record the miss and hand back nothing. The crew drops to rung 2 from here."""
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info("trend scout skipped", extra={"reason": reason})
        self._record(reason, latency_ms, fallback_reason=reason, degradation_level=2)
        return []

    def _record(
        self,
        outcome: TrendOutcome,
        latency_ms: int,
        *,
        cache_hit: bool = False,
        results: int = 0,
        dropped: int = 0,
        fallback_reason: str | None = None,
        degradation_level: int | None = None,
        request_id: str | None = None,
    ) -> None:
        self.telemetry.record(
            TrendLookupEvent(
                provider=PROVIDER,
                outcome=outcome,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                results=results,
                dropped=dropped,
                fallback_reason=fallback_reason,
                degradation_level=degradation_level if degradation_level else 1,
                request_id=request_id,
            )
        )


def _overlaps(left: frozenset[str], right: frozenset[str], threshold: float = 0.6) -> bool:
    """Jaccard similarity over content words.

    0.6 is a judgement, arrived at by looking: below it, genuinely different claims about the
    same garment category start merging; above it, a rewritten headline slips through as new.
    """
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= threshold


def _readable(category: GarmentCategory) -> str:
    return category.value.replace("_", " ")


__all__ = [
    "COMMERCE_MARKERS",
    "EDITORIAL_DOMAINS",
    "MAX_TREND_CHARS",
    "PROVIDER",
    "ExaTrendSource",
    "season_for",
]
