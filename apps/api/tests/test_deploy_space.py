"""The Hugging Face Space, checked without Docker.

There is no Docker on the machine this was written on, so the image cannot be built here and
the first real build happens on Hugging Face — eight minutes away, with the failure in a log
somebody has to go and read. That is a bad feedback loop to have no tests in.

So this file asserts the things that would break that build, statically:

* every path the Dockerfile copies is a path `prepare.py` actually assembles
* the port in the Dockerfile matches `app_port` in the Space card
* nothing on the deny list can reach a Space repository, which is **public by default**

It does not assert that the image builds. Nothing here can. What it does is make the
predictable failures — a `COPY` pointing at a file nobody copied, a port that disagrees with
the card — fail in a second rather than in a build log.

It lives in the API suite because that is the Python suite CI runs, and a deployment check
nobody runs is a deployment check that is wrong by the time it matters.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SPACE = REPO / "deploy" / "hf-space"
DOCKERFILE = SPACE / "Dockerfile"


def _prepare_module():
    """Import `prepare.py` by path — it is a script beside a Dockerfile, not a package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("stylelab_space_prepare", SPACE / "prepare.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def assembled(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("space")
    _prepare_module().assemble(out / "build")
    return out / "build"


def _copy_sources() -> list[str]:
    """The build-context paths every `COPY` in the Dockerfile reads from."""
    sources: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$", line.strip())
        if match:
            sources.append(match.group(1))
    return sources


def test_every_path_the_dockerfile_copies_is_one_prepare_assembles(assembled):
    """The failure this file exists for.

    A `COPY apps/api/alembic.ini` against a build context that does not contain it fails the
    image build — on Hugging Face, minutes in, with the reason in a log rather than on a
    screen.
    """
    missing = [source for source in _copy_sources() if not (assembled / source).exists()]

    assert not missing, (
        f"the Dockerfile copies {missing}, which prepare.py does not assemble. "
        "Add them to _INCLUDE, or stop copying them."
    )


def test_the_dockerfile_copies_something_at_all():
    """Guards the parser above. A regex that silently matched nothing would make the test
    that uses it pass for the wrong reason."""
    assert len(_copy_sources()) >= 4


def test_the_exposed_port_matches_the_space_card():
    """Hugging Face reads `app_port` from the README frontmatter and ignores `EXPOSE`.

    So the two can disagree, and when they do the Space builds, starts, serves nothing, and
    reports no error worth reading.
    """
    card = (SPACE / "README.md").read_text(encoding="utf-8")
    app_port = re.search(r"^app_port:\s*(\d+)\s*$", card, re.MULTILINE)
    exposed = re.search(r"^EXPOSE\s+(\d+)\s*$", DOCKERFILE.read_text(encoding="utf-8"), re.M)

    assert app_port and exposed
    assert app_port.group(1) == exposed.group(1)


def test_the_space_card_has_the_frontmatter_hugging_face_requires():
    """Without it the Space is a static page that renders a README."""
    card = (SPACE / "README.md").read_text(encoding="utf-8")

    assert card.startswith("---\n")
    for key in ("title:", "sdk: docker", "app_port:"):
        assert key in card.split("---")[1]


@pytest.mark.parametrize(
    "name", [".env", ".env.example", "stylelab.db", "secrets.key", "wardrobe.sqlite3"]
)
def test_a_secret_file_cannot_reach_a_space_repository(tmp_path, name):
    """A Space repository is **public by default**, and `.env` is the file with the keys in it.

    Asserted by putting each one where it would have to be caught, rather than by trusting a
    `.gitignore` in a different directory to be right.
    """
    prepare = _prepare_module()
    planted = REPO / "apps" / "api" / "app" / name
    planted.write_text("GROQ_API_KEY=not-a-real-key\n", encoding="utf-8")
    try:
        out = tmp_path / "build"
        prepare.assemble(out)
        assert not (out / "apps" / "api" / "app" / name).exists()
    finally:
        planted.unlink(missing_ok=True)


def test_nothing_from_the_web_app_or_the_specs_is_shipped_in_a_python_image(assembled):
    """Not tidiness. Every megabyte is a slower cold start on a Space that sleeps, and a
    container is not a place to keep a second copy of the repository."""
    paths = {p.relative_to(assembled).as_posix() for p in assembled.rglob("*") if p.is_file()}

    assert not any(p.startswith("apps/web") for p in paths)
    assert not any(p.startswith("docs/") for p in paths)
    assert not any(p.startswith("tests/") for p in paths)
    assert not any("__pycache__" in p for p in paths)


def test_the_entrypoint_stops_the_container_when_a_migration_fails(assembled):
    """`set -e`, and it is the whole point of the file.

    Without it uvicorn starts against a schema no revision describes — which is exactly the
    failure S11 spent an afternoon on, arriving as "Something went wrong on our side" at
    every upload instead of as a failed deploy.
    """
    entrypoint = (assembled / "deploy/hf-space/entrypoint.sh").read_text(encoding="utf-8")
    # Commands only. The first version of this assertion compared positions in the whole
    # file and failed on the word "uvicorn" inside a comment that explains the ordering —
    # a test that was wrong about the thing it was checking, in the direction that reads
    # like a real bug.
    commands = [
        line.strip()
        for line in entrypoint.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    joined = "\n".join(commands)

    assert "set -euo pipefail" in commands
    assert any(line.startswith("alembic upgrade head") for line in commands)
    assert joined.index("alembic upgrade head") < joined.index("uvicorn")


def test_the_entrypoint_is_lf_so_the_shebang_survives_windows(assembled):
    """A CRLF shebang fails with `\\r: command not found` — a message that names nothing in
    this repository. `.gitattributes` pins `*.sh` to LF for this reason; this checks the file
    that actually ships."""
    raw = (assembled / "deploy/hf-space/entrypoint.sh").read_bytes()

    assert b"\r\n" not in raw


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed here")
def test_the_image_builds():  # pragma: no cover - requires docker
    """Runs where Docker exists, which is not the machine this was written on.

    Left in rather than omitted: it is the assertion the rest of this file approximates, and
    on any machine that can make it, it should.
    """
    import subprocess

    prepare = _prepare_module()
    out = REPO / "deploy" / "hf-space" / "build"
    prepare.assemble(out)
    result = subprocess.run(
        ["docker", "build", "-t", "stylelab-api:test", "."],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
