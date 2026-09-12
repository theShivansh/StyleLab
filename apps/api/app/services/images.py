"""Image ingest — validate, strip, normalise, checksum.

Every byte a user uploads passes through `prepare_image` before anything else in the system
sees it. Nothing downstream re-checks these properties, so this module is the boundary.

## Order of operations, and why it is this order

    1  byte ceiling          — before decoding, so a huge file is refused cheaply
    2  sniff the real format — from magic bytes, never from the declared MIME type
    3  pixel ceiling         — from the header, before the pixels are read into memory
    4  decode
    5  apply EXIF orientation
    6  resolution floor
    7  re-encode with no metadata
    8  checksum the result

Steps 1 and 3 are separate because they catch different attacks. A byte ceiling alone lets
through a 40KB PNG that decodes to 60000x60000 and exhausts memory; a pixel ceiling alone
lets through a 200MB file. Both are cheap and neither subsumes the other.

Step 2 matters because the declared `Content-Type` is a claim by the uploader. A file named
`.jpg`, announced as `image/jpeg`, containing something else, is refused here on the
strength of its bytes. The declared type is used for one thing only: a clearer message.

## Step 5 is the one that looks optional and is not

EXIF orientation must be **applied** before the metadata is dropped. A phone writes portrait
photographs as landscape pixels plus an orientation tag; strip the tag without rotating the
pixels first and every portrait photo in the wardrobe silently lies on its side — including
in the image sent to the vision model, which then reports the shoulders of a shirt as its
hem. `ImageOps.exif_transpose` is not a nicety.

## What stripping removes, and what actually does the removing

Everything. GPS coordinates above all (docs/SECURITY-PRIVACY.md: "a photo of a jacket on a
bedroom floor should not carry the user's home coordinates into the database"), but also
camera model, serial number, capture timestamp, thumbnails, ICC profiles, DPI and PNG text
chunks.

**Re-encoding from decoded pixels is the whole mechanism.** Pillow's JPEG and PNG savers
write EXIF, an ICC profile or a DPI only when handed one explicitly at save time, and
nothing here hands them anything. The metadata is not stripped so much as never carried
forward.

`clean.info = {}` is belt-and-braces, and this comment used to claim it was the safeguard.
A mutation run says otherwise: remove the line and every metadata assertion still passes,
because under Pillow 11.3 the savers ignore `info` entirely. It is kept because that has not
always been true of Pillow and may not stay true, and its cost is one line — but it is not
what holds the guarantee, and a comment saying it was would send the next reader to the
wrong place.

What holds the guarantee is the output-byte assertions in `tests/test_images.py`, one per
class of metadata. The mutation they *do* catch is the realistic one: adding
`exif=`/`icc_profile=` to these `save()` calls to make stored photographs render more
faithfully. That is a reasonable-sounding change which puts a user's GPS coordinates back in
the database, and it turns four tests red.

## Normalisation

Stored images come out as JPEG when opaque and PNG when they carry alpha, whatever went in.
Two encoders to reason about instead of four, and every stored file written by us.

It also means the checksum is over normalised pixels, so it is invariant to the container
and to metadata: the same photograph off two phones, carrying different camera models and
timestamps, is one image to the cache. It is **not** invariant to re-compression — a phone
that re-encoded the picture lossily on the way out produced different pixels and gets a
different checksum. That is the honest answer rather than a limitation to hide: the cache is
a cheap win on a re-pick, not a promise that a garment is analysed only once.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from hashlib import sha256

from PIL import Image, ImageOps, UnidentifiedImageError

#: What the browser is told to offer, and what is actually accepted. Kept in step with
#: `config.upload.acceptedMimeTypes` in the web app; `tests/test_images.py` pins the list.
ALLOWED_MIME_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif")

#: Magic-byte prefixes, longest-first where they overlap. The authority on what a file is.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)

#: ISO base media format: `....ftyp<brand>`. WebP is RIFF, so it is sniffed the same way.
_FTYP_BRANDS = {b"avif": "image/avif", b"avis": "image/avif"}

JPEG_QUALITY = 90
#: Quality for the copy sent to the provider. Lower than the stored original on purpose —
#: it is downscaled anyway and every byte is a byte over the wire.
ANALYSIS_JPEG_QUALITY = 82


class ImageRejectedError(Exception):
    """One image was refused, with a code from docs/API-SPEC.md and copy for the user.

    Carries the user-facing message itself rather than a key to look up elsewhere: the
    message is the whole point of refusing an image politely, and a code alone gets
    rendered at the user as "UNSUPPORTED_FORMAT".
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """An accepted image, stripped and normalised, ready to store."""

    data: bytes
    mime_type: str
    width: int
    height: int
    #: sha256 of `data` — the normalised bytes, not what was uploaded. Two uploads of the
    #: same photograph agree here even if their containers or metadata differed.
    checksum: str

    @property
    def byte_size(self) -> int:
        return len(self.data)


def sniff_mime(raw: bytes) -> str | None:
    """The real type of these bytes, or None if it is not one we accept."""
    for prefix, mime in _SIGNATURES:
        if raw.startswith(prefix):
            return mime

    # RIFF....WEBP
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"

    # ....ftypavif — the box length precedes the type, so `ftyp` sits at offset 4.
    if len(raw) >= 12 and raw[4:8] == b"ftyp":
        return _FTYP_BRANDS.get(raw[8:12].lower())

    return None


def prepare_image(
    raw: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int,
    min_edge_px: int,
    max_pixels: int,
) -> PreparedImage:
    """Validate, strip and normalise one upload. Raises `ImageRejectedError`."""
    if not raw:
        raise ImageRejectedError("IMAGE_UNREADABLE", "That file is empty. Try picking it again.")

    if len(raw) > max_bytes:
        megabytes = len(raw) / (1024 * 1024)
        limit = round(max_bytes / (1024 * 1024))
        raise ImageRejectedError(
            "IMAGE_TOO_LARGE", f"That photo is {megabytes:.1f} MB. Keep it under {limit} MB."
        )

    mime = sniff_mime(raw)
    if mime is None or mime not in ALLOWED_MIME_TYPES:
        # The declared type is quoted only when it disagrees with the bytes, because that is
        # the case where the user is confused rather than simply holding the wrong file.
        detail = (
            " It says it is a photo, but its contents are something else."
            if declared_mime in ALLOWED_MIME_TYPES
            else ""
        )
        raise ImageRejectedError(
            "UNSUPPORTED_FORMAT", f"Use a JPEG, PNG, WebP or AVIF photo.{detail}"
        )

    try:
        # Lazy: reads the header, not the pixels. The size check below therefore happens
        # before a decompression bomb is ever expanded.
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > max_pixels:
                raise ImageRejectedError(
                    "IMAGE_TOO_LARGE",
                    f"That photo is {opened.width}x{opened.height}, which is larger than we "
                    "can process. Try one straight from your camera roll.",
                )

            oriented = ImageOps.exif_transpose(opened) or opened
            if min(oriented.width, oriented.height) < min_edge_px:
                raise ImageRejectedError(
                    "IMAGE_UNREADABLE",
                    f"That photo is only {oriented.width}x{oriented.height}. It is too small "
                    "to read a garment from — try the full-size version.",
                )
            data, mime_type = _reencode(oriented)
            size = (oriented.width, oriented.height)
    except ImageRejectedError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        # A valid signature and an unreadable body: truncated download, corrupt file.
        raise ImageRejectedError(
            "IMAGE_UNREADABLE", "We couldn't open that photo. It may be damaged — try again."
        ) from error

    return PreparedImage(
        data=data,
        mime_type=mime_type,
        width=size[0],
        height=size[1],
        checksum=sha256(data).hexdigest(),
    )


def analysis_variant(data: bytes, *, max_edge_px: int) -> bytes:
    """A downscaled JPEG of a stored image, for sending to the vision provider.

    Smaller than the stored original on purpose. A 4000px photograph of a shirt carries no
    more garment information than a 1024px one; it costs more to send, takes longer to
    analyse, and pushes an inlined image past the provider's payload ceiling.

    Always JPEG, with any alpha flattened onto white — the original keeps its transparency,
    and a cut-out garment on a white ground is what the model would see on a white wall.

    Derived on demand rather than stored as a second object. One asset, one file: a cached
    variant would be a second thing to delete when the user deletes their photograph, and
    the first thing to be forgotten.
    """
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA") if opened.mode in ("RGBA", "LA", "P") else opened
        image = _flatten(image) if image.mode == "RGBA" else image.convert("RGB")

        if max(image.width, image.height) > max_edge_px:
            image.thumbnail((max_edge_px, max_edge_px), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=ANALYSIS_JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


# --- internals -------------------------------------------------------------------------


def _flatten(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.split()[-1])
    return background


def _reencode(image: Image.Image) -> tuple[bytes, str]:
    """Write the pixels out with no metadata attached.

    Do not add `exif=`, `icc_profile=` or `dpi=` to these `save()` calls. Passing metadata
    explicitly is the only way Pillow writes any, which makes their absence the strip — see
    the module docstring, and `tests/test_images.py` for the four assertions that fail if
    they come back.
    """
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )

    clean = image.convert("RGBA" if has_alpha else "RGB")
    clean.info = {}

    buffer = io.BytesIO()
    if has_alpha:
        clean.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), "image/png"

    clean.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue(), "image/jpeg"


__all__ = [
    "ALLOWED_MIME_TYPES",
    "ANALYSIS_JPEG_QUALITY",
    "JPEG_QUALITY",
    "ImageRejectedError",
    "PreparedImage",
    "analysis_variant",
    "prepare_image",
    "sniff_mime",
]
