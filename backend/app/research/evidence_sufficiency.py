"""Deterministic report-level evidence sufficiency policy.

The input is a normalized snapshot of persisted retrieval, source-access,
methodology, material-claim, and audit records. Model judgments may be inputs,
but this policy keeps them advisory and never calls them independent review.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

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
