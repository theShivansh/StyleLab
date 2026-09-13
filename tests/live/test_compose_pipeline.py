"""Composition and swap, end to end, against the real provider.

The S7 half of what `test_upload_pipeline.py` does for S6: photographs in, a real look out,
with the real text model doing the styling and the real ownership re-validation checking it
afterwards.

What only a live run can answer here — and the reason this file exists rather than one more
mocked route test:

* **Does the text model honour `ADVICE_JSON_SCHEMA`?** Strict Structured Outputs refused two
  of our schemas the first time S6 ran; `MockGroqProvider` returns scripted content and never
  validates the schema it is handed, so it cannot tell us.
* **Is the token ceiling high enough for a reasoning model?** `openai/gpt-oss-120b` spends
  its budget thinking before it emits anything, so too small a ceiling returns an *empty*
  response rather than a short one. That cost S6 an afternoon on the vision path; this is the
  text path, with a different budget.
* **Does a real model, given real garments, name only ids it was given?** The ownership
  re-validation runs either way, but a live run is the only place its input is genuinely
  out of our hands.

Billed and `smoke`-marked, and the wardrobe is stocked **once** for the whole module.
That is not only thrift. The first version of this file called the upload path per test
and tripped the account's output-tokens-per-minute limit on the third photograph of the
third test - nine vision calls inside four minutes. Extraction already has its own live
test (`test_upload_pipeline.py`); repeating it here bought nothing and cost the suite a
red run that said "rate limited" rather than anything about composition.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from capacity import skip_if_at_capacity, tolerating_capacity

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "data" / "samples"
SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _samples() -> list[Path]:
    if not SAMPLES.is_dir():
        pytest.skip(f"no sample photographs in {SAMPLES.relative_to(REPO_ROOT)}")
    found = [p for p in sorted(SAMPLES.iterdir()) if p.suffix.lower() in SUFFIXES]
    if len(found) < 3:
        pytest.skip("composing needs a top, a bottom and a pair of shoes in data/samples")
    return found


@pytest.fixture(scope="module")
def live_api(api_key, paced, tmp_path_factory):
    """The real application against real Groq. Same construction as the upload pipeline.

    Module-scoped, because the wardrobe it holds is stocked by real vision calls and every
    test here composes from the same one.
    """
    from app.db.session import build_engine, create_all, session_factory
    from app.main import create_app
    from app.services.storage import LocalObjectStore
    from fastapi.testclient import TestClient

    root = tmp_path_factory.mktemp("live-compose")
    engine = build_engine(f"sqlite+pysqlite:///{(root / 'live.db').as_posix()}")
    create_all(engine)

    app = create_app(
        store=LocalObjectStore(root / "uploads"),
        sessions=session_factory(engine),
    )
    with TestClient(app) as client:
        yield client
    engine.dispose()


def _await_job(client, headers, job_id: str, timeout_s: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.25)
    raise AssertionError(f"job {job_id} did not finish inside {timeout_s}s")


@pytest.fixture(scope="module")
def stocked(live_api) -> tuple[dict[str, str], list[dict]]:
    """One session, one upload of the samples, one set of vision calls."""
    return _stock(live_api)


def _stock(client) -> tuple[dict[str, str], list[dict]]:
    """Upload the samples, wait for every extraction, and return the wardrobe."""
    session = client.post("/api/v1/session").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    response = client.post(
        "/api/v1/wardrobe/items",
        files=[
            ("images[]", (path.name, path.read_bytes(), "image/png")) for path in _samples()
        ],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    for item in response.json()["items"]:
        job = _await_job(client, headers, item["job_id"])
        skip_if_at_capacity(job)
        assert job["status"] == "completed", job

    wardrobe = client.get("/api/v1/wardrobe/items", headers=headers).json()["items"]
    return headers, wardrobe


@pytest.mark.smoke
def test_a_real_wardrobe_composes_a_real_look(live_api, stocked):
    """The whole path: upload, extract, compose, read the result.

    The three sample photographs are a top, a bottom and a pair of shoes, so a complete look
    is possible — and if the live extraction reads them as three tops, this fails with the
    honest gap answer rather than inventing a trouser, which is also worth knowing.
    """
    headers, wardrobe = stocked
    owned = {garment["item_id"] for garment in wardrobe}

    started = live_api.post(
        "/api/v1/outfits/compose",
        json={"occasion": "everyday", "vibe": "minimal", "fit_preference": "regular"},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    job = _await_job(live_api, headers, started.json()["job_id"])
    skip_if_at_capacity(job)
    assert job["status"] == "completed", job

    if job["result_id"] is None:
        # The honest gap answer. Legitimate if the live reading did not produce three roles,
        # but it must still be a *named* gap rather than a shrug.
        assert job["result"]["missing_roles"], job
        pytest.skip(f"live extraction produced no complete outfit: {job['result']['missing_roles']}")

    outfit = live_api.get(f"/api/v1/outfits/{job['result_id']}", headers=headers).json()

    assert outfit["status"] == "ready"
    assert outfit["slots"], outfit
    # Every garment on the screen is one the caller owns. The re-validation ran server-side;
    # this is the assertion that it ran over a response we did not write.
    assert {slot["item_id"] for slot in outfit["slots"]} <= owned
    assert 0 <= outfit["match_score"] <= 100
    assert outfit["rationale"], "a look with no reasoning is a look nobody can trust"
    assert outfit["name"]

    # Nothing on this screen may be a commerce claim (docs/DECISIONS.md).
    text = " ".join(
        [outfit["name"], *outfit["rationale"], *(tip["tip"] for tip in outfit["pro_tips"])]
    ).lower()
    for banned in ("$", "£", "buy", "purchase", "shop at", "http"):
        assert banned not in text, f"advisory text made a commerce claim: {text}"


@pytest.mark.smoke
async def test_the_advisor_answers_within_its_token_ceiling(transport, settings):
    """The reasoning-model trap, on the text path — asked directly.

    `openai/gpt-oss-120b` thinks before it writes, so a ceiling that would be generous for a
    non-reasoning model returns nothing at all. S6 found that on the vision path: an empty
    response with `finish_reason="length"`, which reads like a schema problem and is not one.
    The transport now names that case, and this is the text path's version of the canary.

    **Deliberately not routed through `CompositionService`.** The first version composed
    through the whole pipeline and asserted the result was not degraded — which made a
    provider rate-limit (the account's output-tokens-per-minute ceiling, hit whenever this
    file ran after the upload suite) indistinguishable from the token ceiling this test is
    actually about. The ladder is *supposed* to swallow a 429 and answer from the ranker;
    that behaviour has its own tests. Here the question is narrower and needs the failure
    raw: does the live model, given a real candidate set and this many tokens, return output
    that satisfies `ADVICE_JSON_SCHEMA`?

    Synthetic garments rather than uploaded ones, for the same reason: three vision calls to
    set up a text-model assertion is three chances to fail for an unrelated reason.
    """
    from app.adapters.groq_text import GroqOutfitAdvisor
    from app.domain.models import (
        AdviceRequest,
        Formality,
        GarmentCategory,
        GarmentExtraction,
        ItemStatus,
        WardrobeItem,
    )

    def garment(item_id: str, category: GarmentCategory, colour: str, sub: str) -> WardrobeItem:
        return WardrobeItem(
            item_id=item_id,
            user_id="live-canary",
            status=ItemStatus.READY,
            extraction=GarmentExtraction(
                category=category,
                subcategory=sub,
                color_primary=colour,
                fit="regular",
                formality=Formality.SMART_CASUAL,
                style_tags=["minimal"],
            ),
        )

    request = AdviceRequest(
        user_id="live-canary",
        candidates=[
            garment("live-top", GarmentCategory.TOP, "white", "oxford shirt"),
            garment("live-bottom", GarmentCategory.BOTTOM, "navy", "chino"),
            garment("live-shoe", GarmentCategory.FOOTWEAR, "white", "sneaker"),
        ],
        occasion="work",
        vibe="minimal",
        required_roles=[GarmentCategory.TOP, GarmentCategory.BOTTOM, GarmentCategory.FOOTWEAR],
    )

    advisor = GroqOutfitAdvisor(
        transport,
        model=settings.groq_text_model,
        max_tokens=settings.agent_max_output_tokens,
    )

    with tolerating_capacity():
        advice = await advisor.advise(request)

    # Schema-valid output arrived, at the configured ceiling. If this fails with the token
    # ceiling message from `groq_transport._to_result`, raise `agent_max_output_tokens`.
    assert advice.outfit is not None, "the live advisor returned no outfit"
    assert advice.outfit.item_ids
    assert advice.rationale, "an advisory response with no reasoning is not advice"
    # The adapter does not filter ids and must not: ownership is re-validated above it. What
    # this asserts is only that the live model was given three ids and used that vocabulary.
    assert set(advice.outfit.item_ids) <= {"live-top", "live-bottom", "live-shoe"}


@pytest.mark.smoke
def test_a_slot_with_one_garment_names_the_gap_and_still_swaps(live_api, stocked):
    """The swap path over live data.

    The sample wardrobe holds exactly one garment per role, which makes it the honest test of
    the empty case: alternatives must come back as a **named gap** rather than an error, and
    the route must still accept the documented no-op swap (the garment already in the slot).

    The timing assertion is the point of the second half. A swap is a scoped read, a pure
    recompute and one row rewritten - nothing here may reach a provider, because that is what
    makes the signature interaction instant. Two seconds is a ceiling an accidental model call
    could not fit under.
    """
    headers, _ = stocked

    started = live_api.post(
        "/api/v1/outfits/compose", json={"occasion": "everyday"}, headers=headers
    )
    job = _await_job(live_api, headers, started.json()["job_id"])
    skip_if_at_capacity(job)
    if job["result_id"] is None:
        pytest.skip("no complete outfit from this wardrobe")

    outfit = live_api.get(f"/api/v1/outfits/{job['result_id']}", headers=headers).json()
    slot = outfit["slots"][0]
    role = slot["role"]

    alternatives = live_api.get(
        f"/api/v1/outfits/{outfit['outfit_id']}/alternatives",
        params={"role": role},
        headers=headers,
    ).json()
    assert alternatives["current_item_id"] == slot["item_id"]

    replacement = (
        alternatives["alternatives"][0]["item"]["item_id"]
        if alternatives["alternatives"]
        else slot["item_id"]
    )
    if not alternatives["alternatives"]:
        # One garment in this role, so there is nothing to swap to. Named, not errored.
        assert alternatives["gap"]["generic_description"]
        assert alternatives["gap"]["category"] == role

    started_at = time.monotonic()
    swapped = live_api.post(
        f"/api/v1/outfits/{outfit['outfit_id']}/swap",
        json={"role": role, "replacement_item_id": replacement},
        headers=headers,
    )
    elapsed = time.monotonic() - started_at

    assert swapped.status_code == 200, swapped.text
    body = swapped.json()
    assert {entry["role"]: entry["item_id"] for entry in body["slots"]}[role] == replacement
    # Untouched slots are untouched, live data included.
    assert [entry["role"] for entry in body["slots"]] == [
        entry["role"] for entry in outfit["slots"]
    ]
    assert elapsed < 2.0, f"a swap took {elapsed:.2f}s - did something call a model?"
