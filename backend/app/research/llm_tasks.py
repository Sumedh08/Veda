from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import PlannedSubquestion

APPRAISAL_FIELD_NAMES = (
    "design_type",
    "population",
    "geography",
    "time_period",
    "sample",
    "identification_strategy",
    "intervention_or_exposure",
    "comparator",
    "outcomes",
    "measure",
    "effect_size_and_uncertainty",
    "limitations",
    "funding_or_conflicts",
    "missingness",
    "external_validity",
)


class AppraisalField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal[
        "design_type",
        "population",
        "geography",
        "time_period",
        "sample",
        "identification_strategy",
        "intervention_or_exposure",
        "comparator",
        "outcomes",
        "measure",
        "effect_size_and_uncertainty",
        "limitations",
        "funding_or_conflicts",
        "missingness",
        "external_validity",
    ]
    value: str = Field(max_length=160)
    passage_ids: list[str] = Field(max_length=3)


class SourceAppraisal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    fields: list[AppraisalField] = Field(max_length=15)


class ClaimEconomicFacetDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal[
        "population",
        "intervention_or_exposure",
        "comparator",
        "outcome",
        "estimate",
        "uncertainty",
        "geography",
        "time_period",
        "measure",
    ]
    value: str = Field(max_length=160)
    passage_ids: list[str] = Field(max_length=3)


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    relationship: Literal["supports", "qualifies", "contradicts", "insufficient"]
    rationale: str = Field(max_length=120)
    passage_ids: list[str] = Field(max_length=3)
    evidence_kind: Literal[
        "causal_estimate",
        "association",
        "other_study_result",
        "descriptive_statistic",
        "forecast_or_model",
        "commentary_or_theory",
        "unknown",
    ]
    economic_facets: list[ClaimEconomicFacetDraft] = Field(max_length=9)


class ResearchAppraisalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2]
    source_appraisals: list[SourceAppraisal] = Field(max_length=30)
    claim_assessments: list[ClaimAssessment] = Field(max_length=120)


class ComparisonEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    passage_ids: list[str] = Field(min_length=1, max_length=6)


class ClaimRelationshipDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_a_id: str
    claim_b_id: str
    relationship: Literal[
        "contradicts", "heterogeneous", "qualifies", "consistent", "incomparable", "insufficient"
    ]
    scope_alignment: Literal["same", "different", "unknown"]
    scope_differences: list[
        Literal[
            "population",
            "geography",
            "time_period",
            "outcome",
            "measure",
            "intervention_or_exposure",
            "comparator",
            "method",
        ]
    ] = Field(max_length=8)
    rationale: str = Field(min_length=1, max_length=159, pattern=r".*[.!?]$")
    evidence: list[ComparisonEvidenceLink] = Field(min_length=2, max_length=12)

    @field_validator("rationale")
    @classmethod
    def require_complete_rationale(cls, value: str) -> str:
        if not value.rstrip().endswith((".", "!", "?")):
            raise ValueError("comparison rationale must be a complete sentence")
        if len(value) >= 160:
            raise ValueError("comparison rationale reaches its schema limit and may be truncated")
        return value


class GroundedHypothesisDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=240)
    evidence: list[ComparisonEvidenceLink] = Field(min_length=1, max_length=8)
    uncertainty: str = Field(min_length=1, max_length=160)


class CompetingHypothesesDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis_a: GroundedHypothesisDraft
    hypothesis_b: GroundedHypothesisDraft
    why_competing: str = Field(min_length=1, max_length=180)


class ResearchComparisonBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    relationships: list[ClaimRelationshipDraft] = Field(max_length=8)
    competing_hypotheses: list[CompetingHypothesesDraft] = Field(max_length=2)


class ReportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=239, pattern=r".*[.!?]$")
    claim_ids: list[str] = Field(min_length=1, max_length=8)
    requirement_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("statement")
    @classmethod
    def require_complete_statement(cls, value: str) -> str:
        if not value.rstrip().endswith((".", "!", "?")):
            raise ValueError("report finding must be a complete sentence")
        if len(value) >= 240:
            raise ValueError("report finding reaches its schema limit and may be truncated")
        return value


class ReportQualification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=219, pattern=r".*[.!?]$")
    claim_ids: list[str] = Field(min_length=1, max_length=8)
    requirement_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("statement")
    @classmethod
    def require_complete_statement(cls, value: str) -> str:
        if not value.rstrip().endswith((".", "!", "?")):
            raise ValueError("report qualification must be a complete sentence")
        if len(value) >= 220:
            raise ValueError("report qualification reaches its schema limit and may be truncated")
        return value


ShortReportText = Annotated[str, Field(min_length=1, max_length=180)]


class DecisionImplicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "consider_pilot",
        "scale",
        "pause",
        "avoid",
        "collect_more_evidence",
        "monitor",
        "no_recommendation",
    ]
    condition: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=240)
    assumptions: list[ShortReportText] = Field(min_length=1, max_length=3)
    unknowns: list[ShortReportText] = Field(min_length=1, max_length=3)
    claim_ids: list[str] = Field(min_length=1, max_length=8)
    requirement_ids: list[str] = Field(default_factory=list, max_length=8)


class ResearchReportDraft(BaseModel):
    """Compact, evidence-linked synthesis contract; conclusions stay passage-grounded."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[4]
    findings: list[ReportFinding] = Field(max_length=5)
    qualifications: list[ReportQualification] = Field(max_length=4)
    decision_implications: list[DecisionImplicationDraft] = Field(max_length=2)
    unanswered_questions: list[ShortReportText] = Field(max_length=5)
    company_specific_inputs: list[ShortReportText] = Field(max_length=5)


class ResearchPlanSelectionDraftV1(BaseModel):
    """Model selection over a finite deterministic plan candidate set."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    query_indices: list[int] = Field(min_length=1, max_length=8)
    additional_subquestions: list[PlannedSubquestion] = Field(max_length=2)

    @field_validator("query_indices")
    @classmethod
    def validate_indices(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value) or len(value) != len(set(value)):
            raise ValueError("plan query indices must be unique non-negative integers")
        return value


class CandidateRelevanceAssessmentItemV1(BaseModel):
    """Model output is restricted to fixed candidate keys and relevance labels."""

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment: Literal[
        "directly_relevant", "potentially_relevant", "background", "unrelated", "uncertain"
    ]
    reason: str = Field(min_length=1, max_length=240)


class CandidateRelevanceReviewV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    assessments: list[CandidateRelevanceAssessmentItemV1] = Field(max_length=12)


class SemanticSupportAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, max_length=16)
    verdict: Literal[
        "supported", "partially_supported", "contradicted", "irrelevant", "insufficient"
    ]
    rationale: str = Field(min_length=1, max_length=240)
    passage_ids: list[str] = Field(max_length=12)


class UncitedMaterialClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=280)
    section: str = Field(min_length=1, max_length=80)
    recommendation: Literal["add_citation", "qualify", "remove_or_rewrite", "none"]


class SemanticReportAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    support_assessments: list[SemanticSupportAssessment] = Field(max_length=28)
    uncited_material_claims: list[UncitedMaterialClaim] = Field(max_length=20)
