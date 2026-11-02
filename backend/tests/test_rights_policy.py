import pytest
from pydantic import ValidationError

from app.config import Settings
from app.research.rights_policy import RightsContext, evaluate_rights


def _private_report(**overrides):
    values = {
        "source_identity_verified": True,
        "publicly_accessible": True,
        "document_http_status": 200,
        "robots_status": "rules_checked",
        "robots_allows": True,
        "site_terms_status": "checked_no_restriction_signal",
        "use_mode": "private_research",
        "jurisdiction": "IN",
        "purpose": "research",
        "work_type": "institutional_report",
    }
    values.update(overrides)
    return RightsContext(**values)


def test_unstated_license_allows_limited_private_processing_without_redistribution():
    decision = evaluate_rights(_private_report(license_status="not_stated"))

    assert decision.discovery == "PERMITTED_METADATA"
    assert decision.access == "PERMITTED"
    assert decision.analysis == "PERMITTED_WITH_LIMITATIONS"
    assert decision.retention == "LIMITED_EXCERPTS"
    assert decision.sharing == "CITATION_ONLY"
    assert decision.basis == "india_private_research_exception_candidate"
    assert decision.max_retained_verbatim_characters == 1200
    assert decision.max_retained_passages == 4
    assert decision.legal_review_required is False
    assert decision.policy_version == "private-research-v1"


@pytest.mark.parametrize(
    "context, expected_analysis, expected_retention",
    [
        (_private_report(jurisdiction=None), "REVIEW_REQUIRED", "METADATA_ONLY"),
        (_private_report(jurisdiction="GB"), "REVIEW_REQUIRED", "METADATA_ONLY"),
        (_private_report(use_mode="commercial"), "REVIEW_REQUIRED", "METADATA_ONLY"),
        (
            _private_report(site_terms_status="restriction_signal"),
            "REVIEW_REQUIRED",
            "METADATA_ONLY",
        ),
        (
            _private_report(site_terms_status="unavailable"),
            "REVIEW_REQUIRED",
            "METADATA_ONLY",
        ),
        (
            _private_report(work_type="computer_program"),
            "REVIEW_REQUIRED",
            "METADATA_ONLY",
        ),
    ],
)
def test_private_profile_does_not_cover_out_of_scope_or_uncertain_cases(
    context, expected_analysis, expected_retention
):
    decision = evaluate_rights(context)
    assert decision.analysis == expected_analysis
    assert decision.retention == expected_retention
    assert decision.sharing == "CITATION_ONLY"


@pytest.mark.parametrize("work_type", ["unknown", "official_statistics", "press_release"])
def test_private_profile_requires_a_classified_research_publication(work_type):
    decision = evaluate_rights(_private_report(work_type=work_type))
    assert decision.analysis == "REVIEW_REQUIRED"
    assert decision.retention == "METADATA_ONLY"


def test_public_access_does_not_override_document_access_denial_or_robots_disallow():
    denied_document = evaluate_rights(_private_report(document_http_status=403))
    disallowed_robots = evaluate_rights(_private_report(robots_allows=False))

    assert denied_document.access == "DENIED"
    assert denied_document.analysis == "DENIED"
    assert disallowed_robots.access == "DENIED"
    assert disallowed_robots.analysis == "DENIED"


def test_robots_http_4xx_unavailability_is_distinct_from_document_http_403():
    unavailable_robots = evaluate_rights(_private_report(robots_status="unavailable_4xx"))
    denied_document = evaluate_rights(
        _private_report(robots_status="unavailable_4xx", document_http_status=403)
    )

    assert unavailable_robots.access == "PERMITTED"
    assert unavailable_robots.robots_status == "unavailable_4xx"
    assert denied_document.access == "DENIED"
    assert denied_document.reason_codes == ("document_access_denied",)


def test_robots_server_or_network_failure_does_not_authorize_access():
    for robots_status in ("unreachable", "server_error", "not_checked"):
        decision = evaluate_rights(_private_report(robots_status=robots_status))
        assert decision.access in {"DENIED", "REVIEW_REQUIRED"}
        assert decision.analysis != "PERMITTED_WITH_LIMITATIONS"


def test_explicit_item_license_can_permit_scoped_sharing_but_not_full_document_retention():
    decision = evaluate_rights(
        _private_report(
            license_status="verified",
            license_code="cc-by",
            license_evidence="item_license",
            use_mode="public_sharing",
        )
    )

    assert decision.analysis == "PERMITTED"
    assert decision.retention == "LICENSE_SCOPED"
    assert decision.sharing == "LICENSE_SCOPED"
    assert decision.max_retained_verbatim_characters is None


def test_item_specific_restriction_overrides_general_site_license():
    decision = evaluate_rights(
        _private_report(
            license_status="verified",
            license_code="cc-by",
            license_evidence="item_license",
            item_specific_restriction=True,
        )
    )

    assert decision.analysis == "REVIEW_REQUIRED"
    assert decision.retention == "METADATA_ONLY"
    assert decision.sharing == "CITATION_ONLY"


def test_public_domain_requires_a_verified_item_specific_assertion():
    unverified = evaluate_rights(
        _private_report(license_status="public_domain", public_domain_verified=False)
    )
    verified = evaluate_rights(
        _private_report(license_status="public_domain", public_domain_verified=True)
    )

    assert unverified.analysis == "REVIEW_REQUIRED"
    assert verified.analysis == "PERMITTED"
    assert verified.sharing == "PUBLIC_DOMAIN"


def test_unverified_identity_cannot_enter_content_analysis():
    decision = evaluate_rights(_private_report(source_identity_verified=False))
    assert decision.access == "PERMITTED"
    assert decision.analysis == "REVIEW_REQUIRED"
    assert decision.retention == "METADATA_ONLY"


def test_rights_profile_requires_explicit_valid_configuration():
    defaults = Settings(_env_file=None)
    configured = Settings(
        _env_file=None,
        rights_use_mode="private_research",
        rights_jurisdiction="in",
    )

    assert defaults.rights_use_mode == "private_research"
    assert defaults.rights_jurisdiction == ""
    assert configured.rights_jurisdiction == "IN"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rights_use_mode="unrestricted")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rights_jurisdiction="IND")
