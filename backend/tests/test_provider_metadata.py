from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routes import _source_out
from app.providers.metadata import versioned_provider_metadata


def test_openaire_metadata_accepts_catalog_ids_with_dot_separators():
    metadata = versioned_provider_metadata(
        "OpenAIRE",
        {
            "openaire_id": "openaire____::report.v1",
            "metadata_license": "CC-BY",
            "metadata_attribution": "OpenAIRE Graph",
            "metadata_license_url": "https://graph.openaire.eu/docs/apis/terms/",
            "organization_records": [
                {
                    "openaire_id": "openaire____::organization.v1",
                    "display_name": "A Specialist Institute",
                    "website_url": "https://example.org",
                }
            ],
        },
    )

    assert metadata["openaire_id"] == "openaire____::report.v1"
    assert metadata["organization_records"][0]["openaire_id"] == ("openaire____::organization.v1")


@pytest.mark.parametrize(
    ("provider", "metadata", "preserved"),
    [
        ("Crossref", {"work_type": "journal-article"}, {"work_type": "journal-article"}),
        (
            "OpenAlex",
            {
                "openalex_id": "https://openalex.org/W123",
                "open_access": {"is_oa": True, "oa_status": "gold"},
                "best_oa_location": {
                    "landing_page_url": "https://example.org/article",
                    "license": "cc-by",
                    "source": {"display_name": "Journal"},
                },
                "work_type": "article",
            },
            {
                "openalex_id": "https://openalex.org/W123",
                "open_access": {"is_oa": True, "oa_status": "gold"},
                "best_oa_location": {
                    "landing_page_url": "https://example.org/article",
                    "license": "cc-by",
                    "source": {"display_name": "Journal"},
                },
                "work_type": "article",
            },
        ),
        (
            "World Bank Data360",
            {
                "statistics": {
                    "indicator_id": "WB_WDI_SP_POP_TOTL",
                    "license": "CC BY-4.0",
                    "observations": [
                        {
                            "value": "8215424893",
                            "period": "2025",
                            "geography_code": "WLD",
                            "unit_multiplier": 0,
                        }
                    ],
                },
                "selection_block_reason": "license_not_verified",
            },
            {
                "statistics": {
                    "indicator_id": "WB_WDI_SP_POP_TOTL",
                    "license": "CC BY-4.0",
                    "observations": [
                        {
                            "value": "8215424893",
                            "period": "2025",
                            "geography_code": "WLD",
                            "unit_multiplier": 0,
                        }
                    ],
                },
                "selection_block_reason": "license_not_verified",
            },
        ),
        (
            "ILOSTAT",
            {
                "statistics": {
                    "indicator_id": "EMP_TEMP_SEX_AGE_NB",
                    "database_id": "ILOSTAT",
                    "observations": [{"value": "3500000000", "period": "2024"}],
                }
            },
            {
                "statistics": {
                    "indicator_id": "EMP_TEMP_SEX_AGE_NB",
                    "database_id": "ILOSTAT",
                    "observations": [{"value": "3500000000", "period": "2024"}],
                }
            },
        ),
    ],
)
def test_provider_v1_validates_and_preserves_known_fields(provider, metadata, preserved):
    result = versioned_provider_metadata(provider, metadata)

    assert result["schema_version"] == 1
    assert {key: result[key] for key in preserved} == preserved
    assert result["extensions"] == {}


def test_legacy_provider_metadata_is_upcast_and_unknown_fields_are_extensions():
    legacy = {
        "work_type": "journal-article",
        "historic_parser_note": {"imported": True},
    }

    result = versioned_provider_metadata("Crossref", legacy)

    assert result == {
        "schema_version": 1,
        "extensions": {"historic_parser_note": {"imported": True}},
        "work_type": "journal-article",
    }
    assert legacy["historic_parser_note"] == {"imported": True}


def test_openalex_affiliation_identity_survives_metadata_versioning_for_discovery():
    result = versioned_provider_metadata(
        "OpenAlex",
        {
            "institution_ids": {
                "openalex": ["I123"],
                "ror": ["https://ror.org/03yrm5c26"],
            },
            "institution_records": [
                {
                    "openalex_id": "I123",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "display_name": "Unseeded Climate Research Institute",
                    "country_code": "IN",
                    "type": "facility",
                }
            ],
            "journal_issns": ["1234-5679"],
        },
    )

    assert result["institution_ids"]["openalex"] == ["I123"]
    assert result["institution_records"][0]["display_name"] == (
        "Unseeded Climate Research Institute"
    )
    assert result["journal_issns"] == ["1234-5679"]
    assert result["extensions"] == {}


def test_unknown_nested_provider_fields_are_labeled_as_extensions():
    result = versioned_provider_metadata(
        "World Bank Data360",
        {
            "statistics": {
                "indicator_id": "WB_WDI_SP_POP_TOTL",
                "legacy_catalog_note": "descriptive only",
                "observations": [{"value": "12", "period": "2025", "provider_flag": "A"}],
            }
        },
    )

    assert result["statistics"]["extensions"] == {"legacy_catalog_note": "descriptive only"}
    assert result["statistics"]["observations"][0]["extensions"] == {"provider_flag": "A"}


@pytest.mark.parametrize(
    "provider,metadata",
    [
        ("Crossref", {"schema_version": 2}),
        ("Crossref", {"work_type": 4}),
        ("OpenAlex", {"open_access": {"is_oa": "yes"}}),
        ("OpenAlex", {"has_content": {"pdf": "true"}}),
        ("World Bank Data360", {"selection_block_reason": "license_rejected"}),
        ("ILOSTAT", {"statistics": {"observations": "not-an-array"}}),
        ("Crossref", {"extensions": ["not-an-object"]}),
    ],
)
def test_provider_metadata_rejects_future_versions_and_malformed_known_fields(provider, metadata):
    with pytest.raises((ValueError, ValidationError)):
        versioned_provider_metadata(provider, metadata)


def test_openalex_content_availability_is_exposed_without_untrusted_download_urls():
    source = SimpleNamespace(
        id="source-1",
        title="OpenAlex metadata record",
        doi="10.5555/example",
        url="https://doi.org/10.5555/example",
        authors_json=[],
        published_year=2025,
        publisher=None,
        metadata_json={
            "provider": "OpenAlex",
            "provider_metadata": {
                "openalex_id": "https://openalex.org/W123",
                "has_content": {"pdf": True, "grobid_xml": True},
                "organization_discovery": {
                    "organization_id": "https://ror.org/03yrm5c26",
                    "organization_name": "Unseeded Climate Research Institute",
                    "identity_status": "VERIFIED_ESTABLISHED",
                    "verification_method": "openalex_affiliation_plus_ror_exact_id",
                    "verification_source": "https://api.ror.org/v2/organizations/03yrm5c26",
                    "openalex_institution_id": "I123",
                    "quality_assessment": "not_assessed",
                },
                "content_urls": {
                    "pdf": "https://content.openalex.org/works/W123.pdf",
                    "grobid_xml": "https://content.openalex.org/works/W123.grobid-xml",
                },
            },
        },
        source_type="scholarly_article",
        retrieval_status="metadata_only",
        abstract_excerpt=None,
        appraisal_json={},
    )

    output = _source_out(source)

    assert output["openalex_fulltext_availability"] == {"pdf": True, "grobid_xml": True}
    assert "content_urls" not in output
    assert output["retrieval_status"] == "metadata_only"
    assert output["organization_provenance"]["organization_name"] == (
        "Unseeded Climate Research Institute"
    )


def test_provider_metadata_enforces_json_depth_and_byte_bounds():
    with pytest.raises(ValueError, match="64 KiB"):
        versioned_provider_metadata("Crossref", {"legacy": ["x" * 16_000 for _ in range(5)]})

    nested = value = {}
    for _ in range(14):
        nested["child"] = {}
        nested = nested["child"]
    with pytest.raises(ValueError, match="nesting"):
        versioned_provider_metadata("Crossref", value)


def test_verified_web_publication_provenance_exposes_bounded_rights_and_origin_fields():
    source = SimpleNamespace(
        id="source-web-publication",
        title="Verified official research publication",
        doi="10.5555/example",
        url="https://windlab.example/reports/example",
        authors_json=[],
        published_year=2025,
        publisher="Windlab Research",
        metadata_json={
            "provider": "Crossref",
            "provider_metadata": {
                "organization_discovery": {
                    "organization_id": "https://ror.org/01abcde23",
                    "organization_name": "Unseeded Wind Research Institute",
                    "identity_status": "VERIFIED_ESTABLISHED",
                    "verification_method": "crawl4ai_search_result_domain_plus_ror_exact_domain",
                    "verification_source": "https://api.ror.org/v2/organizations/01abcde23",
                    "official_domain": "windlab.example",
                    "official_publication_url": "https://windlab.example/reports/example",
                    "publisher_verification": "verified_organization_domain_and_crossref_publisher_identity",
                    "publication_discovery_provider": "Crawl4AI Cloud site search plus Crossref DOI resolution",
                    "publication_content_access": "not_retrieved",
                    "publication_rights_status": "metadata_only_not_assessed",
                    "quality_assessment": "not_assessed",
                }
            },
        },
        source_type="scholarly_article",
        retrieval_status="metadata_only",
        abstract_excerpt=None,
        appraisal_json={},
    )

    output = _source_out(source)

    assert output["organization_provenance"]["official_domain"] == "windlab.example"
    assert output["organization_provenance"]["official_publication_url"] == (
        "https://windlab.example/reports/example"
    )
    assert output["organization_provenance"]["publication_discovery_provider"] == (
        "Crawl4AI Cloud site search plus Crossref DOI resolution"
    )
    assert output["organization_provenance"]["publication_content_access"] == "not_retrieved"
    assert output["organization_provenance"]["publication_rights_status"] == (
        "metadata_only_not_assessed"
    )


def test_crossref_linked_domain_is_not_serialized_as_a_verified_official_domain():
    source = SimpleNamespace(
        id="source-crossref-domain-lead",
        title="Climate Resilient Cities",
        doi="10.46830/wrirpt.22.00055",
        url="https://doi.org/10.46830/wrirpt.22.00055",
        authors_json=[],
        published_year=2024,
        publisher="World Resources Institute",
        metadata_json={
            "provider": "Crossref",
            "provider_metadata": {
                "organization_discovery": {
                    "organization_id": "https://ror.org/047ktk903",
                    "organization_name": "World Resources Institute",
                    "identity_status": "VERIFIED_DOMAIN_SPECIALIST",
                    "verification_method": "ror_exact_publisher_name_plus_crossref_linked_domain",
                    "verification_source": "https://api.crossref.org/works/10.46830/wrirpt.22.00055",
                    "official_domain": "wri-india.org",
                    "official_publication_url": "https://doi.org/10.46830/wrirpt.22.00055",
                    "quality_assessment": "not_assessed",
                }
            },
        },
        source_type="institutional_report",
        retrieval_status="metadata_only",
        abstract_excerpt=None,
        appraisal_json={},
    )

    provenance = _source_out(source)["organization_provenance"]

    assert "official_domain" not in provenance
    assert provenance["publisher_linked_domain"] == "wri-india.org"


def test_crossref_verified_official_site_metadata_survives_source_serialization():
    source = SimpleNamespace(
        id="source-crossref-publisher-catalog",
        title="Grid Integration Research Report",
        doi=None,
        url="https://specialist-energy.example/reports/grid-integration",
        authors_json=[],
        published_year=None,
        publisher="Specialist Energy Institute",
        metadata_json={
            "provider": "Official site publication search",
            "provider_metadata": {
                "schema_version": 1,
                "extensions": {
                    "official_site_discovery": {
                        "organization_id": "crossref-publisher:verified-test",
                        "organization_name": "Specialist Energy Institute",
                        "identity_status": "VERIFIED_DOMAIN_SPECIALIST",
                        "verification_source": (
                            "https://api.crossref.org/works/10.5555%2Fpublisher-report"
                        ),
                        "official_domain": "specialist-energy.example",
                        "homepage_url": "https://specialist-energy.example/",
                        "api_url": "https://specialist-energy.example/wp-json/wp/v2/search",
                        "discovery_query": "grid integration research report",
                        "wordpress_record_id": 3,
                        "result_type": "post",
                        "result_subtype": "research",
                        "metadata_access": "public_official_site_search_api",
                        "content_fetched": False,
                        "rights_status": "not_assessed",
                        "quality_assessment": "not_assessed",
                        "publisher_verification": (
                            "crossref_doi_title_publisher_and_link_domain_match"
                        ),
                    }
                },
            },
        },
        source_type="institutional_report",
        retrieval_status="metadata_only",
        abstract_excerpt=None,
        appraisal_json={},
    )

    output = _source_out(source)

    assert output["official_site_publication"]["publisher_verification"] == (
        "crossref_doi_title_publisher_and_link_domain_match"
    )


def test_unknown_provider_metadata_is_preserved_only_as_descriptive_extension():
    result = versioned_provider_metadata("Future Registry", {"opaque": {"value": 3}})

    assert result == {
        "schema_version": 1,
        "extensions": {"opaque": {"value": 3}},
    }
