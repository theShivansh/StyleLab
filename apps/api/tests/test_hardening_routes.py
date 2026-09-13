"""The hardening added in S11, asserted through HTTP.

`test_ratelimit.py` proves the bucket arithmetic. This file proves the bucket is actually
*wired* — that the endpoints which spend money are the ones behind it, that the price of an
upload is the number of photographs rather than the number of requests, and that a refusal
comes back as the documented envelope with a header a client can act on.

The distinction matters because a limiter nobody called would pass every test in the other
file.
"""

from __future__ import annotations

import pytest

from tests.support import make_image


@pytest.fixture
def caller(api, stubs):
    """A session with the transport scripted to answer extractions successfully."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    return api.start_session()


def photo(name: str = "shirt.png", shade: int = 0):
    return ("images[]", (name, make_image(fmt="PNG", colour=(shade, 60, 90)), "image/png"))


def upload(api, caller, count: int = 1):
    files = [photo(f"shirt{index}.png", shade=index) for index in range(count)]
    return api.post("/api/v1/wardrobe/items", files=files, headers=caller.headers)


# --- the limit is wired to the endpoints that spend money -----------------------------------


def test_an_upload_over_the_limit_is_refused_with_the_documented_envelope(api, caller):
    api.set_quota("uploads", 1)

    assert upload(api, caller).status_code == 201
    refused = upload(api, caller)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "RATE_LIMITED"
    assert refused.json()["error"]["retryable"] is True
    # The message never says which quota. A caller learning that learns the shape of our
    # provider spend, and a user only ever needs to know to wait.
    assert "quota" not in refused.json()["error"]["message"].lower()


def test_the_refusal_carries_a_retry_after_a_client_can_act_on(api, caller):
    api.set_quota("uploads", 1, seconds=600)
    upload(api, caller)

    refused = upload(api, caller)

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) == 600


def test_an_upload_is_priced_per_photograph_not_per_request(api, caller):
    """The whole reason the limiter is a bucket rather than a counter.

    Three photographs in one POST are three vision calls. Priced per request, the cheapest
    way to drain a metered key would be to send them all at once — which is also exactly
    what the documented primary flow does.
    """
    api.set_quota("uploads", 3)

    assert upload(api, caller, count=3).status_code == 201
    assert upload(api, caller, count=1).status_code == 429


def test_re_analysis_draws_on_the_same_bucket_as_the_upload(api, caller, wait_for_job):
    """A retry is a provider call too.

    The upload queue offers a per-card retry, so a client that hit the upload limit could
    otherwise sit on `reanalyze` and keep spending — the cheapest possible bypass, reachable
    through a button in the product.
    """
    body = upload(api, caller).json()["items"][0]
    wait_for_job(caller.headers, body["job_id"])
    api.set_quota("uploads", 1)

    assert (
        api.post(
            f"/api/v1/wardrobe/items/{body['item_id']}/reanalyze", headers=caller.headers
        ).status_code
        == 202
    )
    refused = api.post(
        f"/api/v1/wardrobe/items/{body['item_id']}/reanalyze", headers=caller.headers
    )

    assert refused.status_code == 429


def test_composition_is_limited_separately_from_upload(api, caller):
    """Separate buckets, because the two cost different things.

    A shared one would mean a user who uploaded a full wardrobe could not then compose from
    it, which is the one sequence the product exists to perform.
    """
    api.set_quota("compositions", 1)
    api.set_quota("uploads", 24)

    assert upload(api, caller, count=3).status_code == 201
    assert api.post("/api/v1/outfits/compose", json={}, headers=caller.headers).status_code == 202
    assert api.post("/api/v1/outfits/compose", json={}, headers=caller.headers).status_code == 429


def test_new_sessions_are_limited_so_identities_are_not_an_unlimited_resource(api):
    """The limit that holds the other two up.

    Without it, a client that exhausts its upload quota simply asks for another identity —
    and with no authentication (blocker B15), asking is free.
    """
    api.set_quota("sessions", 2)

    assert api.post("/api/v1/session").status_code == 201
    assert api.post("/api/v1/session").status_code == 201
    assert api.post("/api/v1/session").status_code == 429


def test_one_user_hitting_a_limit_does_not_throttle_another(api, stubs):
    api.transport_double.default = stubs.fixture("extraction_success.json")
    api.set_quota("uploads", 1)
    first = api.start_session()
    second = api.start_session()

    upload(api, first)

    assert upload(api, first).status_code == 429
    assert upload(api, second).status_code == 201


def test_reading_a_wardrobe_is_never_rate_limited(api, caller, wait_for_job):
    """Reads cost a database query, and a user reviewing their wardrobe makes a lot of them.

    A limit here would produce a product that refuses to show somebody their own clothes, to
    defend against an attacker who could have requested the landing page just as cheaply.
    """
    body = upload(api, caller).json()["items"][0]
    wait_for_job(caller.headers, body["job_id"])
    api.set_quota("uploads", 1)
    api.set_quota("compositions", 1)

    for _ in range(30):
        assert api.get("/api/v1/wardrobe/items", headers=caller.headers).status_code == 200


# --- request ids ------------------------------------------------------------------------------


def test_every_response_carries_a_request_id(api):
    response = api.get("/api/v1/ping")

    assert response.headers["X-Request-ID"].startswith("req_")


def test_an_error_body_carries_the_same_id_as_the_header(api, caller):
    """The point of the field: the user-facing messages are deliberately vague, so the id is
    the only thing connecting a user's report to a log line."""
    api.set_quota("uploads", 1)
    upload(api, caller)

    refused = upload(api, caller)

    assert refused.json()["error"]["request_id"] == refused.headers["X-Request-ID"]


def test_a_caller_supplied_id_is_kept_so_a_trace_survives_the_hop(api):
    response = api.get("/api/v1/ping", headers={"X-Request-ID": "web-01H9Z.trace:7"})

    assert response.headers["X-Request-ID"] == "web-01H9Z.trace:7"


def test_a_hostile_request_id_is_replaced_rather_than_echoed(api):
    """It is written into a response header and into logs.

    Echoing an unvalidated header into both is a header-injection primitive on one side and
    log forging on the other — a newline and the attacker writes their own log line, which
    is how an audit trail stops being evidence.
    """
    for hostile in ["a\r\nX-Evil: 1", "x" * 200, "trace id with spaces", "<script>"]:
        response = api.get("/api/v1/ping", headers={"X-Request-ID": hostile})

        assert response.headers["X-Request-ID"].startswith("req_")


def test_a_request_id_is_not_derived_from_anything_the_caller_sent(api, caller):
    """Two identical requests get different ids, so the id carries no information about the
    request — which is what lets a 404 include one without becoming an oracle."""
    first = api.get("/api/v1/wardrobe/items/item_nope", headers=caller.headers)
    second = api.get("/api/v1/wardrobe/items/item_nope", headers=caller.headers)

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
