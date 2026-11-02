from app.providers.ror import ROROrganization
from app.providers.scholarly import ScholarlyWork
from app.research.organization_discovery import (
    deduplicate_organization_candidates,
    discover_affiliated_organizations,
    select_official_publication_search_organization,
)
from app.research.source_governance import planned_source_classes


def _work(*, ror_id="https://ror.org/03yrm5c26", name="Climate Research Institute"):
    return ScholarlyWork(
        external_id="doi:10.1234/research",
        title="Renewable-energy investment and climate policy",
        doi="10.1234/research",
        url="https://doi.org/10.1234/research",
        authors=[{"name": "A Researcher"}],
        published_year=2025,
        publisher="Research Journal",
        abstract_excerpt="A study of renewable energy investment in India.",
        query="renewable energy investment India",
        provider="OpenAlex",
        provider_metadata={
            "openalex_id": "https://openalex.org/W123",
            "institution_records": [
                {
                    "openalex_id": "I123",
                    "ror_id": ror_id,
                    "display_name": name,
                    "country_code": "IN",
                    "type": "education",
                }
            ],
        },
    )


def _verified_record(name="Climate Research Institute"):
    return ROROrganization(
        ror_id="https://ror.org/03yrm5c26",
        canonical_name=name,
        aliases=("CRI",),
        organization_types=("education", "nonprofit"),
        domains=("cri.example",),
        official_urls=("https://cri.example",),
        country_code="IN",
        record_status="active",
        last_modified="2026-10-20",
        retrieved_at="2026-11-01T10:00:00+00:00",
        api_url="https://api.ror.org/v2/organizations/03yrm5c26",
    )


def test_unseeded_organization_is_discovered_and_verified_from_affiliation_and_ror():
    requested = []

    def verify(ror_id):
        requested.append(ror_id)
        return _verified_record()

    result = discover_affiliated_organizations([_work()], verify_ror=verify)

    assert requested == ["https://ror.org/03yrm5c26"]
    assert len(result) == 1
    organization = result[0]
    assert organization.identity_status == "VERIFIED_ESTABLISHED"
    assert organization.registry_match is False
    assert organization.official_domains == ["cri.example"]
    assert organization.related_publications[0]["doi"] == "10.1234/research"
    assert organization.quality_assessment == "not_assessed"
    assert organization.verification_timestamp == "2026-11-01T10:00:00+00:00"
    assert organization.verification_date == "2026-11-01"
    assert organization.source_record_updated_at == "2026-10-20"


def test_unresolved_or_name_mismatched_organization_is_not_promoted():
    result = discover_affiliated_organizations(
        [_work(name="Institute of Energy Research")],
        verify_ror=lambda _ror_id: _verified_record(),
    )
    assert result[0].identity_status == "PENDING_VERIFICATION"
    assert any("does not exactly match" in item for item in result[0].limitations)


def test_organization_without_ror_stays_pending_and_does_not_claim_domain_verification():
    result = discover_affiliated_organizations(
        [_work(ror_id=None)], verify_ror=lambda _ror_id: (_ for _ in ()).throw(AssertionError())
    )
    assert result[0].identity_status == "PENDING_VERIFICATION"
    assert result[0].official_domains == []
    assert result[0].verification_method == "openalex_author_affiliation_only"


def test_organization_discovery_deduplicates_publication_identity_and_bounds_lookups():
    works = [_work(), _work()]
    requested = []
    result = discover_affiliated_organizations(
        works,
        verify_ror=lambda ror_id: requested.append(ror_id) or _verified_record(),
    )
    assert requested == ["https://ror.org/03yrm5c26"]
    assert len(result[0].related_publications) == 1


def test_openaire_affiliation_is_resolved_to_ror_and_retains_openaire_identity():
    work = ScholarlyWork(
        external_id="doi:10.1234/openaire",
        title="Renewable-energy investment and climate policy",
        doi="10.1234/openaire",
        url="https://doi.org/10.1234/openaire",
        authors=[],
        published_year=2025,
        publisher="Research Institute Repository",
        abstract_excerpt="A study of renewable energy investment in India.",
        query="renewable energy investment India",
        provider="OpenAIRE",
        provider_metadata={
            "openaire_id": "doi_________::product-1",
            "organization_records": [
                {
                    "openaire_id": "openorgs____::institute-1",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "display_name": "Climate Research Institute",
                    "website_url": "https://cri.example",
                    "country_code": "IN",
                    "type": "openaire_affiliation",
                }
            ],
        },
    )
    requested = []

    result = discover_affiliated_organizations(
        [work],
        verify_ror=lambda ror_id: requested.append(ror_id) or _verified_record(),
    )

    assert requested == ["https://ror.org/03yrm5c26"]
    assert result[0].identity_status == "VERIFIED_ESTABLISHED"
    assert result[0].openaire_ids == ["openorgs____::institute-1"]
    assert result[0].related_publications[0]["openaire_id"] == "doi_________::product-1"
    assert result[0].related_publications[0]["provider"] == "OpenAIRE"


def test_candidate_deduplication_skips_duplicate_names_before_bounded_identity_checks():
    candidates = [
        {
            "openaire_id": "org-1",
            "canonical_name": "Energy Research Institute",
            "country_code": "GB",
        },
        {
            "openaire_id": "org-2",
            "canonical_name": "Energy Research Institute",
            "country_code": "GB",
        },
        {
            "openaire_id": "org-3",
            "canonical_name": "Offshore Renewable Energy Catapult",
            "country_code": "GB",
        },
        {
            "openaire_id": "org-4",
            "canonical_name": "Energy Research Institute",
            "country_code": "IN",
        },
    ]

    assert [item["openaire_id"] for item in deduplicate_organization_candidates(candidates)] == [
        "org-1",
        "org-3",
    ]


def test_official_site_search_covers_a_planned_government_source_before_a_publisher():
    publisher = {
        "organization_id": "https://ror.org/00xhkbc10",
        "canonical_name": "Academic Publisher",
        "organization_types": ["company"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }
    official_agency = {
        "organization_id": "https://ror.org/00pe0tf51",
        "canonical_name": "International Food Agency",
        "organization_types": ["government"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }

    selected = select_official_publication_search_organization(
        [publisher, official_agency],
        planned_source_classes=["academic", "multilateral", "government"],
    )

    assert selected == official_agency


def test_official_site_search_preserves_discovery_order_without_planned_government_coverage():
    publisher = {
        "organization_id": "https://ror.org/00xhkbc10",
        "canonical_name": "Academic Publisher",
        "organization_types": ["company"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }
    official_agency = {
        "organization_id": "https://ror.org/00pe0tf51",
        "canonical_name": "International Food Agency",
        "organization_types": ["government"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }

    selected = select_official_publication_search_organization(
        [publisher, official_agency],
        planned_source_classes=["academic", "think_tank"],
    )

    assert selected == publisher


def test_food_policy_plan_routes_bounded_official_search_to_verified_government_body():
    question = (
        "Which policies have reduced food price volatility and improved food security "
        "for smallholder agriculture in South Asia, and what evidence explains "
        "differences in outcomes?"
    )
    publisher = {
        "organization_id": "https://ror.org/00xhkbc10",
        "canonical_name": "Academic Publisher",
        "organization_types": ["company"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }
    food_agency = {
        "organization_id": "https://ror.org/00pe0tf51",
        "canonical_name": "Food and Agriculture Organization of the United Nations",
        "organization_types": ["government"],
        "identity_status": "VERIFIED_ESTABLISHED",
    }

    selected = select_official_publication_search_organization(
        [publisher, food_agency],
        planned_source_classes=planned_source_classes(question),
    )

    assert selected == food_agency
