"""`GET /internal/db-activity` — the scheduled connectivity check.

A Supabase project on the free tier pauses after a stretch with no database activity, so a
daily job touches it. The thing worth testing is that it is a **real** check rather than a
keep-alive wearing one's clothes: it opens a session against the configured database and
runs a statement, so an unreachable or misconfigured database fails the job.

Three properties carry the weight here, and the third is the one that is easy to get wrong:

1. a valid token gets a real answer
2. a missing or wrong token gets 401, and an unconfigured deployment gets 503 — a different
   problem deserving a different answer
3. **the token is checked before the database is touched**, so the endpoint cannot be used
   to make this API hammer its own database from outside
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.routers.internal import TOKEN_HEADER

TOKEN = "test-db-activity-token-not-a-real-credential"


@pytest.fixture
def configured(monkeypatch):
    """Set `DB_ACTIVITY_TOKEN` for the duration of a test.

    Through the settings cache rather than the environment: `get_settings` is `lru_cache`d
    and the app read it at boot, so setting an environment variable here would change
    nothing the running application can see.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "db_activity_token", TOKEN)
    return TOKEN


@pytest.fixture
def unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_activity_token", "")


# --- the happy path -----------------------------------------------------------------------


def test_a_valid_token_gets_a_real_answer_from_the_database(api, configured):
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: configured})

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["dialect"] == "sqlite"  # whatever the suite is pointed at
    assert isinstance(body["latency_ms"], int)
    assert body["checked_at"]


def test_the_response_carries_nothing_that_could_leak_a_credential(api, configured):
    """A Postgres URL contains a password. The boot log records the dialect only, and so
    does this — a monitoring endpoint that answers with its connection string is a
    credential disclosure with a status code of 200."""
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: configured})

    rendered = response.text.lower()
    for forbidden in ["password", "postgres://", "postgresql://", "sqlite:", "@", "://", TOKEN]:
        assert forbidden not in rendered, f"{forbidden!r} appeared in the response body"


def test_it_actually_executes_a_statement_rather_than_asserting_it_could(api, configured):
    """The difference between a connectivity check and a decoration.

    Counted at the engine, so a version of this endpoint that returned `{"database": "ok"}`
    without touching anything would fail here — which is exactly the implementation somebody
    reaches for when the real one is inconvenient.
    """
    from sqlalchemy import event

    engine = api.app.state.sessions.kw["bind"]
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = api.get("/internal/db-activity", headers={TOKEN_HEADER: configured})
        assert response.status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert any("SELECT 1" in statement.upper() for statement in statements)


# --- refusals ------------------------------------------------------------------------------


def test_a_missing_token_is_refused(api, configured):
    response = api.get("/internal/db-activity")

    assert response.status_code == 401


def test_a_wrong_token_is_refused(api, configured):
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: "not-the-token"})

    assert response.status_code == 401


def test_a_token_that_is_a_prefix_of_the_real_one_is_refused(api, configured):
    """`compare_digest`, not `==`. The prefix case is the one a naive comparison leaks
    timing on, and it is the one an attacker would actually walk."""
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: configured[:-1]})

    assert response.status_code == 401


def test_an_empty_token_header_is_refused_rather_than_matching_an_unset_secret(api, unconfigured):
    """The bug this guards is specific and quiet: with `DB_ACTIVITY_TOKEN` unset, an empty
    supplied token equals an empty expected token, and a naive check would let anybody in."""
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: ""})

    assert response.status_code == 503


def test_an_unconfigured_deployment_says_so_rather_than_claiming_a_bad_token(api, unconfigured):
    """A different problem, so a different answer.

    An operator who has set nothing should not spend an afternoon believing they set it
    wrongly. 503 rather than 401, and never 200.
    """
    response = api.get("/internal/db-activity", headers={TOKEN_HEADER: "anything"})

    assert response.status_code == 503


def test_a_session_token_cannot_be_presented_as_an_operations_credential(api, configured):
    """Different credential, different header, no overlap.

    A product session is handed to anyone who asks for one (blocker B15). If it also opened
    this endpoint, every visitor could reach it.
    """
    caller = api.start_session()

    response = api.get("/internal/db-activity", headers=caller.headers)

    assert response.status_code == 401


# --- the ordering property -------------------------------------------------------------------


def test_the_database_is_not_touched_until_the_token_has_been_checked(api, configured):
    """The security property, asserted as an absence.

    Without this ordering, an unauthenticated flood is a way to make this API open a
    connection per request and exhaust its own pool from the outside — a denial of service
    delivered through the endpoint added to *prevent* downtime.
    """
    from sqlalchemy import event

    engine = api.app.state.sessions.kw["bind"]
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        for headers in ({}, {TOKEN_HEADER: "wrong"}, {TOKEN_HEADER: ""}):
            assert api.get("/internal/db-activity", headers=headers).status_code == 401
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert statements == [], f"a refused request still queried the database: {statements}"


# --- shape ------------------------------------------------------------------------------------


def test_it_is_not_under_the_product_api_prefix(api, configured):
    """An operations endpoint beside `/health`, not part of the versioned wardrobe contract."""
    response = api.get("/api/v1/internal/db-activity", headers={TOKEN_HEADER: configured})

    assert response.status_code == 404


def test_health_is_left_alone(api):
    """`/health` stays liveness-only. Giving it a database query would turn every Postgres
    hiccup into an orchestrator restart loop, which is why there are two endpoints."""
    response = api.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
