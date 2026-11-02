"""Reviewed host policy for licensed scholarly full-text retrieval.

OpenAlex location metadata alone is not a review of the destination host's terms.
The checked-in registry intentionally has no allowed hosts until a host-specific
terms/access review is recorded. Tests inject a narrow policy callback; runtime
retrieval always uses this reviewed registry.
"""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

PERMITTED_LICENSES = {"cc0", "cc-by"}
MAX_POLICY_AGE_DAYS = 365
POLICY_FILE = Path(__file__).with_name("retrieval-host-policies.json")


@dataclass(frozen=True)
class ReviewedHostPolicy:
    host: str
    policy_id: str
    terms_url: str
    reviewed_at: date
    licenses: frozenset[str]
    minimum_interval_seconds: float = 0.0


def _read_registry(path: Path = POLICY_FILE) -> tuple[dict[str, ReviewedHostPolicy], bool]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return {}, False
        records = payload.get("hosts")
        if not isinstance(records, list):
            return {}, False
        policies: dict[str, ReviewedHostPolicy] = {}
        for record in records:
            if not isinstance(record, dict):
                return {}, False
            host = record.get("host")
            policy_id = record.get("policy_id")
            terms_url = record.get("terms_url")
            reviewed = record.get("reviewed_at")
            licenses = record.get("allowed_licenses")
            minimum_interval = record.get("minimum_interval_seconds")
            if (
                not isinstance(host, str)
                or not host
                or host != host.encode("idna").decode("ascii").lower()
                or "*" in host
                or not isinstance(policy_id, str)
                or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", policy_id)
                or not isinstance(terms_url, str)
                or urlsplit(terms_url).scheme != "https"
                or not urlsplit(terms_url).hostname
                or not isinstance(reviewed, str)
                or not isinstance(licenses, list)
                or not licenses
                or any(item not in PERMITTED_LICENSES for item in licenses)
                or isinstance(minimum_interval, bool)
                or not isinstance(minimum_interval, (int, float))
                or not math.isfinite(minimum_interval)
                or not 0 <= minimum_interval <= 86_400
                or host in policies
            ):
                return {}, False
            reviewed_at = date.fromisoformat(reviewed)
            if reviewed_at > datetime.now(UTC).date():
                return {}, False
            policies[host] = ReviewedHostPolicy(
                host=host,
                policy_id=policy_id,
                terms_url=terms_url,
                reviewed_at=reviewed_at,
                licenses=frozenset(licenses),
                minimum_interval_seconds=float(minimum_interval),
            )
        return policies, True
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}, False


_HOST_POLICIES, _REGISTRY_VALID = _read_registry()


def reviewed_host_policy(host: str, license_code: str) -> ReviewedHostPolicy:
    """Require an exact host entry with recent terms review and license scope."""
    if not _REGISTRY_VALID:
        raise ValueError("host_policy_registry_invalid")
    try:
        normalized_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("host_policy_unknown") from None
    policy = _HOST_POLICIES.get(normalized_host)
    if policy is None:
        raise ValueError("host_policy_unknown")
    if (datetime.now(UTC).date() - policy.reviewed_at).days > MAX_POLICY_AGE_DAYS:
        raise ValueError("host_policy_stale")
    if license_code not in policy.licenses:
        raise ValueError("host_license_not_reviewed")
    return policy
