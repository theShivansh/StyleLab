"""Boot's schema check: strict about what the code needs, tolerant of what it does not.

The rule these pin down came from planning the first real rollout. Additive migrations put the
database ahead of the release that is still running, and a check that refused *any* difference
turned "migrate first, then deploy" into "migrate first, then watch the live release refuse its
next cold start". So the check is asymmetric, and both halves are asserted here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.models import Base
from app.db.session import build_engine
from app.domain.errors import ConfigurationError
from app.preflight import verify_schema


@pytest.fixture
def engine(tmp_path):
    eng = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'schema.db').as_posix()}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_a_database_that_matches_the_models_boots(engine):
    verify_schema(engine)


def test_a_table_added_by_a_later_release_does_not_stop_this_one_booting(engine):
    """The rollout case. Migration applied, new code not live yet, old code cold-starts."""
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE added_by_a_later_release (id INTEGER PRIMARY KEY)"))

    verify_schema(engine)


def test_a_nullable_column_added_by_a_later_release_is_tolerated(engine):
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN added_later TEXT"))

    verify_schema(engine)


def test_a_table_the_models_need_is_still_fatal(engine):
    """The half that must not loosen. This is the S11 failure: queries against a table that
    is not there, arriving as "Something went wrong on our side" at every request."""
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE jobs"))

    with pytest.raises(ConfigurationError, match="alembic upgrade head"):
        verify_schema(engine)


def test_the_refusal_names_the_operation_and_never_the_contents(engine):
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE asset_blobs"))

    with pytest.raises(ConfigurationError) as refused:
        verify_schema(engine)

    assert "add_table" in str(refused.value)
    assert "remove_" not in str(refused.value)
