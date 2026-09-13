"""The only module that knows Exa exists.

Everything above this file speaks `SearchTransport` (`search.py`), the same way everything
above `groq_transport.py` speaks `ChatTransport`. `tests/test_adapter_boundary.py` fails the
build if the string `exa` appears as an import or a symbol outside `app/adapters/`.

## Why HTTP rather than the SDK

`exa_py` wraps one POST. Taking the dependency would buy retry behaviour we already have a
house style for, a client lifecycle we would have to manage anyway, and a second opinion
about what a timeout means. `httpx` is already in the tree because the API is served on it.
The endpoint is `POST /search` and the request is a dict; there is nothing here worth a
vendor SDK.

## Retry policy

Deliberately none. This is not the Groq transport, and the difference is worth stating: a
failed *generation* costs the user their outfit, so it is worth three attempts with backoff.
A failed *trend lookup* costs the user a paragraph of context — the crew drops the Trend
Scout, records degradation level 2, and carries on. Retrying inside the request would spend
the latency budget on the least important thing in it.

## What is not sent

The user's id, their item ids, or any text extracted from their photographs. A trend query
is built from region, season and a style vocabulary — see `exa_trends.py`. Nothing about one
person's wardrobe should end up in a third party's query logs.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

import httpx

from app.adapters.search import (
    SearchContractError,
    SearchError,
    SearchHit,
    SearchQuery,
    SearchRateLimitedError,
    SearchRefusedError,
    SearchResponse,
    SearchTimeoutError,
)

logger = logging.getLogger("stylelab.search")

EXA_BASE_URL = "https://api.exa.ai"
DEFAULT_TIMEOUT_S = 8.0

#: Search types Exa accepts. `auto` lets it choose between keyword and neural per query,
#: which is the documented default for general use and what the product asks for.
SEARCH_TYPES = ("auto", "neural", "keyword", "fast")


def _parse_date(raw: object) -> date | None:
    """Exa's `publishedDate`, which is an ISO 8601 timestamp, a bare date, or absent.

    Returns `None` rather than raising for anything unparseable. A result with an
    unreadable date is a result with no date, and `exa_trends.py` drops it — which is the
    same outcome by a route that says why.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _hit(raw: object) -> SearchHit | None:
    """One result object to a `SearchHit`, or `None` if it is not one.

    A result with no URL is not a citation and cannot be shown to anybody, so it is dropped
    here rather than carried forward as a hit that will fail validation later.
    """
    if not isinstance(raw, dict):
        return None
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        return None

    highlights = raw.get("highlights")
    extracts = (
        tuple(h for h in highlights if isinstance(h, str) and h.strip())
        if isinstance(highlights, list)
        else ()
    )

    return SearchHit(
        url=url.strip(),
        title=raw.get("title") if isinstance(raw.get("title"), str) else None,
        published_at=_parse_date(raw.get("publishedDate")),
        author=raw.get("author") if isinstance(raw.get("author"), str) else None,
        highlights=extracts,
        text=raw.get("text") if isinstance(raw.get("text"), str) else None,
    )


class ExaSearchTransport:
    """`SearchTransport` over Exa's `POST /search`."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        base_url: str = EXA_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            # Same rule as the Groq key: a missing credential is a loud failure at
            # construction, never a component that quietly returns nothing at runtime.
            raise ValueError("EXA_API_KEY is required to construct ExaSearchTransport")
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def search(self, query: SearchQuery) -> SearchResponse:
        payload = self._payload(query)
        started = time.perf_counter()

        try:
            response = await self._post(payload)
        except httpx.TimeoutException as error:
            raise SearchTimeoutError("the search provider timed out") from error
        except httpx.HTTPError as error:
            # Never `str(error)`: an httpx message embeds the URL, and the URL is the query.
            raise SearchError(f"{type(error).__name__} from the search provider") from error

        latency_ms = int((time.perf_counter() - started) * 1000)
        self._raise_for_status(response)

        try:
            body = response.json()
        except ValueError as error:
            raise SearchContractError("the search provider did not return JSON") from error
        if not isinstance(body, dict):
            raise SearchContractError("the search response was not an object")

        results = body.get("results")
        if results is None:
            results = []
        if not isinstance(results, list):
            raise SearchContractError("the search response had no usable results array")

        hits = tuple(hit for raw in results if (hit := _hit(raw)) is not None)
        return SearchResponse(
            hits=hits,
            latency_ms=latency_ms,
            request_id=response.headers.get("x-request-id"),
            resolved_type=(
                body.get("resolvedSearchType")
                if isinstance(body.get("resolvedSearchType"), str)
                else None
            ),
            cost_usd=_cost(body.get("costDollars")),
        )

    # --- internals ----------------------------------------------------------------------

    def _payload(self, query: SearchQuery) -> dict[str, Any]:
        search_type = query.search_type if query.search_type in SEARCH_TYPES else "auto"
        payload: dict[str, Any] = {
            "query": query.query,
            "type": search_type,
            "numResults": max(1, min(25, query.max_results)),
        }
        if query.highlights:
            # Highlights only. Asking for full `text` would mean paying to download an
            # article in order to keep forty words of it, and would put far more untrusted
            # web copy into the process than the product has any use for.
            payload["contents"] = {"highlights": True}
        if query.published_after is not None:
            payload["startPublishedDate"] = f"{query.published_after.isoformat()}T00:00:00.000Z"
        if query.domains:
            payload["includeDomains"] = list(query.domains)
        return payload

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {"x-api-key": self._api_key, "Content-Type": "application/json"}
        if self._client is not None:
            return await self._client.post(
                f"{self._base_url}/search",
                json=payload,
                headers=headers,
                timeout=self._timeout_s,
            )
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            return await client.post(f"{self._base_url}/search", json=payload, headers=headers)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 429:
            raise SearchRateLimitedError("the search provider rate-limited us")
        if status in (401, 402, 403, 400, 422):
            # A bad key, an exhausted balance or a malformed request. Retrying spends the
            # same quota for the same answer.
            logger.warning("search provider refused the request", extra={"status": status})
            raise SearchRefusedError("the search provider refused the request")
        raise SearchError(f"the search provider returned {status}")


def _cost(raw: object) -> float | None:
    if isinstance(raw, dict):
        total = raw.get("total")
        if isinstance(total, int | float):
            return float(total)
    return None


__all__ = ["DEFAULT_TIMEOUT_S", "EXA_BASE_URL", "SEARCH_TYPES", "ExaSearchTransport"]
