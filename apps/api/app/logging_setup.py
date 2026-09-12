"""Keeping credentials out of the access log.

docs/SECURITY-PRIVACY.md: signed URLs are "never logged, never sent to analytics, never
placed in a query string". The third is satisfied by putting the image token in the path
(`app/routers/assets.py`). The first is not satisfied by anything we write ourselves — it is
undone by the server. Uvicorn's access log records the request line, the request line
contains the path, and the path contains a live capability for one of the user's
photographs. Every image the wardrobe screen renders would land in a log file as a working
link.

So the filter below redacts it at the logging layer rather than at every call site. A rule
about what must not be logged, enforced by asking people not to log it, is a rule that holds
until the first person adds a debug line.

Only the token is removed. The asset id stays, because an access log with no idea which
resource was served is not much of an access log, and the id on its own grants nothing.
"""

from __future__ import annotations

import logging
import re

#: `/api/v1/assets/<asset id>/<token>` — the token is the last segment and the only secret.
_IMAGE_PATH = re.compile(r"(/assets/[A-Za-z0-9_-]+/)[A-Za-z0-9_.\-]+")

REDACTION = r"\1[redacted]"


class RedactImageTokens(logging.Filter):
    """Strips image tokens from a log record before it is formatted.

    Rewrites the message and the args rather than the formatted output: uvicorn's access
    logger keeps the request line in `record.args`, so a filter that only looked at
    `record.msg` would find the format string and leave the credential untouched.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "/assets/" in record.msg:
            record.msg = _IMAGE_PATH.sub(REDACTION, record.msg)

        if isinstance(record.args, tuple):
            record.args = tuple(
                _IMAGE_PATH.sub(REDACTION, arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _IMAGE_PATH.sub(REDACTION, value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }

        return True


def install_log_redaction() -> None:
    """Attach the filter to the loggers that see a request path.

    Applied to the handlers as well as the loggers: a filter on a logger does not run for
    records that were emitted by a child logger and propagated up, and `uvicorn.access` is
    exactly that shape.
    """
    redactor = RedactImageTokens()
    for name in ("uvicorn.access", "uvicorn.error", "stylelab"):
        logger = logging.getLogger(name)
        logger.addFilter(redactor)
        for handler in logger.handlers:
            handler.addFilter(redactor)

    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)


__all__ = ["REDACTION", "RedactImageTokens", "install_log_redaction"]
