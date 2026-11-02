"""Privacy filters for third-party HTTP client request logs."""

import logging
from urllib.parse import urlsplit, urlunsplit


def redact_http_url(value: object) -> object:
    """Remove URL credentials, query parameters, and fragments from log values."""
    if not isinstance(value, str):
        value = str(value)
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value.partition("?")[0].partition("#")[0]
        # Keep endpoint diagnostics but strip user-info as well as user data and
        # credentials commonly passed as query parameters.
        safe_authority = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, safe_authority, parts.path, "", ""))
    except ValueError:
        # A malformed URL should never cause the original value to be logged.
        return "[redacted URL]"


class HttpxRequestLogFilter(logging.Filter):
    """Redact the URL argument in HTTPX's structured request log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "httpx" or not isinstance(record.args, tuple) or len(record.args) < 2:
            return True
        safe_args = list(record.args)
        safe_args[1] = redact_http_url(safe_args[1])
        record.args = tuple(safe_args)
        return True
