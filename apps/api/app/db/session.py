"""Engine and session construction.

`build_engine` takes a URL and has no default and raises on a blank one. `get_engine` reads
settings, where an unconfigured `DATABASE_URL` resolves to a local **file**. Neither can
reach a throwaway in-memory database, for the same reason there is no demo mode: a silent
downgrade that looks like it worked is worse than a loud failure at boot. A file on disk is
not that downgrade — the wardrobe is still there tomorrow, and the dialect is logged.

SQLite gets `PRAGMA foreign_keys = ON` on every connection. It is off by default, which
would quietly turn the composite foreign keys in `app.db.models` — the ones that make
cross-user leakage unrepresentable — into decoration. `tests/test_persistence.py` asserts
the pragma is on, because a constraint nobody enforces is worse than no constraint at all:
it reads like a guarantee.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base
from app.domain.errors import ConfigurationError


def build_engine(url: str, *, echo: bool = False) -> Engine:
    """An engine for an explicit URL."""
    if not url:
        raise ConfigurationError("build_engine requires a database URL")

    engine = create_engine(url, echo=echo, future=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enforce_foreign_keys(connection, _record):  # pragma: no cover - driver callback
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine(*, echo: bool = False) -> Engine:
    """The configured engine, or the local file default.

    `Settings.resolved_database_url` fills in a file-backed SQLite URL when nothing is
    configured. That is not the fallback this module's docstring refuses: the prohibition is
    on an **in-memory** database, which vanishes on restart while looking like it worked.
    A named file does not, and the dialect is logged at boot.

    The distinction earned itself in S6. `.env.example` ships `DATABASE_URL=` with no value,
    pydantic-settings reports that as `""` rather than as absent, and a blank-means-refuse
    rule turned a correctly-followed setup instruction into a boot failure telling the
    developer to configure the thing they had just configured.

    It still raises if the resolved URL is somehow empty, because `build_engine` has no
    default of its own and nothing should be able to reach it without one.
    """
    return build_engine(get_settings().resolved_database_url, echo=echo)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions that do not expire on commit.

    The repository converts rows to frozen domain objects and hands those out, so callers
    never hold a live row and a post-commit refresh would be pure overhead.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create the schema. Local and test use only — migrations land in S11 with deployment."""
    Base.metadata.create_all(engine)


__all__ = ["build_engine", "create_all", "get_engine", "session_factory"]
