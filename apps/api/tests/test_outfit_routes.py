"""Result and swap, over the real HTTP surface.

Real routes, real database, real domain, real adapters — only the transport is a double, so
the prompt construction, the schema parse, the ownership re-validation and the scoring all
run exactly as they do live.

Two properties are asserted over and over, because both are invisible when they break:

* **404, never 403.** Another user's outfit must read exactly like one that never existed.
* **One slot changes, the rest stay still.** Not as a feeling — as the item ids of the
  untouched slots being identical before and after.
"""

from __future__ import annotations

import json

import pytest

from app.config import get_settings
from tests.support import make_image

ROLES = ("top", "bottom", "footwear")


def _photo(shade: int) -> tuple[str, tuple[str, bytes, str]]:
    """A distinct photograph. Distinct because the checksum cache is doing its job: two
    byte-identical uploads correctly produce one garment, which is the wrong wardrobe for
    a test that needs three."""
    return (
        "images[]",
        (f"g{shade}.png", make_image(fmt="PNG", colour=(20 + shade * 40, 60, 90)), "image/png"),
    )


def _upload_ready(api, caller, wait_for_job, shade: int, role: str) -> str:
    """One garment, analysed, then corrected into the role this test needs.

    The correction is how the roles are set: the scripted extraction reads every photograph
    as a top, and `PATCH` is the documented way a user settles a field. It also means the
    wardrobe under test contains items whose category is user-owned rather than model-owned,
    which is the more interesting case.
    """
    body = api.post(
        "/api/v1/wardrobe/items", files=[_photo(shade)], headers=caller.headers
    ).json()["items"][0]
    assert wait_for_job(caller.headers, body["job_id"])["status"] == "completed"

    if role != "top":
        patched = api.patch(
            f"/api/v1/wardrobe/items/{body['item_id']}",
            json={"category": role},
            headers=caller.headers,
        )
        assert patched.status_code == 200, patched.text
    return str(body["item_id"])


@pytest.fixture
def wardrobe(api, stubs, wait_for_job):
    """A caller owning exactly one of each core role — the minimum that composes."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    caller = api.start_session()
    items = {
        role: _upload_ready(api, caller, wait_for_job, shade, role)
        for shade, role in enumerate(ROLES)
    }
    return caller, items


def script_advice(api, *, item_ids, **overrides) -> None:
    """Script the text model with one advisory response naming these ids."""
    payload: dict = {
        "outfit": {
            "item_ids": list(item_ids),
            "name": "Quiet Navy",
            "occasion": "everyday",
            "match_score": 91,
        },
        "rationale": ["The palette holds together."],
        "confidence": 0.84,
        "pro_tips": [
            {"tip": "Half-tuck the shirt to shorten the torso line.", "type": "proportion"}
        ],
        "budget_tricks": [],
        "wardrobe_gaps": [],
        "trend_notes": [],
        "missing_roles": [],
        "degradation_level": 1,
    }
    payload.update(overrides)
    api.transport_double.script[get_settings().groq_text_model] = json.dumps(payload)


def compose(api, caller, wait_for_job, **body) -> dict:
    started = api.post(
        "/api/v1/outfits/compose", json=body or {"occasion": "everyday"}, headers=caller.headers
    )
    assert started.status_code == 202, started.text
    return wait_for_job(caller.headers, started.json()["job_id"])


def composed_outfit(api, caller, wait_for_job, items) -> dict:
    script_advice(api, item_ids=list(items.values()))
    job = compose(api, caller, wait_for_job)
    assert job["status"] == "completed", job
    outfit = api.get(f"/api/v1/outfits/{job['result_id']}", headers=caller.headers)
    assert outfit.status_code == 200, outfit.text
    return outfit.json()


# --- composing -----------------------------------------------------------------------------


def test_composing_returns_a_job_before_anything_reaches_a_model(api, wardrobe):
    """202 and a job id. The route cannot have waited for the advisor: it has no reference
    to one, which is the same structural guarantee the upload route holds."""
    caller, items = wardrobe
    script_advice(api, item_ids=list(items.values()))
    before = len(api.transport_double.calls)

    response = api.post(
        "/api/v1/outfits/compose", json={"occasion": "everyday"}, headers=caller.headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "compose_outfit"
    assert body["status"] == "queued"
    assert body["result_id"] is None
    assert len(api.transport_double.calls) == before


def test_the_job_reports_composition_stages_not_extraction_ones(api, wardrobe, wait_for_job):
    """The two vocabularies are separate on purpose. A composition reporting "finding
    garment" would be naming work it is not doing (CLAUDE.md motion rules)."""
    caller, items = wardrobe
    script_advice(api, item_ids=list(items.values()))

    job = compose(api, caller, wait_for_job)

    assert job["stage"] == "ready"
    assert job["progress"] == 1.0


def test_a_composed_look_comes_back_with_every_slot_resolved(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    assert outfit["status"] == "ready"
    assert [slot["role"] for slot in outfit["slots"]] == list(ROLES)
    assert {slot["item"]["item_id"] for slot in outfit["slots"]} == set(items.values())
    assert all(slot["item"]["image_url"] for slot in outfit["slots"])
    assert outfit["missing_roles"] == []


def test_the_score_shown_is_recomputed_not_the_one_the_advisor_asserted(
    api, wardrobe, wait_for_job
):
    """Step 9 of the orchestration, through the wire. The advisor said 91."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    assert outfit["match_score"] != 91
    assert 0 <= outfit["match_score"] <= 100
    # The name is the advisor's to write; the number is not.
    assert outfit["name"] == "Quiet Navy"


def test_the_advisory_content_survives_to_the_result_screen(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    assert outfit["pro_tips"][0]["tip"].startswith("Half-tuck")
    assert outfit["confidence"] == 0.84
    assert outfit["degradation_level"] == 1


def test_an_advisor_naming_an_unowned_id_degrades_rather_than_serving_it(
    api, wardrobe, wait_for_job
):
    """Case 01 through the whole stack. The look still arrives; it is built by the ranker
    over the same candidates, and it says so with a degradation level."""
    caller, items = wardrobe
    script_advice(api, item_ids=[items["top"], items["bottom"], "item_not_yours"])

    job = compose(api, caller, wait_for_job)
    outfit = api.get(f"/api/v1/outfits/{job['result_id']}", headers=caller.headers).json()

    assert job["status"] == "completed"
    assert outfit["degradation_level"] == 4
    assert {slot["item_id"] for slot in outfit["slots"]} <= set(items.values())


def test_an_insufficient_wardrobe_is_a_completed_job_naming_the_gap(
    api, stubs, wait_for_job
):
    """Rung 5, and deliberately not a failure. A `failed` job offers a retry, and retrying
    cannot conjure a pair of trousers."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    caller = api.start_session()
    _upload_ready(api, caller, wait_for_job, 0, "top")

    job = compose(api, caller, wait_for_job)

    assert job["status"] == "completed"
    assert job["result_id"] is None
    assert job["result"]["missing_roles"] == ["bottom", "footwear"]
    assert job["result"]["wardrobe_gaps"]
    assert "error" not in job


def test_composing_never_asks_the_model_when_a_role_is_empty(api, stubs, wait_for_job):
    """There is nothing to deliberate about, and paying for a crew run to be told what a
    count already told us is waste."""
    api.transport_double.default = stubs.fixture("extraction_success.json")
    caller = api.start_session()
    _upload_ready(api, caller, wait_for_job, 0, "top")
    text_model = get_settings().groq_text_model

    compose(api, caller, wait_for_job)

    assert text_model not in api.transport_double.models_called


def test_a_compose_request_cannot_name_the_items_to_use(api, wardrobe, wait_for_job):
    """Candidates are retrieved server-side. An accepted `item_ids` would move the ownership
    boundary into the request body."""
    caller, items = wardrobe
    script_advice(api, item_ids=list(items.values()))

    response = api.post(
        "/api/v1/outfits/compose",
        json={"occasion": "everyday", "item_ids": ["item_not_yours"]},
        headers=caller.headers,
    )
    job = wait_for_job(caller.headers, response.json()["job_id"])
    outfit = api.get(f"/api/v1/outfits/{job['result_id']}", headers=caller.headers).json()

    assert {slot["item_id"] for slot in outfit["slots"]} == set(items.values())


# --- alternatives ----------------------------------------------------------------------------


def test_alternatives_are_owned_items_of_that_role_best_first(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")
    another = _upload_ready(api, caller, wait_for_job, 9, "footwear")

    body = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}/alternatives",
        params={"role": "footwear"},
        headers=caller.headers,
    ).json()

    offered = [entry["item"]["item_id"] for entry in body["alternatives"]]
    assert set(offered) == {spare, another}
    # The garment already in the slot is not offered as an alternative to itself.
    assert items["footwear"] not in offered
    assert body["current_item_id"] == items["footwear"]
    assert body["gap"] is None
    scores = [entry["match_score"] for entry in body["alternatives"]]
    assert scores == sorted(scores, reverse=True)


def test_alternatives_are_scored_in_the_look_not_on_their_own(api, wardrobe, wait_for_job):
    """"Compatible" is measured against the pieces actually on screen. Each candidate
    reports what the *look* would score with it in, and the delta from where it stands."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    _upload_ready(api, caller, wait_for_job, 7, "footwear")

    body = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}/alternatives",
        params={"role": "footwear"},
        headers=caller.headers,
    ).json()

    entry = body["alternatives"][0]
    assert entry["match_score"] == outfit["match_score"] + entry["delta"]


def test_a_slot_with_nothing_else_to_offer_names_the_gap_rather_than_erroring(
    api, wardrobe, wait_for_job
):
    """Empty is a valid answer (prompts/06). A user who owns one pair of shoes has a small
    wardrobe, not a broken request."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    response = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}/alternatives",
        params={"role": "footwear"},
        headers=caller.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["alternatives"] == []
    assert body["gap"]["category"] == "footwear"
    assert body["gap"]["generic_description"]
    # Generic, and no way to buy it. The product sells nothing.
    assert "http" not in body["gap"]["generic_description"]


def test_alternatives_for_a_role_the_look_does_not_have(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    response = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}/alternatives",
        params={"role": "outerwear"},
        headers=caller.headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROLE_NOT_IN_OUTFIT"


# --- swapping --------------------------------------------------------------------------------


def test_a_swap_changes_one_slot_and_leaves_the_others_identical(api, wardrobe, wait_for_job):
    """The signature product moment, asserted as data rather than as a feeling."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")
    before = {slot["role"]: slot["item_id"] for slot in outfit["slots"]}

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": spare},
        headers=caller.headers,
    )

    assert response.status_code == 200, response.text
    after = {slot["role"]: slot["item_id"] for slot in response.json()["slots"]}
    assert after["footwear"] == spare
    assert after["top"] == before["top"]
    assert after["bottom"] == before["bottom"]
    # Slot order is the rank on the join row, and it does not move when one row is rewritten.
    assert [s["role"] for s in response.json()["slots"]] == [s["role"] for s in outfit["slots"]]


def test_a_swap_needs_no_provider_call(api, wardrobe, wait_for_job):
    """Swap is a scoped read, a pure recompute and one row rewritten. Routing it through a
    model would make the fastest interaction in the product the slowest."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")
    before = len(api.transport_double.calls)

    api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": spare},
        headers=caller.headers,
    )

    assert len(api.transport_double.calls) == before


def test_a_swap_rewrites_the_words_that_described_the_old_look(api, wardrobe, wait_for_job):
    """A tip about the shoe the user just swapped out is the visual state disagreeing with
    the wardrobe state, in prose."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")
    assert outfit["pro_tips"], "the original look was narrated"

    swapped = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": spare},
        headers=caller.headers,
    ).json()

    assert swapped["pro_tips"] == []
    assert any("recomputed" in line.lower() for line in swapped["rationale"])
    assert swapped["rationale"] != outfit["rationale"]


def test_a_swap_rescores_the_look(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")

    swapped = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": spare},
        headers=caller.headers,
    ).json()

    reread = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}", headers=caller.headers
    ).json()
    assert 0 <= swapped["match_score"] <= 100
    # The persisted score and the returned one are the same number, so a reload cannot
    # disagree with what the user just saw.
    assert reread["match_score"] == swapped["match_score"]


def test_a_garment_of_the_wrong_role_cannot_fill_a_slot(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": items["top"]},
        headers=caller.headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROLE_MISMATCH"


def test_swapping_in_the_garment_already_there_is_a_no_op(api, wardrobe, wait_for_job):
    """The second tap on the item you just chose should do nothing, not report a problem."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": items["footwear"]},
        headers=caller.headers,
    )

    assert response.status_code == 200
    assert response.json()["match_score"] == outfit["match_score"]
    assert response.json()["rationale"] == outfit["rationale"]


def test_a_swap_request_missing_its_fields_is_refused_without_a_stack_trace(
    api, wardrobe, wait_for_job
):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap", json={}, headers=caller.headers
    )

    assert response.status_code == 422
    assert "error" in response.json()


# --- deletion, and the repair path ------------------------------------------------------------


def test_deleting_a_garment_makes_its_look_incomplete_rather_than_short(
    api, wardrobe, wait_for_job
):
    """Case 14. The slot keeps its place with no garment in it, so the screen can say which
    piece went missing and offer a swap for that role."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    deleted = api.delete(
        f"/api/v1/wardrobe/items/{items['bottom']}", headers=caller.headers
    ).json()
    reread = api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}", headers=caller.headers
    ).json()

    assert deleted["affected_outfits"] == [outfit["outfit_id"]]
    assert reread["status"] == "incomplete"
    assert reread["missing_roles"] == ["bottom"]
    slots = {slot["role"]: slot for slot in reread["slots"]}
    assert slots["bottom"]["item"] is None
    assert slots["top"]["item"] is not None


def test_a_swap_repairs_an_incomplete_look(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    api.delete(f"/api/v1/wardrobe/items/{items['bottom']}", headers=caller.headers)
    replacement = _upload_ready(api, caller, wait_for_job, 5, "bottom")

    swapped = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "bottom", "replacement_item_id": replacement},
        headers=caller.headers,
    ).json()

    assert swapped["status"] == "ready"
    assert swapped["missing_roles"] == []
    assert {slot["role"]: slot["item_id"] for slot in swapped["slots"]}["bottom"] == replacement


def test_a_deleted_garment_cannot_be_swapped_back_in(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    spare = _upload_ready(api, caller, wait_for_job, 7, "footwear")
    api.delete(f"/api/v1/wardrobe/items/{spare}", headers=caller.headers)

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": spare},
        headers=caller.headers,
    )

    assert response.status_code == 404


# --- saving -------------------------------------------------------------------------------------


def test_saving_a_look_is_idempotent(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    path = f"/api/v1/outfits/{outfit['outfit_id']}/save"

    first = api.post(path, headers=caller.headers)
    second = api.post(path, headers=caller.headers)
    reread = api.get(f"/api/v1/outfits/{outfit['outfit_id']}", headers=caller.headers).json()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert reread["saved"] is True


def test_an_unsaved_look_says_so(api, wardrobe, wait_for_job):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    assert outfit["saved"] is False


# --- ownership ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer nonsense"}, {"Authorization": "Basic abc"}],
)
def test_every_outfit_route_needs_a_token_this_api_signed(api, headers):
    for method, path in [
        ("POST", "/api/v1/outfits/compose"),
        ("GET", "/api/v1/outfits/outfit_1"),
        ("GET", "/api/v1/outfits/outfit_1/alternatives?role=top"),
        ("POST", "/api/v1/outfits/outfit_1/swap"),
        ("POST", "/api/v1/outfits/outfit_1/save"),
    ]:
        response = api.request(method, path, headers=headers, json={})
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"


def test_another_users_look_is_indistinguishable_from_one_that_never_existed(
    api, wardrobe, wait_for_job
):
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)
    stranger = api.start_session()

    for method, path, body in [
        ("GET", f"/api/v1/outfits/{outfit['outfit_id']}", None),
        ("GET", f"/api/v1/outfits/{outfit['outfit_id']}/alternatives?role=top", None),
        (
            "POST",
            f"/api/v1/outfits/{outfit['outfit_id']}/swap",
            {"role": "top", "replacement_item_id": items["top"]},
        ),
        ("POST", f"/api/v1/outfits/{outfit['outfit_id']}/save", None),
    ]:
        response = api.request(method, path, headers=stranger.headers, json=body)
        assert response.status_code == 404, f"{method} {path} answered {response.status_code}"
        # Not "forbidden", which would confirm the look is real and somebody's.
        assert "403" not in response.text


def test_a_swap_cannot_reach_another_users_garment(api, wardrobe, wait_for_job, stubs):
    """The composite foreign key would refuse the write anyway. This asserts the layer above
    it never gets that far, and answers 404 rather than leaking a constraint error."""
    caller, items = wardrobe
    outfit = composed_outfit(api, caller, wait_for_job, items)

    stranger = api.start_session()
    api.transport_double.default = stubs.fixture("extraction_success.json")
    theirs = _upload_ready(api, stranger, wait_for_job, 3, "footwear")

    response = api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": "footwear", "replacement_item_id": theirs},
        headers=caller.headers,
    )

    assert response.status_code == 404
    reread = api.get(f"/api/v1/outfits/{outfit['outfit_id']}", headers=caller.headers).json()
    assert {slot["item_id"] for slot in reread["slots"]} == set(items.values())


def test_a_composition_only_ever_sees_the_callers_own_wardrobe(
    api, wardrobe, wait_for_job, stubs
):
    """Case 11 on the compose path: the candidate set handed to the advisor is one user's."""
    caller, items = wardrobe
    stranger = api.start_session()
    api.transport_double.default = stubs.fixture("extraction_success.json")
    theirs = _upload_ready(api, stranger, wait_for_job, 4, "top")

    script_advice(api, item_ids=list(items.values()))
    compose(api, caller, wait_for_job)

    advice_calls = [
        call
        for call in api.transport_double.calls
        if call.model == get_settings().groq_text_model
    ]
    prompt = json.dumps([str(message) for message in advice_calls[-1].messages])
    assert theirs not in prompt
    assert stranger.user_id not in prompt
