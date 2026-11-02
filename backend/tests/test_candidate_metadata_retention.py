from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.routes import _candidate_out
from app.research.candidate_metadata_retention import snapshot_candidate_abstract


def test_provider_metadata_alone_does_not_clear_abstract_text_rights():
    text, status = snapshot_candidate_abstract(
        abstract_excerpt="A study-specific metadata abstract."
    )

    assert text is None
    assert status == "not_retained_item_text_rights_unverified"


def test_crossref_abstract_is_not_retained_without_item_level_reuse_rights():
    text, status = snapshot_candidate_abstract(abstract_excerpt="A publisher-copyrighted abstract.")

    assert text is None
    assert status == "not_retained_item_text_rights_unverified"


def test_missing_abstract_has_distinct_status_from_rights_restriction():
    assert snapshot_candidate_abstract(abstract_excerpt=None) == (
        None,
        "not_available",
    )


def test_candidate_api_never_exposes_text_without_current_item_version_rights_status():
    candidate = SimpleNamespace(
        id="candidate-1",
        provider="OpenAlex",
        provider_record_id="openalex:W1",
        canonical_identity="openalex:w1",
        title="A study",
        abstract_excerpt="Old snapshot stored under provider-wide CC0 assumption.",
        abstract_excerpt_retention_status="retained_openalex_metadata_cc0_v1",
        doi=None,
        url="https://openalex.org/W1",
        published_year=2026,
        query_text="study query",
        ranking_order=1,
        relevance_json=None,
        disposition="excluded",
        reason_code="source_limit",
        canonical_source_id=None,
        discovered_at=datetime(2026, 10, 31, tzinfo=UTC),
    )

    result = _candidate_out(candidate)

    assert result["abstract_excerpt"] is None
    assert result["abstract_excerpt_retention_status"] == "not_retained_item_text_rights_unverified"


def test_candidate_api_does_not_claim_verified_retention_when_excerpt_is_missing():
    candidate = SimpleNamespace(
        id="candidate-2",
        provider="Crossref",
        provider_record_id="doi:10.5555/example",
        canonical_identity="doi:10.5555/example",
        title="A study",
        abstract_excerpt=None,
        abstract_excerpt_retention_status="retained_item_license_verified_v1",
        doi="10.5555/example",
        url="https://doi.org/10.5555/example",
        published_year=2026,
        query_text="study query",
        ranking_order=1,
        relevance_json=None,
        disposition="excluded",
        reason_code="source_limit",
        canonical_source_id=None,
        discovered_at=datetime(2026, 10, 31, tzinfo=UTC),
    )

    result = _candidate_out(candidate)

    assert result["abstract_excerpt"] is None
    assert result["abstract_excerpt_retention_status"] == "not_available"
