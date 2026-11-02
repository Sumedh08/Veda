from dataclasses import replace

from app.providers.scholarly import ScholarlyWork
from app.research.publication_provenance import corroborate_openaire_publication_lead


def _openaire_work() -> ScholarlyWork:
    return ScholarlyWork(
        external_id="openaire:openaire____::report-123",
        title="Urban Heat Vulnerability and Adaptation in Indian Cities",
        doi=None,
        url="https://research.example.org/reports/urban-heat-adaptation",
        authors=[],
        published_year=2025,
        publisher="Urban Research Institute",
        abstract_excerpt="A report assesses urban heat vulnerability and adaptation strategies.",
        query="Urban Heat Vulnerability and Adaptation in Indian Cities",
        provider="OpenAIRE",
        provider_metadata={
            "openaire_id": "openaire____::report-123",
            "organization_records": [
                {
                    "openaire_id": "openaire____::org-456",
                    "display_name": "Urban Research Institute",
                    "website_url": "https://www.research.example.org/",
                    "type": "research institute",
                }
            ],
            "instance_types": ["report"],
        },
        source_type="institutional_report",
    )


def _lead() -> dict[str, str]:
    return {
        "title": "Urban heat vulnerability and adaptation in Indian cities",
        "url": "https://www.research.example.org/reports/urban-heat-adaptation",
        "domain": "www.research.example.org",
    }


def test_openaire_catalog_can_corroborate_a_doi_less_publication_and_domain_without_ror():
    result = corroborate_openaire_publication_lead(_openaire_work(), _lead())

    assert result.status == "corroborated"
    assert result.reason_code == "exact_catalog_title_location_and_publisher_domain_match"
    assert result.organization is not None
    assert result.organization["openaire_id"] == "openaire____::org-456"
    assert result.organization["display_name"] == "Urban Research Institute"
    assert result.official_domain == "research.example.org"
    assert result.catalog_record_id == "openaire____::report-123"


def test_openaire_provenance_rejects_self_asserted_or_mismatched_publications():
    work = _openaire_work()

    assert (
        corroborate_openaire_publication_lead(
            replace(work, provider="Unverified website"), _lead()
        ).reason_code
        == "unsupported_catalog_provider"
    )
    assert (
        corroborate_openaire_publication_lead(
            replace(work, title="Unrelated agricultural policy publication"), _lead()
        ).reason_code
        == "catalog_title_mismatch"
    )
    assert (
        corroborate_openaire_publication_lead(
            replace(work, url="https://lookalike.example.net/reports/urban-heat-adaptation"),
            _lead(),
        ).reason_code
        == "catalog_location_domain_mismatch"
    )
    assert (
        corroborate_openaire_publication_lead(
            replace(work, url="https://www.research.example.org/publication-details"), _lead()
        ).reason_code
        == "catalog_location_not_item_specific"
    )
    assert (
        corroborate_openaire_publication_lead(
            replace(
                work,
                provider_metadata={
                    **work.provider_metadata,
                    "organization_records": [
                        {
                            "openaire_id": "openaire____::org-456",
                            "display_name": "Urban Research Institute",
                            "website_url": "https://urban-research.example.net/",
                        }
                    ],
                },
            ),
            _lead(),
        ).reason_code
        == "publisher_organization_domain_mismatch"
    )


def test_openaire_provenance_rejects_lookalikes_ambiguous_names_and_missing_record_ids():
    work = _openaire_work()
    lookalike = {**_lead(), "domain": "research-example.org"}
    assert (
        corroborate_openaire_publication_lead(work, lookalike).reason_code
        == "catalog_location_domain_mismatch"
    )

    missing_id = replace(
        work,
        provider_metadata={**work.provider_metadata, "openaire_id": None},
    )
    assert (
        corroborate_openaire_publication_lead(missing_id, _lead()).reason_code
        == "catalog_record_id_missing"
    )

    ambiguous = replace(
        work,
        provider_metadata={
            **work.provider_metadata,
            "organization_records": [
                *work.provider_metadata["organization_records"],
                {
                    "openaire_id": "openaire____::org-789",
                    "display_name": "Urban Research Institute",
                    "website_url": "https://research.example.org/",
                },
            ],
        },
    )
    assert (
        corroborate_openaire_publication_lead(ambiguous, _lead()).reason_code
        == "publisher_organization_ambiguous"
    )


def test_openaire_publisher_field_must_match_its_linked_organization_record():
    work = replace(_openaire_work(), publisher="Forged Publisher")

    assert (
        corroborate_openaire_publication_lead(work, _lead()).reason_code
        == "publisher_organization_name_mismatch"
    )
