"""Separate source access, research processing, retention and sharing decisions.

This is an operational policy evaluator, not a legal-opinion engine.  Its
private-research profile records a jurisdiction-specific statutory-exception
candidate and applies strict minimization; it never turns that candidate into a
public redistribution grant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

RIGHTS_POLICY_VERSION = "private-research-v1"
PRIVATE_RESEARCH_MAX_VERBATIM_CHARACTERS = 1200
PRIVATE_RESEARCH_MAX_PASSAGES = 4
ALLOWED_ROBOTS_STATES = {"rules_checked", "unavailable_4xx"}
LICENSED_REUSE_CODES = {"cc0", "cc-by"}
PRIVATE_RESEARCH_WORK_TYPES = {"institutional_report", "scholarly_article"}


@dataclass(frozen=True)
class RightsContext:
    source_identity_verified: bool
    publicly_accessible: bool
    document_http_status: int | None
    robots_status: str
    robots_allows: bool | None
    site_terms_status: str
    use_mode: Literal["private_research", "commercial", "public_sharing"]
    jurisdiction: str | None
    purpose: str = "research"
    work_type: str = "research_work"
    license_status: str = "not_stated"
    license_code: str | None = None
    license_evidence: str | None = None
    public_domain_verified: bool = False
    item_specific_restriction: bool = False
    authentication_required: bool = False
    verified_domains: tuple[str, ...] = ()
    terms_url: str | None = None


@dataclass(frozen=True)
class RightsDecision:
    discovery: str
    access: str
    analysis: str
    retention: str
    sharing: str
    basis: str
    policy_version: str
    legal_review_required: bool
    max_retained_verbatim_characters: int | None
    max_retained_passages: int | None
    robots_status: str
    site_terms_status: str
    verified_domains: tuple[str, ...]
    terms_url: str | None
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def may_analyze(self) -> bool:
        return self.analysis in {"PERMITTED", "PERMITTED_WITH_LIMITATIONS"}

    @property
    def may_fetch_for_analysis(self) -> bool:
        return self.access == "PERMITTED" and self.may_analyze

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["warnings"] = list(self.warnings)
        return value


def evaluate_rights(context: RightsContext) -> RightsDecision:
    """Evaluate independent permission dimensions from explicit evidence.

    A robots 4xx response is represented as ``unavailable_4xx`` per RFC 9309;
    a document 401/403 is still a direct access denial.  Website-terms signals
    do not stand in for copyright permission and a machine-detected restriction
    requires review rather than being interpreted as a final legal conclusion.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    access = "PERMITTED"
    analysis = "REVIEW_REQUIRED"
    retention = "METADATA_ONLY"
    sharing = "CITATION_ONLY"
    basis = "unresolved"
    max_text: int | None = 0
    max_passages: int | None = 0

    status = context.document_http_status
    if status in {401, 403} or context.authentication_required:
        access = "DENIED"
        analysis = "DENIED"
        reasons.append("document_access_denied")
    elif status == 404:
        access = "UNAVAILABLE"
        analysis = "NOT_ASSESSED"
        reasons.append("document_not_found")
    elif status is not None and status >= 500:
        access = "UNAVAILABLE"
        analysis = "NOT_ASSESSED"
        reasons.append("document_server_error")
    elif not context.publicly_accessible:
        access = "REVIEW_REQUIRED"
        reasons.append("public_access_not_established")

    if context.robots_status not in ALLOWED_ROBOTS_STATES:
        if context.robots_status == "rate_limited":
            access = "DEFERRED"
            reasons.append("robots_request_rate_limited")
        elif context.robots_status == "disallowed" or context.robots_allows is False:
            access = "DENIED"
            analysis = "DENIED"
            reasons.append("robots_disallowed")
        elif context.robots_status == "unreachable":
            access = "DENIED"
            analysis = "DENIED"
            reasons.append("robots_unreachable")
        elif context.robots_status == "not_checked":
            access = "REVIEW_REQUIRED"
            reasons.append("robots_not_checked")
        else:
            access = "REVIEW_REQUIRED"
            reasons.append("robots_status_unresolved")
    elif context.robots_allows is False:
        access = "DENIED"
        analysis = "DENIED"
        reasons.append("robots_disallowed")

    if context.site_terms_status == "restriction_signal":
        if access == "PERMITTED":
            access = "REVIEW_REQUIRED"
        reasons.append("site_terms_restriction_signal_requires_review")
    elif context.site_terms_status not in {
        "checked_no_restriction_signal",
        "not_found",
    }:
        reasons.append("site_terms_not_sufficiently_checked")

    if access != "PERMITTED":
        if analysis not in {"DENIED", "NOT_ASSESSED"}:
            analysis = "REVIEW_REQUIRED"
        return RightsDecision(
            discovery="PERMITTED_METADATA",
            access=access,
            analysis=analysis,
            retention=retention,
            sharing=sharing,
            basis=basis,
            policy_version=RIGHTS_POLICY_VERSION,
            legal_review_required=analysis == "REVIEW_REQUIRED",
            max_retained_verbatim_characters=max_text,
            max_retained_passages=max_passages,
            robots_status=context.robots_status,
            site_terms_status=context.site_terms_status,
            verified_domains=context.verified_domains,
            terms_url=context.terms_url,
            reason_codes=tuple(dict.fromkeys(reasons)),
            warnings=tuple(warnings),
        )

    if context.item_specific_restriction:
        reasons.append("item_specific_restriction_requires_review")
    elif context.license_status == "verified" and context.license_code in LICENSED_REUSE_CODES:
        if context.license_evidence:
            analysis = "PERMITTED"
            retention = "LICENSE_SCOPED"
            sharing = "LICENSE_SCOPED"
            basis = "verified_item_license"
            max_text = None
            max_passages = None
            reasons.append("item_license_verified")
        else:
            reasons.append("license_evidence_missing")
    elif context.license_status == "public_domain" and context.public_domain_verified:
        analysis = "PERMITTED"
        retention = "LICENSE_SCOPED"
        sharing = "PUBLIC_DOMAIN"
        basis = "verified_item_public_domain_assertion"
        max_text = None
        max_passages = None
        reasons.append("item_public_domain_verified")
    elif context.license_status in {"restricted", "conflicting", "unrecognized_or_restricted"}:
        reasons.append("license_restricted_or_conflicting")
    elif (
        context.license_status == "not_stated"
        and context.source_identity_verified
        and _private_research_profile_applies(context)
    ):
        analysis = "PERMITTED_WITH_LIMITATIONS"
        retention = "LIMITED_EXCERPTS"
        sharing = "CITATION_ONLY"
        basis = "india_private_research_exception_candidate"
        max_text = PRIVATE_RESEARCH_MAX_VERBATIM_CHARACTERS
        max_passages = PRIVATE_RESEARCH_MAX_PASSAGES
        reasons.append("private_research_exception_candidate")
        warnings.append(
            "Jurisdiction-specific private-research policy applied; this is not a legal opinion."
        )
        if context.site_terms_status == "not_found":
            warnings.append(
                "No linked or standard terms page was found; this is not proof of permission."
            )
    else:
        reasons.append("no_applicable_processing_basis")

    if context.site_terms_status == "restriction_signal":
        analysis = "REVIEW_REQUIRED"
        retention = "METADATA_ONLY"
        sharing = "CITATION_ONLY"
        max_text = 0
        max_passages = 0
    elif not context.source_identity_verified and analysis not in {"DENIED", "NOT_ASSESSED"}:
        analysis = "REVIEW_REQUIRED"
        retention = "METADATA_ONLY"
        sharing = "CITATION_ONLY"
        max_text = 0
        max_passages = 0
        reasons.append("source_identity_not_verified")

    if analysis == "REVIEW_REQUIRED":
        reasons.append("legal_basis_or_source_terms_unresolved")

    return RightsDecision(
        discovery="PERMITTED_METADATA",
        access=access,
        analysis=analysis,
        retention=retention,
        sharing=sharing,
        basis=basis,
        policy_version=RIGHTS_POLICY_VERSION,
        legal_review_required=analysis == "REVIEW_REQUIRED",
        max_retained_verbatim_characters=max_text,
        max_retained_passages=max_passages,
        robots_status=context.robots_status,
        site_terms_status=context.site_terms_status,
        verified_domains=context.verified_domains,
        terms_url=context.terms_url,
        reason_codes=tuple(dict.fromkeys(reasons)),
        warnings=tuple(warnings),
    )


def _private_research_profile_applies(context: RightsContext) -> bool:
    return (
        context.use_mode == "private_research"
        and context.jurisdiction is not None
        and context.jurisdiction.strip().upper() == "IN"
        and context.purpose == "research"
        and context.work_type.strip().casefold() in PRIVATE_RESEARCH_WORK_TYPES
        and context.site_terms_status in {"checked_no_restriction_signal", "not_found"}
        and not context.item_specific_restriction
        and context.publicly_accessible
    )
