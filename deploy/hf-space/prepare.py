"""Assemble and upload the Hugging Face Space that serves the STYLELAB API.

    python deploy/hf-space/prepare.py --dry-run          # assemble locally, upload nothing
    python deploy/hf-space/prepare.py --space you/name   # assemble and upload

## What it copies, and what it does not

The Space is a Python image. It gets `apps/api` — the application, its migrations and its
`alembic.ini` — plus the Dockerfile, the entrypoint and the Space card. It does not get the
web app, the test suites, the specs, or `data/samples`: a container is not a place to keep a
copy of the repository, and every megabyte is a slower cold start.

It explicitly does not copy `.env`, `.env.example`, `stylelab.db` or `var/`. That is not
tidiness — a Space repository is public by default, and `.env` is the file with the keys in
it. `_REFUSED` below is checked by name and by suffix rather than left to a `.gitignore`
somewhere else being right.

## Credentials

**This script never handles a secret.** It uploads code using whatever login the Hugging Face
CLI already has (`hf auth login`), and the API keys the Space needs are set by a human in the
Space's own settings page. A deployment script that takes an API key as an argument is a
deployment script that puts one in a shell history.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

#: Copied into the Space, as (source, destination) relative to the repo and Space roots.
_INCLUDE: list[tuple[str, str]] = [
    ("apps/api/app", "apps/api/app"),
    ("apps/api/migrations", "apps/api/migrations"),
    ("apps/api/pyproject.toml", "apps/api/pyproject.toml"),
    ("apps/api/alembic.ini", "apps/api/alembic.ini"),
    ("deploy/hf-space/Dockerfile", "Dockerfile"),
    ("deploy/hf-space/entrypoint.sh", "deploy/hf-space/entrypoint.sh"),
    ("deploy/hf-space/README.md", "README.md"),
]

#: Never copied, whatever else says so. Names and suffixes, checked on every file.
_REFUSED_NAMES = {".env", ".env.example", ".env.local", "stylelab.db", "token.txt"}
_REFUSED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".pyc"}
_REFUSED_DIRS = {"__pycache__", ".git", "var", "node_modules", ".venv", ".ruff_cache"}


def _refused(path: Path) -> bool:
    if path.name in _REFUSED_NAMES or path.suffix in _REFUSED_SUFFIXES:
        return True
    return any(part in _REFUSED_DIRS for part in path.parts)


def _copy_tree(source: Path, destination: Path) -> list[Path]:
    """Copy a directory, refusing anything on the deny list and reporting what landed."""
    copied: list[Path] = []
    for item in sorted(source.rglob("*")):
        if item.is_dir() or _refused(item.relative_to(REPO)):
            continue
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(target)
    return copied


def assemble(into: Path) -> list[Path]:
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)

    copied: list[Path] = []
    for source_name, destination_name in _INCLUDE:
        source = REPO / source_name
        destination = into / destination_name
        if not source.exists():
            raise SystemExit(f"missing from the repository: {source_name}")
        if source.is_dir():
            copied += _copy_tree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination)

    # Belt and braces. The deny list above is a rule about what is copied; this is a check on
    # what actually arrived, and the two are worth keeping separate — the first can be wrong
    # in a way only the second notices.
    leaked = [p for p in into.rglob("*") if p.is_file() and _refused(p.relative_to(into))]
    if leaked:
        raise SystemExit(f"refusing to upload: {[str(p) for p in leaked]}")

    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", help="Target Space, as 'owner/name'.")
    parser.add_argument("--dry-run", action="store_true", help="Assemble only; upload nothing.")
    parser.add_argument(
        "--out",
        default=str(HERE / "build"),
        help="Where to assemble the Space repository (default: deploy/hf-space/build).",
    )
    arguments = parser.parse_args()

    out = Path(arguments.out)
    copied = assemble(out)
    total = sum(p.stat().st_size for p in copied)
    print(f"assembled {len(copied)} files ({total / 1024:.0f} KB) into {out}")

    if arguments.dry_run or not arguments.space:
        print("\nnothing uploaded.")
        print("To upload:  python deploy/hf-space/prepare.py --space <owner>/<name>")
        print("First run:  hf auth login")
        return 0

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub is not installed:  pip install huggingface_hub", file=sys.stderr)
        return 1

    api = HfApi()
    # No token argument anywhere in this file. `HfApi` reads the CLI login, so the credential
    # stays where the user put it and never passes through an argument list.
    api.create_repo(arguments.space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(
        folder_path=str(out),
        repo_id=arguments.space,
        repo_type="space",
        commit_message="Deploy STYLELAB API",
    )
    print(f"\nuploaded to https://huggingface.co/spaces/{arguments.space}")
    print("The build will fail until the secrets in the Space card are set. That is the")
    print("boot check refusing to serve a misconfigured API rather than a problem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
