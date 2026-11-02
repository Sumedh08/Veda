"""Deterministic report-level evidence sufficiency policy.

The input is a normalized snapshot of persisted retrieval, source-access,
methodology, material-claim, and audit records. Model judgments may be inputs,
but this policy keeps them advisory and never calls them independent review.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_VERSION = "evidence-sufficiency-v1"

RequirementType = Literal[
    "bibliographic",
    "descriptive",
    "numerical",
    "comparative",
    "causal",
    "methodological",
    "negative_or_absence",
    "generalization",
]
SupportStatus = Literal[
    "supported",
    "partially_supported",
    "contradicted",
    "irrelevant",
    "insufficient",
    "not_assessed",
]
EvidenceSufficiencyStatus = Literal["EVIDENCE_VERIFIED", "PROVISIONAL", "INSUFFICIENT_EVIDENCE"]
AdaptiveSufficiencyStatus = Literal[
    "SUFFICIENT_FOR_SCOPE", "PRELIMINARY_EVIDENCE_MAP", "INSUFFICIENT_EVIDENCE"
]


class MaterialRequirementV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requirement_id: str = Field(pattern=r"^Q[1-8]$")
    text: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=500)


class QuestionEvidencePlanV1(BaseModel):
    """Auditable, question-specific sufficiency criteria, not a validated universal rubric."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    question_kind: Literal[
        "narrow_source_specific",
        "descriptive",
        "causal",
        "comparative",
        "forecasting",
        "policy_decision",
        "explanatory",
        "mixed",
    ]
    scope_breadth: Literal["narrow", "bounded", "broad", "underspecified"]
    material_requirements: list[MaterialRequirementV1] = Field(min_length=1, max_length=8)
    evidence_dimensions: list[str] = Field(min_length=1, max_length=12)
    minimum_criteria: list[str] = Field(min_length=1, max_length=16)
    independent_corroboration_expected: bool
    required_independent_investigations: int | None = Field(default=None, ge=2, le=8)
    classification_reasons: list[str] = Field(min_length=1, max_length=12)
    interpretation_limit: Literal[
        "Operational question-adaptive criteria; not a scientifically validated universal standard."
    ] = "Operational question-adaptive criteria; not a scientifically validated universal standard."

    @model_validator(mode="after")
    def validate_corroboration_rule(self) -> QuestionEvidencePlanV1:
        if self.independent_corroboration_expected != (
            self.required_independent_investigations is not None
        ):
            raise ValueError("independent corroboration rule must include its operational floor")
        if [item.requirement_id for item in self.material_requirements] != [
            f"Q{index}" for index in range(1, len(self.material_requirements) + 1)
        ]:
            raise ValueError("material requirement ids must be contiguous and ordered")
        return self


class EvidenceIndependenceUnit(BaseModel):
    """One publication/work record with only explicitly reviewed independence facts."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1, max_length=36)
    publication_identity: str = Field(min_length=1, max_length=500)
    source_type: Literal[
        "scholarly_article", "institutional_report", "official_statistics", "other_research"
    ]
    evidence_role: Literal[
        "primary_empirical", "synthesis", "official_statistics", "institutional_analysis", "unknown"
    ]
    passage_count: int = Field(ge=0, le=100_000)
    content_access_classes: list[str] = Field(default_factory=list, max_length=16)
    document_version_ids: list[str] = Field(default_factory=list, max_length=32)
    independence_status: Literal[
        "unknown",
        "same_investigation",
        "overlapping_dataset",
        "independent_investigation",
        "review_synthesis",
    ] = "unknown"
    independence_reviewed: bool = False
    investigation_id: str | None = Field(default=None, max_length=200)
    dataset_ids: list[str] = Field(default_factory=list, max_length=32)
    assessment_basis: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_independence_evidence(self) -> EvidenceIndependenceUnit:
        if self.independence_status == "unknown":
            if self.independence_reviewed or self.assessment_basis:
                raise ValueError("unknown independence cannot carry a completed assessment")
            return self
        if not self.independence_reviewed or not self.assessment_basis:
            raise ValueError("classified independence requires an explicit reviewed basis")
        if self.independence_status in {"same_investigation", "independent_investigation"}:
            if not self.investigation_id:
                raise ValueError("investigation relationship requires an investigation id")
        if self.independence_status == "overlapping_dataset" and not self.dataset_ids:
            raise ValueError("overlapping-dataset assessment requires dataset identities")
        if self.independence_status == "review_synthesis" and self.evidence_role != "synthesis":
            raise ValueError("review-synthesis status requires a synthesis evidence role")
        return self


class PublicationIndependenceGroupV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    publication_identity: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=100)
    source_types: list[
        Literal[
            "scholarly_article", "institutional_report", "official_statistics", "other_research"
        ]
    ]
    evidence_roles: list[
        Literal[
            "primary_empirical",
            "synthesis",
            "official_statistics",
            "institutional_analysis",
            "unknown",
        ]
    ]
    passage_count: int = Field(ge=0, le=100_000)
    document_version_count: int = Field(ge=0, le=3200)
    content_access_classes: list[str] = Field(max_length=16)
    independence_status: Literal[
        "unknown",
        "same_investigation",
        "overlapping_dataset",
        "independent_investigation",
        "review_synthesis",
    ]
    overlapping_dataset_reuse: bool = False
    investigation_id: str | None = Field(default=None, max_length=200)
    dataset_ids: list[str] = Field(max_length=32)


class EvidenceIndependenceSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    source_records: int = Field(ge=0, le=10_000)
    publication_groups: int = Field(ge=0, le=10_000)
    content_bearing_publication_groups: int = Field(ge=0, le=10_000)
    full_text_publication_groups: int = Field(ge=0, le=10_000)
    abstract_only_publication_groups: int = Field(ge=0, le=10_000)
    unclassified_content_publication_groups: int = Field(ge=0, le=10_000)
    document_versions: int = Field(ge=0, le=32_000)
    same_publication_version_groups: int = Field(ge=0, le=10_000)
    same_investigation_groups: int = Field(ge=0, le=10_000)
    independent_investigations_confirmed: int = Field(ge=0, le=10_000)
    corroboration_eligible_investigation_ids: list[str] = Field(max_length=10_000)
    overlapping_dataset_pairs: int = Field(ge=0, le=10_000)
    review_synthesis_groups: int = Field(ge=0, le=10_000)
    unknown_independence_publications: int = Field(ge=0, le=10_000)
    groups: list[PublicationIndependenceGroupV1] = Field(max_length=100)
    assessment_limit: Literal[
        "Different publication or publisher identities alone do not establish independent investigations."
    ] = "Different publication or publisher identities alone do not establish independent investigations."

    @model_validator(mode="after")
    def validate_independence_count(self) -> EvidenceIndependenceSummaryV1:
        eligible = self.corroboration_eligible_investigation_ids
        if len(set(eligible)) != len(eligible):
            raise ValueError("corroboration eligible investigation ids must be unique")
        if self.independent_investigations_confirmed != len(eligible):
            raise ValueError("independent investigation count must match eligible ids")
        return self


class MaterialRequirementEvidenceV1(BaseModel):
    """Source-linked support and reviewed independence for one material question requirement."""

    model_config = ConfigDict(extra="forbid", strict=True)

    requirement_id: str = Field(pattern=r"^Q[1-8]$")
    linked_publication_identities: list[str] = Field(default_factory=list, max_length=100)
    supporting_publication_identities: list[str] = Field(default_factory=list, max_length=100)
    confirmed_independent_investigation_ids: list[str] = Field(default_factory=list, max_length=100)
    independence_unknown_publication_identities: list[str] = Field(
        default_factory=list, max_length=100
    )
    known_non_independent_publication_identities: list[str] = Field(
        default_factory=list, max_length=100
    )


def publication_identity_key(
    *,
    doi: str | None,
    url: str | None,
    title: str,
    published_year: int | None,
    publisher: str | None,
    authors: list[str],
    fallback_id: str = "unresolved",
) -> str:
    """Identify a work across copies/versions without treating it as an investigation.

    DOI is the strongest key. DOI-less records use the normalized title with the
    year and first named author where available, falling back to publisher. URL
    is used only when bibliographic identity is too sparse to group safely.
    """

    normalized_doi = (doi or "").strip().casefold()
    normalized_doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized_doi)
    normalized_doi = normalized_doi.removeprefix("doi:").strip().rstrip(".,; ")
    if re.fullmatch(r"10\.\d{4,9}/\S+", normalized_doi):
        return f"doi:{normalized_doi}"[:500]

    normalized_title = " ".join(re.sub(r"[^\w]+", " ", title.casefold()).split())
    normalized_year = str(published_year) if isinstance(published_year, int) else ""

    def normalize_label(value: str | None) -> str:
        return " ".join(re.sub(r"[^\w]+", " ", (value or "").casefold()).split())

    first_author = next((normalize_label(author) for author in authors if author.strip()), "")
    publisher_key = normalize_label(publisher)
    identity_detail = first_author or publisher_key
    if normalized_title and (normalized_year or identity_detail):
        detail_type = "author" if first_author else "publisher"
        return f"bibliographic:{normalized_title}|year:{normalized_year}|{detail_type}:{identity_detail}"[
            :500
        ]

    if isinstance(url, str) and url.strip():
        parsed = urlsplit(url.strip())
        if parsed.scheme.casefold() == "https" and parsed.hostname:
            host = parsed.hostname.casefold().rstrip(".")
            try:
                port = parsed.port
            except ValueError:
                return f"record:{fallback_id}"[:500]
            port_suffix = f":{port}" if port and port != 443 else ""
            path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
            return f"url:https://{host}{port_suffix}{path}"[:500]

    return f"record:{fallback_id}"[:500]


class AdaptiveSufficiencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan: QuestionEvidencePlanV1
    independence: EvidenceIndependenceSummaryV1
    content_bearing_source_count: int = Field(ge=0, le=10_000)
    material_claims_expected: int = Field(ge=0, le=10_000)
    material_claims_supported: int = Field(ge=0, le=10_000)
    covered_requirement_ids: list[str] = Field(max_length=8)
    material_requirement_evidence: list[MaterialRequirementEvidenceV1] = Field(
        default_factory=list, max_length=8
    )
    counterevidence_search_completed: bool
    bounded_search_complete: bool
    source_class_coverage_complete: bool
    deterministic_citation_integrity_passed: bool
    semantic_audit_complete: bool
    unresolved_material_contradictions: int = Field(ge=0, le=10_000)
    unmet_evidence_criteria: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_supported_claim_count(self) -> AdaptiveSufficiencyInput:
        if self.material_claims_supported > self.material_claims_expected:
            raise ValueError("supported material claims cannot exceed expected claims")
        valid_ids = {item.requirement_id for item in self.plan.material_requirements}
        if not set(self.covered_requirement_ids).issubset(valid_ids):
            raise ValueError("covered requirements must be present in the saved question plan")
        requirement_ids = [item.requirement_id for item in self.material_requirement_evidence]
        if len(requirement_ids) != len(set(requirement_ids)) or not set(requirement_ids).issubset(
            valid_ids
        ):
            raise ValueError("requirement evidence must have unique ids from the saved plan")
        groups_by_identity = {
            group.publication_identity: group for group in self.independence.groups
        }
        for evidence in self.material_requirement_evidence:
            linked = set(evidence.linked_publication_identities)
            supporting = set(evidence.supporting_publication_identities)
            if not linked.issubset(groups_by_identity):
                raise ValueError("requirement evidence must link to summarized publications")
            if not supporting.issubset(linked):
                raise ValueError("supporting publications must be linked to the requirement")
            if not set(evidence.independence_unknown_publication_identities).issubset(linked):
                raise ValueError("unknown-independence publications must link to the requirement")
            if not set(evidence.known_non_independent_publication_identities).issubset(linked):
                raise ValueError("known non-independent publications must link to the requirement")
            reviewed_independent = {
                group.investigation_id
                for identity, group in groups_by_identity.items()
                if identity in supporting
                and group.independence_status == "independent_investigation"
                and group.investigation_id
                and group.investigation_id
                in self.independence.corroboration_eligible_investigation_ids
            }
            if not set(evidence.confirmed_independent_investigation_ids).issubset(
                reviewed_independent
            ):
                raise ValueError("corroborating investigations must support this requirement")
            if any(
                groups_by_identity[identity].independence_status != "unknown"
                for identity in evidence.independence_unknown_publication_identities
            ):
                raise ValueError("unknown-independence links must remain unclassified")
            if any(
                groups_by_identity[identity].independence_status
                not in {"same_investigation", "overlapping_dataset", "review_synthesis"}
                and not groups_by_identity[identity].overlapping_dataset_reuse
                for identity in evidence.known_non_independent_publication_identities
            ):
                raise ValueError(
                    "known non-independent links need an explicit non-independent status"
                )
        return self


class AdaptiveEvidenceSufficiencyDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    status: AdaptiveSufficiencyStatus
    question_plan: QuestionEvidencePlanV1
    independence: EvidenceIndependenceSummaryV1
    covered_requirement_ids: list[str] = Field(max_length=8)
    uncovered_requirement_ids: list[str] = Field(max_length=8)
    material_requirement_evidence: list[MaterialRequirementEvidenceV1] = Field(max_length=8)
    blocking_conditions: list[str] = Field(max_length=64)
    minimum_criteria: list[str] = Field(max_length=16)
    supporting_basis: list[str] = Field(max_length=32)
    human_review_status: Literal["not_performed"] = "not_performed"
    scientific_validation_status: Literal["not_independently_validated"] = (
        "not_independently_validated"
    )


class RetrievalCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    planned_lenses: int = Field(ge=0, le=100)
    completed_lenses: int = Field(ge=0, le=100)
    failed_lenses: int = Field(ge=0, le=100)
    candidate_ledger_complete: bool
    relevant_exclusions_disclosed: bool
    counterevidence_search_completed: bool
    citation_expansion_complete: bool


class SourceAccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    eligible_studies: int = Field(ge=0, le=10_000)
    critical_access_assessed: bool
    critical_studies: int = Field(ge=0, le=10_000)
    critical_studies_with_usable_methods_results: int = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_critical_counts(self) -> SourceAccessInput:
        if self.critical_studies_with_usable_methods_results > self.critical_studies:
            raise ValueError("usable critical full-text count cannot exceed critical study count")
        return self


class MethodologyCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    critical_appraisals_expected: int = Field(ge=0, le=10_000)
    critical_appraisals_assessed: int = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_appraisal_counts(self) -> MethodologyCoverageInput:
        if self.critical_appraisals_assessed > self.critical_appraisals_expected:
            raise ValueError("assessed critical appraisals cannot exceed expected appraisals")
        return self


class MaterialClaimCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str = Field(min_length=1, max_length=36)
    requirement_types: list[RequirementType] = Field(min_length=1, max_length=8)
    provenance_valid: bool
    support_status: SupportStatus
    numerical_evidence_present: bool | None
    causal_design_assessed: bool | None
    explicit_absence_evidence: bool | None
    methodological_evidence_present: bool | None = None
    population_scope_assessed: bool | None = None
    unresolved_contradiction: bool


class VerificationCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    material_items_expected: int = Field(ge=0, le=10_000)
    material_items_assessed: int = Field(ge=0, le=10_000)
    deterministic_links_passed: bool
    semantic_audit_complete: bool
    semantic_batch_coverage_complete: bool
    uncited_scan_complete: bool
    audit_input_truncated: bool

    @model_validator(mode="after")
    def validate_audit_counts(self) -> VerificationCoverageInput:
        if self.material_items_assessed > self.material_items_expected:
            raise ValueError("assessed material items cannot exceed expected items")
        return self


class SufficiencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    retrieval: RetrievalCoverageInput
    source_access: SourceAccessInput
    methodology: MethodologyCoverageInput
    material_claims: list[MaterialClaimCheck] = Field(max_length=10_000)
    verification: VerificationCoverageInput


class EvidenceSufficiencyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    status: EvidenceSufficiencyStatus
    rules_evaluated: list[str] = Field(max_length=32)
    blocking_conditions: list[str] = Field(max_length=64)
    warnings: list[str] = Field(max_length=64)
    supporting_record_ids: list[str] = Field(max_length=10_000)
    policy_version: str = POLICY_VERSION
    decision_timestamp: datetime
    human_review_status: Literal["not_performed"] = "not_performed"


def evaluate_evidence_sufficiency(
    values: SufficiencyInput | dict,
    *,
    evaluated_at: datetime,
) -> EvidenceSufficiencyDecision:
    """Return a conservative, reproducible status from a bounded evidence snapshot."""
    snapshot = (
        values if isinstance(values, SufficiencyInput) else SufficiencyInput.model_validate(values)
    )
    blockers: list[str] = []
    warnings: list[str] = []
    rules = [
        "eligible_study_presence",
        "search_lens_coverage",
        "counterevidence_search_coverage",
        "bounded_citation_expansion",
        "candidate_ledger_and_exclusion_disclosure",
        "critical_fulltext_access_and_methodology",
        "claim_provenance_and_semantic_support",
        "type_specific_evidence_requirements",
        "complete_material_claim_audit",
        "semantic_audit_batch_coverage",
        "no_unresolved_material_contradictions",
        "human_review_disclosure",
    ]

    if snapshot.source_access.eligible_studies == 0:
        blockers.append("no_eligible_studies")
    if not snapshot.material_claims:
        blockers.append("no_material_claims_with_evidence")

    retrieval = snapshot.retrieval
    if (
        retrieval.planned_lenses == 0
        or retrieval.completed_lenses != retrieval.planned_lenses
        or retrieval.failed_lenses > 0
    ):
        blockers.append("search_lens_coverage_incomplete")
    if not retrieval.candidate_ledger_complete:
        blockers.append("candidate_ledger_incomplete")
    if not retrieval.relevant_exclusions_disclosed:
        blockers.append("relevant_exclusions_not_disclosed")
    if not retrieval.counterevidence_search_completed:
        blockers.append("counterevidence_search_incomplete")
    if not retrieval.citation_expansion_complete:
        blockers.append("citation_expansion_incomplete")

    access = snapshot.source_access
    if not access.critical_access_assessed:
        blockers.append("critical_source_access_not_assessed")
    if access.critical_studies_with_usable_methods_results < access.critical_studies:
        blockers.append("critical_fulltext_methods_results_incomplete")
    methodology = snapshot.methodology
    if methodology.critical_appraisals_assessed < methodology.critical_appraisals_expected:
        blockers.append("critical_methodological_appraisal_incomplete")

    for claim in snapshot.material_claims:
        if not claim.provenance_valid:
            blockers.append(f"invalid_claim_provenance:{claim.claim_id}")
        if claim.support_status != "supported":
            blockers.append(f"claim_support_{claim.support_status}:{claim.claim_id}")
        if claim.unresolved_contradiction:
            blockers.append(f"unresolved_material_contradiction:{claim.claim_id}")
        for requirement_type in claim.requirement_types:
            if requirement_type == "numerical" and claim.numerical_evidence_present is not True:
                blockers.append(f"numerical_evidence_unverified:{claim.claim_id}")
            elif requirement_type == "causal" and claim.causal_design_assessed is not True:
                blockers.append(f"causal_design_not_assessed:{claim.claim_id}")
            elif (
                requirement_type == "negative_or_absence"
                and claim.explicit_absence_evidence is not True
            ):
                blockers.append(f"explicit_absence_evidence_missing:{claim.claim_id}")
            elif (
                requirement_type == "methodological"
                and claim.methodological_evidence_present is not True
            ):
                blockers.append(f"methodological_evidence_missing:{claim.claim_id}")
            elif (
                requirement_type == "generalization" and claim.population_scope_assessed is not True
            ):
                blockers.append(f"population_scope_not_assessed:{claim.claim_id}")

    verification = snapshot.verification
    if not verification.deterministic_links_passed:
        blockers.append("deterministic_citation_integrity_failed")
    if not verification.semantic_audit_complete:
        blockers.append("semantic_material_claim_audit_incomplete")
    if not verification.semantic_batch_coverage_complete:
        blockers.append("semantic_audit_batch_coverage_incomplete")
    if verification.material_items_assessed != verification.material_items_expected:
        blockers.append("material_claim_audit_coverage_incomplete")
    if not verification.uncited_scan_complete:
        blockers.append("uncited_material_claim_scan_incomplete")
    if verification.audit_input_truncated:
        blockers.append("semantic_audit_input_truncated")

    blockers = list(dict.fromkeys(blockers))
    insufficient = access.eligible_studies == 0 or verification.material_items_expected == 0
    if snapshot.material_claims:
        insufficient = insufficient or all(
            claim.support_status in {"insufficient", "irrelevant", "not_assessed"}
            for claim in snapshot.material_claims
        )
    if insufficient:
        status: EvidenceSufficiencyStatus = "INSUFFICIENT_EVIDENCE"
    elif blockers:
        status = "PROVISIONAL"
    else:
        status = "EVIDENCE_VERIFIED"

    if access.critical_studies_with_usable_methods_results < access.critical_studies:
        warnings.append(
            "One or more critical studies lack usable full-text Methods/Results evidence."
        )
    if any(claim.support_status == "partially_supported" for claim in snapshot.material_claims):
        warnings.append("At least one material claim has only partial model-assisted support.")
    if any(claim.support_status == "contradicted" for claim in snapshot.material_claims):
        warnings.append("At least one material claim is contradicted by its cited evidence.")
    warnings.append("Automated evidence checks are not independent peer review.")

    return EvidenceSufficiencyDecision(
        status=status,
        rules_evaluated=rules,
        blocking_conditions=blockers,
        warnings=warnings,
        supporting_record_ids=[claim.claim_id for claim in snapshot.material_claims],
        decision_timestamp=evaluated_at,
    )


_REQUIREMENT_PATTERNS: tuple[tuple[RequirementType, re.Pattern[str]], ...] = (
    (
        "negative_or_absence",
        re.compile(
            r"\b(?:not|never)\s+(?:been\s+)?(?:measured|quantified|assessed|collected)\b|"
            r"\b(?:did|does|do|was|were|is|are)\s+not\s+(?:measure|quantify|assess|collect)\b|"
            r"\bno\b.{0,50}\b(?:evidence|effect|difference|measurement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "numerical",
        re.compile(r"(?<![\w])(?:[+-]?\d+(?:[.,]\d+)?%?)(?![\w])"),
    ),
    (
        "methodological",
        re.compile(
            r"\b(?:randomi[sz]ed|sample|participants?|method(?:s|ology)?|trial|design|"
            r"confound(?:ing|er|ers)|identification strategy|selection bias)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "causal",
        re.compile(
            r"\b(?:caus(?:e|ed|es|al|ally)|effect of|impact of|lead(?:s|ing)? to|"
            r"improv(?:e|ed|es|ing)|increas(?:e|ed|es|ing)|reduc(?:e|ed|es|ing)|"
            r"decreas(?:e|ed|es|ing)|boost(?:s|ed|ing)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "comparative",
        re.compile(
            r"\b(?:compared with|compared to|versus|vs\.?|difference between)\b", re.IGNORECASE
        ),
    ),
    (
        "generalization",
        re.compile(
            r"\b(?:generaliz\w*|generalizability|across all|industry[- ]wide|all developers)\b",
            re.IGNORECASE,
        ),
    ),
)


def infer_evidence_requirements(text: str) -> list[RequirementType]:
    """Conservatively identify which evidence checks a report assertion invokes.

    This is a routing aid, not a truth judgment. A statement may require several
    checks; unmatched statements receive the descriptive requirement.
    """
    matches = [kind for kind, pattern in _REQUIREMENT_PATTERNS if pattern.search(text)]
    return matches or ["descriptive"]


_SOURCE_SPECIFIC_QUESTION = re.compile(
    r"\b(?:what|which|how)\b.{0,55}\b(?:the|this|cited|referenced)\s+"
    r"(?:specific\s+)?(?:study|paper|report|trial|evaluation)\b",
    re.IGNORECASE,
)
_QUESTION_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "causal",
        re.compile(
            r"\b(?:effect|impact|affect|influence|caus\w*|reduce[sd]?|increase[sd]?|"
            r"improve[sd]?|worsen[sd]?|lead to|result in|attribut\w*)\b|"
            r"\bwhether\b.{0,60}\bchanges?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "comparative",
        re.compile(
            r"\b(?:compare|compared|versus|vs\.?|difference(?:s)? between|better than|"
            r"differ\w*|disagree\w*|associated with|linked to|correlat\w*|"
            r"(?:link|relat|connect|correspond|tie)\w*\b.{0,100}\b(?:to|with)|"
            r"relationship between|track|align)\b",
            re.I,
        ),
    ),
    (
        "forecasting",
        re.compile(
            r"\b(?:forecast|predict|projection|projected|scenario|future outlook)\w*\b", re.I
        ),
    ),
    (
        "policy_decision",
        re.compile(
            r"\b(?:policy|policies|reform|strategy|strategies|intervention\w*|should|"
            r"regulatory|adaptation|how can|what actions)\b",
            re.IGNORECASE,
        ),
    ),
    ("explanatory", re.compile(r"\b(?:why|how|mechanism|mechanisms|explain)\b", re.IGNORECASE)),
)
_BREADTH_TERMS = re.compile(
    r"\b(?:across|multiple|worldwide|global|developing economies|countries|regions|"
    r"industry[- ]wide|over time|since\s+\d{4})\b",
    re.IGNORECASE,
)
_MULTIPLE_EVIDENCE_UNITS = re.compile(
    r"\b(?:studies|papers|trials|experiments|datasets|reports|publications|literature)\b",
    re.IGNORECASE,
)
_QUESTION_SCOPE_CUE = re.compile(
    r"\b(?:in|among|within|for|across)\s+(?:the\s+)?"
    r"(?:[A-Z][A-Za-z-]+|(?:[A-Za-z-]+\s+){0,3}(?:cities|city|regions?|"
    r"communities|districts?|neighbou?rhoods?|countries|states|provinces|"
    r"hospitals?|units?|households?|workers?|patients?|farmers?|firms?|"
    r"populations?|age groups?|gender groups?|semi-arid|coastal))\b|"
    r"\bsince\s+\d{4}\b|\bby\s+(?:age|gender|sex|income|region|country|population)\b",
    re.IGNORECASE,
)
_ASSOCIATION_QUESTION = re.compile(
    r"\b(?:associated with|linked to|correlat\w*|relationship between|track\w*|align\w*|"
    r"(?:link|relat|connect|correspond|tie)\w*\b.{0,100}\b(?:to|with))\b",
    re.IGNORECASE,
)
_QUANTITATIVE_QUESTION = re.compile(
    r"\b(?:how many|what fraction|what proportion|what percentage|what rates?|"
    r"annual rates?|prevalence|incidence|share of|estimate the number)\b",
    re.IGNORECASE,
)
_TIME_SERIES_QUESTION = re.compile(
    r"\b(?:annual|yearly|over time|since\s+\d{4}|trend(?:s)?|time series)\b",
    re.IGNORECASE,
)


def build_question_evidence_plan(
    question: str,
    scope: dict[str, Any] | None,
    subquestions: list[dict[str, Any]] | None,
) -> QuestionEvidencePlanV1:
    """Derive explainable evidence needs from the saved question plan, not a source quota."""
    text = " ".join(question.split())
    normalized_scope = scope if isinstance(scope, dict) else {}
    source_specific = bool(_SOURCE_SPECIFIC_QUESTION.search(text))
    detected_types = [kind for kind, pattern in _QUESTION_TYPE_PATTERNS if pattern.search(text)]
    if source_specific:
        question_kind = "narrow_source_specific"
    elif len(detected_types) > 1:
        question_kind = "mixed"
    elif detected_types:
        question_kind = detected_types[0]
    else:
        question_kind = "descriptive"

    requirements: list[MaterialRequirementV1] = []
    for item in (subquestions or [])[:8]:
        if not isinstance(item, dict):
            continue
        requirement_text = item.get("text")
        purpose = item.get("purpose")
        if not isinstance(requirement_text, str) or not requirement_text.strip():
            continue
        requirements.append(
            MaterialRequirementV1(
                requirement_id=f"Q{len(requirements) + 1}",
                text=" ".join(requirement_text.split())[:300],
                purpose=(
                    " ".join(purpose.split())[:500]
                    if isinstance(purpose, str) and purpose.strip()
                    else "Address this material part of the question."
                ),
            )
        )
    if not requirements:
        requirements = [
            MaterialRequirementV1(
                requirement_id="Q1",
                text=text[:300],
                purpose="Main research question; no saved subquestion decomposition was available.",
            )
        ]

    explicit_scope = bool(_QUESTION_SCOPE_CUE.search(text)) or any(
        isinstance(normalized_scope.get(key), str) and normalized_scope[key].strip()
        for key in ("geography", "population", "time_horizon", "decision_objective")
    )
    multiple_evidence_body = bool(_MULTIPLE_EVIDENCE_UNITS.search(text)) and not source_specific
    broad_scope = (
        bool(_BREADTH_TERMS.search(text))
        or multiple_evidence_body
        or any(
            isinstance(normalized_scope.get(key), str)
            and bool(_BREADTH_TERMS.search(normalized_scope[key]))
            for key in ("geography", "population", "time_horizon", "context")
        )
    )
    if question_kind == "narrow_source_specific" and len(requirements) == 1:
        scope_breadth = "narrow"
    elif broad_scope:
        scope_breadth = "broad"
    elif explicit_scope:
        scope_breadth = "bounded"
    else:
        scope_breadth = "underspecified"

    high_inference_question = question_kind in {
        "causal",
        "comparative",
        "forecasting",
        "policy_decision",
        "mixed",
    }
    require_independent_corroboration = (
        (high_inference_question and scope_breadth != "narrow")
        or (len(requirements) > 2 and question_kind != "narrow_source_specific")
        or (question_kind == "explanatory" and scope_breadth == "broad")
        or (multiple_evidence_body and question_kind != "narrow_source_specific")
    )
    dimensions = ["source_linked_passage_provenance", "material_subquestion_coverage"]
    criteria = [
        "material_claims_have_valid_source_and_passage_links",
        "each_material_requirement_has_supported_source_linked_evidence",
        "scope_and_limitations_are_disclosed",
    ]
    reasons = [f"question_type:{question_kind}", f"scope_breadth:{scope_breadth}"]
    if multiple_evidence_body:
        reasons.append("question asks for findings across a body of research publications")
    if len(requirements) > 2:
        reasons.append("saved plan decomposes the question into multiple material requirements")
    if question_kind == "narrow_source_specific":
        dimensions.append("requested_work_methods_findings_and_limits")
        criteria.append("the requested work and version are identifiable and directly inspected")
        reasons.append("question explicitly asks what a particular publication reports")
    if question_kind == "causal" or "causal" in detected_types:
        dimensions.extend(["causal_design", "outcome_measure", "alternative_explanations"])
        criteria.append(
            "causal design, outcome definition, and important alternatives are appraised"
        )
    if question_kind == "comparative" or "comparative" in detected_types:
        dimensions.append("cross-study_scope_comparability")
        criteria.append(
            "comparisons preserve population, geography, period, and outcome differences"
        )
    if question_kind == "forecasting":
        dimensions.extend(["model_assumptions", "scenario_uncertainty"])
        criteria.append("forecast assumptions and scenario uncertainty are disclosed")
    if question_kind == "policy_decision" or "policy_decision" in detected_types:
        dimensions.extend(["implementation_context", "policy_tradeoffs", "primary_outcomes"])
        criteria.append(
            "policy outcomes, implementation context, and material tradeoffs are represented"
        )
    if "explanatory" in detected_types:
        dimensions.extend(["mechanisms", "alternative_explanations"])
        criteria.append(
            "proposed mechanisms are distinguished from observed outcomes and alternatives"
        )
    if _ASSOCIATION_QUESTION.search(text):
        dimensions.append("association_design_and_alternative_explanations")
        criteria.append(
            "associations are not upgraded to causal effects without an appropriate design"
        )
    if _QUANTITATIVE_QUESTION.search(text):
        dimensions.append("quantitative_measurement_and_denominator")
        criteria.append(
            "numerical claims use identifiable measures, denominators, periods, and original data where available"
        )
    if _TIME_SERIES_QUESTION.search(text):
        dimensions.append("time_series_comparability")
        criteria.append(
            "definitions and measurement changes over time are disclosed before comparing rates"
        )
    if require_independent_corroboration:
        dimensions.extend(["independent_investigations", "counterevidence"])
        criteria.append(
            "broad or high-inference material claims have corroboration from separately characterized investigations"
        )
        criteria.append("the bounded counterevidence search completed and its limits are disclosed")
        reasons.append(
            "the inference type or scope makes independent corroboration decision-relevant"
        )

    return QuestionEvidencePlanV1(
        question_kind=question_kind,
        scope_breadth=scope_breadth,
        material_requirements=requirements,
        evidence_dimensions=list(dict.fromkeys(dimensions)),
        minimum_criteria=list(dict.fromkeys(criteria)),
        independent_corroboration_expected=require_independent_corroboration,
        required_independent_investigations=2 if require_independent_corroboration else None,
        classification_reasons=reasons,
    )


def summarize_evidence_independence(
    units: list[EvidenceIndependenceUnit | dict[str, Any]],
) -> EvidenceIndependenceSummaryV1:
    """Collapse versions/duplicate works and count only explicitly reviewed investigations."""
    parsed = [
        item
        if isinstance(item, EvidenceIndependenceUnit)
        else EvidenceIndependenceUnit.model_validate(item)
        for item in units
    ]

    def normalized_identity(value: str) -> str:
        identity = " ".join(value.strip().casefold().split())
        identity = re.sub(r"^https?://(?:dx\.)?doi\.org/", "doi:", identity)
        if identity.startswith("doi:"):
            identity = identity.removeprefix("doi:").strip()
        identity = identity.rstrip(".,;")
        if re.fullmatch(r"10\.\d{4,9}/\S+", identity):
            return f"doi:{identity}"
        parsed_url = urlsplit(identity)
        if parsed_url.scheme in {"http", "https"} and parsed_url.hostname:
            host = parsed_url.hostname.casefold().rstrip(".")
            try:
                port = parsed_url.port
            except ValueError:
                return identity
            default_port = 443 if parsed_url.scheme == "https" else 80
            port_suffix = f":{port}" if port and port != default_port else ""
            path = re.sub(r"/+", "/", parsed_url.path or "/").rstrip("/") or "/"
            return f"url:{parsed_url.scheme}://{host}{port_suffix}{path}"
        return identity

    grouped: dict[str, list[EvidenceIndependenceUnit]] = {}
    for unit in parsed:
        grouped.setdefault(normalized_identity(unit.publication_identity), []).append(unit)

    group_models: list[PublicationIndependenceGroupV1] = []
    confirmed_investigations: set[str] = set()
    investigation_to_publications: dict[str, set[str]] = {}
    reviewed_datasets: dict[str, set[str]] = {}
    group_status_by_identity: dict[str, str] = {}
    group_versions = 0

    for identity, members in sorted(grouped.items()):
        statuses = {member.independence_status for member in members}
        status = statuses.pop() if len(statuses) == 1 else "unknown"
        investigation_ids = {
            member.investigation_id
            for member in members
            if member.independence_status in {"same_investigation", "independent_investigation"}
            and member.independence_reviewed
            and member.investigation_id
        }
        investigation_id = next(iter(investigation_ids)) if len(investigation_ids) == 1 else None
        if len(investigation_ids) > 1:
            status = "unknown"
        dataset_ids = sorted(
            {
                dataset
                for member in members
                if member.independence_reviewed
                for dataset in member.dataset_ids
            }
        )
        versions = {version for member in members for version in member.document_version_ids}
        access_classes = sorted(
            {access_class for member in members for access_class in member.content_access_classes}
        )
        if len(versions) > 1:
            group_versions += 1
        group_has_content = any(member.passage_count > 0 for member in members)
        if status == "independent_investigation" and investigation_id and group_has_content:
            confirmed_investigations.add(investigation_id)
        if status in {"independent_investigation", "same_investigation"} and investigation_id:
            investigation_to_publications.setdefault(investigation_id, set()).add(identity)
        if dataset_ids and all(member.independence_reviewed for member in members):
            reviewed_datasets[identity] = set(dataset_ids)
        group_status_by_identity[identity] = status
        group_models.append(
            PublicationIndependenceGroupV1(
                publication_identity=identity[:500],
                source_ids=list(dict.fromkeys(member.source_id for member in members))[:100],
                source_types=list(dict.fromkeys(member.source_type for member in members)),
                evidence_roles=list(dict.fromkeys(member.evidence_role for member in members)),
                passage_count=sum(member.passage_count for member in members),
                document_version_count=len(versions),
                content_access_classes=access_classes[:16],
                independence_status=status,
                overlapping_dataset_reuse=False,
                investigation_id=investigation_id,
                dataset_ids=dataset_ids[:32],
            )
        )

    overlapping_pairs = 0
    overlapping_investigation_ids: set[str] = set()
    identities = sorted(reviewed_datasets)
    for index, identity_a in enumerate(identities):
        for identity_b in identities[index + 1 :]:
            if not reviewed_datasets[identity_a].intersection(reviewed_datasets[identity_b]):
                continue
            overlapping_pairs += 1
            for identity in (identity_a, identity_b):
                status = group_status_by_identity[identity]
                if status == "independent_investigation":
                    investigation_id = next(
                        (
                            member.investigation_id
                            for member in grouped[identity]
                            if member.independence_status == "independent_investigation"
                        ),
                        None,
                    )
                    if investigation_id:
                        overlapping_investigation_ids.add(investigation_id)

    confirmed_investigations.difference_update(overlapping_investigation_ids)
    for group in group_models:
        if group.investigation_id in overlapping_investigation_ids:
            group.overlapping_dataset_reuse = True
    same_investigation_groups = sum(
        len(publications) > 1 for publications in investigation_to_publications.values()
    )
    return EvidenceIndependenceSummaryV1(
        source_records=len(parsed),
        publication_groups=len(group_models),
        content_bearing_publication_groups=sum(group.passage_count > 0 for group in group_models),
        full_text_publication_groups=sum(
            bool(
                {
                    "full_text_html",
                    "full_text_jats",
                    "full_text_pdf",
                    "official_publication_page_body",
                }.intersection(group.content_access_classes)
            )
            for group in group_models
        ),
        abstract_only_publication_groups=sum(
            group.passage_count > 0 and group.content_access_classes == ["abstract_only"]
            for group in group_models
        ),
        unclassified_content_publication_groups=sum(
            group.passage_count > 0 and not group.content_access_classes for group in group_models
        ),
        document_versions=sum(group.document_version_count for group in group_models),
        same_publication_version_groups=group_versions,
        same_investigation_groups=same_investigation_groups,
        independent_investigations_confirmed=len(confirmed_investigations),
        corroboration_eligible_investigation_ids=sorted(confirmed_investigations),
        overlapping_dataset_pairs=overlapping_pairs,
        review_synthesis_groups=sum(
            group.independence_status == "review_synthesis" for group in group_models
        ),
        unknown_independence_publications=sum(
            group.independence_status == "unknown" for group in group_models
        ),
        groups=group_models[:100],
    )


def evaluate_adaptive_sufficiency(
    values: AdaptiveSufficiencyInput | dict[str, Any],
) -> AdaptiveEvidenceSufficiencyDecisionV1:
    """Apply explainable question-specific criteria without a fixed publication-count target."""
    snapshot = (
        values
        if isinstance(values, AdaptiveSufficiencyInput)
        else AdaptiveSufficiencyInput.model_validate(values)
    )
    plan = snapshot.plan
    required_ids = {item.requirement_id for item in plan.material_requirements}
    covered_ids = set(snapshot.covered_requirement_ids)
    uncovered_ids = sorted(required_ids - covered_ids)
    blockers: list[str] = []
    basis: list[str] = []

    if snapshot.content_bearing_source_count == 0:
        blockers.append("no_content_bearing_evidence")
    else:
        basis.append(f"content_bearing_source_records:{snapshot.content_bearing_source_count}")
    if snapshot.material_claims_expected == 0:
        blockers.append("no_material_claims_assessed")
    elif snapshot.material_claims_supported == 0:
        blockers.append("no_supported_material_claims")
    elif snapshot.material_claims_supported < snapshot.material_claims_expected:
        blockers.append("material_claim_support_incomplete")
    else:
        basis.append(f"supported_material_claims:{snapshot.material_claims_supported}")
    if uncovered_ids:
        blockers.extend(f"material_requirement_uncovered:{item_id}" for item_id in uncovered_ids)
    else:
        basis.append(f"covered_material_requirements:{len(covered_ids)}")
    if not snapshot.bounded_search_complete:
        blockers.append("bounded_search_or_candidate_ledger_incomplete")
    if not snapshot.source_class_coverage_complete:
        blockers.append("planned_source_class_coverage_incomplete")
    if not snapshot.deterministic_citation_integrity_passed:
        blockers.append("deterministic_citation_integrity_failed")
    if not snapshot.semantic_audit_complete:
        blockers.append("material_claim_semantic_audit_incomplete")
    if snapshot.unresolved_material_contradictions:
        blockers.append("unresolved_material_contradictions")
    blockers.extend(
        f"evidence_criterion_unmet:{criterion}" for criterion in snapshot.unmet_evidence_criteria
    )
    if plan.independent_corroboration_expected:
        if not snapshot.counterevidence_search_completed:
            blockers.append("counterevidence_search_incomplete")
        required_independent = plan.required_independent_investigations or 2
        known_independent = snapshot.independence.independent_investigations_confirmed
        if known_independent < required_independent:
            blockers.append("independent_corroboration_not_established")
        else:
            basis.append(f"confirmed_independent_investigations:{known_independent}")
        requirement_evidence_by_id = {
            item.requirement_id: item for item in snapshot.material_requirement_evidence
        }
        for requirement in plan.material_requirements:
            requirement_evidence = requirement_evidence_by_id.get(requirement.requirement_id)
            corroborating_investigations = (
                set(requirement_evidence.confirmed_independent_investigation_ids)
                if requirement_evidence
                else set()
            )
            if len(corroborating_investigations) < required_independent:
                blockers.append(
                    "independent_corroboration_not_established_for_requirement:"
                    f"{requirement.requirement_id}"
                )

    if snapshot.content_bearing_source_count == 0 or snapshot.material_claims_expected == 0:
        status: AdaptiveSufficiencyStatus = "INSUFFICIENT_EVIDENCE"
    elif blockers:
        status = "PRELIMINARY_EVIDENCE_MAP"
    else:
        status = "SUFFICIENT_FOR_SCOPE"
    return AdaptiveEvidenceSufficiencyDecisionV1(
        status=status,
        question_plan=plan,
        independence=snapshot.independence,
        covered_requirement_ids=sorted(covered_ids),
        uncovered_requirement_ids=uncovered_ids,
        material_requirement_evidence=snapshot.material_requirement_evidence,
        blocking_conditions=list(dict.fromkeys(blockers)),
        minimum_criteria=plan.minimum_criteria,
        supporting_basis=basis,
    )
