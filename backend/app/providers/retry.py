"""Small bounded retry helpers for explicitly safe provider requests."""

import math
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_SAFE_GET_RETRIES = 1
# Inference requests are POSTs and are never automatically resent. The GET retry
# policy below applies only to idempotent retrieval providers.
MAX_RATE_LIMIT_RETRIES = 0
MAX_RETRY_DELAY_SECONDS = 0.5
DEFAULT_RETRY_DELAY_SECONDS = 0.2
SAFE_GET_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def bounded_retry_delay(headers: Mapping[str, str], *, retry_number: int) -> float | None:
    """Parse Retry-After or return None when its minimum exceeds the local wait budget."""
    raw = headers.get("Retry-After", "")[:128].strip()
    delay: float | None = None
    if raw:
        try:
            delay = float(raw)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delay = (retry_at - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = None
    if delay is None or not math.isfinite(delay):
        delay = DEFAULT_RETRY_DELAY_SECONDS * (2 ** max(0, min(retry_number, 4)))
    if delay > MAX_RETRY_DELAY_SECONDS:
        return None
    return max(delay, 0.0)


def parse_retry_after_seconds(
    headers: Mapping[str, str], *, maximum_seconds: float = 86_400.0
) -> float | None:
    """Parse a provider cooldown without sleeping or shortening a long server delay."""
    raw = headers.get("Retry-After", "")[:128].strip()
    if not raw:
        return None
    try:
        delay = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            delay = (retry_at - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(delay) or delay < 0 or delay > maximum_seconds:
        return None
    return delay


def wait_for_retry(headers: Mapping[str, str], *, retry_number: int) -> float | None:
    delay = bounded_retry_delay(headers, retry_number=retry_number)
    if delay is not None and delay > 0:
        time.sleep(delay)
    return delay


def repair_json_envelope(value: object) -> tuple[str, str | None]:
    """Remove one complete Markdown fence without changing or guessing JSON data."""
    if not isinstance(value, str):
        raise ValueError("Structured response was not text")
    content = value.strip()
    lines = content.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().casefold() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        repaired = "\n".join(lines[1:-1]).strip()
        if repaired:
            return repaired, "markdown_json_fence_removed"
    return content, None
