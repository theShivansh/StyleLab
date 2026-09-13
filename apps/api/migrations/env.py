"""Alembic environment.

Blocker B12, closed in S11. Until now the schema existed wherever somebody had run
`Base.metadata.create_all` — which is fine for tests and for a laptop, and means a deployed
database can never receive a change. S11 made that concrete rather than theoretical by
adding a column (`assets.purged_at`, the retention flag): without a migration path, the
release that needs it cannot be applied to a database that already exists.

Two things here are deliberately different from the generated template.

**The URL comes from our settings, not from `alembic.ini`.** A second place that names the
database is a second place to get it wrong, and the one in the ini file is the one nobody
updates — so a migration would run against a developer's SQLite file while the application
talked to Postgres. `app.config.Settings.resolved_database_url` is the single answer, which
also means `DATABASE_URL` works here exactly as it does everywhere else.

**The metadata is imported from the application.** `--autogenerate` compares the models to
the live database, so it has to be the same `Base` the application uses, not a copy.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.config import get_settings
from app.db.models import Base
from app.db.session import build_engine

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is **not** cosmetic, and the generated template has
    # it the other way round. `fileConfig` defaults to disabling every logger that already
    # exists and is not named in the ini file — which here is every `stylelab.*` logger.
    #
    # Found by a test rather than reasoned about: adding `tests/test_migrations.py` made two
    # unrelated logging tests go red, because configuring Alembic in-process had silently
    # switched off the application's logging for the rest of the session. The same thing
    # would happen to a deployment that ran a migration in-process before serving, and there
    # the symptom is not a red test — it is an application that never logs again.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    """The database this migration runs against.

    `-x url=...` wins, so a one-off migration against a specific database does not require
    editing a file or exporting an environment variable. Otherwise the same URL the
    application resolves, including the local SQLite default.
    """
    supplied = context.get_x_argument(as_dictionary=True).get("url")
    return supplied or get_settings().resolved_database_url


def run_migrations_offline() -> None:
    """Emit SQL without connecting.

    `alembic upgrade head --sql` produces a script a DBA can read before anyone runs it,
    which is what makes a production migration reviewable rather than a leap.
    """
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER a column in place, so a change that Postgres does trivially
        # needs a table rebuild. Told to Alembic rather than discovered during a release.
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run against a live connection.

    Built through `app.db.session.build_engine` rather than `engine_from_config` so a SQLite
    migration gets the same `PRAGMA foreign_keys=ON` the application does. Without it a
    migration would run with the composite foreign keys switched off — which is precisely
    when you would want them on.
    """
    connectable = build_engine(_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
