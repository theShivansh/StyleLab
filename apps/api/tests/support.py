"""Shared test helpers.

A module rather than fixtures in `conftest.py` because these are called directly, not
injected — and a `conftest` imported by name as well as collected by pytest gets registered
twice, which makes fixture resolution depend on import order.

Images are generated rather than committed. A test that depends on a binary in the
repository is a test nobody can adjust, and these need to vary by size, mode and metadata.
The real photographs in `data/samples/` are for the live suite, where an actual garment is
the point.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_from_tests_ai(name: str, filename: str) -> ModuleType:
    """Import a module out of the repository-root `tests/ai/` directory.

    Loaded by explicit file path rather than by putting the repository root on `sys.path`,
    because that root contains a `tests` package of its own and the two would collide under
    one import name. `conftest.py` uses the same trick for `stubs.py`; this lives here so a
    test module can reach the crew fixtures at import time, which a fixture cannot help with.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = REPO_ROOT / "tests" / "ai" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_image(
    *,
    size: tuple[int, int] = (600, 800),
    fmt: str = "JPEG",
    mode: str = "RGB",
    exif: bool = False,
    colour: tuple[int, int, int] = (40, 60, 90),
    **save_kwargs: object,
) -> bytes:
    """One synthetic photograph, optionally carrying EXIF with GPS and an orientation tag."""
    image = Image.new(mode, size, colour if mode != "RGBA" else (*colour, 255))
    buffer = io.BytesIO()

    if not exif:
        image.save(buffer, fmt, **save_kwargs)
        return buffer.getvalue()

    tags = image.getexif()
    tags[0x0112] = 6  # orientation: rotate 90 degrees, applied before the block is dropped
    tags[0x010F] = "ACME Phone"
    gps = tags.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 30.0, 0.0)
    gps[3] = "W"
    gps[4] = (0.0, 7.0, 0.0)
    image.save(buffer, fmt, exif=tags, **save_kwargs)
    return buffer.getvalue()


__all__ = ["load_from_tests_ai", "make_image"]
