from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from app.providers.retry import (
    MAX_RATE_LIMIT_RETRIES,
    MAX_RETRY_DELAY_SECONDS,
    MAX_SAFE_GET_RETRIES,
    bounded_retry_delay,
    repair_json_envelope,
)


def test_retry_policy_is_single_attempt_and_clamps_provider_delay():
    assert MAX_SAFE_GET_RETRIES == 1
    assert MAX_RATE_LIMIT_RETRIES == 0
    assert bounded_retry_delay({"Retry-After": "60"}, retry_number=0) is None
    assert bounded_retry_delay({"Retry-After": "-1"}, retry_number=0) == 0
    assert bounded_retry_delay({"Retry-After": "NaN"}, retry_number=0) == 0.2


def test_retry_after_http_date_is_parsed_and_bounded():
    future = datetime.now(UTC) + timedelta(seconds=30)
    value = bounded_retry_delay(
        {"Retry-After": format_datetime(future, usegmt=True)}, retry_number=0
    )
    assert value is None
    assert MAX_RETRY_DELAY_SECONDS == 0.5


def test_structured_json_repair_only_removes_one_complete_fence():
    fenced = "  ```json" + chr(10) + '{"ok":true}' + chr(10) + "```  "
    normalized, repair = repair_json_envelope(fenced)
    assert normalized == '{"ok":true}'
    assert repair == "markdown_json_fence_removed"

    plain = "prefix" + chr(10) + '{"ok":true}' + chr(10) + "```"
    unchanged, no_repair = repair_json_envelope(plain)
    assert unchanged == plain
    assert no_repair is None
