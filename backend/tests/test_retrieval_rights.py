import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.research import retrieval_rights


def _record(*, host="papers.example", reviewed_at=None, licenses=None):
    return {
        "host": host,
        "policy_id": "publisher-terms-2026-01",
        "terms_url": f"https://{host}/terms",
        "reviewed_at": (reviewed_at or date.today()).isoformat(),
        "allowed_licenses": licenses or ["cc-by", "cc0"],
        "minimum_interval_seconds": 0,
    }


def test_registry_is_exact_host_scoped_and_license_scoped(monkeypatch):
    monkeypatch.setattr(
        retrieval_rights,
        "_HOST_POLICIES",
        {
            "papers.example": retrieval_rights.ReviewedHostPolicy(
                host="papers.example",
                policy_id="publisher-terms-2026-01",
                terms_url="https://papers.example/terms",
                reviewed_at=date.today(),
                licenses=frozenset({"cc-by", "cc0"}),
            )
        },
    )
    monkeypatch.setattr(retrieval_rights, "_REGISTRY_VALID", True)

    policy = retrieval_rights.reviewed_host_policy("PAPERS.EXAMPLE", "cc-by")
    assert policy.policy_id == "publisher-terms-2026-01"
    assert policy.terms_url == "https://papers.example/terms"
    with pytest.raises(ValueError, match="host_policy_unknown"):
        retrieval_rights.reviewed_host_policy("sub.papers.example", "cc-by")
    with pytest.raises(ValueError, match="host_license_not_reviewed"):
        retrieval_rights.reviewed_host_policy("papers.example", "public-domain")


def test_invalid_or_stale_registry_fails_closed(tmp_path, monkeypatch):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text(
        json.dumps({"schema_version": 1, "hosts": [_record(licenses=["public-domain"])]}),
        encoding="utf-8",
    )
    invalid, valid = retrieval_rights._read_registry(invalid_file)
    assert invalid == {}
    assert not valid

    stale_file = tmp_path / "stale.json"
    stale_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hosts": [_record(reviewed_at=datetime.now(UTC).date() - timedelta(days=366))],
            }
        ),
        encoding="utf-8",
    )
    stale, valid = retrieval_rights._read_registry(stale_file)
    assert valid
    monkeypatch.setattr(retrieval_rights, "_HOST_POLICIES", stale)
    monkeypatch.setattr(retrieval_rights, "_REGISTRY_VALID", valid)
    with pytest.raises(ValueError, match="host_policy_stale"):
        retrieval_rights.reviewed_host_policy("papers.example", "cc-by")


def test_checked_in_host_registry_allows_only_reviewed_strathprints_cc_by_research_copy():
    policies, valid = retrieval_rights._read_registry()
    assert valid
    policy = policies["strathprints.strath.ac.uk"]
    assert policy.policy_id == "strathprints-research-copy-2026-11-01"
    assert policy.terms_url == "https://strathprints.strath.ac.uk/policies.html"
    assert policy.licenses == frozenset({"cc-by"})
    with pytest.raises(ValueError, match="host_license_not_reviewed"):
        retrieval_rights.reviewed_host_policy("strathprints.strath.ac.uk", "cc0")


@pytest.mark.parametrize("interval", [True, -1, 86_401, float("inf"), "1"])
def test_registry_rejects_invalid_minimum_request_intervals(tmp_path, interval):
    record = _record()
    record["minimum_interval_seconds"] = interval
    path = tmp_path / "invalid-interval.json"
    path.write_text(json.dumps({"schema_version": 1, "hosts": [record]}), encoding="utf-8")
    policies, valid = retrieval_rights._read_registry(path)
    assert policies == {}
    assert not valid


def test_registry_requires_explicit_minimum_request_interval(tmp_path):
    record = _record()
    del record["minimum_interval_seconds"]
    path = tmp_path / "missing-interval.json"
    path.write_text(json.dumps({"schema_version": 1, "hosts": [record]}), encoding="utf-8")
    policies, valid = retrieval_rights._read_registry(path)
    assert policies == {}
    assert not valid
