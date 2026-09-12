"""Image ingest.

The EXIF tests assert on the **output bytes**, not on the code path. A test that checks
`exif_transpose` was called proves the call happened; a test that reads the saved file back
and finds no GPS proves the property the privacy spec actually asks for.
"""

from __future__ import annotations

import io
from hashlib import sha256

import pytest
from PIL import Image

from app.services.images import (
    ALLOWED_MIME_TYPES,
    ImageRejectedError,
    analysis_variant,
    prepare_image,
    sniff_mime,
)
from tests.support import make_image

BOUNDS = {"max_bytes": 10 * 1024 * 1024, "min_edge_px": 128, "max_pixels": 40_000_000}


def prepare(raw: bytes, **overrides):
    return prepare_image(raw, **{**BOUNDS, **overrides})


# --- the allow-list ---------------------------------------------------------------------


def test_the_api_accepts_exactly_what_the_browser_offers():
    """The web client's `acceptedMimeTypes` and this list must agree.

    Written out rather than imported from anywhere: these are two codebases and the list is
    duplicated on purpose (client validation is a courtesy, the API is the gate). This test
    is the thing that notices when only one of them changes.
    """
    assert ALLOWED_MIME_TYPES == ("image/jpeg", "image/png", "image/webp", "image/avif")


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_every_accepted_format_survives_ingest(fmt):
    prepared = prepare(make_image(fmt=fmt))
    assert prepared.width == 600
    assert prepared.height == 800
    assert prepared.mime_type in ALLOWED_MIME_TYPES


def test_the_bytes_decide_the_type_not_the_declared_header():
    """A PDF announced as `image/jpeg` is refused on its contents."""
    with pytest.raises(ImageRejectedError) as raised:
        prepare(b"%PDF-1.7\n" + b"0" * 4096, declared_mime="image/jpeg")

    assert raised.value.code == "UNSUPPORTED_FORMAT"
    # The user is told their file disagreed with itself, which is the actionable part.
    assert "contents are something else" in raised.value.message


def test_a_disallowed_format_is_named_in_terms_the_user_can_act_on():
    with pytest.raises(ImageRejectedError) as raised:
        prepare(b"GIF89a" + b"0" * 64)
    assert raised.value.code == "UNSUPPORTED_FORMAT"
    assert "JPEG" in raised.value.message


def test_sniffing_recognises_the_container_formats():
    assert sniff_mime(make_image(fmt="JPEG")) == "image/jpeg"
    assert sniff_mime(make_image(fmt="PNG")) == "image/png"
    assert sniff_mime(make_image(fmt="WEBP")) == "image/webp"
    assert sniff_mime(b"not an image at all") is None


# --- bounds ------------------------------------------------------------------------------


def test_an_oversized_file_is_refused_before_it_is_decoded():
    with pytest.raises(ImageRejectedError) as raised:
        prepare(make_image(), max_bytes=128)
    assert raised.value.code == "IMAGE_TOO_LARGE"
    assert "MB" in raised.value.message


def test_a_thumbnail_is_refused_with_its_own_reason():
    with pytest.raises(ImageRejectedError) as raised:
        prepare(make_image(size=(64, 64)))
    assert raised.value.code == "IMAGE_UNREADABLE"
    assert "too small" in raised.value.message


def test_a_pixel_bomb_is_refused_even_though_its_byte_size_is_small():
    """The reason the two ceilings are separate.

    A flat 12000x12000 PNG compresses to a few hundred kilobytes — comfortably inside any
    byte limit — and decodes to 144 megapixels. The byte ceiling cannot see it.
    """
    bomb = make_image(size=(12000, 12000), fmt="PNG")
    assert len(bomb) < BOUNDS["max_bytes"], "fixture is not actually small"

    with pytest.raises(ImageRejectedError) as raised:
        prepare(bomb, max_pixels=1_000_000)
    assert raised.value.code == "IMAGE_TOO_LARGE"


def test_an_empty_file_is_refused():
    with pytest.raises(ImageRejectedError) as raised:
        prepare(b"")
    assert raised.value.code == "IMAGE_UNREADABLE"


def test_a_truncated_image_is_refused_rather_than_crashing():
    """A valid signature over a body that stops halfway."""
    whole = make_image(fmt="PNG")
    with pytest.raises(ImageRejectedError) as raised:
        prepare(whole[: len(whole) // 3])
    assert raised.value.code == "IMAGE_UNREADABLE"


# --- EXIF ---------------------------------------------------------------------------------


def test_gps_coordinates_do_not_survive_ingest():
    """docs/SECURITY-PRIVACY.md: a jacket on a bedroom floor must not carry home."""
    raw = make_image(exif=True)
    assert Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825), "fixture has no GPS"

    prepared = prepare(raw)

    reread = Image.open(io.BytesIO(prepared.data))
    assert dict(reread.getexif()) == {}
    assert dict(reread.getexif().get_ifd(0x8825)) == {}


def test_no_metadata_at_all_survives_ingest():
    """Not just GPS. Camera model, timestamps, thumbnails — the whole block goes.

    Asserted on the raw bytes as well as the parsed tags: a marker Pillow chooses not to
    expose is still a marker sitting in a file we store.
    """
    prepared = prepare(make_image(exif=True))
    assert b"Exif" not in prepared.data
    assert b"ACME Phone" not in prepared.data


def test_the_colour_profile_and_dpi_do_not_survive_ingest():
    """The metadata that rides in `info` rather than in the EXIF block.

    This test exists because a mutation run found the gap. Removing `clean.info = {}` broke
    nothing: the EXIF assertions above still passed, because EXIF is dropped by re-encoding
    from pixels and not by that line at all. An ICC profile and a DPI *are* read back out of
    `info` by Pillow's savers, so they were the metadata actually riding through — and
    nothing was looking.
    """
    from PIL import ImageCms

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    raw = make_image(fmt="JPEG", icc_profile=icc, dpi=(300, 300))
    assert Image.open(io.BytesIO(raw)).info.get("icc_profile"), "fixture has no profile"

    prepared = prepare(raw)

    stored = Image.open(io.BytesIO(prepared.data))
    assert stored.info.get("icc_profile") is None
    assert stored.info.get("dpi") is None


def test_orientation_is_applied_before_the_tag_is_dropped():
    """The subtle one, and the one that would ship silently.

    The fixture is 600x800 pixels with orientation 6, meaning "rotate 90°" — so the
    photograph a human sees is 800x600. Strip the tag without rotating and the stored image
    is 600x800 and lying on its side, in the wardrobe *and* in the image sent to the model.
    """
    prepared = prepare(make_image(size=(600, 800), exif=True))

    assert (prepared.width, prepared.height) == (800, 600)
    assert Image.open(io.BytesIO(prepared.data)).size == (800, 600)


# --- normalisation and the checksum -------------------------------------------------------


def test_alpha_is_preserved_and_opaque_images_become_jpeg():
    assert prepare(make_image(mode="RGBA", fmt="PNG")).mime_type == "image/png"
    assert prepare(make_image(mode="RGB", fmt="PNG")).mime_type == "image/jpeg"


def test_the_same_file_uploaded_twice_has_one_checksum():
    """The property the upload cache actually rests on."""
    assert prepare(make_image(fmt="PNG")).checksum == prepare(make_image(fmt="PNG")).checksum


def test_the_checksum_is_of_the_stored_bytes_not_the_uploaded_ones():
    prepared = prepare(make_image(exif=True))
    assert prepared.checksum == sha256(prepared.data).hexdigest()


def test_metadata_alone_does_not_change_the_checksum():
    """A direct consequence of stripping before hashing, and worth having.

    The same photograph off two phones carries different camera models and timestamps.
    Hashing the uploaded bytes would make those two different images and analyse both;
    hashing the stripped pixels makes them one.
    """
    import io

    from PIL import Image

    image = Image.new("RGB", (600, 800), (40, 60, 90))
    tags = image.getexif()
    tags[0x010F] = "ACME Phone"
    gps = tags.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 30.0, 0.0)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", exif=tags)

    assert prepare(buffer.getvalue()).checksum == prepare(make_image(fmt="PNG")).checksum


def test_a_lossless_container_change_does_not_change_the_checksum():
    """PNG and lossless WebP of the same pixels are the same photograph."""
    assert (
        prepare(make_image(fmt="WEBP", lossless=True)).checksum
        == prepare(make_image(fmt="PNG")).checksum
    )


def test_a_lossy_re_encode_is_a_different_photograph():
    """The limit of the cache, asserted so nobody mistakes it for content addressing.

    A phone that re-compressed the picture on the way out produced different pixels, and
    the checksum says so. That is the correct answer — we cannot know the two were meant to
    be the same image — but it means the cache is a cheap win on re-picks, not a guarantee
    that a garment is never analysed twice.
    """
    assert prepare(make_image(fmt="WEBP")).checksum != prepare(make_image(fmt="PNG")).checksum


# --- the provider copy --------------------------------------------------------------------


def test_the_provider_copy_is_downscaled_and_smaller():
    prepared = prepare(make_image(size=(2400, 3200), fmt="PNG"))
    variant = analysis_variant(prepared.data, max_edge_px=1024)

    assert max(Image.open(io.BytesIO(variant)).size) == 1024
    assert len(variant) < len(prepared.data)


def test_the_provider_copy_is_always_jpeg_even_from_a_transparent_original():
    """Alpha is flattened onto white for the model, and kept in the stored original."""
    prepared = prepare(make_image(mode="RGBA", fmt="PNG"))
    variant = analysis_variant(prepared.data, max_edge_px=1024)

    assert prepared.mime_type == "image/png"
    assert Image.open(io.BytesIO(variant)).format == "JPEG"


def test_a_small_image_is_not_upscaled_for_the_provider():
    prepared = prepare(make_image(size=(300, 400), fmt="PNG"))
    variant = analysis_variant(prepared.data, max_edge_px=1024)
    assert Image.open(io.BytesIO(variant)).size == (300, 400)
