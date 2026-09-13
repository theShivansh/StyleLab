"""Private object storage and image references."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app.adapters.transport import ImageReferenceSource
from app.security.identity import IMAGE_PURPOSE
from app.security.tokens import TokenSigner
from app.services.images import prepare_image
from app.services.storage import (
    DatabaseObjectStore,
    InlineImageSource,
    LocalObjectStore,
    ObjectStore,
    SignedUrlImageSource,
    StorageError,
    browser_image_url,
    extension_for,
    image_subject,
    split_image_subject,
    storage_key,
)
from tests.support import make_image


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(tmp_path / "uploads")


def _database_store(tmp_path):
    from app.db.models import Base
    from app.db.session import build_engine, session_factory

    engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'blobs.db').as_posix()}")
    Base.metadata.create_all(engine)
    return DatabaseObjectStore(session_factory(engine))


@pytest.fixture(params=["local", "database"])
def any_store(request, tmp_path):
    """Both implementations, through one set of tests.

    The Protocol is only worth having if the two are actually interchangeable, and the way to
    find out is to run the same assertions against each rather than to write a second file
    that drifts. A behaviour asserted here is a behaviour a caller may rely on without
    knowing which store it holds.
    """
    if request.param == "local":
        return LocalObjectStore(tmp_path / "uploads")
    return _database_store(tmp_path)


# --- the store contract, for both implementations -------------------------------------------


def test_the_store_satisfies_the_protocol(any_store):
    assert isinstance(any_store, ObjectStore)


async def test_a_stored_object_comes_back_byte_identical(any_store):
    key = storage_key("user_1", "asset_1", extension="jpg")
    await any_store.put(key, b"\xff\xd8\xffsome bytes", content_type="image/jpeg")

    assert await any_store.exists(key)
    assert await any_store.get(key) == b"\xff\xd8\xffsome bytes"


async def test_deleting_is_idempotent(any_store):
    key = storage_key("user_1", "asset_1", extension="jpg")
    await any_store.put(key, b"x", content_type="image/jpeg")
    await any_store.delete(key)
    await any_store.delete(key)
    assert not await any_store.exists(key)


async def test_putting_the_same_key_twice_replaces_rather_than_raises(any_store):
    """An upload retried after a timeout must not fail on the second attempt with an
    integrity error the user sees as "something went wrong on our side"."""
    key = storage_key("user_1", "asset_1", extension="jpg")
    await any_store.put(key, b"first", content_type="image/jpeg")
    await any_store.put(key, b"second", content_type="image/jpeg")

    assert await any_store.get(key) == b"second"


async def test_reading_a_missing_object_raises_a_storage_error(any_store):
    with pytest.raises(StorageError):
        await any_store.get(storage_key("user_1", "missing", extension="jpg"))


@pytest.mark.parametrize(
    "key",
    ["../../etc/passwd", "user_1/../../secret.jpg", "user_1", "a/b/c.jpg", "user_1/.jpg"],
)
async def test_a_malformed_key_is_refused_before_anything_is_stored(any_store, key):
    """Both stores validate, not only the one where a key becomes a path.

    In the database store a key becomes a primary key, and a store that persists whatever
    string it is handed can be made to hold rows nothing will ever read or delete — which is
    a quieter failure than a traversal but is the same missing check.
    """
    with pytest.raises(StorageError):
        await any_store.put(key, b"x", content_type="image/jpeg")


async def test_reading_a_missing_object_raises_without_naming_a_path(store):
    with pytest.raises(StorageError) as raised:
        await store.get(storage_key("user_1", "missing", extension="jpg"))
    # The message reaches a log and a log reaches somewhere else. No filesystem layout in it.
    assert "uploads" not in str(raised.value)
    assert str(store.root) not in str(raised.value)


# --- the database store, on the property it exists for --------------------------------------


async def test_the_database_store_keeps_nothing_in_the_process(tmp_path):
    """The whole reason it exists.

    A second `DatabaseObjectStore` over the same database sees what the first one wrote —
    which is what a replacement container is, and what a second replica is. `LocalObjectStore`
    on a host with no volume cannot do this, and that is not a performance difference: the
    wardrobe rows outlive the photographs and the user is shown broken images.
    """
    from app.db.models import Base
    from app.db.session import build_engine, session_factory

    url = f"sqlite+pysqlite:///{(tmp_path / 'shared.db').as_posix()}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)

    key = storage_key("user_1", "asset_1", extension="jpg")
    first = DatabaseObjectStore(session_factory(engine))
    await first.put(key, b"pixels", content_type="image/jpeg")
    engine.dispose()

    reopened = build_engine(url)
    try:
        assert await DatabaseObjectStore(session_factory(reopened)).get(key) == b"pixels"
    finally:
        reopened.dispose()


async def test_the_database_store_records_the_size_it_was_given(tmp_path):
    """`byte_size` is denormalised on purpose: answering "how much database is this costing"
    should not mean reading every photograph back out of it."""
    from app.db.models import AssetBlobRow

    store = _database_store(tmp_path)
    key = storage_key("user_1", "asset_1", extension="jpg")
    await store.put(key, b"x" * 1234, content_type="image/webp")

    # Reaching past the interface on purpose: the point of the assertion is the row.
    with store._sessions() as session:
        row = session.get(AssetBlobRow, key)

    assert row is not None
    assert row.byte_size == 1234
    assert row.content_type == "image/webp"


# --- which store a deployment gets -----------------------------------------------------------


@pytest.mark.parametrize(
    ("backend", "expected"),
    [("local", LocalObjectStore), ("database", DatabaseObjectStore)],
)
def test_the_setting_chooses_the_store(backend, expected, tmp_path):
    """`STORAGE_BACKEND` is the only thing that decides, and it decides in one place.

    Asserted because the alternative — inferring it from `DATABASE_URL` looking like Postgres,
    or from `APP_ENV` — would be a deployment silently changing where a user's photographs
    live based on something that reads like it is about a database.
    """
    from app.config import Settings
    from app.main import _object_store

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key="not-a-real-key",
        storage_backend=backend,
        storage_root=str(tmp_path / "uploads"),
    )

    assert isinstance(_object_store(settings, _database_store(tmp_path)._sessions), expected)


async def test_no_partial_file_is_left_behind_under_the_key(store):
    """Write-then-replace: a reader never opens a half-written photograph."""
    key = storage_key("user_1", "asset_1", extension="jpg")
    await store.put(key, b"a" * 4096, content_type="image/jpeg")

    assert list(store.root.rglob("*.part")) == []


# --- keys, and the filename that never becomes a path -------------------------------------


def test_a_storage_key_is_derived_from_the_owner_and_the_asset():
    assert storage_key("user_1", "asset_2", extension="png") == "user_1/asset_2.png"


@pytest.mark.parametrize(
    "segment",
    ["..", "../etc", "a/b", "a\\b", "", "a b", "a.b", "*", "~", "a\x00b"],
)
def test_a_key_segment_outside_the_safe_alphabet_is_refused(segment):
    """The uploaded filename is user input, and user input is not a path component."""
    with pytest.raises(StorageError):
        storage_key(segment, "asset_1", extension="jpg")
    with pytest.raises(StorageError):
        storage_key("user_1", segment, extension="jpg")


@pytest.mark.parametrize(
    "key",
    [
        "../../secret.txt",
        "user_1/../../secret.txt",
        "user_1/..%2fsecret.jpg",
        "user_1",
        "user_1/a/b.jpg",
        "/absolute/path.jpg",
    ],
)
async def test_the_store_refuses_a_key_that_escapes_its_root(store, key):
    """Validated where the filesystem is touched, not only where keys are built.

    `storage_key` is the only constructor today. This check is in `_path` because the
    constructor being the only one is a property of today's code, and the one that matters
    is a property of the store.
    """
    with pytest.raises(StorageError):
        await store.get(key)


def test_extensions_map_only_the_formats_we_accept():
    assert extension_for("image/jpeg") == "jpg"
    assert extension_for("image/png") == "png"
    assert extension_for("image/webp") == "webp"
    assert extension_for("image/avif") == "avif"
    assert extension_for("application/pdf") == "bin"


# --- the provider reference ---------------------------------------------------------------


async def test_the_inline_source_satisfies_the_image_reference_protocol(store):
    assert isinstance(InlineImageSource(store, max_edge_px=512), ImageReferenceSource)


async def test_the_inline_source_hands_the_provider_a_downscaled_jpeg(store):
    """One call, and it does both jobs: reads the private object, shrinks it for the wire."""
    prepared = prepare_image(
        make_image(size=(2000, 2500), fmt="PNG"),
        max_bytes=10 * 1024 * 1024,
        min_edge_px=128,
        max_pixels=40_000_000,
    )
    key = storage_key("user_1", "asset_1", extension="png")
    await store.put(key, prepared.data, content_type=prepared.mime_type)

    url = await InlineImageSource(store, max_edge_px=640).provider_url(key)

    assert url.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(url.removeprefix("data:image/jpeg;base64,"))
    assert max(Image.open(io.BytesIO(decoded)).size) == 640
    assert len(decoded) < len(prepared.data)


async def test_the_inline_source_never_returns_a_url_pointing_anywhere(store):
    """The privacy property of inlining: there is no reference left over to leak.

    A signed URL exists after the request and can be logged, cached or forwarded. A data URL
    is the bytes, in the request body, and nothing else.
    """
    key = storage_key("user_1", "asset_1", extension="jpg")
    await store.put(key, make_image(), content_type="image/jpeg")

    url = await InlineImageSource(store, max_edge_px=256).provider_url(key)

    assert "http" not in url
    assert key not in url


def test_the_signed_url_source_refuses_to_pretend_it_works():
    """It exists so that inlining looks like the local choice, not the only one.

    Raising is the point. A stub returning a plausible-looking URL would be a path that
    silently sent nothing fetchable to the provider — and S11 is where it gets a body.
    """
    with pytest.raises(NotImplementedError) as raised:
        SignedUrlImageSource(object())
    assert "S11" in str(raised.value)


# --- the browser reference ----------------------------------------------------------------


def test_a_browser_image_url_puts_no_credential_in_a_query_string():
    """docs/SECURITY-PRIVACY.md, taken literally rather than argued with."""
    url = browser_image_url(
        "asset_1",
        user_id="user_1",
        base_url="http://localhost:8000/api/v1",
        signer=TokenSigner("k" * 32),
        ttl_s=60,
    )

    assert "?" not in url
    assert url.startswith("http://localhost:8000/api/v1/assets/asset_1/")


def test_the_image_token_binds_the_owner_as_well_as_the_asset():
    """What keeps the asset route a scoped read rather than a primary-key load."""
    signer = TokenSigner("k" * 32)
    url = browser_image_url(
        "asset_1",
        user_id="user_1",
        base_url="http://x/api/v1",
        signer=signer,
        ttl_s=60,
    )
    token = url.rsplit("/", 1)[-1]

    claims = signer.verify(token, purpose=IMAGE_PURPOSE)
    assert split_image_subject(claims.subject) == ("user_1", "asset_1")


def test_an_image_subject_round_trips():
    assert split_image_subject(image_subject("user_1", "asset_2")) == ("user_1", "asset_2")


@pytest.mark.parametrize("subject", ["", "user_1", "/asset_1", "user_1/"])
def test_a_subject_that_is_not_owner_and_asset_is_refused(subject):
    with pytest.raises(ValueError):
        split_image_subject(subject)
