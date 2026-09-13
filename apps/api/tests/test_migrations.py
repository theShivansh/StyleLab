"""The migrations, and the one thing that keeps them true.

Blocker B12 was "there are no migrations". Adding one closes it exactly once; what keeps it
closed is this file, because the real failure mode is not "nobody wrote a migration" — it is
**somebody adds a column to a model, `create_all` picks it up, every test passes, and the
deployed database never gets it.** The models and the migrations drift apart silently and
the first symptom is an `UndefinedColumn` in production.

So the assertion is not "a migration exists". It is that a database built by running the
migrations is **indistinguishable** from one built by `create_all` — which is the same
comparison `alembic revision --autogenerate` makes, run as a test instead of as a command
somebody remembers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.db.models import Base
from app.db.session import build_engine

API_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    # Through `-x`, the same seam a one-off production migration uses, so the test exercises
    # the path an operator would actually take rather than a private one.
    config.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    return config


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite+pysqlite:///{(tmp_path / 'migrated.db').as_posix()}"


def upgrade_to_head(url: str) -> None:
    from alembic import command

    command.upgrade(alembic_config(url), "head")


def test_the_migrations_build_the_schema_the_models_describe(db_url):
    """The assertion that makes the migration worth having.

    `compare_metadata` is what `--autogenerate` runs. An empty diff means a fresh database
    built by `alembic upgrade head` and one built by `create_all` are the same database —
    so adding a column to a model without a migration turns this red, in CI, rather than in
    production three weeks later.
    """
    upgrade_to_head(db_url)

    engine = build_engine(db_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], (
        "the models and the migrations disagree. Run:\n"
        "  cd apps/api && alembic revision --autogenerate -m 'describe the change'\n"
        f"diff: {differences}"
    )


def test_every_table_the_application_reads_exists_after_a_migration(db_url):
    """Named explicitly as well as compared structurally.

    `compare_metadata` would also be satisfied by a migration that created nothing and a
    `Base` that described nothing. This is the cheap sanity check that the baseline is not
    empty.
    """
    upgrade_to_head(db_url)

    engine = build_engine(db_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {
        "users",
        "assets",
        "wardrobe_items",
        "item_extractions",
        "outfits",
        "outfit_items",
        "saved_outfits",
        "style_profiles",
    } <= tables


def test_the_retention_column_is_in_the_migration_and_not_only_in_the_model(db_url):
    """`assets.purged_at` is the column that made B12 concrete.

    It is the flag that records a photograph's bytes are actually gone
    (`app/services/retention.py`). A deployment whose database lacks it cannot run the
    sweep, so "we delete your photographs after thirty days" would silently stop being true.
    """
    upgrade_to_head(db_url)

    engine = build_engine(db_url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("assets")}
    finally:
        engine.dispose()

    assert "purged_at" in columns
    assert "deleted_at" in columns


def test_configuring_alembic_does_not_switch_off_the_application_logging(db_url):
    """The bug this file found on the day it was written.

    Alembic's generated `env.py` calls `logging.config.fileConfig(...)`, whose default is
    `disable_existing_loggers=True` — so configuring it disables every logger not named in
    `alembic.ini`, which is every `stylelab.*` logger there is.

    It surfaced as two unrelated logging tests going red once this file existed, which is a
    lucky way to find it. The unlucky way is a deployment that runs a migration in-process
    before serving and then never logs anything again.

    Captured with a handler of its own rather than `caplog`, because `fileConfig` also
    *replaces* the root handlers — including pytest's. That second effect is inherent to
    configuring logging from a file and is harmless across tests; the one being guarded here
    is the permanent one.
    """
    import logging

    upgrade_to_head(db_url)

    captured: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = Collect()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        for name in ("stylelab", "stylelab.preflight", "stylelab.generation", "stylelab.crew"):
            logger = logging.getLogger(name)
            assert not logger.disabled, f"{name} was silenced by configuring alembic"
            logger.warning("still audible: %s", name)
    finally:
        root.removeHandler(handler)

    assert len(captured) == 4


def test_there_is_exactly_one_head():
    """Two heads mean two branches of history and `upgrade head` refusing to choose.

    It happens when two people generate a revision from the same parent, and it is
    discovered at the worst moment: during a deploy, by a command that does nothing.
    """
    script = ScriptDirectory(str(API_ROOT / "migrations"))

    heads = script.get_heads()

    assert len(heads) == 1, f"multiple migration heads: {heads}. Merge them with `alembic merge`."


def test_every_revision_can_be_walked_back():
    """A migration with no `downgrade` is a one-way door.

    Not because downgrades are run often — they are not — but because writing one forces the
    author to know what their migration did, and a `pass` in the body is a note that nobody
    did.
    """
    script = ScriptDirectory(str(API_ROOT / "migrations"))
    offenders = []

    for revision in script.walk_revisions():
        source = Path(revision.path).read_text(encoding="utf-8")
        body = source.split("def downgrade()", 1)
        if len(body) == 1:
            offenders.append(f"{revision.revision}: no downgrade()")
        elif "op." not in body[1]:
            offenders.append(f"{revision.revision}: downgrade() does nothing")

    assert not offenders, "\n".join(offenders)


def test_a_postgres_url_can_actually_be_opened():
    """The driver `docs/DEPLOYMENT.md` tells operators to use must be installed.

    Found in S12 by trying to deploy. The deployment guide has said
    `DATABASE_URL=postgresql+psycopg://…` since S11 and nothing in `pyproject.toml` could
    open one — the container would have built and then failed at boot on
    `ModuleNotFoundError: No module named 'psycopg'`.

    Asserted by building the engine, which resolves and imports the DBAPI module, and not by
    connecting: this suite must not need a Postgres server. The failure mode being guarded
    is a missing *driver*, and that is exactly what engine construction catches.
    """
    engine = build_engine("postgresql+psycopg://user:pw@db.example.invalid:5432/stylelab")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_the_deployment_guide_and_the_dependency_list_name_the_same_driver():
    """The two were out of sync for a whole phase, in a file nobody runs.

    Read from both rather than restated here, so this cannot pass by agreeing with itself.
    """
    import re
    import tomllib

    guide = (API_ROOT.parents[1] / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    drivers = set(re.findall(r"postgresql\+(\w+)://", guide))
    assert drivers, "the deployment guide no longer shows a Postgres URL"

    declared = " ".join(pyproject["project"]["dependencies"])
    for driver in drivers:
        assert driver in declared, (
            f"docs/DEPLOYMENT.md tells operators to use postgresql+{driver}:// and "
            f"pyproject.toml does not declare it"
        )
