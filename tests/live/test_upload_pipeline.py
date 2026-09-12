"""The upload path, end to end, against the real provider.

This is the acceptance criterion S3 deferred and S6 owes: *the full upload → wardrobe path
completes against live Groq, with the vision fallback chain exercised.*

It runs the whole API — routes, ingest, storage, EXIF strip, downscale, the real
`GroqWardrobeAnalyzer`, the real transport — over the photographs in `data/samples/`. The
only thing absent is a browser.

Billed, `smoke`-marked, and deliberately small: one extraction for the happy path and one
for the fallback. Everything provable without a key is proved in `apps/api/tests/` and
`tests/ai/` on every push. What cannot be proved there, and what this catches, is the class
of failure where our schema is valid JSON Schema and the provider still refuses it — which
is exactly what happened the first time this file ran.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "data" / "samples"
SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _samples(limit: int) -> list[Path]:
    if not SAMPLES.is_dir():
        pytest.skip(f"no sample photographs in {SAMPLES.relative_to(REPO_ROOT)}")
    found = [p for p in sorted(SAMPLES.iterdir()) if p.suffix.lower() in SUFFIXES]
    if not found:
        pytest.skip(f"no usable image in {SAMPLES.relative_to(REPO_ROOT)}")
    return found[:limit]


@pytest.fixture
def live_api(api_key, tmp_path):
    """The real application, with real Groq, over a temporary store and database.

    No transport double anywhere. `create_app` is called exactly as production calls it
    apart from `store` and `sessions`, which point at `tmp_path` so a test run does not
    deposit a wardrobe in the working tree.
    """
    from app.db.session import build_engine, create_all, session_factory
    from app.main import create_app
    from app.services.storage import LocalObjectStore
    from fastapi.testclient import TestClient

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'live.db').as_posix()}")
    create_all(engine)

    app = create_app(
        store=LocalObjectStore(tmp_path / "uploads"),
        sessions=session_factory(engine),
    )
    with TestClient(app) as client:
        yield client
    engine.dispose()


def _await_job(client, headers, job_id: str, timeout_s: float = 120.0) -> dict:
    """Poll the documented endpoint. A real vision call takes seconds, not milliseconds."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.25)
    raise AssertionError(f"job {job_id} did not finish inside {timeout_s}s")


@pytest.mark.smoke
def test_the_whole_upload_path_completes_against_live_groq(live_api):
    """Photographs in, garments out. Nothing stubbed.

    The wardrobe that comes out of this is also the demo wardrobe (blocker B6): the sample
    photographs are a top, a bottom and a pair of shoes, which is a complete outfit and the
    minimum the composer needs.
    """
    samples = _samples(3)
    session = live_api.post("/api/v1/session").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    response = live_api.post(
        "/api/v1/wardrobe/items",
        files=[
            ("images[]", (path.name, path.read_bytes(), "image/png"))
            for path in samples
        ],
        headers=headers,
    )
    assert response.status_code == 201
    uploaded = response.json()["items"]
    assert [item["status"] for item in uploaded] == ["analyzing"] * len(samples), uploaded

    for item in uploaded:
        job = _await_job(live_api, headers, item["job_id"])
        assert job["status"] == "completed", job
        assert job["stage"] == "ready"

    wardrobe = live_api.get("/api/v1/wardrobe/items", headers=headers).json()["items"]
    assert len(wardrobe) == len(samples)

    for garment in wardrobe:
        assert garment["status"] == "ready"
        assert garment["category"] in ("top", "bottom", "footwear", "outerwear", "accessory")
        # The honesty signal. A garment with no per-field confidence cannot be hedged and
        # cannot invite a correction, which is most of what the extraction screen is for —
        # and it is what a strict schema with an unfillable `field_confidence` produced.
        assert garment["field_confidence"], f"no confidence scores for {garment['item_id']}"
        assert all(0.0 <= score <= 1.0 for score in garment["field_confidence"].values())
        assert garment["image_url"]

    # The audit trail is what makes the reading evidence rather than an assertion.
    first = wardrobe[0]["item_id"]
    audit = live_api.get(
        f"/api/v1/wardrobe/items/{first}/extractions", headers=headers
    ).json()["extractions"]
    assert audit and audit[0]["schema_valid"] is True
    assert audit[0]["raw_output"], "the model's own words were not kept"

    # And the stored photograph is served back, stripped and re-encoded by us.
    image = live_api.get(wardrobe[0]["image_url"])
    assert image.status_code == 200
    assert b"Exif" not in image.content


@pytest.mark.smoke
async def test_the_fallback_model_answers_when_the_primary_cannot(transport, settings):
    """AI-EVAL-CASES Case 24(a) against the live provider.

    The primary is set to an id Groq does not serve, so the real transport maps the real 404
    into `ProviderModelMissingError`, the analyzer sees `use_fallback_model` and moves on,
    and the **real fallback model** produces the extraction. That chain is three
    independent pieces — error mapping, the fallback decision, and the fallback model's own
    schema compliance — and the mock can only prove the middle one.

    Deliberately not a fabricated model *error*: a deprecated id is the failure this chain
    exists for (CLAUDE.md: "Groq deprecates models on weeks of notice"), and it is the one
    that can be provoked honestly.
    """
    import base64

    from app.adapters.groq_vision import GroqWardrobeAnalyzer
    from app.domain.models import GarmentImage
    from app.services.images import analysis_variant, prepare_image

    sample = _samples(1)[0]
    prepared = prepare_image(
        sample.read_bytes(), max_bytes=20 * 1024 * 1024, min_edge_px=128, max_pixels=40_000_000
    )
    downscaled = analysis_variant(prepared.data, max_edge_px=settings.analysis_max_edge_px)

    class Inline:
        async def provider_url(self, storage_key: str, *, ttl_s: int = 300) -> str:
            return "data:image/jpeg;base64," + base64.b64encode(downscaled).decode("ascii")

    analyzer = GroqWardrobeAnalyzer(
        transport,
        model="qwen/qwen3.8-27b-retired-in-this-test",
        fallback_model=settings.groq_vision_model,
        urls=Inline(),
        max_tokens=settings.groq_vision_max_tokens,
    )

    outcome = await analyzer.analyze_with_audit(
        GarmentImage(asset_id="live", storage_key=sample.name)
    )

    assert outcome.extraction.category is not None
    assert outcome.used_fallback is True
    assert outcome.model == settings.groq_vision_model

    # Both attempts are recorded: the refusal and the reading. An audit trail that kept only
    # the second could not show that a model had been retired.
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].schema_valid is False
    assert outcome.attempts[0].rejected_reason
    assert outcome.attempts[1].schema_valid is True
