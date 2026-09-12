"""Keeping image capabilities out of the access log.

docs/SECURITY-PRIVACY.md: signed URLs are "never logged". The wardrobe screen renders one
image URL per garment, so without this the access log of a single session holds a working
link to every photograph in it — and a log file is the thing most likely to be copied into
a support ticket, a paste bin or a log aggregator.

The tests exercise the filter through the logging machinery rather than calling `sub`
directly, because the bug it exists to prevent is specifically about *where* uvicorn keeps
the request line.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_setup import RedactImageTokens, install_log_redaction

TOKEN = "eyJleHAiOjE3OTE4MjU4MTN9.r_IqieifV2HBJMIJJJTWItMKndqok13UBTkIZhbyWVI"
PATH = f"/api/v1/assets/asset_abc123/{TOKEN}"


@pytest.fixture
def captured():
    """A logger with the filter installed and its output collected."""
    records: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("stylelab.test.redaction")
    logger.handlers = [Collect()]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addFilter(RedactImageTokens())
    yield logger, records
    logger.handlers = []
    logger.filters = []


def test_a_token_in_the_message_is_redacted(captured):
    logger, records = captured

    logger.info("GET %s HTTP/1.1" % PATH)  # noqa: UP031 - a pre-formatted message on purpose

    assert TOKEN not in records[0]
    assert "[redacted]" in records[0]


def test_a_token_in_the_arguments_is_redacted(captured):
    """The case that matters, and the one a naive filter misses.

    Uvicorn's access logger emits a format string and keeps the request line in
    `record.args`. A filter that only rewrote `record.msg` would find `'%s - "%s" %d'` —
    nothing sensitive in it — and pass the credential straight through.
    """
    logger, records = captured

    logger.info('%s - "%s %s HTTP/1.1" %d', "127.0.0.1:1", "GET", PATH, 200)

    assert TOKEN not in records[0]
    assert "[redacted]" in records[0]


def test_the_asset_id_survives_so_the_log_still_says_what_was_served(captured):
    logger, records = captured

    logger.info("GET %s", PATH)

    assert "asset_abc123" in records[0]


def test_dict_style_arguments_are_redacted_too(captured):
    logger, records = captured

    logger.info("%(method)s %(path)s", {"method": "GET", "path": PATH})

    assert TOKEN not in records[0]


def test_nothing_else_is_touched(captured):
    """A filter that mangles ordinary log lines gets switched off, which defeats it."""
    logger, records = captured

    logger.info("extraction stored for %s in %dms", "item_1", 412)

    assert records[0] == "extraction stored for item_1 in 412ms"


def test_non_string_arguments_pass_through_unharmed(captured):
    logger, records = captured

    logger.info("counted %d over %s", 7, None)

    assert records[0] == "counted 7 over None"


def test_the_filter_returns_true_so_records_are_not_dropped():
    """Redaction, not suppression. A filter that returned False would delete the access log."""
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "GET %s", (PATH,), None
    )
    assert RedactImageTokens().filter(record) is True


def test_installation_reaches_the_loggers_that_see_a_request_path():
    install_log_redaction()

    for name in ("uvicorn.access", "uvicorn.error", "stylelab"):
        logger = logging.getLogger(name)
        assert any(isinstance(f, RedactImageTokens) for f in logger.filters), name
        # Handlers too: a filter on a logger does not run for records propagated up from a
        # child, and `uvicorn.access` is exactly that shape.
        for handler in logger.handlers:
            assert any(isinstance(f, RedactImageTokens) for f in handler.filters)


def test_the_served_image_path_is_the_shape_the_filter_matches(api, stubs, wait_for_job):
    """Guards against the filter and the route drifting apart.

    The regex is written against `/assets/<id>/<token>`. If the route ever moved the token —
    into a query string, or to a different segment — the filter would silently stop matching
    and nothing else would fail. So the real URL is checked against the real filter.
    """
    api.transport_double.default = stubs.fixture("extraction_success.json")
    caller = api.start_session()

    body = api.post(
        "/api/v1/wardrobe/items",
        files=[("images[]", ("s.png", _png(), "image/png"))],
        headers=caller.headers,
    ).json()["items"][0]
    wait_for_job(caller.headers, body["job_id"])

    url = api.get(
        f"/api/v1/wardrobe/items/{body['item_id']}", headers=caller.headers
    ).json()["image_url"]
    token = url.rpartition("/")[2]

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "GET %s", (url,), None)
    RedactImageTokens().filter(record)

    assert token not in record.getMessage()


def _png() -> bytes:
    from tests.support import make_image

    return make_image(fmt="PNG")
