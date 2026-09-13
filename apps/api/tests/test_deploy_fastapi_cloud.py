"""The deployment contract, checked here rather than in a build log.

The backend deploys to FastAPI Cloud, which builds from `apps/api` — the directory holding
`pyproject.toml` — installs it, and serves the entrypoint with `fastapi run`. There is no
Dockerfile and no start command, which removes a whole class of mistakes and leaves a
narrower one: **facts about the deployment that live in two places and can disagree.**

That is the shape of every defect S12 found by trying to ship, so every test here reads
*both* sources rather than restating one of them:

* the entrypoint declared in `pyproject.toml` against the object that actually exists
* the Python version pinned for the platform against the one CI tests on
* the upload ignore list against the files the application needs at runtime
* the variables `docs/DEPLOYMENT.md` tells an operator to set against the settings that exist

None of this asserts the build succeeds; nothing here can. It asserts that the predictable
ways to make it fail are absent.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"
DEPLOYMENT_DOC = REPO / "docs" / "DEPLOYMENT.md"

#: The Application Directory set in the FastAPI Cloud dashboard. Relative to the repository
#: root, and the directory this suite lives under.
APPLICATION_DIRECTORY = "apps/api"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((API / "pyproject.toml").read_text(encoding="utf-8"))


# --- what the platform runs ------------------------------------------------------------------


def test_the_application_directory_is_where_pyproject_lives(pyproject):
    """The one field typed into the dashboard, and the only one nothing else can check.

    FastAPI Cloud installs from the directory holding `pyproject.toml`. Leaving it blank on a
    monorepo is the documented first failure — the build finds no project at the repository
    root — so the value is written down here and in docs/DEPLOYMENT.md.
    """
    assert (REPO / APPLICATION_DIRECTORY / "pyproject.toml").is_file()
    assert APPLICATION_DIRECTORY in DEPLOYMENT_DOC.read_text(encoding="utf-8")


def test_the_cli_is_a_dependency_because_the_platform_is_what_runs_the_app(pyproject):
    """`fastapi[standard]`, not bare `fastapi`.

    The extra is what brings `fastapi-cli`. Without it the project installs cleanly and then
    there is no `fastapi run` to serve it — a failure that arrives after the build, which is
    the expensive place for it to arrive.
    """
    dependencies = pyproject["project"]["dependencies"]
    assert any(d.startswith("fastapi[standard]") for d in dependencies), dependencies


def test_the_declared_entrypoint_is_a_real_fastapi_application(pyproject):
    """Declared rather than auto-detected, and then checked against the object.

    `app/main.py` is on the platform's detection list today. The declaration costs one line
    and removes a dependency on that list staying the same; this test is what makes the
    declaration worth more than a comment.
    """
    from fastapi import FastAPI

    entrypoint = pyproject["tool"]["fastapi"]["entrypoint"]
    module_path, _, attribute = entrypoint.partition(":")

    import importlib

    module = importlib.import_module(module_path)

    assert isinstance(getattr(module, attribute), FastAPI)


def test_the_python_pin_agrees_with_the_version_ci_tests_on():
    """The S12 defect, in the place it would happen next.

    `requires-python` is a range, and FastAPI Cloud resolves a range to the newest version in
    it. So without a pin the platform would build on 3.12 while CI proved 3.11 — two green
    stacks, neither of them the other, which is exactly how a suite stays green against a
    version the agent framework does not support.
    """
    pinned = (API / ".python-version").read_text(encoding="utf-8").strip()
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    tested = set(re.findall(r'python-version:\s*"([^"]+)"', workflow))

    assert tested, "CI no longer pins a python version; this test cannot check agreement"
    assert tested == {pinned}, f"platform builds on {pinned}, CI proves {sorted(tested)}"


def test_the_pinned_python_is_one_the_project_declares_support_for(pyproject):
    requires = pyproject["project"]["requires-python"]
    pinned = (API / ".python-version").read_text(encoding="utf-8").strip()

    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    # A `.python-version` of "3.11" means the 3.11 series; `3.11.0` is the lowest member and
    # is what an exclusive upper bound would have to exclude for the pin to be wrong.
    assert Version(f"{pinned}.0") in SpecifierSet(requires)


# --- what gets uploaded -----------------------------------------------------------------------


def test_nothing_the_running_app_needs_is_excluded_from_the_upload():
    """`.fastapicloudignore` trims the upload. It must not trim the deployment.

    `migrations/` and `alembic.ini` are the ones worth naming: they are not imported by the
    application, so nothing else in this suite would notice them going missing, and their
    absence surfaces as a schema that cannot be upgraded from a shell that no longer has the
    revisions.
    """
    ignored = [
        line.strip()
        for line in (API / ".fastapicloudignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    required = ["app/", "app", "migrations/", "migrations", "alembic.ini", "pyproject.toml"]
    assert not set(ignored) & set(required), ignored


def test_the_ignore_file_does_not_re_include_an_env_file():
    """The S12 incident, as a rule a file cannot break.

    `.fastapicloudignore` can *un-ignore* paths with `!`, which is precisely the mechanism
    that would put a local `.env` back into an upload after `.gitignore` kept it out of the
    repository. Nothing in this project has a reason to do that.
    """
    text = (API / ".fastapicloudignore").read_text(encoding="utf-8")

    assert not re.search(r"^\s*!.*\.env", text, re.MULTILINE), text


# --- what an operator is told to set ------------------------------------------------------------


def _documented_api_variables() -> set[str]:
    """Environment variable names from the API sections of docs/DEPLOYMENT.md.

    Scoped to the API sections deliberately: the same document also carries `NEXT_PUBLIC_*`,
    which belongs to the web build and is not a setting this application has.
    """
    text = DEPLOYMENT_DOC.read_text(encoding="utf-8")
    start = text.index("### API — required")
    end = text.index("### Web")

    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text[start:end], re.MULTILINE))


def test_every_variable_the_guide_names_is_a_setting_that_exists():
    """A deployment guide that names a variable nothing reads is worse than one that omits it.

    The operator sets it, the behaviour does not change, and the thing they were trying to
    fix is still broken — with the documentation agreeing that they did it right. S12 found
    this in the other direction (a driver the guide required and nothing installed); this is
    the same disagreement with the arrow reversed.
    """
    from app.config import Settings

    fields = {name.upper() for name in Settings.model_fields}

    assert _documented_api_variables() <= fields, sorted(_documented_api_variables() - fields)


def test_the_settings_this_deployment_turns_on_are_documented():
    """The four that are not defaults on the target platform.

    A managed runtime with no volume, more than one process and a proxy in front needs all four
    set, and each one is silent when it is wrong: photographs disappear, a poll reports a running
    job as missing, every visitor shares one rate-limit bucket, and the schema is whatever the
    last person did by hand.
    """
    documented = _documented_api_variables()

    for variable in ("STORAGE_BACKEND", "JOB_BACKEND", "TRUSTED_PROXY_HOPS", "APP_ENV"):
        assert variable in documented, variable
