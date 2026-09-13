"""Environment preflight: the settings that are fine on a laptop and wrong in production.

Every default in `app/config.py` leans toward *a fresh clone runs*, and each of those
choices was right on its own. Together they add up to something this phase had to look at:
**the application cannot tell a laptop from a deployment.** An ephemeral signing key, a
SQLite file in the working directory, a CORS origin of `http://localhost:3000` — all three
are correct locally, all three are broken in a container, and not one of them says so.

The failure mode is the expensive kind, because none of it looks like a crash:

* an ephemeral `SESSION_SECRET` means a deploy silently logs every visitor out, and a second
  replica rejects the first replica's tokens — so a user's wardrobe disappears roughly half
  the time, depending on which instance the load balancer picked
* a SQLite file on a container filesystem means the whole database is deleted on the next
  deploy, and nobody finds out until someone comes back
* a `localhost` CORS origin means every browser request fails preflight, which reads from
  the outside exactly like the API being down

So: one function, called at boot, that knows which environment it is in. `APP_ENV=local`
(the default) keeps every accommodation and warns. `APP_ENV=production` turns the
accommodations into refusals.

## Why it collects findings instead of raising on the first one

An operator fixing a deployment wants the list. Raising on `SESSION_SECRET` alone means
they set it, redeploy, wait, and get told about `DATABASE_URL` — three round trips through a
container build to learn three things that were all knowable at once. `verify_deployment`
checks everything and raises once, with all of it.

## Why it is a boot check and not a runtime one

Same reason `verify_models` is (`app/adapters/boot.py`): a configuration error is not
retryable, no user request will fix it, and the person who can act on it is watching the
deploy log, not the error rate. Fail where they are looking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Engine

from app.domain.errors import ConfigurationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config import Settings

logger = logging.getLogger("stylelab.preflight")

#: A secret shorter than this is worse than an absent one: absent is loud and generates 256
#: random bits, while `SESSION_SECRET=stylelab` is silent and forgeable by anyone who
#: guesses the product name. 32 characters is the length of the generated default it
#: replaces, so the bar is "at least as good as having set nothing".
MIN_SESSION_SECRET_CHARS = 32

#: Hosts that mean "somebody left the local default in". Checked as the origin's host so
#: `http://localhost:3000` and `https://127.0.0.1` are both caught.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing that is not right, and what it will cost.

    `consequence` is not decoration. A boot failure that says "SESSION_SECRET is required"
    tells an operator what to type; one that says what breaks without it tells them whether
    to believe the next person who suggests removing the check.
    """

    setting: str
    problem: str
    consequence: str

    def __str__(self) -> str:
        return f"{self.setting}: {self.problem} — {self.consequence}"


def verify_deployment(settings: Settings) -> list[Finding]:
    """Check the environment. Returns advisory findings; raises on fatal ones.

    In `local` every finding is advisory and returned for logging. In `production` the
    findings that make the application incorrect — not merely inconvenient — are collected
    and raised together as one `ConfigurationError`.
    """
    findings = _findings(settings)
    if settings.app_env != "production":
        # Locally, most of these are not findings at all — `WEB_ORIGIN=http://localhost:3000`
        # is *correct* on a laptop, and warning about it on every boot is how a developer
        # learns to skim past preflight, including on the day it says something new.
        return [finding for finding in findings if finding.setting in WARNED_LOCALLY]

    fatal = [finding for finding in findings if finding.setting in FATAL_IN_PRODUCTION]
    advisory = [finding for finding in findings if finding.setting not in FATAL_IN_PRODUCTION]
    if fatal:
        listed = "\n  - ".join(str(finding) for finding in fatal)
        raise ConfigurationError(
            f"APP_ENV=production, but {len(fatal)} setting(s) still hold their local "
            f"defaults:\n  - {listed}\n"
            "These are the defaults that let a fresh clone run. See docs/DEPLOYMENT.md."
        )
    return advisory


#: Fatal in production. Everything else is a warning, and the split is deliberate: a setting
#: is on this list when leaving it wrong makes the deployment *incorrect*, not when it makes
#: it less good. `EXA_API_KEY` is not here — the product composes outfits without trends and
#: discloses the degradation, which is a documented state and not a broken one.
#:
#: `STORAGE_BACKEND` is not here either, and that one is a closer call since S13: left at
#: `local` on a runtime with no volume, photographs really are lost. It stays advisory
#: because a mounted volume is a perfectly good answer and preflight cannot see whether one
#: is there — refusing would block the deployments that had already solved it.
FATAL_IN_PRODUCTION = frozenset({"SESSION_SECRET", "DATABASE_URL", "WEB_ORIGIN"})

#: Worth saying on a laptop too, because these two change what the application *does right
#: now* rather than what it would do if deployed. An unset `SESSION_SECRET` is the one that
#: interrupted a demo rehearsal in S6 (blocker B6): the dev server restarted, every image
#: link stopped verifying, and the wardrobe on screen went blank for no visible reason.
#: `EXA_API_KEY` is here because its absence silently changes every composition's
#: degradation level.
#:
#: The rest are correct locally and only wrong deployed. Warning about those on every `pnpm
#: dev` would teach a developer to skim preflight, which costs more than it buys.
WARNED_LOCALLY = frozenset({"SESSION_SECRET", "EXA_API_KEY"})


def _findings(settings: Settings) -> list[Finding]:
    findings: list[Finding] = []

    secret = settings.session_secret
    if not secret:
        findings.append(
            Finding(
                "SESSION_SECRET",
                "not set, so tokens are signed with a key generated for this process",
                "sessions and image links stop verifying after a restart, and a second "
                "instance rejects this one's tokens",
            )
        )
    elif len(secret) < MIN_SESSION_SECRET_CHARS:
        findings.append(
            Finding(
                "SESSION_SECRET",
                f"is {len(secret)} characters; at least {MIN_SESSION_SECRET_CHARS} are needed",
                "a short secret is guessable, and a guessed one forges any session token "
                "and any image capability in the system",
            )
        )

    if not settings.database_url:
        findings.append(
            Finding(
                "DATABASE_URL",
                "not set, so the wardrobe lives in a SQLite file in the working directory",
                "a container filesystem does not survive a deploy, so every wardrobe is "
                "deleted on the next release",
            )
        )

    if _is_local_origin(settings.web_origin):
        findings.append(
            Finding(
                "WEB_ORIGIN",
                f"is {settings.web_origin!r}, which is a local address",
                "CORS preflight refuses the deployed front end, and every request fails in "
                "a way that looks like the API being down",
            )
        )

    if not settings.exa_api_key:
        findings.append(
            Finding(
                "EXA_API_KEY",
                "not set, so the Trend Scout does not run",
                "every composition reports degradation level 2; outfits are unaffected",
            )
        )

    if settings.storage_backend != "database":
        findings.append(
            Finding(
                "STORAGE_BACKEND",
                f"is {settings.storage_backend!r}, so uploaded images are written to the "
                "container filesystem",
                "a managed runtime replaces that filesystem on every deploy and discards it "
                "when the app scales to zero, so the wardrobe rows outlive the photographs "
                "they point at and a user is shown broken pictures of their own clothes. "
                "Set STORAGE_BACKEND=database, or mount a volume at STORAGE_ROOT",
            )
        )

    if settings.job_backend != "database":
        findings.append(
            Finding(
                "JOB_BACKEND",
                f"is {settings.job_backend!r}, so job records live in the memory of one process",
                "a redeploy, a restart or a second replica answers 404 to a poll for a job "
                "that is still running, and the upload card fails with a message about a "
                "missing item while the garment is being read. Set JOB_BACKEND=database",
            )
        )

    return findings


def _is_local_origin(origin: str) -> bool:
    """Is this origin a local address?

    Parsed rather than substring-matched: `https://localhost.example.com` is a real host
    that contains the word, and refusing to start over it would be a check that is wrong in
    the direction nobody can debug.
    """
    from urllib.parse import urlsplit

    host = urlsplit(origin).hostname
    return host is not None and host.lower() in LOCAL_HOSTS


def verify_schema(engine: Engine) -> None:
    """Refuse to serve against a database that does not match the models.

    Written after this exact failure, live, during the S11 audit. The local database had been
    created by `create_all` before `assets.purged_at` existed; `create_all` adds missing
    *tables* and never missing *columns*, so it silently did nothing. Every upload then died
    on `no such column: assets.purged_at` and the user-facing result was
    *"Something went wrong on our side"* — the correct message for an unclassified error and
    a useless one for a problem with a one-line fix.

    Fatal in every environment, which is a stronger stance than the rest of this module
    takes. The justification is that there is no degraded mode here: a schema the queries do
    not match means every request fails anyway, so the only question is whether the operator
    finds out from a boot message that names the fix or from a stream of 500s that does not.

    Uses Alembic's own comparison — the same one `--autogenerate` runs — so this check and
    `tests/test_migrations.py` cannot come to different conclusions about what "matches"
    means.

    ## What it tolerates, and why that is not a loosening

    Something the database has and the models do not — a table, a column, an index — is
    **allowed**. Something the models need and the database lacks is still fatal.

    The first version refused both, and S13b found what that cost while planning a rollout on
    the live deployment. Every additive migration puts the database ahead of the release that
    is still running. With a check that refused extra tables, applying the migration first
    stops that release surviving its next cold start — and on a platform that scales to zero,
    the next cold start is minutes away. Deploying the code first fails too, because the new
    release is missing its table. The strict check made the only safe ordering impossible.

    The asymmetry is the real rule: a query can only fail on what it asks for. An additive
    column must be nullable or carry a server default, or the running release's inserts fail
    — which is a rule for whoever writes the migration, not something this check can see.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.models import Base

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        differences = [
            entry
            for entry in compare_metadata(context, Base.metadata)
            if not _operation(entry).startswith("remove_")
        ]

    if not differences:
        return

    # Operation names only; enough detail to act on, and no table contents anywhere near it.
    summary = ", ".join(sorted({_operation(entry) for entry in differences}))
    raise ConfigurationError(
        f"the database schema does not match the models ({len(differences)} difference(s): "
        f"{summary}).\n"
        "Run `cd apps/api && alembic upgrade head`.\n"
        "If this database predates the migrations (created by create_all before S11), it is "
        "not described by any revision: recreate it, or apply the missing columns by hand "
        "and then `alembic stamp head`. See docs/DEPLOYMENT.md."
    )


def _operation(entry: object) -> str:
    """The operation name of one Alembic diff entry.

    A tuple per change — `("add_table", table)` — or a list of tuples for a group of changes
    to one column. `remove_*` is the database holding something the models do not mention.
    """
    if isinstance(entry, list):
        return str(entry[0][0]) if entry else ""
    return str(entry[0])  # type: ignore[index]


def log_findings(findings: list[Finding]) -> None:
    """Say what is not right, once, at boot.

    WARNING rather than INFO. These are all things somebody will eventually be surprised by,
    and a line nobody's log aggregator alerts on is a line that was not worth writing.
    """
    for finding in findings:
        logger.warning("preflight: %s", finding)


__all__ = [
    "FATAL_IN_PRODUCTION",
    "LOCAL_HOSTS",
    "MIN_SESSION_SECRET_CHARS",
    "WARNED_LOCALLY",
    "Finding",
    "log_findings",
    "verify_deployment",
    "verify_schema",
]
