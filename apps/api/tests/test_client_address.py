"""Who the session limiter thinks is calling, behind a proxy and not behind one.

`POST /session` is the only rate limit keyed on an address rather than on a user, because
there is no account to throttle instead (blocker B15). That makes the address the limiter's
entire notion of identity, and getting it wrong fails in two opposite ways:

* believe the socket peer behind a proxy, and every visitor on earth shares one bucket — ten
  sessions per fifteen minutes for the whole internet, which is a deployment that stops
  admitting people on the day somebody links to it
* believe `X-Forwarded-For` without counting hops, and the limiter is switched off by anyone
  who sets a header

So the setting is a count of trusted proxies, and this file holds it to both ends.
"""

from __future__ import annotations

import pytest

from app.deps import forwarded_peer

CHAIN = "203.0.113.7, 198.51.100.4, 192.0.2.9"


# --- the parsing, on its own ----------------------------------------------------------------


def test_no_trusted_proxy_means_the_header_is_not_read_at_all():
    """The default, and the only safe one for a host reachable directly."""
    assert forwarded_peer(CHAIN, hops=0) is None


def test_one_trusted_proxy_reads_the_entry_that_proxy_appended():
    """The rightmost entry is the address the nearest proxy actually saw.

    It is also the only entry a client cannot write: the proxy appends it *after* whatever
    the client sent.
    """
    assert forwarded_peer(CHAIN, hops=1) == "192.0.2.9"


def test_two_trusted_proxies_step_one_further_left():
    assert forwarded_peer(CHAIN, hops=2) == "198.51.100.4"


def test_a_client_supplied_prefix_cannot_be_reached_with_one_hop():
    """The spoof this counts hops to defeat.

    A caller sends `X-Forwarded-For: 1.2.3.4` hoping to be charged as somebody else. The
    proxy appends their real address, so the rightmost entry is still theirs.
    """
    assert forwarded_peer("1.2.3.4, 192.0.2.9", hops=1) == "192.0.2.9"


def test_a_chain_shorter_than_the_configured_hops_is_refused():
    """The request did not arrive the way the configuration says it does, so nothing in the
    header is worth believing. Falling back over-throttles; guessing would under-throttle."""
    assert forwarded_peer("192.0.2.9", hops=2) is None


def test_a_missing_header_is_refused_rather_than_invented():
    assert forwarded_peer(None, hops=1) is None
    assert forwarded_peer("", hops=1) is None


@pytest.mark.parametrize("value", ["not-an-address", "'; DROP TABLE users;--", "x" * 5000])
def test_an_entry_that_is_not_an_address_is_not_used_as_a_bucket_key(value):
    """Two reasons, and the second is the one that bites.

    A misconfigured hop count must land on the socket peer rather than on a string the
    caller chose. And the limiter tracks up to ten thousand keys — a caller who can put
    arbitrary text in that map can fill it, which is the memory exhaustion
    `MAX_TRACKED_KEYS` exists to bound.
    """
    assert forwarded_peer(f"192.0.2.9, {value}", hops=1) is None


def test_surrounding_whitespace_is_tolerated_because_proxies_write_it():
    assert forwarded_peer(" 1.2.3.4 ,  192.0.2.9 ", hops=1) == "192.0.2.9"


def test_ipv6_is_an_address():
    assert forwarded_peer("1.2.3.4, 2001:db8::1", hops=1) == "2001:db8::1"


# --- the same thing through the API ---------------------------------------------------------


def test_without_a_trusted_proxy_two_callers_share_one_bucket(api):
    """Not a bug — it is the correct reading of a header nobody has said to trust, and it is
    exactly what a deployed API does when `TRUSTED_PROXY_HOPS` is left unset."""
    api.set_quota("sessions", 1)

    first = api.post("/api/v1/session", headers={"X-Forwarded-For": "192.0.2.1"})
    second = api.post("/api/v1/session", headers={"X-Forwarded-For": "192.0.2.2"})

    assert first.status_code == 201
    assert second.status_code == 429


def test_behind_one_trusted_proxy_two_callers_get_their_own_buckets(api):
    """The reason the setting exists. On a managed platform every request arrives from the
    platform's address, so without this the eleventh visitor in fifteen minutes is refused a
    session and the product looks broken to everyone at once."""
    api.app.state.trusted_proxy_hops = 1
    api.set_quota("sessions", 1)

    first = api.post("/api/v1/session", headers={"X-Forwarded-For": "192.0.2.1"})
    second = api.post("/api/v1/session", headers={"X-Forwarded-For": "192.0.2.2"})
    again = api.post("/api/v1/session", headers={"X-Forwarded-For": "192.0.2.1"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert again.status_code == 429


def test_a_caller_behind_the_proxy_cannot_buy_a_second_bucket_with_a_header(api):
    """The attack the hop count defeats, end to end: the caller writes the left of the chain
    and the proxy writes the right, so both requests land in the same bucket."""
    api.app.state.trusted_proxy_hops = 1
    api.set_quota("sessions", 1)

    first = api.post("/api/v1/session", headers={"X-Forwarded-For": "10.0.0.1, 192.0.2.1"})
    second = api.post("/api/v1/session", headers={"X-Forwarded-For": "10.0.0.2, 192.0.2.1"})

    assert first.status_code == 201
    assert second.status_code == 429
