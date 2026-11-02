import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    domain: str = Field(default="AI adoption economics", min_length=1, max_length=120)

    @field_validator("title", "domain")
    @classmethod
    def strip_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value.strip()


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    domain: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("title", "domain")
    @classmethod
    def strip_if_present(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value.strip()


class ProjectPurgeRequest(BaseModel):
    confirmation: Literal["DELETE"]
    project_title: str = Field(min_length=1, max_length=160)

    @field_validator("project_title")
    @classmethod
    def strip_project_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Project title cannot be blank")
        return value.strip()


class VedaDataPurgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE VEDA DATA"]


class VedaDataPurgeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_projects: int = Field(ge=0)
    deleted_preferences: bool
    daily_quota_counters_preserved_until_utc_date: date
    identity_provider_account_deleted: Literal[False]


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str
    domain: str
    archived_at: datetime | None
    purge_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RetrievedDocumentRecordV1(BaseModel):
    """Strict immutable metadata for one retrieved content snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str = Field(min_length=36, max_length=36)
    source_id: str = Field(min_length=1, max_length=36)
    identity_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_version: str = Field(min_length=1, max_length=200)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    locator: str = Field(min_length=1, max_length=300)
    media_type: str = Field(min_length=1, max_length=120)
    access_class: Literal[
        "abstract_only",
        "full_text_html",
        "full_text_pdf",
        "full_text_jats",
        "official_statistics",
        "official_publication_page_body",
    ]
    hash_scope: Literal[
        "raw_document_bytes",
        "bounded_provider_excerpt",
        "normalized_observation_snapshot",
        "legacy_passage_snapshot",
    ]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_event_json_value(value)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 65_536:
            raise ValueError("retrieved-document metadata exceeds its 64 KiB boundary")
        return value


class ClaimUnitSpanV1(BaseModel):
    """Bounded exact character span used by one extracted research claim."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    text: str = Field(min_length=1, max_length=600)
    start: int = Field(ge=0, le=600)
    end: int = Field(ge=1, le=600)
    status: Literal["atomized_exact_span", "whole_sentence", "compound_unatomized"]

    @model_validator(mode="after")
    def validate_span_length(self) -> "ClaimUnitSpanV1":
        if self.start >= self.end or self.end - self.start != len(self.text):
            raise ValueError("claim span offsets must match the exact bounded text")
        return self


class ExtractedPassageV1(BaseModel):
    """Strict transient passage record; source content is never silently clipped."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    id: str = Field(min_length=36, max_length=36)
    source_id: str = Field(min_length=1, max_length=36)
    document_id: str = Field(min_length=36, max_length=36)
    identity_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_version: Literal[1] = 1
    ordinal: int = Field(ge=0, le=10_000)
    locator: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=600)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    truncated: bool
    access_level: Literal[
        "abstract_only",
        "full_text_html",
        "full_text_pdf",
        "full_text_jats",
        "official_statistics",
        "official_publication_page_body",
    ]

    @model_validator(mode="after")
    def validate_content_hash(self) -> "ExtractedPassageV1":
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.content_hash:
            raise ValueError("passage content hash must match the exact passage text")
        return self


class ExtractedClaimV1(BaseModel):
    """Versioned claim span that remains tied to its bounded source passage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    source_id: str = Field(min_length=1, max_length=36)
    passage_id: str = Field(min_length=36, max_length=36)
    passage_text: str = Field(min_length=1, max_length=600)
    unit: ClaimUnitSpanV1
    atomization_version: Literal[1] = 1

    @model_validator(mode="after")
    def validate_exact_passage_span(self) -> "ExtractedClaimV1":
        if self.unit.end > len(self.passage_text):
            raise ValueError("claim span exceeds its exact source passage")
        if self.passage_text[self.unit.start : self.unit.end] != self.unit.text:
            raise ValueError("claim span text must match its exact source passage")
        return self


class UserPreferencesPatch(BaseModel):
    default_depth: Literal["quick", "standard", "deep"] | None = None
    default_budget_ceiling_usd: float | None = Field(default=None, ge=0, le=2)
    retention_days: Literal[30, 90, 365] | None = None


class JobCreate(BaseModel):
    question: str = Field(min_length=10, max_length=2000)
    context: str = Field(default="", max_length=4000)
    geography: str | None = Field(default=None, max_length=160)
    population: str | None = Field(default=None, max_length=300)
    time_horizon: str | None = Field(default=None, max_length=160)
    decision_objective: str | None = Field(default=None, max_length=500)
    comparator: str | None = Field(default=None, max_length=300)
    target_outcome: str | None = Field(default=None, max_length=300)
    denominator: str | None = Field(default=None, max_length=200)
    assumptions_to_test: str | None = Field(default=None, max_length=1000)
    depth: Literal["quick", "standard", "deep"] = "standard"
    model_provider: Literal["disabled", "openrouter", "openai", "sarvam"] | None = None
    model_name: str | None = Field(default=None, max_length=160)
    budget_ceiling_usd: float = Field(default=0.0, ge=0, le=20)
    budget_ceiling_inr: float = Field(default=0.0, ge=0, le=20)
    idempotency_key: str = Field(min_length=8, max_length=120)
    parent_job_id: str | None = None
    conversation_id: str | None = None

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Question must contain at least 10 non-whitespace characters")
        return value

    @field_validator("comparator", "target_outcome", "denominator", "assumptions_to_test")
    @classmethod
    def normalize_optional_planning_input(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class ResearchScopeV1(BaseModel):
    """Versioned, bounded research scope persisted with each job."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    context: str | None = Field(default=None, max_length=4000)
    geography: str | None = Field(default=None, max_length=160)
    population: str | None = Field(default=None, max_length=300)
    time_horizon: str | None = Field(default=None, max_length=160)
    decision_objective: str | None = Field(default=None, max_length=500)
    comparator: str | None = Field(default=None, max_length=300)
    target_outcome: str | None = Field(default=None, max_length=300)
    denominator: str | None = Field(default=None, max_length=200)
    assumptions_to_test: str | None = Field(default=None, max_length=1000)
    extensions: dict[str, Any] = Field(default_factory=dict)


def versioned_scope(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate v1 scopes and losslessly envelope unversioned legacy scopes."""
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("research scope must be an object")
    raw = dict(value)
    if "schema_version" in raw:
        return ResearchScopeV1.model_validate(raw).model_dump(mode="json")

    known = {
        key: raw.pop(key)
        for key in (
            "context",
            "geography",
            "population",
            "time_horizon",
            "decision_objective",
            "comparator",
            "target_outcome",
            "denominator",
            "assumptions_to_test",
        )
        if key in raw
    }
    known["extensions"] = raw
    return ResearchScopeV1.model_validate(known).model_dump(mode="json")


class PlannedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=500)
    focus: Literal[
        "direct_evidence",
        "requested_scope",
        "follow_up_update",
        "counterevidence",
        "limitations_and_measurement",
        "design_and_scope",
        "heterogeneity",
    ]


class SearchProviderExecutionV1(BaseModel):
    """One bounded provider query outcome for an exact research search lens."""

    model_config = ConfigDict(extra="forbid", strict=True)

    provider: Literal["Crossref", "OpenAlex"]
    status: Literal["completed", "failed", "not_attempted"]
    results: int = Field(ge=0, le=100)
    error_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    elapsed_ms: int | None = Field(default=None, ge=0, le=600_000)

    @model_validator(mode="after")
    def validate_status(self) -> "SearchProviderExecutionV1":
        if self.status == "failed" and self.error_code is None:
            raise ValueError("failed provider query must retain a sanitized error code")
        if self.status != "failed" and self.error_code is not None:
            raise ValueError("successful or unattempted provider query cannot have an error code")
        if self.status != "completed" and self.results:
            raise ValueError("only a completed provider query may report candidates")
        return self


class SearchLensExecutionV1(BaseModel):
    """Auditable execution record for one query/rationale in a research plan."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    lens_id: str = Field(pattern=r"^L[1-8]$")
    category: Literal[
        "DIRECT_QUESTION",
        "TERMINOLOGY_EXPANSION",
        "STUDY_DESIGN",
        "CONTRARY_OR_NULL_EVIDENCE",
        "SUBGROUP_OR_POPULATION",
        "ALTERNATIVE_EXPLANATION",
    ]
    purpose: str = Field(min_length=1, max_length=500)
    focus: Literal[
        "direct_evidence",
        "requested_scope",
        "follow_up_update",
        "counterevidence",
        "limitations_and_measurement",
        "design_and_scope",
        "heterogeneity",
    ]
    exact_query: str = Field(min_length=1, max_length=300)
    started_at: datetime
    completed_at: datetime | None = None
    pagination_state: Literal["single_page_bounded", "not_attempted"]
    status: Literal["completed", "partial", "failed", "not_attempted"]
    providers: list[SearchProviderExecutionV1] = Field(max_length=2)
    candidate_keys: list[str] = Field(max_length=128)
    selected_candidate_keys: list[str] = Field(max_length=20)
    retrieval_cost_status: Literal["unknown"] = "unknown"

    @field_validator("candidate_keys", "selected_candidate_keys")
    @classmethod
    def unique_candidate_records(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("search-lens candidate records must be unique")
        return value

    @model_validator(mode="after")
    def validate_execution_summary(self) -> "SearchLensExecutionV1":
        states = {record.status for record in self.providers}
        if self.status == "not_attempted":
            if (
                any(record.status != "not_attempted" for record in self.providers)
                or self.completed_at is not None
                or self.candidate_keys
            ):
                raise ValueError("unattempted lens cannot contain provider or candidate results")
        elif self.completed_at is None:
            raise ValueError("attempted lens must record its completion time")
        elif self.status == "completed" and (not states or states != {"completed"}):
            raise ValueError("completed lens requires completed provider queries")
        elif self.status == "failed" and ("completed" in states or "failed" not in states):
            raise ValueError("failed lens requires failures and no successful provider query")
        elif self.status == "partial" and not ("completed" in states and states != {"completed"}):
            raise ValueError(
                "partial lens requires both successful and incomplete provider queries"
            )
        if not set(self.selected_candidate_keys).issubset(self.candidate_keys):
            raise ValueError("selected search-lens candidates must have been discovered")
        return self


class CitationExpansionSeedV1(BaseModel):
    """One eligible OpenAlex seed and its bounded one-hop sample accounting."""

    model_config = ConfigDict(extra="forbid", strict=True)

    openalex_work_id: str = Field(pattern=r"^W[0-9]{1,20}$")
    references_available: int = Field(ge=0, le=100_000)
    backward_candidate_keys: list[str] = Field(max_length=10)
    forward_result_count: int | None = Field(default=None, ge=0, le=10_000_000)
    forward_returned_count: int | None = Field(default=None, ge=0, le=10)
    forward_candidate_keys: list[str] = Field(max_length=10)


class CitationExpansionErrorV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stage: Literal["work_details", "backward_references", "forward_citations"]
    error_code: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86_400)


class CitationExpansionExecutionV1(BaseModel):
    """Versioned account of a capped citation-neighborhood metadata request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    status: Literal[
        "completed",
        "partial",
        "failed",
        "not_attempted_operator_opt_in_required",
        "not_attempted_deadline",
        "not_attempted_no_eligible_seeds",
    ]
    method: Literal["openalex_one_hop_bounded_v1"]
    seed_limit: Literal[2] = 2
    per_direction_limit: Literal[3] = 3
    seed_work_ids: list[str] = Field(max_length=2)
    seeds: list[CitationExpansionSeedV1] = Field(max_length=2)
    requests_attempted: int = Field(ge=0, le=8)
    candidate_keys: list[str] = Field(max_length=40)
    omitted_backward_count: int = Field(ge=0, le=200_000)
    reported_cost_usd: float | None = Field(default=None, ge=0, le=100)
    reported_cost_status: Literal["provider_reported_complete", "unknown", "not_observed"]
    sampling_note: str = Field(min_length=1, max_length=500)
    errors: list[CitationExpansionErrorV1] = Field(max_length=8)

    @model_validator(mode="after")
    def validate_citation_expansion(self) -> "CitationExpansionExecutionV1":
        if len(set(self.seed_work_ids)) != len(self.seed_work_ids):
            raise ValueError("citation-expansion seed IDs must be unique")
        if self.status.startswith("not_attempted") and self.requests_attempted != 0:
            raise ValueError("unattempted citation expansion cannot report provider requests")
        if (
            self.reported_cost_status == "provider_reported_complete"
            and self.reported_cost_usd is None
        ):
            raise ValueError("complete reported citation cost requires a numeric amount")
        if self.reported_cost_status == "not_observed" and self.reported_cost_usd is not None:
            raise ValueError("unobserved citation cost cannot contain an amount")
        if self.status == "completed" and self.errors:
            raise ValueError("completed citation expansion cannot contain provider errors")
        if not set(self.seed_work_ids).issuperset(seed.openalex_work_id for seed in self.seeds):
            raise ValueError("citation-expansion details must refer to a requested seed")
        return self


class PlannedSubquestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=500)


def _validate_lexical_overlap_features(features: BaseModel) -> None:
    if features.weights != {"title_coverage": 0.7, "abstract_coverage": 0.3}:
        raise ValueError("ranking weights must match lexical_overlap_v1")
    if features.query_term_count == 0:
        expected_title = expected_abstract = expected_score = 0.0
    else:
        expected_title = len(features.matched_title_terms) / features.query_term_count
        expected_abstract = len(features.matched_abstract_terms) / features.query_term_count
        expected_score = 0.7 * expected_title + 0.3 * expected_abstract
    if (
        abs(features.title_coverage - expected_title) > 1e-6
        or abs(features.abstract_coverage - expected_abstract) > 1e-6
        or abs(features.score - expected_score) > 1e-6
    ):
        raise ValueError("lexical overlap score and coverage must match stored features")
    if features.matched_title_terms != sorted(set(features.matched_title_terms)):
        raise ValueError("matched title terms must be unique and sorted")
    if features.matched_abstract_terms != sorted(set(features.matched_abstract_terms)):
        raise ValueError("matched abstract terms must be unique and sorted")
    if len(features.matched_title_terms) > features.query_term_count:
        raise ValueError("matched title terms cannot exceed the query-term count")
    if len(features.matched_abstract_terms) > features.query_term_count:
        raise ValueError("matched abstract terms cannot exceed the query-term count")
    if (
        features.query_terms != sorted(set(features.query_terms))
        or len(features.query_terms) != features.query_term_count
    ):
        raise ValueError("query terms must be unique, sorted, and match the term count")
    if not set(features.matched_title_terms).issubset(features.query_terms):
        raise ValueError("matched title terms must come from the query")
    if not set(features.matched_abstract_terms).issubset(features.query_terms):
        raise ValueError("matched abstract terms must come from the query")


class PlannedQueryAlignmentV1(BaseModel):
    """Lexical overlap with the exact provider query that returned the candidate."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    algorithm: Literal["lexical_overlap_v1"]
    ranking_query_basis: Literal["recorded_provider_query"]
    score: float = Field(ge=0, le=1)
    score_scale: Literal["0_to_1"]
    query_term_count: int = Field(ge=0, le=120)
    query_terms: list[str] = Field(max_length=120)
    query_terms_truncated: bool
    matched_title_terms: list[str] = Field(max_length=120)
    matched_abstract_terms: list[str] = Field(max_length=120)
    title_coverage: float = Field(ge=0, le=1)
    abstract_coverage: float = Field(ge=0, le=1)
    weights: dict[Literal["title_coverage", "abstract_coverage"], float]
    explanation: str = Field(min_length=1, max_length=300)
    interpretation_limit: Literal[
        "Retrieval relevance only; not source quality, study validity, claim support, or truth."
    ]

    @model_validator(mode="after")
    def validate_feature_consistency(self) -> "PlannedQueryAlignmentV1":
        _validate_lexical_overlap_features(self)
        return self


class CandidateRelevanceV1(BaseModel):
    """Reproducible bibliographic overlap features; never an evidence-quality judgment."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    algorithm: Literal["lexical_overlap_v1"]
    ranking_query_basis: Literal["user_research_question"]
    score: float = Field(ge=0, le=1)
    score_scale: Literal["0_to_1"]
    query_term_count: int = Field(ge=0, le=120)
    query_terms: list[str] = Field(max_length=120)
    query_terms_truncated: bool
    matched_title_terms: list[str] = Field(max_length=120)
    matched_abstract_terms: list[str] = Field(max_length=120)
    title_coverage: float = Field(ge=0, le=1)
    abstract_coverage: float = Field(ge=0, le=1)
    weights: dict[Literal["title_coverage", "abstract_coverage"], float]
    explanation: str = Field(min_length=1, max_length=300)
    planned_query_alignment: PlannedQueryAlignmentV1 | None = None
    selection_score: float | None = Field(default=None, ge=0, le=1)
    selection_basis: Literal["user_question", "recorded_provider_query", "tie"] | None = None
    topic_eligibility_basis: (
        Literal["original_question", "recorded_query_domain_expansion", "not_eligible"] | None
    ) = None
    interpretation_limit: Literal[
        "Retrieval relevance only; not source quality, study validity, claim support, or truth."
    ]

    @model_validator(mode="after")
    def validate_feature_consistency(self) -> "CandidateRelevanceV1":
        _validate_lexical_overlap_features(self)
        if self.planned_query_alignment is None:
            if self.selection_score is not None or self.selection_basis is not None:
                raise ValueError("selection metadata requires planned-query alignment features")
        else:
            expected_selection_score = max(self.score, self.planned_query_alignment.score)
            expected_basis = (
                "tie"
                if self.score == self.planned_query_alignment.score
                else "user_question"
                if self.score > self.planned_query_alignment.score
                else "recorded_provider_query"
            )
            if (
                self.selection_score != expected_selection_score
                or self.selection_basis != expected_basis
            ):
                raise ValueError(
                    "selection metadata must identify the strongest lexical retrieval signal"
                )
        return self


class ScholarlyWorkRecordV1(BaseModel):
    """Bounded provider-neutral record carried from discovery into persistence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    external_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    doi: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    authors: list[dict[str, str]] = Field(max_length=100)
    published_year: int | None = Field(default=None, ge=1000, le=3000)
    publisher: str | None = Field(default=None, max_length=300)
    abstract_excerpt: str | None = Field(default=None, max_length=600)
    query: str = Field(min_length=1, max_length=300)
    provider: str = Field(default="Crossref", min_length=1, max_length=100)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    source_type: Literal["scholarly_article", "institutional_report", "official_statistics"] = (
        "scholarly_article"
    )

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        if any(
            len(author) > 8
            or any(not key or len(key) > 80 or len(name) > 300 for key, name in author.items())
            for author in value
        ):
            raise ValueError("candidate author metadata exceeds its field boundary")
        return value

    @field_validator("provider_metadata")
    @classmethod
    def validate_provider_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_event_json_value(value)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 65_536:
            raise ValueError("candidate provider metadata exceeds its 64 KiB boundary")
        return value


class CandidateOccurrenceV1(BaseModel):
    """One metadata-only discovery occurrence and its deterministic disposition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    candidate_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    record: ScholarlyWorkRecordV1
    canonical_identity: str = Field(min_length=1, max_length=500)
    relevance: CandidateRelevanceV1 | None = None
    source_governance: dict[str, Any] | None = None
    disposition: Literal["selected", "excluded"]
    reason_code: Literal[
        "license_not_verified",
        "no_requested_geography_observation",
        "duplicate_canonical_identity",
        "malformed_bibliographic_title",
        "repository_artifact_description_not_abstract",
        "insufficient_topic_overlap",
        "selected_by_relevance",
        "selected_by_discovery_order",
        "source_limit",
    ]
    canonical_external_id: str | None = Field(default=None, max_length=500)
    discovered_at: datetime
    ranking_order: int = Field(ge=1, le=10_000)

    @field_validator("source_governance")
    @classmethod
    def validate_source_governance_record(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is None:
            return None
        from app.research.source_governance import SourceGovernanceDecision

        return SourceGovernanceDecision.model_validate(value).model_dump(mode="json")

    @model_validator(mode="after")
    def validate_candidate_disposition(self) -> "CandidateOccurrenceV1":
        is_statistics = self.record.source_type == "official_statistics"
        if is_statistics != (self.relevance is None):
            raise ValueError("only official-statistics candidates omit lexical relevance")
        if self.disposition == "selected":
            expected = "selected_by_discovery_order" if is_statistics else "selected_by_relevance"
            if (
                self.reason_code != expected
                or self.canonical_external_id != self.record.external_id
            ):
                raise ValueError("selected candidate must identify its selected source record")
        elif self.reason_code in {"selected_by_relevance", "selected_by_discovery_order"}:
            raise ValueError("excluded candidate cannot use a selected disposition reason")
        if self.canonical_external_id == self.record.external_id and self.reason_code in {
            "license_not_verified",
            "no_requested_geography_observation",
            "malformed_bibliographic_title",
            "repository_artifact_description_not_abstract",
            "source_limit",
        }:
            raise ValueError("excluded candidate cannot identify itself as selected")
        return self


def candidate_relevance_for_api(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return valid bounded lexical features or omit corrupt optional ranking metadata."""
    if not isinstance(value, Mapping):
        return None
    try:
        _validate_event_json_value(value)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 65_536:
            return None
        return CandidateRelevanceV1.model_validate(value).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError):
        return None


class DecisionContextOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_objective: str | None = None
    context: str | None = None
    population: str | None = None
    geography: str | None = None
    time_horizon: str | None = None


class PlanStoppingCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution: str = Field(min_length=1, max_length=1000)
    insufficient_evidence: str = Field(min_length=1, max_length=1000)
    incomparability: str = Field(min_length=1, max_length=1000)
    counterevidence: str = Field(min_length=1, max_length=1000)


class ResearchPlanV2(BaseModel):
    """Versioned deterministic plan; planning metadata is not a model assessment."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    version: Literal[2]
    planning_mode: Literal["deterministic_bounded_no_model"]
    decision_context: DecisionContextOut
    scope_status: Literal["specified", "underspecified"]
    missing_scope_fields: list[
        Literal["decision_objective", "population", "geography", "time_horizon"]
    ]
    scope_notice: str = Field(min_length=1, max_length=500)
    queries: list[str] = Field(min_length=1, max_length=8)
    query_rationales: list[PlannedQuery] = Field(min_length=1, max_length=8)
    subquestions: list[PlannedSubquestion] = Field(min_length=1, max_length=5)
    stopping_criteria: PlanStoppingCriteria
    resource_limits: dict[str, Any]

    @model_validator(mode="after")
    def validate_search_plan(self) -> "ResearchPlanV2":
        if self.queries != [item.query for item in self.query_rationales]:
            raise ValueError("query_rationales must align one-to-one with queries")
        if "counterevidence" not in {item.focus for item in self.query_rationales}:
            raise ValueError("every profile must reserve a planned counterevidence query")
        missing = self.missing_scope_fields
        if bool(missing) != (self.scope_status == "underspecified"):
            raise ValueError("scope_status must agree with missing_scope_fields")
        return self

    @field_validator("resource_limits")
    @classmethod
    def validate_resource_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        return CheckpointDepthProfileV1.model_validate(value).model_dump(mode="python")


class PlanningCounterfactualLens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["specified", "unspecified"]
    user_statement: str | None = Field(default=None, max_length=300)
    prompt: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def validate_status(self) -> "PlanningCounterfactualLens":
        if (self.user_statement is not None) != (self.status == "specified"):
            raise ValueError(
                "counterfactual status must match whether the user supplied a comparator"
            )
        return self


class PlanningOutcomeLens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["specified", "partially_specified", "unspecified"]
    target_outcome: str | None = Field(default=None, max_length=300)
    denominator: str | None = Field(default=None, max_length=200)
    possible_outcomes_prompt: str = Field(min_length=1, max_length=600)
    denominator_prompt: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def validate_status(self) -> "PlanningOutcomeLens":
        specified_count = sum(
            value is not None for value in (self.target_outcome, self.denominator)
        )
        expected = (
            "unspecified"
            if specified_count == 0
            else "specified"
            if specified_count == 2
            else "partially_specified"
        )
        if self.status != expected:
            raise ValueError("outcome status must match the supplied outcome and denominator")
        return self


class PlanningAssumptionsLens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["user_supplied", "not_provided"]
    user_supplied_text: str | None = Field(default=None, max_length=1000)
    system_inferred_assumptions: list[str] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_user_only(self) -> "PlanningAssumptionsLens":
        if (self.user_supplied_text is not None) != (self.status == "user_supplied"):
            raise ValueError("assumption status must match explicit user input")
        if self.system_inferred_assumptions:
            raise ValueError("deterministic planning cannot infer user assumptions")
        return self


class PlanningConfoundingLens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicability: Literal["evaluate_if_nonrandomized_or_observational_evidence"]
    considerations: list[
        Literal[
            "confounding",
            "selection_and_attrition",
            "measurement_and_reporting",
            "concurrent_changes_or_spillovers",
        ]
    ]
    prompt: str = Field(min_length=1, max_length=800)


class PlanningEvidenceTypesLens(BaseModel):
    model_config = ConfigDict(extra="forbid")

    types_to_consider: list[
        Literal[
            "randomized_or_experimental",
            "quasi_experimental",
            "observational_or_panel",
            "qualitative_or_implementation",
            "systematic_review_or_meta_analysis",
            "official_descriptive_statistics",
        ]
    ]
    mode: Literal["planning_lenses_only_not_provider_filters"]
    provider_type_filter_applied: Literal[False]


class ResearchPlanningLensesV3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparator_or_counterfactual: PlanningCounterfactualLens
    outcomes: PlanningOutcomeLens
    assumptions: PlanningAssumptionsLens
    confounding: PlanningConfoundingLens
    evidence_types: PlanningEvidenceTypesLens


class ResearchPlanV3(BaseModel):
    """Deterministic research plan with explicit, non-inferential analytical lenses."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[3]
    version: Literal[3]
    planning_mode: Literal["deterministic_bounded_no_model"]
    decision_context: DecisionContextOut
    scope_status: Literal["specified", "underspecified"]
    missing_scope_fields: list[
        Literal["decision_objective", "population", "geography", "time_horizon"]
    ]
    scope_notice: str = Field(min_length=1, max_length=500)
    planning_lenses: ResearchPlanningLensesV3
    queries: list[str] = Field(min_length=1, max_length=8)
    query_rationales: list[PlannedQuery] = Field(min_length=1, max_length=8)
    subquestions: list[PlannedSubquestion] = Field(min_length=1, max_length=8)
    stopping_criteria: PlanStoppingCriteria
    resource_limits: dict[str, Any]

    @model_validator(mode="after")
    def validate_search_plan(self) -> "ResearchPlanV3":
        if self.queries != [item.query for item in self.query_rationales]:
            raise ValueError("query_rationales must align one-to-one with queries")
        if "counterevidence" not in {item.focus for item in self.query_rationales}:
            raise ValueError("every profile must reserve a planned counterevidence query")
        if bool(self.missing_scope_fields) != (self.scope_status == "underspecified"):
            raise ValueError("scope_status must agree with missing_scope_fields")
        return self

    @field_validator("resource_limits")
    @classmethod
    def validate_resource_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        return CheckpointDepthProfileV1.model_validate(value).model_dump(mode="python")


class ResearchPlanProvenanceV1(BaseModel):
    """Truthful record of model-assisted selection or deterministic fallback."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["model_selection_applied", "deterministic_fallback"]
    provider: Literal["openrouter", "openai", "sarvam"] | None = None
    model: str | None = Field(default=None, max_length=200)
    fallback_reason: (
        Literal[
            "provider_disabled",
            "provider_not_configured",
            "budget_limit",
            "daily_limit",
            "depth_limit",
            "time_limit",
            "provider_error",
            "uncertain_outcome",
            "invalid_model_plan",
            "provider_blocked",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_provenance(self) -> "ResearchPlanProvenanceV1":
        if self.status == "model_selection_applied":
            if not self.provider or not self.model or self.fallback_reason is not None:
                raise ValueError(
                    "applied model plan requires provider/model and no fallback reason"
                )
        elif self.fallback_reason is None:
            raise ValueError("deterministic plan must disclose its fallback reason")
        if (self.provider is None) != (self.model is None):
            raise ValueError("planning provider and model provenance must be paired")
        return self


class ResearchPlanV4(BaseModel):
    """Strict plan envelope with explicit model-selection or fallback provenance."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[4]
    version: Literal[4]
    planning_mode: Literal["model_assisted_selection", "deterministic_fallback"]
    planning_provenance: ResearchPlanProvenanceV1
    decision_context: DecisionContextOut
    scope_status: Literal["specified", "underspecified"]
    missing_scope_fields: list[
        Literal["decision_objective", "population", "geography", "time_horizon"]
    ]
    scope_notice: str = Field(min_length=1, max_length=500)
    planning_lenses: ResearchPlanningLensesV3
    queries: list[str] = Field(min_length=1, max_length=8)
    query_rationales: list[PlannedQuery] = Field(min_length=1, max_length=8)
    subquestions: list[PlannedSubquestion] = Field(min_length=1, max_length=8)
    stopping_criteria: PlanStoppingCriteria
    resource_limits: dict[str, Any]

    @model_validator(mode="after")
    def validate_search_plan(self) -> "ResearchPlanV4":
        if self.queries != [item.query for item in self.query_rationales]:
            raise ValueError("query_rationales must align one-to-one with queries")
        if "counterevidence" not in {item.focus for item in self.query_rationales}:
            raise ValueError("every plan must preserve a counterevidence query")
        if bool(self.missing_scope_fields) != (self.scope_status == "underspecified"):
            raise ValueError("scope_status must agree with missing_scope_fields")
        expected_mode = (
            "model_assisted_selection"
            if self.planning_provenance.status == "model_selection_applied"
            else "deterministic_fallback"
        )
        if self.planning_mode != expected_mode:
            raise ValueError("planning mode must agree with its provenance")
        return self

    @field_validator("resource_limits")
    @classmethod
    def validate_resource_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        return CheckpointDepthProfileV1.model_validate(value).model_dump(mode="python")


class CheckpointDepthProfileV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: Literal["quick", "standard", "deep"]
    max_queries: int = Field(ge=1, le=8)
    max_records_per_provider_query: int = Field(ge=1, le=20)
    max_sources: int = Field(ge=1, le=100)
    max_html_pages: int = Field(ge=0, le=20)
    max_html_passages: int = Field(ge=0, le=2000)
    max_passages: int = Field(ge=1, le=5000)
    max_model_calls: int = Field(ge=0, le=100)
    max_prompt_characters_per_call: int = Field(ge=1, le=1_000_000)
    max_prompt_characters_total: int = Field(ge=1, le=5_000_000)
    max_prompt_tokens_per_call: int = Field(ge=1, le=1_000_000)
    max_prompt_token_budget_total: int = Field(ge=1, le=5_000_000)
    max_output_tokens_per_call: int = Field(ge=1, le=100_000)
    max_output_token_budget_total: int = Field(ge=1, le=1_000_000)
    max_retries: int = Field(ge=0, le=20)
    max_step_seconds: int = Field(ge=1, le=3600)
    max_pdf_documents: int = Field(default=0, ge=0, le=20)


class CheckpointFollowUpContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    parent_job_id: str = Field(min_length=1, max_length=36)
    parent_question: str = Field(min_length=1, max_length=2000)
    parent_report_id: str | None = Field(default=None, max_length=36)
    parent_report_status: str | None = Field(default=None, max_length=80)
    reused_claim_ids: list[str] = Field(max_length=8)
    reuse_method: Literal["lexical_token_overlap_top8_with_parent_evidence"]
    reuse_boundary: str = Field(min_length=1, max_length=1000)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("reused_claim_ids")
    @classmethod
    def bound_claim_ids(cls, value: list[str]) -> list[str]:
        if any(not claim_id or len(claim_id) > 36 for claim_id in value):
            raise ValueError("reused claim identifiers must be bounded non-empty strings")
        return value


class CheckpointCitationAuditV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    level: str = Field(min_length=1, max_length=100)
    claims_checked: int = Field(ge=0, le=10_000)
    claims_with_valid_source_and_passage: int | None = Field(default=None, ge=0, le=10_000)
    status: Literal["passed", "needs_review"] | None = None
    semantic_support_check: str | None = Field(default=None, max_length=100)
    uncited_material_claim_scan: str | None = Field(default=None, max_length=100)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class CheckpointCitationSourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=1000)
    doi: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    passages: list[str] = Field(max_length=1000)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("passages")
    @classmethod
    def bound_passage_ids(cls, value: list[str]) -> list[str]:
        if any(not passage_id or len(passage_id) > 36 for passage_id in value):
            raise ValueError("citation passage identifiers must be bounded non-empty strings")
        return value


class CheckpointRetryLineageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parent_source_id: str = Field(min_length=1, max_length=36)
    source_id: str = Field(min_length=1, max_length=36)
    kind: Literal["html", "pdf", "jats"]


class CheckpointRetrievalContinuationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    parent_job_id: str = Field(min_length=1, max_length=36)
    budget_ceiling_usd: float = Field(ge=0, le=20)
    budget_ceiling_inr: float = Field(default=0.0, ge=0, le=20)
    retries: list[CheckpointRetryLineageV1] = Field(max_length=100)
    evidence_copy_boundary: str = Field(min_length=1, max_length=2000)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class CheckpointDeferredRetrySourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: str = Field(min_length=1, max_length=36)
    kinds: list[Literal["html", "pdf", "jats"]] = Field(min_length=1, max_length=3)


class CheckpointDeferredRetryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    sources: list[CheckpointDeferredRetrySourceV1] = Field(max_length=100)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class CheckpointEnvelopeV1(BaseModel):
    """Bounded, typed checkpoint sections with an explicit legacy extension area."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    workflow_version: int = Field(default=1, ge=1, le=100)
    depth_profile: CheckpointDepthProfileV1 | None = None
    follow_up_context: CheckpointFollowUpContextV1 | None = None
    plan: ResearchPlanV2 | ResearchPlanV3 | ResearchPlanV4 | None = None
    citation_audit: CheckpointCitationAuditV1 | None = None
    citation_map: dict[str, CheckpointCitationSourceV1] | None = Field(default=None, max_length=100)
    retrieval_continuation: CheckpointRetrievalContinuationV1 | None = None
    deferred_retrieval_retry: CheckpointDeferredRetryV1 | None = None
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("citation_map")
    @classmethod
    def validate_citation_labels(
        cls, value: dict[str, CheckpointCitationSourceV1] | None
    ) -> dict[str, CheckpointCitationSourceV1] | None:
        if value is not None and any(
            not re.fullmatch(r"S[1-9]\d{0,2}", citation_id) for citation_id in value
        ):
            raise ValueError("citation map labels must use bounded S-number identifiers")
        return value


class ReportCitationMapV1(BaseModel):
    """Versioned storage envelope for immutable report citation references."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    citations: dict[str, CheckpointCitationSourceV1] = Field(max_length=100)
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("citations")
    @classmethod
    def validate_citation_labels(
        cls, value: dict[str, CheckpointCitationSourceV1]
    ) -> dict[str, CheckpointCitationSourceV1]:
        if any(not re.fullmatch(r"S[1-9]\d{0,2}", citation_id) for citation_id in value):
            raise ValueError("citation map labels must use bounded S-number identifiers")
        return value

    @model_validator(mode="after")
    def validate_citation_entry_count(self) -> "ReportCitationMapV1":
        if len(self.citations) > 100:
            raise ValueError("report citation map exceeds its source limit")
        return self


class ReportClaimUnitV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str = Field(min_length=1, max_length=36)
    text: str = Field(min_length=1, max_length=5000)
    source_sentence: str = Field(min_length=1, max_length=16_384)
    passage_id: str = Field(min_length=1, max_length=36)
    atomization_status: str = Field(min_length=1, max_length=100)
    atomization_version: int = Field(ge=1, le=100)
    span_start: int = Field(ge=0, le=16_384)
    span_end: int = Field(ge=1, le=16_384)
    span_offset_unit: Literal["unicode_codepoint_exclusive_end"]
    economic_facets: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_span(self) -> "ReportClaimUnitV1":
        if self.span_end <= self.span_start or self.span_end > len(self.source_sentence):
            raise ValueError("report claim span must fit its source sentence")
        if self.source_sentence[self.span_start : self.span_end] != self.text:
            raise ValueError("report claim text must match its source sentence span")
        return self


class ReportDecisionImplicationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal[
        "consider_pilot",
        "scale",
        "pause",
        "avoid",
        "collect_more_evidence",
        "monitor",
        "no_recommendation",
    ]
    condition: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=700)
    assumptions: list[str] = Field(min_length=1, max_length=6)
    unknowns: list[str] = Field(min_length=1, max_length=6)
    claim_ids: list[str] = Field(min_length=1, max_length=12)
    passage_ids: list[str] = Field(max_length=12)
    citations: list[str] = Field(max_length=12)
    status: str = Field(min_length=1, max_length=100)


class ReportLinkIntegrityV1(BaseModel):
    """Deterministic source/passage-link checks; it makes no semantic claim."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    level: Literal["deterministic_link_integrity_only"]
    status: Literal["passed", "needs_review"]
    claims_checked: int = Field(ge=0, le=10_000)
    claims_with_valid_source_and_passage: int | None = Field(default=None, ge=0, le=10_000)


class ReportSemanticAssessmentV1(BaseModel):
    """Advisory model assessment kept distinct from deterministic link integrity."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    method: Literal["not_performed", "model_assisted_not_independently_verified"]
    support_check: str = Field(max_length=100)
    uncited_material_claim_scan: str = Field(max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    audit_schema_version: int | None = Field(default=None, ge=1, le=100)
    items: list[dict[str, Any]] = Field(max_length=256)
    uncited_claims: list[dict[str, Any]] = Field(max_length=200)
    rejected_records: int = Field(ge=0, le=1000)
    input_truncated: bool
    skip_reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_audit_status(self) -> "ReportSemanticAssessmentV1":
        support_not_run = self.support_check == "not_performed"
        uncited_not_run = self.uncited_material_claim_scan == "not_performed"
        if support_not_run != uncited_not_run:
            raise ValueError("semantic support and uncited-claim checks must share run status")
        if support_not_run and (
            self.provider is not None
            or self.model is not None
            or self.audit_schema_version is not None
            or self.items
            or self.uncited_claims
            or self.rejected_records
        ):
            raise ValueError("not-performed semantic audit cannot contain model audit records")
        return self


class ConditionalStatisticsProviderOutcomeV1(BaseModel):
    """Why one optional official-statistics adapter ran or was skipped."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    status: Literal["searched", "not_applicable", "not_attempted"]
    reason_code: (
        Literal[
            "unsupported_topic",
            "geography_not_supplied",
            "unsupported_geography",
            "no_query_plan",
            "deadline_elapsed",
        ]
        | None
    ) = None
    requests: int = Field(default=0, ge=0, le=1)
    results: int = Field(default=0, ge=0, le=1000)
    failures: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_route_outcome(self) -> "ConditionalStatisticsProviderOutcomeV1":
        if self.status == "searched":
            if self.reason_code is not None or self.requests != 1:
                raise ValueError("a searched route must record one request and no skip reason")
            if self.failures > self.requests:
                raise ValueError("route failures cannot exceed requests")
        elif self.status == "not_applicable":
            if self.reason_code not in {
                "unsupported_topic",
                "geography_not_supplied",
                "unsupported_geography",
            }:
                raise ValueError("a non-applicable route requires a topic or geography reason")
            if self.requests or self.results or self.failures:
                raise ValueError("a non-applicable route cannot contain provider outcomes")
        else:
            if self.reason_code not in {"no_query_plan", "deadline_elapsed"}:
                raise ValueError("a route not attempted requires a bounded execution reason")
            if self.requests or self.results or self.failures:
                raise ValueError("a route not attempted cannot contain provider outcomes")
        return self


class ConditionalStatisticsRoutingV1(BaseModel):
    """Versioned optional-provider routing details, separate from scholarly coverage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    world_bank_data360: ConditionalStatisticsProviderOutcomeV1
    ilostat: ConditionalStatisticsProviderOutcomeV1


class ReportConditionalStatisticsRoutingV1(BaseModel):
    """Typed conditional-provider outcomes inside saved report coverage."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["recorded", "not_recorded_for_historical_run", "invalid_record"]
    schema_version: Literal[1] | None = None
    world_bank_data360: ConditionalStatisticsProviderOutcomeV1 | None = None
    ilostat: ConditionalStatisticsProviderOutcomeV1 | None = None

    @model_validator(mode="after")
    def validate_report_routing_record(self) -> "ReportConditionalStatisticsRoutingV1":
        if self.status == "recorded":
            if self.schema_version != 1 or self.world_bank_data360 is None or self.ilostat is None:
                raise ValueError(
                    "recorded report routing requires both versioned provider outcomes"
                )
        elif self.schema_version is not None or self.world_bank_data360 or self.ilostat:
            raise ValueError("unrecorded report routing cannot contain provider outcome data")
        return self


class ReportSearchCoverageV1(BaseModel):
    """Forward-compatible report coverage with a typed optional route record."""

    model_config = ConfigDict(extra="allow")

    conditional_statistics_routing: ReportConditionalStatisticsRoutingV1 | None = None
    citation_expansion: CitationExpansionExecutionV1 | None = None


class ReportVerificationRecordV1(BaseModel):
    """Bounded report checks and synthesis metadata with legacy extensions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    report_schema_version: Literal[1, 2]
    level: Literal["deterministic_link_integrity_only"]
    status: Literal["passed", "needs_review"]
    claims_checked: int = Field(ge=0, le=10_000)
    claims_with_valid_source_and_passage: int | None = Field(default=None, ge=0, le=10_000)
    semantic_support_check: str = Field(max_length=100)
    uncited_material_claim_scan: str = Field(max_length=100)
    semantic_audit_provider: str | None = Field(default=None, max_length=100)
    semantic_audit_model: str | None = Field(default=None, max_length=200)
    semantic_audit_schema_version: int | None = Field(default=None, ge=1, le=100)
    semantic_audit_items: list[dict[str, Any]] = Field(max_length=256)
    uncited_material_claims: list[dict[str, Any]] = Field(max_length=200)
    rejected_semantic_audit_records: int = Field(ge=0, le=1000)
    uncited_scan_input_truncated: bool
    semantic_audit_skip_reason: str | None = Field(default=None, max_length=300)
    model_assisted_appraisal: str = Field(max_length=100)
    model_assisted_synthesis: str = Field(max_length=100)
    finding_to_claim_links: str = Field(max_length=100)
    comparison_section: dict[str, Any] = Field(max_length=64)
    search_coverage: ReportSearchCoverageV1
    findings_with_valid_claim_links: int = Field(ge=0, le=10_000)
    qualifications_with_valid_claim_links: int = Field(ge=0, le=10_000)
    rejected_findings_with_unsupported_numbers: int = Field(ge=0, le=10_000)
    rejected_qualifications_with_unsupported_numbers: int = Field(ge=0, le=10_000)
    decision_implication_status: str = Field(max_length=120)
    decision_implications: list[ReportDecisionImplicationV1] = Field(max_length=6)
    rejected_decision_implications: int = Field(ge=0, le=1000)
    claim_units: list[ReportClaimUnitV1] = Field(max_length=10_000)
    citation_link_integrity: ReportLinkIntegrityV1
    semantic_assessment: ReportSemanticAssessmentV1
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @model_validator(mode="after")
    def validate_separated_assessments(self) -> "ReportVerificationRecordV1":
        if (
            self.citation_link_integrity.level != self.level
            or self.citation_link_integrity.status != self.status
            or self.citation_link_integrity.claims_checked != self.claims_checked
            or self.citation_link_integrity.claims_with_valid_source_and_passage
            != self.claims_with_valid_source_and_passage
        ):
            raise ValueError("deterministic citation integrity fields must agree")
        if (
            self.semantic_assessment.support_check != self.semantic_support_check
            or self.semantic_assessment.uncited_material_claim_scan
            != self.uncited_material_claim_scan
            or self.semantic_assessment.provider != self.semantic_audit_provider
            or self.semantic_assessment.model != self.semantic_audit_model
            or self.semantic_assessment.audit_schema_version != self.semantic_audit_schema_version
            or self.semantic_assessment.items != self.semantic_audit_items
            or self.semantic_assessment.uncited_claims != self.uncited_material_claims
            or self.semantic_assessment.rejected_records != self.rejected_semantic_audit_records
            or self.semantic_assessment.input_truncated != self.uncited_scan_input_truncated
            or self.semantic_assessment.skip_reason != self.semantic_audit_skip_reason
        ):
            raise ValueError("semantic assessment fields must agree")
        return self


class ReportVerificationEnvelopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    record: ReportVerificationRecordV1
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class BuiltReportStageV1(BaseModel):
    """Validated transient report payload passed from synthesis into persistence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    body_markdown: str = Field(min_length=1, max_length=500_000)
    citation_map: ReportCitationMapV1
    verification: ReportVerificationRecordV1
    model_name: str | None = Field(default=None, max_length=160)


_CHECKPOINT_SECTION_MODELS: dict[str, type[BaseModel]] = {
    "depth_profile": CheckpointDepthProfileV1,
    "follow_up_context": CheckpointFollowUpContextV1,
    "citation_audit": CheckpointCitationAuditV1,
    "retrieval_continuation": CheckpointRetrievalContinuationV1,
    "deferred_retrieval_retry": CheckpointDeferredRetryV1,
}


def versioned_checkpoint(value: Mapping[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Upcast bounded legacy checkpoints; strict mode is required for new writes.

    Malformed legacy sections are retained under extensions.invalid_legacy_sections
    and omitted from their active section so recovery code can use its safe fallback.
    """
    if not isinstance(value, Mapping):
        raise ValueError("research checkpoint must be an object")
    raw = dict(value)
    _validate_checkpoint_json_value(raw)
    encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 262_144:
        raise ValueError("research checkpoint exceeds its 256 KiB storage boundary")
    version = raw.pop("schema_version", 1)
    if version != 1 or isinstance(version, bool):
        raise ValueError("unsupported research checkpoint schema version")
    extensions = raw.pop("extensions", {})
    if not isinstance(extensions, Mapping):
        raise ValueError("research checkpoint extensions must be an object")
    extensions = dict(extensions)
    known_fields = set(CheckpointEnvelopeV1.model_fields) - {"schema_version", "extensions"}
    fields = {key: raw.pop(key) for key in list(raw) if key in known_fields}
    for key, item in raw.items():
        if key in extensions:
            raise ValueError("checkpoint extension conflicts with a legacy field")
        extensions[key] = item

    invalid_sections: dict[str, Any] = {}
    for key, model in _CHECKPOINT_SECTION_MODELS.items():
        if key in fields and fields[key] is not None:
            fields[key] = _versioned_checkpoint_section(fields[key], model, strict=strict)
            if fields[key] is None:
                invalid_sections[key] = value[key]
                fields.pop(key)
    if "plan" in fields and fields["plan"] is not None:
        fields["plan"] = _versioned_checkpoint_plan(fields["plan"], strict=strict)
        if fields["plan"] is None:
            invalid_sections["plan"] = value["plan"]
            fields.pop("plan")
    if "citation_map" in fields and fields["citation_map"] is not None:
        citation_map = fields["citation_map"]
        if isinstance(citation_map, Mapping) and len(citation_map) <= 100:
            try:
                fields["citation_map"] = {
                    str(citation_id): _versioned_checkpoint_section(
                        item, CheckpointCitationSourceV1, strict=True
                    )
                    for citation_id, item in citation_map.items()
                }
                if any(
                    not key.startswith("S") or not key[1:].isdigit()
                    for key in fields["citation_map"]
                ):
                    raise ValueError("citation map keys must use S-number labels")
            except (ValidationError, ValueError):
                if strict:
                    raise
                invalid_sections["citation_map"] = value["citation_map"]
                fields.pop("citation_map", None)
        elif strict:
            raise ValueError("citation map must be a bounded object")
        else:
            invalid_sections["citation_map"] = value["citation_map"]
            fields.pop("citation_map", None)
    if invalid_sections:
        existing = extensions.get("invalid_legacy_sections", {})
        if not isinstance(existing, Mapping):
            raise ValueError("invalid legacy checkpoint section envelope")
        extensions["invalid_legacy_sections"] = {**dict(existing), **invalid_sections}
    fields["schema_version"] = 1
    fields.setdefault("workflow_version", 1)
    fields["extensions"] = extensions
    try:
        checkpoint = CheckpointEnvelopeV1.model_validate(fields)
    except ValidationError:
        if strict:
            raise
        # Invalid scalar envelope fields cannot be trusted for recovery. Keep
        # their original values in extensions and rely on dataclass defaults.
        for key in ("workflow_version",):
            if key in fields:
                extensions.setdefault("invalid_legacy_sections", {})[key] = fields.pop(key)
        fields["extensions"] = extensions
        checkpoint = CheckpointEnvelopeV1.model_validate(fields)
    result = checkpoint.model_dump(mode="json", exclude_unset=True)
    _remove_empty_checkpoint_extensions(result, root=True)
    return result


def _versioned_checkpoint_section(
    value: Any, model: type[BaseModel], *, strict: bool
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        if strict:
            raise ValueError("known checkpoint section must be an object")
        return None
    raw = dict(value)
    if "extensions" in model.model_fields:
        extensions = raw.pop("extensions", {})
        if not isinstance(extensions, Mapping):
            if strict:
                raise ValueError("checkpoint section extensions must be an object")
            return None
        extensions = dict(extensions)
        known_fields = set(model.model_fields) - {"extensions"}
        fields = {key: raw.pop(key) for key in list(raw) if key in known_fields}
        for key, item in raw.items():
            if key in extensions:
                if strict:
                    raise ValueError("checkpoint section extension conflicts with a legacy field")
                return None
            extensions[key] = item
        fields["extensions"] = extensions
        if "schema_version" in model.model_fields:
            fields.setdefault("schema_version", 1)
    else:
        fields = raw
    try:
        validated = model.model_validate(fields)
    except ValidationError:
        if strict:
            raise
        return None
    result = validated.model_dump(mode="json", exclude_unset=True)
    if not result.get("extensions"):
        result.pop("extensions", None)
    return result


def _versioned_checkpoint_plan(value: Any, *, strict: bool) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        if strict:
            raise ValueError("research plan checkpoint must be an object")
        return None
    version = value.get("schema_version", value.get("version"))
    model = (
        ResearchPlanV2
        if version == 2
        else ResearchPlanV3
        if version == 3
        else ResearchPlanV4
        if version == 4
        else None
    )
    if model is None:
        if strict:
            raise ValueError("unsupported research plan checkpoint version")
        return None
    try:
        return model.model_validate(value).model_dump(mode="json")
    except ValidationError:
        if strict:
            raise
        return None


def _validate_checkpoint_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("research checkpoint nesting exceeds its limit")
    if isinstance(value, Mapping):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 200 for key in value):
            raise ValueError("research checkpoint object exceeds its key boundary")
        for item in value.values():
            _validate_checkpoint_json_value(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 1000:
            raise ValueError("research checkpoint array exceeds its item boundary")
        for item in value:
            _validate_checkpoint_json_value(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 16_384:
            raise ValueError("research checkpoint string exceeds its character boundary")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("research checkpoint numbers must be finite")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("research checkpoint must contain only JSON values")


def _remove_empty_checkpoint_extensions(value: Any, *, root: bool = False) -> None:
    if isinstance(value, dict):
        if not root and not value.get("extensions"):
            value.pop("extensions", None)
        for item in value.values():
            _remove_empty_checkpoint_extensions(item)
    elif isinstance(value, list):
        for item in value:
            _remove_empty_checkpoint_extensions(item)


def _validate_report_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("report JSON nesting exceeds its limit")
    if isinstance(value, Mapping):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 200 for key in value):
            raise ValueError("report JSON object exceeds its key boundary")
        for item in value.values():
            _validate_report_json_value(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 10_000:
            raise ValueError("report JSON array exceeds its item boundary")
        for item in value:
            _validate_report_json_value(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 16_384:
            raise ValueError("report JSON string exceeds its character boundary")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("report JSON numbers must be finite")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("report JSON must contain only JSON values")


def _bounded_report_payload(value: Any, *, max_bytes: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("report payload must be an object")
    raw = dict(value)
    _validate_report_json_value(raw)
    encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError("report payload exceeds its storage boundary")
    return raw


def _safe_report_citation_map_fallback() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "citations": {},
        "extensions": {"legacy_read_status": "malformed_or_unsupported"},
    }


def versioned_report_citation_map(
    value: Mapping[str, Any] | None, *, strict: bool = False
) -> dict[str, Any]:
    """Normalize legacy report maps and validate new v1 envelopes without writing legacy rows."""
    try:
        raw = _bounded_report_payload(value or {}, max_bytes=4_194_304)
        version = raw.pop("schema_version", None)
        is_envelope = "citations" in raw or version is not None
        if is_envelope:
            if version != 1 or isinstance(version, bool):
                raise ValueError("unsupported report citation-map schema version")
            citations = raw.pop("citations", None)
            if not isinstance(citations, Mapping) or len(citations) > 100:
                raise ValueError("report citation map must be a bounded object")
            extensions = raw.pop("extensions", {})
            if not isinstance(extensions, Mapping):
                raise ValueError("report citation-map extensions must be an object")
            extensions = dict(extensions)
            for key, item in raw.items():
                if key in extensions:
                    raise ValueError("report citation-map extension conflicts with a field")
                extensions[key] = item
        else:
            citations = {
                key: item
                for key, item in raw.items()
                if isinstance(key, str) and re.fullmatch(r"S[1-9]\d{0,2}", key)
            }
            extensions = {
                key: item
                for key, item in raw.items()
                if not isinstance(key, str) or not re.fullmatch(r"S[1-9]\d{0,2}", key)
            }
            if strict and extensions:
                raise ValueError("new report citation maps cannot contain unknown root fields")

        normalized: dict[str, dict[str, Any]] = {}
        invalid_entries: dict[str, str] = {}
        for label, entry in citations.items():
            if not isinstance(label, str) or not re.fullmatch(r"S[1-9]\d{0,2}", label):
                if strict:
                    raise ValueError("citation map labels must use bounded S-number identifiers")
                invalid_entries[str(label)[:200]] = "invalid_label"
                continue
            try:
                citation = _versioned_checkpoint_section(
                    entry, CheckpointCitationSourceV1, strict=strict
                )
                if citation is None:
                    raise ValueError("invalid citation record")
                normalized[label] = citation
            except (ValidationError, ValueError):
                if strict:
                    raise
                invalid_entries[label] = "invalid_legacy_record"
        if invalid_entries:
            prior = extensions.get("invalid_legacy_entries", {})
            if not isinstance(prior, Mapping):
                if strict:
                    raise ValueError("invalid report citation-map extension")
                prior = {}
            extensions["invalid_legacy_entries"] = {**dict(prior), **invalid_entries}
        result = ReportCitationMapV1.model_validate(
            {"schema_version": 1, "citations": normalized, "extensions": extensions}
        )
        return result.model_dump(mode="json", exclude_unset=True)
    except (ValidationError, ValueError, TypeError):
        if strict:
            raise
        return _safe_report_citation_map_fallback()


_REPORT_VERIFICATION_DEFAULTS: dict[str, Any] = {
    "report_schema_version": 1,
    "level": "deterministic_link_integrity_only",
    "status": "needs_review",
    "claims_checked": 0,
    "claims_with_valid_source_and_passage": None,
    "semantic_support_check": "not_performed",
    "uncited_material_claim_scan": "not_performed",
    "semantic_audit_provider": None,
    "semantic_audit_model": None,
    "semantic_audit_schema_version": None,
    "semantic_audit_items": [],
    "uncited_material_claims": [],
    "rejected_semantic_audit_records": 0,
    "uncited_scan_input_truncated": False,
    "semantic_audit_skip_reason": None,
    "model_assisted_appraisal": "not_performed",
    "model_assisted_synthesis": "not_performed",
    "finding_to_claim_links": "not_recorded",
    "comparison_section": {"status": "not_recorded"},
    "search_coverage": {"status": "not_recorded"},
    "findings_with_valid_claim_links": 0,
    "qualifications_with_valid_claim_links": 0,
    "rejected_findings_with_unsupported_numbers": 0,
    "rejected_qualifications_with_unsupported_numbers": 0,
    "decision_implication_status": "not_recorded",
    "decision_implications": [],
    "rejected_decision_implications": 0,
    "claim_units": [],
}


def _safe_report_verification_fallback() -> dict[str, Any]:
    record = dict(_REPORT_VERIFICATION_DEFAULTS)
    record["citation_link_integrity"] = {
        "schema_version": 1,
        "level": "deterministic_link_integrity_only",
        "status": "needs_review",
        "claims_checked": 0,
        "claims_with_valid_source_and_passage": None,
    }
    record["semantic_assessment"] = {
        "schema_version": 1,
        "method": "not_performed",
        "support_check": "not_performed",
        "uncited_material_claim_scan": "not_performed",
        "provider": None,
        "model": None,
        "audit_schema_version": None,
        "items": [],
        "uncited_claims": [],
        "rejected_records": 0,
        "input_truncated": False,
        "skip_reason": None,
    }
    return {
        "schema_version": 1,
        "record": record,
        "extensions": {"legacy_read_status": "malformed_or_unsupported"},
    }


def versioned_report_verification(
    value: Mapping[str, Any] | None, *, strict: bool = False
) -> dict[str, Any]:
    """Normalize bounded v1/v2 report checks; semantic judgments stay advisory and separate."""
    try:
        raw = _bounded_report_payload(value or {}, max_bytes=8_388_608)
        envelope_extensions: dict[str, Any] = {}
        if "record" in raw:
            version = raw.pop("schema_version", None)
            if version != 1 or isinstance(version, bool):
                raise ValueError("unsupported report-verification envelope version")
            record_value = raw.pop("record")
            if not isinstance(record_value, Mapping):
                raise ValueError("report-verification record must be an object")
            given_extensions = raw.pop("extensions", {})
            if not isinstance(given_extensions, Mapping):
                raise ValueError("report-verification extensions must be an object")
            envelope_extensions = dict(given_extensions)
            for key, item in raw.items():
                if key in envelope_extensions:
                    raise ValueError("report-verification extension conflicts with a field")
                envelope_extensions[key] = item
            fields = dict(record_value)
        else:
            fields = raw

        extensions = fields.pop("extensions", {})
        if not isinstance(extensions, Mapping):
            raise ValueError("report-verification record extensions must be an object")
        extensions = dict(extensions)
        field_names = set(ReportVerificationRecordV1.model_fields) - {
            "extensions",
            "citation_link_integrity",
            "semantic_assessment",
        }
        normalized_fields = {key: fields.pop(key) for key in list(fields) if key in field_names}
        supplied_integrity = fields.pop("citation_link_integrity", None)
        supplied_semantic = fields.pop("semantic_assessment", None)
        for key, item in fields.items():
            if key in extensions:
                raise ValueError("report-verification extension conflicts with a field")
            extensions[key] = item
        if not isinstance(extensions, dict) or len(extensions) > 128:
            raise ValueError("report-verification extensions exceed their boundary")
        for key, default in _REPORT_VERIFICATION_DEFAULTS.items():
            if key != "report_schema_version":
                normalized_fields.setdefault(key, default)
        normalized_fields.setdefault("report_schema_version", 2 if strict else 1)
        normalized_fields["extensions"] = extensions

        deterministic = {
            "schema_version": 1,
            "level": normalized_fields["level"],
            "status": normalized_fields["status"],
            "claims_checked": normalized_fields["claims_checked"],
            "claims_with_valid_source_and_passage": normalized_fields[
                "claims_with_valid_source_and_passage"
            ],
        }
        semantic_support = normalized_fields["semantic_support_check"]
        semantic_uncited = normalized_fields["uncited_material_claim_scan"]
        semantic = {
            "schema_version": 1,
            "method": (
                "not_performed"
                if semantic_support == "not_performed" and semantic_uncited == "not_performed"
                else "model_assisted_not_independently_verified"
            ),
            "support_check": semantic_support,
            "uncited_material_claim_scan": semantic_uncited,
            "provider": normalized_fields["semantic_audit_provider"],
            "model": normalized_fields["semantic_audit_model"],
            "audit_schema_version": normalized_fields["semantic_audit_schema_version"],
            "items": normalized_fields["semantic_audit_items"],
            "uncited_claims": normalized_fields["uncited_material_claims"],
            "rejected_records": normalized_fields["rejected_semantic_audit_records"],
            "input_truncated": normalized_fields["uncited_scan_input_truncated"],
            "skip_reason": normalized_fields["semantic_audit_skip_reason"],
        }
        if supplied_integrity is not None and supplied_integrity != deterministic:
            raise ValueError("report deterministic integrity section conflicts with its record")
        if supplied_semantic is not None and supplied_semantic != semantic:
            raise ValueError("report semantic section conflicts with its record")
        normalized_fields["citation_link_integrity"] = deterministic
        normalized_fields["semantic_assessment"] = semantic

        record = ReportVerificationRecordV1.model_validate(normalized_fields)
        validated = ReportVerificationEnvelopeV1.model_validate(
            {
                "schema_version": 1,
                "record": record.model_dump(mode="json", exclude_none=False),
                "extensions": envelope_extensions,
            }
        )
        result = validated.model_dump(mode="json", exclude_none=False)
        _validate_report_json_value(result)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 8_388_608:
            raise ValueError("report verification exceeds its 8 MiB storage boundary")
        return result
    except (ValidationError, ValueError, TypeError, KeyError):
        if strict:
            raise
        return _safe_report_verification_fallback()


def report_citation_map_for_api(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep the public map shape stable while the database stores an explicit envelope."""
    envelope = versioned_report_citation_map(value)
    return envelope["citations"]


def report_verification_for_api(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Flatten additive legacy extensions for existing readers after bounded validation."""
    envelope = versioned_report_verification(value)
    record = dict(envelope["record"])
    extensions = record.pop("extensions", {})
    outer_extensions = envelope.pop("extensions", {})
    return {**outer_extensions, **extensions, **record}


def build_report_stage_result(
    body_markdown: str,
    citation_map: Mapping[str, Any],
    verification: Mapping[str, Any],
    model_name: str | None,
) -> BuiltReportStageV1:
    """Strictly validate synthesis output before it crosses the persistence boundary."""
    citation_envelope = versioned_report_citation_map(citation_map, strict=True)
    verification_envelope = versioned_report_verification(verification, strict=True)
    return BuiltReportStageV1.model_validate(
        {
            "schema_version": 1,
            "body_markdown": body_markdown,
            "citation_map": citation_envelope,
            "verification": verification_envelope["record"],
            "model_name": model_name,
        }
    )


class AdvanceRequest(BaseModel):
    operation_key: str = Field(min_length=8, max_length=120)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    related_job_id: str | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class JobOut(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    project_id: str
    parent_job_id: str | None
    conversation_id: str | None
    question: str
    scope: dict[str, Any]
    depth: str
    model_provider: str | None = None
    model_name: str | None = None
    budget_ceiling_usd: float
    cost_spent_estimate_usd: float
    cost_reserved_usd: float
    budget_ceiling_inr: float
    cost_spent_estimate_inr: float
    cost_reserved_inr: float
    model_calls_reserved: int
    prompt_characters_reserved: int
    prompt_token_budget_reserved: int
    output_token_budget_reserved: int
    resource_limits: dict[str, Any]
    status: str
    current_stage: str
    version: int
    attempt: int
    error_class: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class EventOut(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    event_type: str
    stage: str | None
    message: str
    data: "JobEventDataV1"
    created_at: datetime


class CandidateRankingEventV1(BaseModel):
    model_config = ConfigDict(extra="allow")

    algorithm: Literal["lexical_overlap_v1", "lexical_overlap_query_alignment_v1"]
    ranking_query_basis: str = Field(min_length=1, max_length=160)
    features: list[str] = Field(max_length=8)
    weights: dict[str, float] = Field(max_length=8)
    selection: str = Field(min_length=1, max_length=300)
    exclusions: list[str] = Field(max_length=16)
    interpretation: str = Field(min_length=1, max_length=300)


class JobEventDataV1(BaseModel):
    """Versioned, additive envelope for persisted stage and control metrics."""

    model_config = ConfigDict(extra="allow")

    data_schema_version: Literal[1] = 1
    status: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=300)
    error_class: str | None = Field(default=None, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    schema_version: int | None = Field(default=None, ge=1, le=100)
    elapsed_seconds: float | None = Field(default=None, ge=0, le=600)
    retryable: bool | None = None
    plan_version: int | None = Field(default=None, ge=1, le=100)
    planning_mode: Literal["model_assisted_selection", "deterministic_fallback"] | None = None
    planning_fallback_reason: (
        Literal[
            "provider_disabled",
            "provider_not_configured",
            "budget_limit",
            "daily_limit",
            "depth_limit",
            "time_limit",
            "provider_error",
            "uncertain_outcome",
            "invalid_model_plan",
            "provider_blocked",
        ]
        | None
    ) = None
    planning_provider: Literal["openrouter", "openai", "sarvam"] | None = None
    planning_model: str | None = Field(default=None, max_length=200)
    query_count: int | None = Field(default=None, ge=0, le=100)
    query_rationales: list[PlannedQuery] | None = Field(default=None, max_length=8)
    subquestion_count: int | None = Field(default=None, ge=0, le=20)
    scope_status: Literal["specified", "underspecified"] | None = None
    missing_scope_fields: (
        list[Literal["decision_objective", "population", "geography", "time_horizon"]] | None
    ) = Field(default=None, max_length=4)
    source_count: int | None = Field(default=None, ge=0, le=1000)
    provider_failures: dict[str, int] | None = Field(default=None, max_length=32)
    provider_result_counts: dict[str, int] | None = Field(default=None, max_length=32)
    provider_query_counts: dict[str, int] | None = Field(default=None, max_length=32)
    provider_query_latencies_ms: dict[str, list[int]] | None = Field(default=None, max_length=32)
    conditional_statistics_routing: ConditionalStatisticsRoutingV1 | None = None
    query_failures: int | None = Field(default=None, ge=0, le=1000)
    queries_planned: int | None = Field(default=None, ge=0, le=100)
    provider_queries_attempted: int | None = Field(default=None, ge=0, le=1000)
    duplicate_records_excluded: int | None = Field(default=None, ge=0, le=1000)
    records_excluded_by_source_cap: int | None = Field(default=None, ge=0, le=1000)
    records_excluded_by_topic_overlap: int | None = Field(default=None, ge=0, le=1000)
    records_excluded_by_malformed_bibliographic_title: int | None = Field(
        default=None, ge=0, le=1000
    )
    records_excluded_by_repository_artifact_description: int | None = Field(
        default=None, ge=0, le=1000
    )
    candidate_occurrences_recorded: int | None = Field(default=None, ge=0, le=1000)
    candidate_ranking: CandidateRankingEventV1 | None = None
    elapsed_limit_reached: bool | None = None
    source_limit: int | None = Field(default=None, ge=0, le=1000)
    providers: list[str] | None = Field(default=None, max_length=32)
    openalex_auth_mode: Literal["keyed_enabled", "keyless"] | None = None
    passage_count: int | None = Field(default=None, ge=0, le=10000)
    claim_count: int | None = Field(default=None, ge=0, le=10000)
    licensed_html_attempts: int | None = Field(default=None, ge=0, le=1000)
    licensed_html_retrieved: int | None = Field(default=None, ge=0, le=1000)
    licensed_html_failures: int | None = Field(default=None, ge=0, le=1000)
    licensed_html_deferred: int | None = Field(default=None, ge=0, le=1000)
    licensed_html_passages: int | None = Field(default=None, ge=0, le=10000)
    licensed_pdf_attempts: int | None = Field(default=None, ge=0, le=1000)
    licensed_pdf_retrieved: int | None = Field(default=None, ge=0, le=1000)
    licensed_pdf_failures: int | None = Field(default=None, ge=0, le=1000)
    licensed_pdf_deferred: int | None = Field(default=None, ge=0, le=1000)
    licensed_pdf_pages_extracted: int | None = Field(default=None, ge=0, le=10000)
    licensed_pdf_passages: int | None = Field(default=None, ge=0, le=10000)
    passage_limit: int | None = Field(default=None, ge=0, le=10000)
    source_appraisals: int | None = Field(default=None, ge=0, le=1000)
    claim_assessments: int | None = Field(default=None, ge=0, le=10000)
    candidate_claims: int | None = Field(default=None, ge=0, le=10000)
    relationships_persisted: int | None = Field(default=None, ge=0, le=10000)
    relationships_rejected: int | None = Field(default=None, ge=0, le=10000)
    hypotheses_persisted: int | None = Field(default=None, ge=0, le=10000)
    hypothesis_pairs_rejected: int | None = Field(default=None, ge=0, le=10000)
    findings_with_valid_claim_links: int | None = Field(default=None, ge=0, le=10000)
    qualifications_with_valid_claim_links: int | None = Field(default=None, ge=0, le=10000)
    citation_count: int | None = Field(default=None, ge=0, le=10000)
    model_synthesis: bool | None = None
    model_skip_reason: str | None = Field(default=None, max_length=300)
    depth: Literal["quick", "standard", "deep"] | None = None
    max_retries: int | None = Field(default=None, ge=0, le=20)
    parent_job_id: str | None = Field(default=None, max_length=36)
    deferred_request_count: int | None = Field(default=None, ge=0, le=1000)
    continuation_job_id: str | None = Field(default=None, max_length=36)

    def __getitem__(self, key: str) -> Any:
        data = self.model_dump(mode="json", exclude_none=True)
        if key not in data:
            raise KeyError(key)
        return data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.model_dump(mode="json", exclude_none=True).get(key, default)


def versioned_event_data(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate known v1 metrics and preserve unknown legacy metric keys."""
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("job event data must be an object")
    raw = dict(value)
    _validate_event_json_value(raw)
    encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 65_536:
        raise ValueError("job event data exceeds its 64 KiB storage boundary")
    return JobEventDataV1.model_validate(raw).model_dump(mode="json", exclude_none=True)


def stage_event_data(value: Mapping[str, Any] | JobEventDataV1) -> JobEventDataV1:
    """Build the bounded transient stage event record used by persistence and the API."""
    raw = (
        value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, JobEventDataV1)
        else value
    )
    return JobEventDataV1.model_validate(versioned_event_data(raw))


def _validate_event_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("job event data nesting exceeds its limit")
    if isinstance(value, Mapping):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 200 for key in value):
            raise ValueError("job event data object exceeds its key boundary")
        for item in value.values():
            _validate_event_json_value(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 1000:
            raise ValueError("job event data array exceeds its item boundary")
        for item in value:
            _validate_event_json_value(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 16_384:
            raise ValueError("job event data string exceeds its character boundary")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("job event data numbers must be finite")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("job event data must contain only JSON values")


EventOut.model_rebuild()


class EventPageOut(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class OpenAlexFullTextAvailabilityOut(BaseModel):
    """Format availability metadata, not a rights grant or retrieval result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pdf: bool | None = None
    grobid_xml: bool | None = None


class InstitutionalPublicationOut(BaseModel):
    publisher_record_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    document_type: str | None = Field(default=None, max_length=160)
    report_number: str | None = Field(default=None, max_length=100)
    metadata_access: Literal["public_official_api"]
    metadata_reuse_rights_status: Literal["not_assessed"]
    full_text_retrieved: Literal[False]
    full_text_rights_status: Literal["not_assessed"]


class OfficialPublicationOut(BaseModel):
    provider: Literal["GOV.UK Search API"]
    record_path: str = Field(pattern=r"^/government/publications/[A-Za-z0-9][A-Za-z0-9-]{0,180}/?$")
    document_type: Literal["policy_paper"]
    publishing_organizations: list[str] = Field(max_length=16)
    publishing_organization_records: list[dict[str, Any]] = Field(
        default_factory=list, max_length=2
    )
    metadata_access: Literal["public_official_api"]
    metadata_reuse_status: Literal["metadata_only_content_rights_not_assessed"]
    api_support_status: Literal["unsupported_best_effort"]
    full_text_retrieved: Literal[False]
    full_text_rights_status: Literal["not_assessed"]


class OfficialSitePublicationOut(BaseModel):
    """Provenance for a catalog result, separate from its linked document content."""

    model_config = ConfigDict(extra="forbid", strict=True)

    organization_id: str = Field(min_length=1, max_length=300)
    organization_name: str = Field(min_length=1, max_length=300)
    identity_status: Literal["VERIFIED_ESTABLISHED", "VERIFIED_DOMAIN_SPECIALIST"]
    verification_source: str | None = Field(default=None, max_length=1000)
    official_domain: str | None = Field(default=None, max_length=253)
    homepage_url: str = Field(pattern=r"^https://", max_length=1000)
    api_url: str = Field(pattern=r"^https://", max_length=1000)
    discovery_query: str = Field(min_length=1, max_length=180)
    wordpress_record_id: int = Field(ge=1)
    result_type: Literal["post"]
    result_subtype: Literal[
        "analysis-report",
        "publication",
        "research",
        "research-paper",
        "report",
        "working-paper",
        "policy-paper",
        "technical-report",
    ]
    metadata_access: Literal["public_official_site_search_api"]
    content_fetched: Literal[False]
    rights_status: Literal["not_assessed"]
    quality_assessment: Literal["not_assessed"]
    publisher_verification: Literal[
        "official_domain_linked_from_ror_verified_site",
        "crossref_doi_title_publisher_and_link_domain_match",
        "verified_organization_domain_and_catalog_record_match",
    ]


class SourceOut(BaseModel):
    id: str
    title: str
    doi: str | None
    url: str | None
    authors: list[Any]
    published_year: int | None
    publisher: str | None
    provider: str
    provider_metadata_schema_version: int | None = None
    source_governance: dict[str, Any] | None = None
    organization_provenance: dict[str, Any] | None = None
    openalex_fulltext_availability: OpenAlexFullTextAvailabilityOut | None = None
    institutional_publication: InstitutionalPublicationOut | None = None
    official_publication: OfficialPublicationOut | None = None
    official_site_publication: OfficialSitePublicationOut | None = None
    source_type: str
    retrieval_status: str
    abstract_excerpt: str | None
    appraisal: dict[str, Any]


class RetrievalAttemptOutcomeV1(BaseModel):
    """Sanitized outcome of one source's HTML or PDF retrieval attempt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    format: Literal["html", "pdf", "jats"]
    outcome: Literal["not_attempted", "retrieved", "partial", "unavailable", "error", "deferred"]
    observed_at: datetime | None = None
    reason_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    error_code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    retry_after_seconds: float | None = Field(default=None, ge=0, le=86400)
    truncated: bool | None = None


class PassageOut(BaseModel):
    id: str
    source_id: str
    document_id: str | None
    identity_version: int
    ordinal: int
    locator: str
    content: str
    content_hash: str
    access_level: str
    truncated: bool
    document: dict[str, Any] | None = None


class ClaimOut(BaseModel):
    id: str
    source_id: str
    passage_id: str
    text: str
    source_sentence: str
    span_start: int | None
    span_end: int | None
    span_offset_unit: str
    atomization_status: str
    atomization_version: int
    claim_type: str
    evidence_status: str
    appraisal: dict[str, Any]
    economic_facets: dict[str, Any]


class ReportOut(BaseModel):
    id: str
    job_id: str
    version: int
    citation_map_schema_version: Literal[1] = 1
    verification_schema_version: Literal[1] = 1
    status: str
    body_markdown: str
    evidence_content_withheld: bool = False
    content_withheld_reason: str | None = None
    citation_map: dict[str, Any]
    verification: dict[str, Any]
    model_name: str | None
    created_at: datetime


class ReportHistoryItemOut(ReportOut):
    project_id: str
    project_title: str
    project_archived_at: datetime | None
    question: str


class ReportHistoryOut(BaseModel):
    items: list[ReportHistoryItemOut]
    total: int
    limit: int
    offset: int
    has_more: bool
    version_semantics: str


class ReportInspectionOut(BaseModel):
    report: ReportOut
    job: dict[str, Any]
    project: ProjectOut
    sources: list[dict[str, Any]]
    claims: list[dict[str, Any]]


AppraisalFieldName = Literal[
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
EconomicFacetName = Literal[
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
EvidenceRecordStatus = Literal["model_assessed_not_independently_verified"]
_APPRAISAL_PAYLOAD_MAX_BYTES = 64 * 1024


class AppraisalValueV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(max_length=500)
    passage_ids: list[str] = Field(max_length=6)
    status: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")

    @model_validator(mode="after")
    def validate_passage_links(self) -> "AppraisalValueV1":
        if len(self.passage_ids) != len(set(self.passage_ids)):
            raise ValueError("passage IDs must be unique")
        if self.value.casefold() == "unknown" and self.passage_ids:
            raise ValueError("unknown appraisal values cannot claim passage support")
        if self.value.casefold() != "unknown" and not self.passage_ids:
            raise ValueError("reported appraisal values require passage support")
        return self


class SourceMethodologicalAppraisalV1(BaseModel):
    """Bounded persisted source appraisal; model judgments remain explicitly advisory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    reason: str | None = Field(default=None, max_length=1000)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=160)
    fields: dict[AppraisalFieldName, AppraisalValueV1] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class ClaimEconomicFacetsV1(BaseModel):
    """Structured economic facets, each linked to the exact source passage."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    evidence_kind: Literal[
        "causal_estimate",
        "association",
        "other_study_result",
        "descriptive_statistic",
        "forecast_or_model",
        "commentary_or_theory",
        "unknown",
    ]
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=160)
    facets: dict[EconomicFacetName, AppraisalValueV1]
    extensions: dict[str, Any] = Field(default_factory=dict)


class ClaimMethodologyAppraisalV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    relationship: Literal["supports", "qualifies", "contradicts", "insufficient"]
    rationale: str = Field(max_length=500)
    passage_ids: list[str] = Field(max_length=6)
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=160)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_passage_links(self) -> "ClaimMethodologyAppraisalV1":
        if len(self.passage_ids) != len(set(self.passage_ids)):
            raise ValueError("passage IDs must be unique")
        if self.status == "model_assessed_not_independently_verified" and not self.passage_ids:
            raise ValueError("model-assessed claim appraisal requires passage support")
        return self


class ClaimAppraisalV1(BaseModel):
    """Versioned claim appraisal envelope with explicit legacy extensions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    extraction: str | None = Field(default=None, max_length=160)
    methodology_appraisal: ClaimMethodologyAppraisalV1 | None = None
    economic_facets: ClaimEconomicFacetsV1
    extensions: dict[str, Any] = Field(default_factory=dict)


class EvidencePassageLinkV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=36)
    passage_ids: list[str] = Field(min_length=1, max_length=6)

    @field_validator("passage_ids")
    @classmethod
    def unique_passage_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence passage IDs must be unique")
        return value


class EvidenceRelationshipV1(BaseModel):
    """A provisional model classification tied to passages for both claims."""

    model_config = ConfigDict(extra="forbid")

    claim_a_id: str = Field(min_length=1, max_length=36)
    claim_b_id: str = Field(min_length=1, max_length=36)
    relationship_type: Literal[
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
    rationale: str = Field(min_length=1, max_length=700)
    evidence: list[EvidencePassageLinkV1] = Field(min_length=2, max_length=2)
    status: EvidenceRecordStatus
    schema_version: Literal[1]
    provider: str | None = Field(max_length=40)
    model_name: str | None = Field(max_length=160)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_claim_pair_links(self) -> "EvidenceRelationshipV1":
        if self.claim_a_id == self.claim_b_id:
            raise ValueError("a relationship must link two distinct claims")
        linked_claims = {item.claim_id for item in self.evidence}
        if linked_claims != {self.claim_a_id, self.claim_b_id}:
            raise ValueError("relationship evidence must link both claims and no others")
        return self


class EvidenceHypothesisV1(BaseModel):
    """One side of a provisional competing-explanation pair."""

    model_config = ConfigDict(extra="forbid")

    comparison_group_id: str = Field(min_length=1, max_length=36)
    side: Literal["A", "B"]
    statement: str = Field(min_length=1, max_length=700)
    evidence: list[EvidencePassageLinkV1] = Field(min_length=1, max_length=8)
    uncertainty: str = Field(min_length=1, max_length=500)
    why_competing: str = Field(min_length=1, max_length=500)
    status: EvidenceRecordStatus
    schema_version: Literal[1]
    provider: str | None = Field(max_length=40)
    model_name: str | None = Field(max_length=160)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_claim_links(self) -> "EvidenceHypothesisV1":
        claim_ids = [item.claim_id for item in self.evidence]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("hypothesis evidence must have one record per claim")
        return self


def _check_appraisal_payload_size(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = dict(value)
    try:
        size = len(json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("appraisal payload must be JSON serializable") from exc
    if size > _APPRAISAL_PAYLOAD_MAX_BYTES:
        raise ValueError("appraisal payload exceeds the 64 KiB limit")
    return raw


def versioned_source_appraisal(
    value: Mapping[str, Any] | None, *, strict: bool = False
) -> dict[str, Any]:
    """Validate new source appraisal writes and upcast legacy rows without rewriting them."""
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("source appraisal must be an object")
    raw = _check_appraisal_payload_size(value)
    if strict:
        record = SourceMethodologicalAppraisalV1.model_validate(raw)
        return record.model_dump(mode="json")
    if raw.get("schema_version") == 1:
        try:
            return SourceMethodologicalAppraisalV1.model_validate(raw).model_dump(mode="json")
        except ValidationError:
            return SourceMethodologicalAppraisalV1(
                status="legacy_unvalidated",
                reason="Stored optional appraisal could not be validated; source evidence remains available.",
            ).model_dump(mode="json")
    known_names = {"status", "reason", "provider", "model", "fields"}
    payload = {key: raw[key] for key in known_names if key in raw}
    payload["schema_version"] = 1
    payload.setdefault("status", "legacy_unassessed" if not raw else "legacy_unvalidated")
    extensions = dict(payload.pop("extensions", {}))
    extensions.update({key: item for key, item in raw.items() if key not in known_names})
    payload["extensions"] = extensions
    try:
        return SourceMethodologicalAppraisalV1.model_validate(payload).model_dump(mode="json")
    except ValidationError:
        return SourceMethodologicalAppraisalV1(
            status="legacy_unvalidated",
            reason="Stored optional appraisal could not be validated; source evidence remains available.",
        ).model_dump(mode="json")


def versioned_claim_appraisal(
    value: Mapping[str, Any] | None, *, strict: bool = False
) -> dict[str, Any]:
    """Validate new claim appraisal writes and normalize valid historical envelopes in memory."""
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("claim appraisal must be an object")
    raw = _check_appraisal_payload_size(value)
    if strict:
        return ClaimAppraisalV1.model_validate(raw).model_dump(mode="json")
    known_names = {"schema_version", "extraction", "methodology_appraisal", "economic_facets"}
    payload = {key: raw[key] for key in known_names if key in raw}
    payload.setdefault("schema_version", 1)
    extensions = dict(raw.get("extensions", {})) if isinstance(raw.get("extensions"), dict) else {}
    extensions.update(
        {key: item for key, item in raw.items() if key not in known_names | {"extensions"}}
    )
    payload["extensions"] = extensions
    economic = payload.get("economic_facets")
    if not isinstance(economic, Mapping):
        payload["economic_facets"] = _empty_claim_economic_facets()
    else:
        economic_raw = dict(economic)
        economic_raw.setdefault("schema_version", 1)
        try:
            payload["economic_facets"] = ClaimEconomicFacetsV1.model_validate(
                economic_raw
            ).model_dump(mode="json")
        except ValidationError:
            payload["economic_facets"] = _empty_claim_economic_facets(status="legacy_unvalidated")
    if "methodology_appraisal" in payload:
        methodology = payload["methodology_appraisal"]
        if isinstance(methodology, Mapping):
            method_raw = dict(methodology)
            method_raw.setdefault("schema_version", 1)
            try:
                payload["methodology_appraisal"] = ClaimMethodologyAppraisalV1.model_validate(
                    method_raw
                ).model_dump(mode="json")
            except ValidationError:
                payload["methodology_appraisal"] = _unassessed_claim_methodology(
                    "Stored optional appraisal could not be validated; claim evidence remains available."
                )
        else:
            payload["methodology_appraisal"] = _unassessed_claim_methodology(
                "Stored optional appraisal could not be validated; claim evidence remains available."
            )
    try:
        return ClaimAppraisalV1.model_validate(payload).model_dump(mode="json")
    except ValidationError:
        return ClaimAppraisalV1(
            economic_facets=ClaimEconomicFacetsV1.model_validate(_empty_claim_economic_facets()),
            extensions={
                "legacy_unvalidated": True,
                "reason": "Stored optional appraisal could not be validated; claim evidence remains available.",
            },
        ).model_dump(mode="json")


def _empty_claim_economic_facets(*, status: str = "not_assessed") -> dict[str, Any]:
    names = (
        "population",
        "intervention_or_exposure",
        "comparator",
        "outcome",
        "estimate",
        "uncertainty",
        "geography",
        "time_period",
        "measure",
    )
    return {
        "schema_version": 1,
        "status": status,
        "evidence_kind": "unknown",
        "provider": None,
        "model": None,
        "facets": {
            name: {"value": "unknown", "passage_ids": [], "status": status} for name in names
        },
    }


def _unassessed_claim_methodology(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "not_assessed",
        "relationship": "insufficient",
        "rationale": reason[:500],
        "passage_ids": [],
    }


def source_appraisal_for_api(value: Mapping[str, Any] | None) -> dict[str, Any]:
    try:
        return versioned_source_appraisal(value)
    except ValueError:
        return SourceMethodologicalAppraisalV1(
            status="legacy_unvalidated",
            reason="Stored optional appraisal could not be validated; source evidence remains available.",
        ).model_dump(mode="json")


def claim_appraisal_for_api(value: Mapping[str, Any] | None) -> dict[str, Any]:
    try:
        normalized = versioned_claim_appraisal(value)
    except ValueError:
        normalized = ClaimAppraisalV1(
            economic_facets=ClaimEconomicFacetsV1.model_validate(_empty_claim_economic_facets()),
            extensions={"legacy_unvalidated": True},
        ).model_dump(mode="json")
    if normalized.get("methodology_appraisal") is None:
        normalized["methodology_appraisal"] = _unassessed_claim_methodology(
            "No methodology appraisal is stored for this claim."
        )
    return normalized


def relationship_record_for_api(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return EvidenceRelationshipV1.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return {
            "claim_a_id": str(value.get("claim_a_id") or "")[:36],
            "claim_b_id": str(value.get("claim_b_id") or "")[:36],
            "relationship_type": "legacy_unvalidated",
            "scope_alignment": "unknown",
            "scope_differences": [],
            "rationale": "Stored optional comparison record could not be validated; linked claims remain available.",
            "evidence": [],
            "status": "legacy_unvalidated",
            "schema_version": 1,
            "provider": None,
            "model_name": None,
        }


def hypothesis_record_for_api(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return EvidenceHypothesisV1.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return {
            "comparison_group_id": str(value.get("comparison_group_id") or "")[:36],
            "side": value.get("side") if value.get("side") in {"A", "B"} else "A",
            "statement": "Stored optional hypothesis could not be validated.",
            "evidence": [],
            "uncertainty": "Unvalidated legacy record.",
            "why_competing": "Unvalidated legacy record.",
            "status": "legacy_unvalidated",
            "schema_version": 1,
            "provider": None,
            "model_name": None,
        }


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
