"""The HTTP surface, end to end.

Real routes, real storage, real database, real adapters — only the transport is a double.
Background analysis runs on the app's own event loop and is waited on by polling
`GET /jobs/{id}`, which is how the browser does it.

The recurring assertion is **404, never 403**. It appears in almost every test here because
it is the one mistake that would be invisible in normal use: everything would work, and the
API would confirm the existence of other users' garments to anyone who asked.
"""

from __future__ import annotations

import pytest

from tests.support import make_image

PNG = ("images[]", ("shirt.png", make_image(fmt="PNG"), "image/png"))


@pytest.fixture
def caller(api, stubs):
    """A session with the transport scripted to answer extractions successfully."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    return api.start_session()


def upload(api, caller, *files, hints=None):
    payload = list(files) or [PNG]
    data = {"category_hints[]": hints} if hints else None
    return api.post("/api/v1/wardrobe/items", files=payload, data=data, headers=caller.headers)


def ready_item(api, caller, wait_for_job, *, shade: int = 0):
    """One garment, uploaded and analysed.

    `shade` varies the pixels. Two calls with the same shade upload byte-identical
    photographs and the checksum cache correctly hands back the first item — which is the
    right behaviour and the wrong setup for a test that needs two distinct garments.
    """
    photo = (
        "images[]",
        (f"shirt{shade}.png", make_image(fmt="PNG", colour=(shade, 60, 90)), "image/png"),
    )
    body = upload(api, caller, photo).json()["items"][0]
    job = wait_for_job(caller.headers, body["job_id"])
    assert job["status"] == "completed", job
    return body["item_id"]


# --- the session seam ---------------------------------------------------------------------


def test_a_session_hands_back_a_token_and_creates_its_user(api):
    response = api.post("/api/v1/session")

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"].startswith("user_")
    assert body["token"]
    assert body["expires_in"] > 0


def test_session_creation_accepts_no_body_and_cannot_be_asked_for_a_user(api):
    """A `POST /session` that took a `user_id` would be a login with no credential."""
    response = api.post("/api/v1/session", json={"user_id": "user_someone_else"})

    assert response.status_code == 201
    assert response.json()["user_id"] != "user_someone_else"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer nonsense"},
        {"Authorization": "Basic abc"},
        {"Authorization": ""},
    ],
)
def test_every_wardrobe_route_needs_a_token_this_api_signed(api, headers):
    for method, path in [
        ("GET", "/api/v1/wardrobe/items"),
        ("GET", "/api/v1/wardrobe/items/item_1"),
        ("PATCH", "/api/v1/wardrobe/items/item_1"),
        ("DELETE", "/api/v1/wardrobe/items/item_1"),
        ("POST", "/api/v1/wardrobe/items/item_1/reanalyze"),
        ("GET", "/api/v1/wardrobe/items/item_1/extractions"),
        ("GET", "/api/v1/jobs/job_1"),
    ]:
        body = {} if method == "PATCH" else None
        response = api.request(method, path, headers=headers, json=body)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
        assert response.json()["error"]["code"]


def test_a_forged_token_cannot_name_another_user(api, caller, wait_for_job):
    """The whole point of signing identity rather than accepting it.

    A token whose payload says `user_victim` but which we did not sign is refused, so the
    caller cannot pick a wardrobe to read.
    """
    import base64
    import json
    import time

    item_id = ready_item(api, caller, wait_for_job)

    claims = {"sub": caller.user_id, "prp": "session", "exp": int(time.time()) + 999}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    forged = f"{body}.not-a-real-signature"

    response = api.get(
        f"/api/v1/wardrobe/items/{item_id}", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


# --- upload -------------------------------------------------------------------------------


def test_an_upload_returns_a_job_per_image(api, caller):
    response = upload(
        api,
        caller,
        ("images[]", ("a.png", make_image(fmt="PNG"), "image/png")),
        ("images[]", ("b.png", make_image(fmt="PNG", colour=(9, 9, 9)), "image/png")),
    )

    assert response.status_code == 201
    items = response.json()["items"]
    assert len(items) == 2
    assert {item["status"] for item in items} == {"analyzing"}
    assert len({item["job_id"] for item in items}) == 2, "one job each, never one per batch"


def test_one_refused_image_does_not_fail_the_request(api, caller):
    """Partial success is a 201 with a per-file refusal, not a 4xx for the batch."""
    response = upload(
        api,
        caller,
        ("images[]", ("good.png", make_image(fmt="PNG"), "image/png")),
        ("images[]", ("bad.pdf", b"%PDF-1.7\n" + b"0" * 2048, "image/png")),
    )

    assert response.status_code == 201
    items = response.json()["items"]
    assert items[0]["status"] == "analyzing"
    assert items[1]["status"] == "rejected"
    assert items[1]["error"]["code"] == "UNSUPPORTED_FORMAT"
    assert items[1]["error"]["message"]
    assert items[1]["item_id"] is None


def test_a_category_hint_is_carried_positionally(api, caller, wait_for_job):
    response = upload(
        api,
        caller,
        ("images[]", ("a.png", make_image(fmt="PNG"), "image/png")),
        hints=["outerwear"],
    )
    item_id = response.json()["items"][0]["item_id"]

    item = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()
    assert item["category"] == "outerwear"


def test_an_unparseable_hint_does_not_cost_the_upload(api, caller):
    """The photograph is the payload; the hint was optional."""
    response = upload(
        api, caller, ("images[]", ("a.png", make_image(fmt="PNG"), "image/png")), hints=["hat"]
    )

    assert response.status_code == 201
    assert response.json()["items"][0]["status"] == "analyzing"


# --- the job endpoint ---------------------------------------------------------------------


def test_a_job_reports_named_stages_and_finishes(api, caller, wait_for_job):
    body = upload(api, caller).json()["items"][0]

    job = wait_for_job(caller.headers, body["job_id"])

    assert job["status"] == "completed"
    assert job["type"] == "analyze_item"
    assert job["stage"] == "ready"
    assert job["progress"] == 1.0


def test_another_users_job_is_not_observable(api, caller, wait_for_job):
    body = upload(api, caller).json()["items"][0]
    wait_for_job(caller.headers, body["job_id"])

    intruder = api.start_session()
    response = api.get(f"/api/v1/jobs/{body['job_id']}", headers=intruder.headers)

    assert response.status_code == 404


def test_a_failing_extraction_fails_one_job_with_its_reason(api, stubs, wait_for_job):
    from app.adapters.provider_errors import ProviderTimeoutError

    api.transport_double.default = ProviderTimeoutError("slow")
    caller = api.start_session()

    body = upload(api, caller).json()["items"][0]
    job = wait_for_job(caller.headers, body["job_id"])

    assert job["status"] == "failed"
    assert job["error"]["code"] == "PROVIDER_TIMEOUT"
    assert job["error"]["retryable"] is True

    # And the card still exists, marked failed, rather than the file appearing to vanish.
    item = api.get(f"/api/v1/wardrobe/items/{body['item_id']}", headers=caller.headers).json()
    assert item["status"] == "failed"


# --- reading the wardrobe -----------------------------------------------------------------


def test_a_read_item_matches_the_documented_shape(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)

    item = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()

    assert set(item) == {
        "item_id",
        "status",
        "category",
        "subcategory",
        "color_primary",
        "color_secondary",
        "pattern",
        "material_guess",
        "fit",
        "formality",
        "season_tags",
        "occasion_tags",
        "style_tags",
        "field_confidence",
        "corrected_fields",
        "quality_warnings",
        "image_url",
    }
    assert "user_id" not in item, "ownership is a server-side property"
    assert item["status"] == "ready"
    assert item["material_guess"] == "cotton"
    assert item["field_confidence"]["material_guess"] == 0.41


def test_the_wardrobe_lists_only_the_callers_garments(api, caller, wait_for_job):
    ready_item(api, caller, wait_for_job)

    intruder = api.start_session()
    assert api.get("/api/v1/wardrobe/items", headers=intruder.headers).json()["items"] == []
    assert len(api.get("/api/v1/wardrobe/items", headers=caller.headers).json()["items"]) == 1


def test_the_wardrobe_shows_items_that_are_still_analysing(api, caller):
    """A card must exist before the reading does, or the user's file seems to vanish.

    The analysis is **held** until the assertion has been made. The first version uploaded and
    then listed, and relied on the listing winning a race against a mock model that answers in
    microseconds. It usually did; under load it did not, and S13b watched a full run go red on
    exactly this test while the suite shared a machine with a live browser session. A test that
    asserts a transient state has to create the state, not hope to catch it.
    """
    import asyncio
    import threading

    released = threading.Event()

    async def hold(_schema: object) -> None:
        # A thread-safe flag polled from the app's loop: an `asyncio.Event` set from this test
        # thread would be touched from outside the loop that awaits it.
        while not released.is_set():
            await asyncio.sleep(0.01)

    api.transport_double.before = hold
    try:
        upload(api, caller)

        items = api.get("/api/v1/wardrobe/items", headers=caller.headers).json()["items"]
        assert [item["status"] for item in items] == ["analyzing"]
    finally:
        released.set()


def test_another_users_item_answers_404_and_not_403(api, caller, wait_for_job):
    """403 would confirm the item exists and belongs to somebody."""
    item_id = ready_item(api, caller, wait_for_job)
    intruder = api.start_session()

    for method, suffix in [("GET", ""), ("DELETE", ""), ("GET", "/extractions")]:
        response = api.request(
            method, f"/api/v1/wardrobe/items/{item_id}{suffix}", headers=intruder.headers
        )
        assert response.status_code == 404, f"{method}{suffix}"
        assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_an_item_that_never_existed_answers_the_same_as_one_owned_by_someone_else(
    api, caller, wait_for_job
):
    """Indistinguishable, which is the requirement.

    S11 added a per-request `request_id` to the envelope, which made the two bodies stop
    being byte-identical without making them distinguishable — so the comparison names what
    it means instead. The stricter form is the better test anyway: it says the id is the
    *only* thing that may differ, which also pins that the id carries nothing about the
    item. An id derived from the path would satisfy the old assertion and leak.
    """
    item_id = ready_item(api, caller, wait_for_job)
    intruder = api.start_session()

    theirs = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=intruder.headers)
    fictional = api.get("/api/v1/wardrobe/items/item_does_not_exist", headers=intruder.headers)

    assert theirs.status_code == fictional.status_code == 404

    identifying = {"request_id"}
    assert {k: v for k, v in theirs.json()["error"].items() if k not in identifying} == {
        k: v for k, v in fictional.json()["error"].items() if k not in identifying
    }
    # Not derived from what was asked for, in either direction.
    assert item_id not in theirs.json()["error"]["request_id"]
    assert theirs.json()["error"]["request_id"] != fictional.json()["error"]["request_id"]


# --- images -------------------------------------------------------------------------------


def test_the_image_url_serves_the_stored_photograph(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    item = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()

    # No session header: the URL is a capability, which is what makes `<img src>` work.
    response = api.get(item["image_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"\xff\xd8\xff")


def test_an_image_url_carries_no_query_string(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    item = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()

    assert "?" not in item["image_url"]


def test_a_tampered_image_token_serves_nothing(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    url = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()["image_url"]

    head, _, token = url.rpartition("/")

    assert api.get(f"{head}/{token[:-4]}xxxx").status_code == 404
    assert api.get(f"{head}/not-a-token").status_code == 404


def test_a_valid_token_cannot_be_pointed_at_a_different_asset(api, caller, wait_for_job):
    """The token is authority for the asset it names, not for the path it arrives on."""
    first = ready_item(api, caller, wait_for_job, shade=10)
    second = ready_item(api, caller, wait_for_job, shade=200)
    assert first != second, "two distinct garments, or there is nothing to point elsewhere"

    def image_url(item_id: str) -> str:
        return api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()[
            "image_url"
        ]

    _, _, token = image_url(first).rpartition("/")
    other_asset = image_url(second).rsplit("/", 2)[-2]

    assert api.get(f"/api/v1/assets/{other_asset}/{token}").status_code == 404


def test_a_session_token_is_not_an_image_token(api, caller, wait_for_job):
    """Why the purpose is signed into the payload."""
    item_id = ready_item(api, caller, wait_for_job)
    url = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()["image_url"]
    asset_path = url.rpartition("/")[0]
    session_token = caller.headers["Authorization"].removeprefix("Bearer ")

    assert api.get(f"{asset_path}/{session_token}").status_code == 404


# --- correction ---------------------------------------------------------------------------


def test_a_correction_is_recorded_and_drops_the_fields_confidence(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)

    response = api.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        json={"color_primary": "black"},
        headers=caller.headers,
    )

    assert response.status_code == 200
    item = response.json()
    assert item["color_primary"] == "black"
    assert "color_primary" in item["corrected_fields"]
    assert "color_primary" not in item["field_confidence"]


def test_a_field_the_user_cannot_correct_is_refused_rather_than_ignored(api, caller, wait_for_job):
    """Silently dropping it would show a screen saying the correction saved when it did not."""
    item_id = ready_item(api, caller, wait_for_job)

    response = api.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        json={"field_confidence": {"category": 1.0}},
        headers=caller.headers,
    )

    assert response.status_code == 422
    assert "field_confidence" in response.json()["error"]["message"]


def test_an_invalid_value_for_a_correctable_field_is_refused_without_echoing_it(
    api, caller, wait_for_job
):
    item_id = ready_item(api, caller, wait_for_job)

    response = api.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        json={"formality": "extremely elegant"},
        headers=caller.headers,
    )

    assert response.status_code == 422
    assert "formality" in response.json()["error"]["message"]
    assert "extremely elegant" not in response.json()["error"]["message"]


def test_an_empty_patch_is_refused(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    response = api.patch(
        f"/api/v1/wardrobe/items/{item_id}", json={}, headers=caller.headers
    )
    assert response.status_code == 422


def test_correcting_another_users_item_answers_404(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    intruder = api.start_session()

    response = api.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        json={"color_primary": "black"},
        headers=intruder.headers,
    )
    assert response.status_code == 404


# --- re-analysis --------------------------------------------------------------------------


def test_reanalyze_returns_a_job_without_blocking(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)

    response = api.post(
        f"/api/v1/wardrobe/items/{item_id}/reanalyze", headers=caller.headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert wait_for_job(caller.headers, body["job_id"])["status"] == "completed"


def test_reanalyze_preserves_a_correction_through_the_http_surface(api, caller, wait_for_job):
    """AI-EVAL-CASES Case 13, over HTTP. The model says navy again; the user said black."""
    item_id = ready_item(api, caller, wait_for_job)
    api.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        json={"color_primary": "black"},
        headers=caller.headers,
    )

    job_id = api.post(
        f"/api/v1/wardrobe/items/{item_id}/reanalyze", headers=caller.headers
    ).json()["job_id"]
    wait_for_job(caller.headers, job_id)

    item = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()
    assert item["color_primary"] == "black"
    assert item["subcategory"] == "oxford shirt", "untouched fields still refresh"


def test_reanalyzing_another_users_item_answers_404(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    intruder = api.start_session()

    response = api.post(
        f"/api/v1/wardrobe/items/{item_id}/reanalyze", headers=intruder.headers
    )
    assert response.status_code == 404


# --- deletion -----------------------------------------------------------------------------


def test_deleting_an_item_removes_it_from_the_wardrobe(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)

    response = api.delete(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers)

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "affected_outfits": []}
    assert api.get("/api/v1/wardrobe/items", headers=caller.headers).json()["items"] == []
    assert api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).status_code == 404


def test_deleting_reports_the_outfits_it_broke(api, caller, wait_for_job):
    """AI-EVAL-CASES Case 14. The user composed that look; they get told what changed."""
    from app.repositories.wardrobe import WardrobeRepository

    item_id = ready_item(api, caller, wait_for_job)

    with api.app.state.sessions() as session:
        WardrobeRepository(session).save_outfit(
            caller.user_id,
            outfit_id="outfit_7",
            name="Quiet Weekday",
            occasion="college",
            item_ids=[item_id],
        )
        session.commit()

    response = api.delete(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers)

    assert response.json()["affected_outfits"] == ["outfit_7"]

    with api.app.state.sessions() as session:
        outfit = WardrobeRepository(session).get_outfit(caller.user_id, "outfit_7")
    assert outfit.status == "incomplete", "never a silent gap"


def test_deleting_twice_answers_404_the_second_time(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)

    path = f"/api/v1/wardrobe/items/{item_id}"
    assert api.delete(path, headers=caller.headers).status_code == 200
    assert api.delete(path, headers=caller.headers).status_code == 404


def test_a_deleted_items_image_stops_being_served(api, caller, wait_for_job):
    item_id = ready_item(api, caller, wait_for_job)
    url = api.get(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers).json()["image_url"]
    assert api.get(url).status_code == 200

    api.delete(f"/api/v1/wardrobe/items/{item_id}", headers=caller.headers)

    # The token has not expired; the asset is soft-deleted and the scoped read no longer
    # finds it. A live capability outliving the user's deletion would make deletion a lie.
    assert api.get(url).status_code == 404


# --- the audit trail ----------------------------------------------------------------------


def test_the_extractions_endpoint_shows_what_the_model_returned(api, caller, wait_for_job):
    """The "show me the grounding" moment in the demo."""
    item_id = ready_item(api, caller, wait_for_job)

    body = api.get(
        f"/api/v1/wardrobe/items/{item_id}/extractions", headers=caller.headers
    ).json()

    assert body["item_id"] == item_id
    assert len(body["extractions"]) == 1
    row = body["extractions"][0]
    assert row["provider"] == "groq"
    assert row["schema_valid"] is True
    assert "oxford shirt" in row["raw_output"]
    assert row["latency_ms"] >= 0


def test_the_extractions_endpoint_shows_rejections_too(api, stubs, wait_for_job):
    api.transport_double.default = stubs.fixture("extraction_malformed.txt")
    caller = api.start_session()

    body = upload(api, caller).json()["items"][0]
    wait_for_job(caller.headers, body["job_id"])

    rows = api.get(
        f"/api/v1/wardrobe/items/{body['item_id']}/extractions", headers=caller.headers
    ).json()["extractions"]

    assert len(rows) == 2
    assert all(row["schema_valid"] is False for row in rows)
    assert all(row["rejected_reason"] for row in rows)


def test_re_uploading_the_same_photograph_returns_the_same_item(api, caller, wait_for_job):
    """The checksum cache, over HTTP. A re-pick is free and does not duplicate the card."""
    first = ready_item(api, caller, wait_for_job, shade=42)
    calls_so_far = len(api.transport_double.calls)

    second = ready_item(api, caller, wait_for_job, shade=42)

    assert second == first
    assert len(api.transport_double.calls) == calls_so_far, "no second extraction"
    assert len(api.get("/api/v1/wardrobe/items", headers=caller.headers).json()["items"]) == 1
