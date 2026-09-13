"""The environment preflight.

Every default in `app/config.py` is tuned so a fresh clone runs. Each was right on its own;
together they meant the application could not tell a laptop from a deployment. These tests
pin the split: `local` keeps every accommodation and says so, `production` refuses to start
on the ones that make the application incorrect.

The asymmetry is the thing being asserted. It would be easy to write a check that is simply
strict, and it would make `pnpm dev` fail for a developer who has done nothing wrong — which
is how a safety check gets a flag, and how a flag gets set to off.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.config import ENV_SYNONYMS, Settings
from app.domain.errors import ConfigurationError
from app.preflight import (
    FATAL_IN_PRODUCTION,
    MIN_SESSION_SECRET_CHARS,
    log_findings,
    verify_deployment,
)

#: A deployment with nothing left at its local default. The baseline the failure cases
#: perturb one setting at a time, so each test names one cause.
DEPLOYED = {
    "app_env": "production",
    "groq_api_key": "not-a-real-key",
    "session_secret": "s" * MIN_SESSION_SECRET_CHARS,
    "database_url": "postgresql+psycopg://user:pw@db.example.com/stylelab",
    "web_origin": "https://stylelab.example.com",
    "exa_api_key": "not-a-real-key",
    "supabase_url": "https://project.supabase.co",
    "storage_backend": "database",
    "job_backend": "database",
}


#: The settings preflight reads. Named here so the "bare clone" test can assert it is
#: looking at the *declared defaults* rather than at whatever is in the developer's `.env`.
PREFLIGHT_READS = (
    "session_secret",
    "database_url",
    "web_origin",
    "exa_api_key",
    "supabase_url",
    "storage_backend",
    "job_backend",
)


def settings_for(**over: object) -> Settings:
    """Settings with `.env` deliberately out of the picture.

    Found by this file: `Settings` reads `.env`, so a test written to assert what a fresh
    clone sees was in fact asserting what *this machine* has configured — and it passed
    here while it would have failed in CI, or the other way round, depending on whose
    laptop it ran on. `_env_file=None` is the whole fix, and the defaults below are then
    taken from the model rather than from the environment.
    """
    values: dict[str, object] = {"groq_api_key": "not-a-real-key", "_env_file": None}
    values.update({field: Settings.model_fields[field].default for field in PREFLIGHT_READS})
    values.update(over)
    return Settings(**values)  # type: ignore[arg-type]


def deployed(**over: object) -> Settings:
    values: dict[str, object] = {"_env_file": None}
    values.update(DEPLOYED)
    values.update(over)
    return Settings(**values)  # type: ignore[arg-type]


def settings_named(findings) -> set[str]:
    return {finding.setting for finding in findings}


# --- local: everything is advisory ---------------------------------------------------------


def test_a_bare_local_clone_starts_and_is_told_what_it_is_running_on():
    """The whole reason the defaults are permissive. This must never become fatal.

    A developer who has just cloned the repository and set `GROQ_API_KEY` has done
    everything the README asks. If preflight refused them, the next commit would add a flag
    to switch preflight off, and the commit after that would ship with the flag set.
    """
    # Asserted against the declared defaults, not against this machine: `web_origin`
    # defaulting to a local address is what makes the fourth finding absent below.
    assert Settings.model_fields["app_env"].default == "local"
    assert Settings.model_fields["web_origin"].default == "http://localhost:3000"

    findings = verify_deployment(settings_for())

    # Only the two that change what the application does *on this machine*. A local boot is
    # not told about `WEB_ORIGIN`, `DATABASE_URL` or `SUPABASE_URL`, because locally those
    # defaults are correct and a warning that fires when nothing is wrong is a warning
    # people learn to skip.
    assert settings_named(findings) == {"SESSION_SECRET", "EXA_API_KEY"}


def test_a_local_finding_says_what_it_costs_not_only_what_is_missing():
    """`consequence` is load-bearing, not decoration.

    "SESSION_SECRET is required" tells an operator what to type. "sessions stop verifying
    after a restart, and a second instance rejects this one's tokens" tells them whether to
    believe the next person who proposes deleting the check.
    """
    (finding,) = [f for f in verify_deployment(settings_for()) if f.setting == "SESSION_SECRET"]

    assert "generated for this process" in finding.problem
    assert "second instance" in finding.consequence
    assert str(finding).startswith("SESSION_SECRET: ")


def test_findings_are_logged_at_warning_so_an_aggregator_can_alert_on_them(caplog):
    with caplog.at_level(logging.WARNING, logger="stylelab.preflight"):
        log_findings(verify_deployment(settings_for()))

    assert [record.levelno for record in caplog.records] == [logging.WARNING] * 2
    assert any("SESSION_SECRET" in record.getMessage() for record in caplog.records)


# --- production: the accommodations become refusals -----------------------------------------


def test_a_fully_configured_deployment_passes_with_nothing_advisory():
    assert verify_deployment(deployed()) == []


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("session_secret", ""),
        ("database_url", ""),
        ("web_origin", "http://localhost:3000"),
    ],
)
def test_each_local_default_surviving_into_production_is_fatal(setting, value):
    with pytest.raises(ConfigurationError) as caught:
        verify_deployment(deployed(**{setting: value}))

    assert setting.upper() in str(caught.value)


def test_every_fatal_setting_is_reported_at_once_not_one_deploy_at_a_time():
    """The reason `verify_deployment` collects rather than raising on the first problem.

    Three settings wrong, fixed one per deploy, is three container builds to learn three
    things that were all knowable before the first one started.
    """
    with pytest.raises(ConfigurationError) as caught:
        verify_deployment(
            deployed(session_secret="", database_url="", web_origin="http://localhost:3000")
        )

    message = str(caught.value)
    assert "3 setting(s)" in message
    for setting in FATAL_IN_PRODUCTION:
        assert setting in message


def test_a_short_secret_is_fatal_because_it_looks_set_and_is_not():
    """Worse than no secret at all.

    Unset generates 256 random bits and logs a warning. `SESSION_SECRET=stylelab` generates
    nothing, logs nothing, and forges every session token in the system to anyone who
    guesses the product name.
    """
    with pytest.raises(ConfigurationError) as caught:
        verify_deployment(deployed(session_secret="stylelab"))

    assert "8 characters" in str(caught.value)
    assert "forges any session token" in str(caught.value)


def test_a_missing_trend_key_is_a_warning_in_production_not_a_refusal():
    """The distinction `app/main.py` already draws, held to at boot.

    The product composes good outfits with no trend context and discloses degradation 2.
    A boot check that refused to start over it would be treating a nice-to-have as the
    product — and the same check is the one that would later be switched off wholesale.
    """
    findings = verify_deployment(deployed(exa_api_key=""))

    assert settings_named(findings) == {"EXA_API_KEY"}


def test_local_storage_in_production_warns_rather_than_refusing():
    """Honest about a gap rather than pretending it is closed.

    Advisory rather than fatal because a mounted volume is a perfectly good answer and
    preflight cannot see whether there is one. So the check says what will happen — a deploy
    takes the photographs with it — and lets the operator decide.
    """
    findings = verify_deployment(deployed(storage_backend="local"))

    assert settings_named(findings) == {"STORAGE_BACKEND"}
    assert "volume" in findings[0].consequence


def test_in_memory_jobs_in_production_warn_and_say_what_the_user_sees():
    """The first defect the live deployment found, as a boot-time sentence.

    Advisory rather than fatal for the same reason storage is: one process forever is a
    legitimate deployment. The consequence names the symptom a user reports, because that is
    what an operator will be searching the logs for.
    """
    findings = verify_deployment(deployed(job_backend="memory"))

    assert settings_named(findings) == {"JOB_BACKEND"}
    assert "isn't in your wardrobe" not in findings[0].consequence  # no copy leaks into logs
    assert "404" in findings[0].consequence


def test_the_storage_warning_asks_about_the_store_and_not_about_supabase():
    """The check this replaced keyed on `SUPABASE_URL`, which was the wrong question.

    A deployment can have a Supabase project — this one does, for its database — and still
    be writing photographs to a container disk that will not survive the next deploy. The
    old check went quiet on exactly that arrangement, which is the arrangement S13 shipped
    into.
    """
    findings = verify_deployment(deployed(supabase_url="", storage_backend="database"))

    assert settings_named(findings) == set()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "https://127.0.0.1",
        "http://0.0.0.0:8080",
        "http://[::1]:3000",
    ],
)
def test_every_spelling_of_a_local_origin_is_caught(origin):
    with pytest.raises(ConfigurationError):
        verify_deployment(deployed(web_origin=origin))


def test_a_real_host_that_merely_contains_localhost_is_not_caught():
    """The check parses the origin rather than searching it for a word.

    `https://localhost.example.com` is a host somebody can own. Refusing to boot on it would
    be a check that is wrong in the direction nobody can debug, because the error message
    would be naming the thing they had correctly configured.
    """
    assert verify_deployment(deployed(web_origin="https://localhost.example.com")) == []


# --- APP_ENV accepts the spellings people write ---------------------------------------------


@pytest.mark.parametrize(
    ("written", "means"),
    [
        ("local", "local"),
        ("development", "local"),
        ("dev", "local"),
        ("DEVELOPMENT", "local"),
        ("  development  ", "local"),
        ("test", "local"),
        ("ci", "local"),
        ("production", "production"),
        ("prod", "production"),
        ("Production", "production"),
        ("staging", "production"),
        ("stage", "production"),
        ("", "local"),
    ],
)
def test_app_env_accepts_the_conventional_spellings(written, means):
    """Found by the obvious thing happening.

    Somebody set `APP_ENV=development` — the most common spelling of this variable anywhere —
    and the API stopped booting with a pydantic literal error naming two values. A setting
    invented in S11 that rejects the industry-standard value for itself is the setting's bug.

    `staging` maps to `production` on purpose rather than to `local`: a staging deployment has
    the same ephemeral filesystem and the same shared signing key as a real one, and is
    exactly where those defaults should be caught rather than tolerated.
    """
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, groq_api_key="not-a-real-key", app_env=written
    )

    assert settings.app_env == means


def test_a_value_nobody_meant_is_still_refused():
    """Silently treating `produciton` as local would switch off every production check over a
    typo — which is the failure this whole mechanism exists to prevent.

    The message names what is accepted, because a literal error listing two values when nine
    are allowed is a message that sends somebody to read the source.
    """
    with pytest.raises(ValidationError) as caught:
        Settings(  # type: ignore[call-arg]
            _env_file=None, groq_api_key="not-a-real-key", app_env="produciton"
        )

    message = str(caught.value)
    assert "produciton" in message
    assert "development" in message and "production" in message


def test_the_synonyms_only_ever_resolve_to_a_behaviour_the_application_has():
    """The map is data, so it can acquire a value the rest of the code does not handle."""
    assert set(ENV_SYNONYMS.values()) == {"local", "production"}
